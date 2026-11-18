import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:rfid_reader_app/device_settings.dart';

/// Simulates firmware 1.6.0-dev.1 BLE replies, one line per notification.
final class FakeReader {
  FakeReader({this.silent = const {}});

  final Set<String> silent;
  final List<String> sent = [];
  final Map<String, String> config = {
    'rfidOnTimeMs': '5000',
    'periodicIntervalMs': '60000',
    'liveViewAutoReadIntervalMs': '12000',
    'longPressMs': '5000',
    'socLowIdleEnabled': '1',
    'socLowThresholdPercent': '10.00',
    'lowSocUsbRecoveryWindowMs': '60000',
    'batteryMinVoltage': '3.30',
    'batteryMaxVoltage': '4.20',
    'ledHeartbeatIntervalMs': '5000',
    'ledHeartbeatOnMs': '200',
    'verbose': '0',
  };
  late DeviceSettingsController controller;
  final List<String> unconsumed = [];

  void _reply(List<String> lines) {
    scheduleMicrotask(() {
      for (final line in lines) {
        if (!controller.handleLine(line)) unconsumed.add(line);
      }
    });
  }

  Future<void> send(String command) async {
    sent.add(command);
    if (silent.contains(command)) return;
    if (command == 'status') {
      _reply([
        'Dashboard Mode: ACTIVE',
        'Idle mode: INACTIVE',
        'Idle reason: none',
        'Low SoC idle: ENABLED',
        'Low SoC USB recovery: INACTIVE',
        'USB recovery remaining: 0s',
        'Reading count: 42',
        'LED status: dashboard_active',
        'Battery voltage: 3.912',
        'Battery SoC: 76.5',
      ]);
    } else if (command.startsWith('get ')) {
      final key = command.substring(4);
      final spec = deviceSettingByKey(key)!;
      _reply(['<${spec.marker}_BEGIN>', config[key]!, '<${spec.marker}_END>']);
    } else if (command.startsWith('set ')) {
      final parts = command.split(' ');
      if (parts[1] == 'liveViewAutoReadIntervalMs' && int.parse(parts[2]) < 8000) {
        _reply(['ERROR: liveViewAutoReadIntervalMs must be 8000-300000']);
        return;
      }
      config[parts[1]] = parts[2];
      _reply(['OK']);
    }
  }
}

DeviceSettingsController makeController(
  FakeReader reader, {
  bool Function()? canSend,
}) {
  final controller = DeviceSettingsController(
    send: reader.send,
    canSend: canSend ?? () => true,
    timeout: const Duration(milliseconds: 50),
  );
  reader.controller = controller;
  return controller;
}

void main() {
  group('DeviceSettingSpec', () {
    test('converts milliseconds to seconds and back', () {
      final spec = deviceSettingByKey('rfidOnTimeMs')!;
      expect(spec.formatDisplay('5000'), '5 s');
      expect(spec.toFirmware(7.5), '7500');
      expect(spec.validate(2), isNotNull);
      expect(spec.validate(61), isNotNull);
      expect(spec.validate(3), isNull);
    });

    test('formats flags and decimals', () {
      expect(deviceSettingByKey('verbose')!.formatDisplay('1'), 'On');
      expect(deviceSettingByKey('verbose')!.formatDisplay('0'), 'Off');
      expect(deviceSettingByKey('batteryMinVoltage')!.formatDisplay('3.30'), '3.30 V');
      expect(deviceSettingByKey('batteryMinVoltage')!.toFirmware(3.456), '3.46');
    });

    test('every setting has a unique key and marker', () {
      expect(kDeviceSettings.map((s) => s.key).toSet(), hasLength(kDeviceSettings.length));
      expect(kDeviceSettings.map((s) => s.marker).toSet(), hasLength(kDeviceSettings.length));
    });
  });

  group('DeviceStatusSummary', () {
    test('accepts plain and tagged status lines', () {
      expect(DeviceStatusSummary.parseLine('[DASHBOARD] Dashboard Mode: ON'),
          ('dashboard mode', 'ON'));
      expect(DeviceStatusSummary.parseLine('[IDLE] Mode: ACTIVE'), ('idle mode', 'ACTIVE'));
      expect(DeviceStatusSummary.parseLine('#1: 2026-08-01 21:13:09, 999, 1, N/A'), isNull);
      expect(DeviceStatusSummary.parseLine('ESP32 Status: OK'), isNull);
    });
  });

  group('DeviceSettingsController', () {
    test('refreshStatus fills typed status and consumes its lines', () async {
      final reader = FakeReader();
      final controller = makeController(reader);

      expect(await controller.refreshStatus(), isTrue);
      final status = controller.status;
      expect(status.dashboardModeActive, isTrue);
      expect(status.idleModeActive, isFalse);
      expect(status.lowSocIdleEnabled, isTrue);
      expect(status.readingCount, 42);
      expect(status.batteryVoltage, closeTo(3.912, 1e-9));
      expect(status.batterySocPercent, 76.5);
      expect(status.usbRecoveryRemainingSeconds, 0);
      expect(reader.unconsumed, isEmpty);
      expect(controller.busy, isFalse);
    });

    test('loadSettings reads every value in order', () async {
      final reader = FakeReader();
      final controller = makeController(reader);

      expect(await controller.loadSettings(), isTrue);
      expect(reader.sent, kDeviceSettings.map((s) => 'get ${s.key}').toList());
      expect(controller.values['rfidOnTimeMs'], '5000');
      expect(controller.values['batteryMaxVoltage'], '4.20');
      expect(reader.unconsumed, isEmpty);
    });

    test('a missing reply times out and the rest still load', () async {
      final reader = FakeReader(silent: {'get verbose'});
      final controller = makeController(reader);

      expect(await controller.loadSettings(), isFalse);
      expect(controller.values.containsKey('verbose'), isFalse);
      expect(controller.values, hasLength(kDeviceSettings.length - 1));
      expect(controller.messageIsError, isTrue);
    });

    test('saveSetting sends firmware units and confirms by reading back', () async {
      final reader = FakeReader();
      final controller = makeController(reader);
      final spec = deviceSettingByKey('rfidOnTimeMs')!;

      expect(await controller.saveSetting(spec, 8), isTrue);
      expect(reader.sent, ['set rfidOnTimeMs 8000', 'get rfidOnTimeMs']);
      expect(controller.values['rfidOnTimeMs'], '8000');
      expect(controller.messageIsError, isFalse);
    });

    test('firmware ERROR reply is shown and nothing is re-read', () async {
      final reader = FakeReader();
      final controller = makeController(reader);
      // Bypass app-side limits to exercise the firmware error path.
      const spec = DeviceSettingSpec(
        key: 'liveViewAutoReadIntervalMs',
        marker: 'GET_LIVEVIEWAUTOREADINTERVALMS',
        label: 'Live View interval',
        group: 'Reading',
        kind: SettingKind.milliseconds,
      );

      expect(await controller.saveSetting(spec, 5), isFalse);
      expect(reader.sent, ['set liveViewAutoReadIntervalMs 5000']);
      expect(controller.message, contains('8000-300000'));
      expect(controller.messageIsError, isTrue);
    });

    test('out-of-range and cross-field values are never sent', () async {
      final reader = FakeReader();
      final controller = makeController(reader);
      await controller.loadSettings();
      reader.sent.clear();

      expect(await controller.saveSetting(deviceSettingByKey('periodicIntervalMs')!, 5), isFalse);
      expect(await controller.saveSetting(deviceSettingByKey('batteryMinVoltage')!, 4.2), isFalse);
      expect(await controller.saveSetting(deviceSettingByKey('ledHeartbeatOnMs')!, 6), isFalse);
      expect(reader.sent, isEmpty);
    });

    test('does nothing while the reader is busy with another task', () async {
      final reader = FakeReader();
      final controller = makeController(reader, canSend: () => false);

      expect(await controller.refreshStatus(), isFalse);
      expect(reader.sent, isEmpty);
      expect(controller.messageIsError, isTrue);
    });

    test('unrelated lines during a request reach the normal parser', () async {
      final reader = FakeReader(silent: {'get rfidOnTimeMs'});
      final controller = makeController(reader);
      final spec = deviceSettingByKey('rfidOnTimeMs')!;

      final future = controller.saveSetting(spec, 6);
      await Future<void>.delayed(Duration.zero);
      expect(controller.handleLine('#5: 2026-08-01 21:13:09, 999, 1, N/A, ANT2'), isFalse);
      await future;
    });

    test('status lines from the Status button update cards passively', () {
      final controller = makeController(FakeReader());
      expect(controller.handleLine('Battery SoC: 50.0'), isFalse);
      expect(controller.status.batterySocPercent, 50.0);
    });

    test('reset on disconnect stops a load in progress', () async {
      final reader = FakeReader(silent: {'get periodicIntervalMs'});
      final controller = makeController(reader);

      final future = controller.loadSettings();
      await Future<void>.delayed(const Duration(milliseconds: 10));
      controller.reset();
      expect(await future, isFalse);
      expect(reader.sent, ['get rfidOnTimeMs', 'get periodicIntervalMs']);
      expect(controller.values, isEmpty);
    });
  });
}
