import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:rfid_reader_app/ble_protocol.dart';

void main() {
  compatibilityTests();
  group('BleProtocolParser', () {
    test('parses legacy stored reading as ANT1', () {
      final readings = BleProtocolParser.parseReadings(
        '#1: 2026-08-01 9:03:05, 999, 141004265912, 24.86\u00B0C',
      );

      expect(readings, hasLength(1));
      expect(readings.single.readingNum, 1);
      expect(readings.single.timestampUtc, DateTime.utc(2026, 8, 1, 9, 3, 5));
      expect(readings.single.country, '999');
      expect(readings.single.tag, '141004265912');
      expect(readings.single.temperatureC, 24.86);
      expect(readings.single.antenna, 'ANT1');
    });

    test('parses antenna-aware stored reading with N/A temperature', () {
      final readings = BleProtocolParser.parseReadings(
        '#2: 2026-08-01 21:13:09, 999, 141004265913, N/A, ANT2',
      );

      expect(readings, hasLength(1));
      expect(readings.single.readingNum, 2);
      expect(readings.single.temperatureC, isNull);
      expect(readings.single.antenna, 'ANT2');
    });

    test('parses signed live RFID result', () {
      final readings = BleProtocolParser.parseReadings(
        '[RFID_RESULT] stored=true ant=ANT2 reading=42 ts=1785633185 '
        'tag=999 141004265912 temp=-1.25\u00B0C',
      );

      expect(readings, hasLength(1));
      expect(readings.single.source, 'live');
      expect(readings.single.antenna, 'ANT2');
      expect(readings.single.readingNum, 42);
      expect(
        readings.single.timestampUtc,
        DateTime.fromMillisecondsSinceEpoch(1785633185 * 1000, isUtc: true),
      );
      expect(readings.single.temperatureC, -1.25);
    });

    test('keeps ANT2 manual read pending until structured result arrives', () {
      final progressMessages = [
        '[RFID][ANT2] Powering ON for 3000 ms',
        '[RFID][ANT2] RFID module powered on, starting read window...',
        'New reading: 999 141012387936 25.09\u00B0C',
        '[RFID][ANT2] Tag detected and stored',
      ];

      for (final message in progressMessages) {
        final response = BleProtocolParser.parseManualReadResponse(message);
        expect(response.type, ManualReadResponseType.pending);
        expect(response.readings, isEmpty);
      }

      final result = BleProtocolParser.parseManualReadResponse(
        '[RFID_RESULT] stored=true ant=ANT2 reading=465 ts=1785809826 '
        'tag=999 141012387936 temp=25.09\u00B0C',
      );

      expect(result.type, ManualReadResponseType.success);
      expect(result.readings, hasLength(1));
      expect(result.readings.single.antenna, 'ANT2');
      expect(result.readings.single.readingNum, 465);
      expect(result.readings.single.temperatureC, 25.09);
    });

    test('parses config and status helper models', () {
      final status = DeviceStatus.parse(
        'Dashboard Mode: ACTIVE\nBattery SoC: 84.2\nLED status: dashboard_active',
      );
      final config = ConfigResponse.parse(
        '<GET_RFIDONTIME_BEGIN>\n12000\n<GET_RFIDONTIME_END>',
      );

      expect(status['dashboard mode'], 'ACTIVE');
      expect(status['battery soc'], '84.2');
      expect(config?.marker, 'GET_RFIDONTIME');
      expect(config?.value, '12000');
    });
  });

  group('BleResponseBuffer', () {
    test('holds incomplete reading until the next chunk completes it', () {
      final buffer = BleResponseBuffer();

      expect(
        buffer.add(utf8.encode('#3: 2026-08-01 21:13:09, 999'), utf8.decode),
        isEmpty,
      );

      final messages = buffer.add(
        utf8.encode(', 141004265913, 25.10\u00B0C, ANT1'),
        utf8.decode,
      );

      expect(messages, hasLength(1));
      expect(BleProtocolParser.parseReadings(messages.single), hasLength(1));
    });
  });
}

// Firmware response fixtures exercise the parser, transport and command state
// together, including notification boundaries inside a field or UTF-8 sequence.
void compatibilityTests() {
  const ant1 =
      '[RFID_RESULT] stored=true ant=ANT1 reading=41 ts=1785633185 '
      'tag=999 141004265912 temp=24.86°C';
  const ant2 =
      '[RFID_RESULT] stored=true ant=ANT2 reading=42 ts=1785633190 '
      'tag=999 141004265913 temp=N/A';
  const stored1 = '#41: 2026-08-01 21:13:05, 999, 141004265912, 24.86°C, ANT1';
  const stored2 = '#42: 2026-08-01 21:13:09, 999, 141004265913, N/A, ANT2';

  group('Firmware/app compatibility', () {
    test('accepts all unpadded legacy timestamp components', () {
      final record = BleProtocolParser.parseStoredReadings(
        '#1: 2026-8-1 9:3:5, 999, 141004265912, 24.86°C',
      ).single;
      expect(record.timestampUtc, DateTime.utc(2026, 8, 1, 9, 3, 5));
      expect(record.timestampText, '2026-08-01 09:03:05');
    });

    test('legacy notification batches keep reading order', () {
      final messages = BleResponseBuffer().addText('$stored1\n$stored2');
      expect(messages, [stored1, stored2]);
    });

    test('framed ANT2 suffix cannot be prematurely treated as ANT1', () {
      final buffer = BleResponseBuffer(lineDelimited: true);
      expect(
        buffer.addText(stored2.substring(0, stored2.indexOf(', ANT2'))),
        isEmpty,
      );
      expect(buffer.addText(', ANT2'), isEmpty);
      final messages = buffer.addText('\n');
      expect(
        BleProtocolParser.parseReadings(messages.single).single.antenna,
        'ANT2',
      );
    });

    test(
      'all possible notification splits preserve UTF-8, records and markers',
      () {
        final wire = utf8.encode(
          'RFID_PROTOCOL_V2\n$stored1\n$stored2\n---END_READINGS---\n',
        );
        for (var split = 1; split < wire.length; split++) {
          final buffer = BleResponseBuffer();
          final messages = [
            ...buffer.add(wire.sublist(0, split)),
            ...buffer.add(wire.sublist(split)),
          ];
          expect(messages, [
            'RFID_PROTOCOL_V2',
            stored1,
            stored2,
            '---END_READINGS---',
          ], reason: 'split $split');
          expect(buffer.usesLineFraming, isTrue);
        }
      },
    );

    test('one byte notifications keep multi-byte temperature intact', () {
      final buffer = BleResponseBuffer(lineDelimited: true);
      final messages = utf8
          .encode('$stored1\r\n$stored2\n')
          .expand((byte) => buffer.add([byte]))
          .toList();
      expect(messages, [stored1, stored2]);
    });

    test('clear keeps negotiated framing and reset removes it', () {
      final buffer = BleResponseBuffer();
      buffer.addText('RFID_PROTOCOL_V2\n');
      buffer.addText('partial');
      buffer.clear();
      expect(buffer.usesLineFraming, isTrue);
      expect(buffer.addText('OK\n'), ['OK']);
      buffer.reset();
      expect(buffer.usesLineFraming, isFalse);
      expect(buffer.addText('OK'), ['OK']);
    });

    test('Read Now retains both results and waits for command completion', () {
      final session = ManualReadSession(
        expectedAntennas: {'ANT1', 'ANT2'},
        requiresCompletionMarker: true,
      );
      expect(session.add(ant1).type, ManualReadResponseType.pending);
      expect(
        session.add('[RFID][ANT1] Power OFF').type,
        ManualReadResponseType.pending,
      );
      expect(session.add(ant2).type, ManualReadResponseType.pending);
      expect(
        session.add('[RFID][ANT2] Power OFF').type,
        ManualReadResponseType.pending,
      );
      final result = session.add('[MANUAL] RFID read complete count=42');
      expect(result.type, ManualReadResponseType.success);
      expect(result.readings.map((r) => r.antenna), ['ANT1', 'ANT2']);
      expect(session.isComplete, isTrue);
    });

    test('ANT1 no-tag does not discard a later ANT2 success', () {
      final session = ManualReadSession(
        expectedAntennas: {'ANT1', 'ANT2'},
        requiresCompletionMarker: true,
      );
      expect(
        session.add('[RFID][ANT1] No tag detected during window').type,
        ManualReadResponseType.pending,
      );
      expect(session.add(ant2).type, ManualReadResponseType.pending);
      expect(
        session
            .add('[MANUAL] RFID read complete count=42')
            .readings
            .single
            .antenna,
        'ANT2',
      );
    });

    test('no-tag from ANT2 recovery attempt is not terminal', () {
      final session = ManualReadSession(
        expectedAntennas: {'ANT1', 'ANT2'},
        requiresCompletionMarker: true,
      );
      session.add('[RFID][ANT1] No tag detected during window');
      session.add('[RFID][ANT2] No tag detected during window');
      expect(session.isComplete, isFalse);
      session.add(ant2);
      expect(
        session.add('[MANUAL] RFID read complete count=42').type,
        ManualReadResponseType.success,
      );
    });

    test('empty dual read ends with no-tag only after completion marker', () {
      final session = ManualReadSession(
        expectedAntennas: {'ANT1', 'ANT2'},
        requiresCompletionMarker: true,
      );
      session.add('[RFID][ANT1] No tag detected during window');
      session.add('[RFID][ANT2] No tag detected during window');
      expect(
        session.add('[MANUAL] RFID read complete count=40').type,
        ManualReadResponseType.noTag,
      );
    });

    test('directed ANT2 read filters other antennas and duplicate output', () {
      final session = ManualReadSession(
        expectedAntennas: {'ANT2'},
        requiresCompletionMarker: true,
      );
      session.add(ant1);
      session.add(ant2);
      session.add(stored2);
      final result = session.add('[MANUAL] ANT2 RFID read complete count=42');
      expect(result.type, ManualReadResponseType.success);
      expect(result.readings, hasLength(1));
      expect(result.readings.single.antenna, 'ANT2');
    });

    test(
      'legacy dual read uses antenna progress and waits for ANT2 power off',
      () {
        final session = ManualReadSession(
          expectedAntennas: {'ANT1', 'ANT2'},
          requiresCompletionMarker: false,
        );
        session.add('[RFID][ANT1] Powering ON for 5000 ms');
        session.add('[RFID][ANT1] Power OFF');
        session.add('[RFID][ANT1] No tag detected during window');
        expect(session.isComplete, isFalse);
        session.add('[RFID][ANT2] Powering ON for 5000 ms');
        session.add('#42: 2026-8-1 9:3:5, 999, 141004265913, N/A');
        final result = session.add('[RFID][ANT2] Power OFF');
        expect(result.type, ManualReadResponseType.success);
        expect(result.readings.single.antenna, 'ANT2');
      },
    );

    test(
      'unsupported commands and hardware errors end the operation immediately',
      () {
        for (final message in [
          'ERROR: Unknown command: readant 2',
          'Unknown command: readant 2',
          '[RFID][ANT2] Read aborted: Module hardware issue detected',
        ]) {
          final session = ManualReadSession(
            expectedAntennas: {'ANT2'},
            requiresCompletionMarker: true,
          );
          final result = session.add(message);
          expect(result.type, ManualReadResponseType.error);
          expect(result.message, message);
          expect(session.isComplete, isTrue);
        }
      },
    );

    test('idle reads report blocked instead of waiting for a timeout', () {
      final session = ManualReadSession(
        expectedAntennas: {'ANT1', 'ANT2'},
        requiresCompletionMarker: true,
      );
      final result = session.add('[IDLE] Manual read blocked: Low battery SoC');
      expect(result.type, ManualReadResponseType.blocked);
      expect(result.message, contains('Low battery SoC'));
      expect(session.isComplete, isTrue);
    });

    test('timeout budget includes both antennas and a recovery window', () {
      final session = ManualReadSession(
        expectedAntennas: {'ANT1', 'ANT2'},
        requiresCompletionMarker: true,
      );
      session.add('[MANUAL] Starting RFID read window (12000ms)');
      expect(session.timeout, const Duration(seconds: 78));
    });
  });
}
