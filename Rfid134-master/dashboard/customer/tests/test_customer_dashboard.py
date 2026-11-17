import ast
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from customer_protocol import manual_read_finished, empty_history_response
import launcher
import pandas as pd

SOURCE = (HERE / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
ANT1 = '[RFID_RESULT] stored=true ant=ANT1 reading=1 ts=1785633185 tag=999 141004265912 temp=24.86°C'
ANT2 = '[RFID_RESULT] stored=true ant=ANT2 reading=2 ts=1785633190 tag=999 141004265913 temp=N/A'
DONE = '[MANUAL] RFID read complete count=2'


class State(dict):
    def __getattr__(self, key):
        return self[key]


class Clock:
    def __init__(self): self.now = 0
    def time(self):
        self.now += .02
        return self.now
    def sleep(self, delay): self.now += delay


class Serial:
    def __init__(self, clock, events=()):
        self.clock = clock
        self.events = list(events)
        self.writes = []
        self.resets = 0
        self.is_open = True
    def reset_input_buffer(self): self.resets += 1
    def write(self, value): self.writes.append(value)
    def flush(self): pass
    @property
    def in_waiting(self): return bool(self.events and self.clock.now >= self.events[0][0])
    def readline(self): return self.events.pop(0)[1].encode() + b'\n'


class CustomerProtocolTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.state = State(esp32_rfidOnTime=5, selected_timezone='UTC')
        streamlit = mock.Mock(session_state=self.state)
        self.env = dict(st=streamlit, time=self.clock, re=re, datetime=datetime, timezone=timezone, pd=pd,
                        manual_read_finished=manual_read_finished,
                        DEFAULT_DASHBOARD_FETCH_TIMEOUT_SECONDS=60,
                        MIN_DASHBOARD_FETCH_TIMEOUT_SECONDS=10, MAX_DASHBOARD_FETCH_TIMEOUT_SECONDS=300,
                        SERIAL_EXCEPTIONS=(OSError, AttributeError), is_serial_valid=lambda ser: ser.is_open,
                        log_general_debug=lambda text: None, log_debug=lambda text: None,
                        _wake_serial=lambda ser: None)
        names = {'send_command', 'parse_readings', 'parse_live_readnow_results', 'read_is_pending',
                 'recover_pending_read', 'readings_to_dataframe', 'merge_live_view_dataframe',
                 'convert_timestamp_to_timezone', 'response_has_ok', 'response_has_error', 'test_connection'}
        nodes = [node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(HERE / 'app.py'), 'exec'), self.env)

    def test_never_finishes_on_first_antenna_or_no_tag(self):
        for text in [ANT1, ANT2, '[RFID][ANT1] No tag detected during window', '[RFID][ANT2] Power OFF']:
            self.assertFalse(manual_read_finished(text))
        self.assertTrue(manual_read_finished(DONE))
        self.assertTrue(manual_read_finished('[MANUAL] RFID read skipped'))

    def test_dual_read_keeps_both_results_through_recovery(self):
        ser = Serial(self.clock, [(1, ANT1), (35, ANT2), (40, DONE)])
        response = self.env['send_command'](ser, 'readnow')
        self.assertIn(DONE, response)
        self.assertEqual([r['Antenna'] for r in self.env['parse_live_readnow_results'](response)], ['ANT1', 'ANT2'])
        self.assertFalse(self.state['read_pending'])
        self.assertEqual(ser.writes, [b'readnow\n'])

    def test_partial_read_blocks_further_commands_until_completion(self):
        ser = Serial(self.clock, [(1, ANT1), (60, ANT2), (60.1, DONE)])
        response = self.env['send_command'](ser, 'readnow')
        self.assertIn(ANT1, response)
        self.assertNotIn(DONE, response)
        self.assertTrue(self.env['read_is_pending'](ser))
        self.assertEqual(self.env['send_command'](ser, 'status'), '')
        self.assertEqual(ser.writes, [b'readnow\n'])
        resets = ser.resets
        self.clock.now = 61
        self.assertTrue(self.env['recover_pending_read'](ser))
        self.assertEqual(ser.resets, resets, 'Recovery must not discard unread bytes')
        self.assertEqual(list(self.state['last_df']['Antenna']), ['ANT1', 'ANT2'])
        self.assertEqual(self.state['read_now_latest_status'], 'readings')
        self.assertFalse(self.env['read_is_pending'](ser))

    def test_pending_read_does_not_block_a_new_connection(self):
        old = Serial(self.clock)
        self.env['send_command'](old, 'readnow')
        self.assertTrue(self.env['read_is_pending'](old))
        new = Serial(self.clock, [(self.clock.now + 1, DONE)])
        self.assertIn(DONE, self.env['send_command'](new, 'readnow'))

    def test_idle_skip_is_terminal(self):
        ser = Serial(self.clock, [(1, '[IDLE] Manual read blocked: Low SoC'), (1.1, '[MANUAL] RFID read skipped')])
        response = self.env['send_command'](ser, 'readnow')
        self.assertIn('skipped', response)
        self.assertLess(self.clock.now, 2)
        self.assertFalse(self.env['read_is_pending'](ser))

    def test_configuration_waits_for_delayed_ok(self):
        ser = Serial(self.clock, [(.2, '[CONFIG] Saved: periodicIntervalMs = 60000'), (2, 'OK')])
        response = self.env['send_command'](ser, 'set periodicIntervalMs 60000')
        self.assertTrue(self.env['response_has_ok'](response))

    def test_configuration_flash_error_cannot_be_overridden_by_ok(self):
        failed = '[CONFIG] Failed to open config file for writing'
        self.assertTrue(self.env['response_has_error'](failed + '\nOK'))
        self.assertFalse(self.env['response_has_ok'](failed + '\nOK'))
        ser = Serial(self.clock, [(1, failed), (1.1, 'OK')])
        self.assertIn(failed, self.env['send_command'](ser, 'set verbose 0'))
        self.assertLess(self.clock.now, 1.1)

    def test_valid_empty_history_is_distinct_from_truncation(self):
        self.assertTrue(empty_history_response('No readings stored.\n'))
        self.assertTrue(empty_history_response('[SERDBG] message\nNo readings stored.'))
        self.assertFalse(empty_history_response(''))
        self.assertFalse(empty_history_response('No readings stored.\n#1: truncated'))

    def test_history_and_live_formats_match_customer_firmware(self):
        stored = '---BEGIN_READINGS---\n#1: 2026-11-16 12:03:05, 999, 141004265912, 24.86°C, ANT1\n#2: 2026-11-16 12:03:09, 999, 141004265913, N/A, ANT2\n---END_READINGS---'
        self.assertEqual([r['Antenna'] for r in self.env['parse_readings'](stored)], ['ANT1', 'ANT2'])
        self.assertEqual([r['Antenna'] for r in self.env['parse_live_readnow_results'](ANT1+'\n'+ANT2)], ['ANT1', 'ANT2'])

    def test_customer_ui_has_no_experimental_commands_or_flash_prompt(self):
        self.assertNotIn('readant', SOURCE)
        self.assertNotIn('RFID_PROTOCOL_V2', SOURCE)
        self.assertNotIn('Flash the current firmware', SOURCE)
        self.assertIn('manual_read_finished(readnow_response)', SOURCE)


class LauncherTests(unittest.TestCase):
    def test_server_applies_requested_loopback_and_port(self):
        from streamlit import config
        with mock.patch('streamlit.web.bootstrap.run') as run:
            launcher.serve(12345)
        self.assertEqual(config.get_option('server.address'), '127.0.0.1')
        self.assertEqual(config.get_option('server.port'), 12345)
        self.assertTrue(config.get_option('server.headless'))
        self.assertFalse(config.get_option('browser.gatherUsageStats'))
        run.assert_called_once()

    def test_only_local_dashboard_urls_are_accepted(self):
        self.assertEqual(launcher.local_url('http://127.0.0.1:8501/'), 'http://127.0.0.1:8501/')
        for url in ['https://example.com/', 'http://127.0.0.1.evil.test:8501/', 'file:///C:/Windows', 'http://127.0.0.1:99999/']:
            self.assertIsNone(launcher.local_url(url))

    def test_lock_prevents_duplicate_dashboard_servers_and_releases(self):
        with tempfile.TemporaryDirectory() as temp:
            first = launcher.InstanceLock(Path(temp) / 'lock')
            second = launcher.InstanceLock(Path(temp) / 'lock')
            self.assertTrue(first.acquire())
            try:
                self.assertFalse(second.acquire())
            finally:
                first.close()
            self.assertTrue(second.acquire())
            second.close()

    def test_child_command_stays_on_loopback_server_path(self):
        command = launcher.child_command(12345)
        self.assertEqual(command[-3:], ['--serve', '--port', '12345'])
        self.assertTrue((launcher.resource_directory() / 'app.py').is_file())
        self.assertTrue((launcher.resource_directory() / 'EB_logo.png').is_file())


if __name__ == '__main__':
    unittest.main()
