import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:rfid_reader_app/ble_protocol.dart';
import 'package:rfid_reader_app/live_view.dart';

/// Captures scheduled callbacks so tests decide when time passes.
final class FakeScheduler {
  final List<(Duration, void Function())> pending = [];

  Timer call(Duration delay, void Function() callback) {
    final entry = (delay, callback);
    pending.add(entry);
    return _FakeTimer(() => pending.remove(entry));
  }

  void fireNext() {
    final entry = pending.removeAt(0);
    entry.$2();
  }
}

final class _FakeTimer implements Timer {
  _FakeTimer(this._onCancel);

  final void Function() _onCancel;
  bool _active = true;

  @override
  void cancel() {
    if (_active) _onCancel();
    _active = false;
  }

  @override
  bool get isActive => _active;

  @override
  int get tick => 0;
}

RfidReadingRecord reading(String antenna, DateTime? time, {String tag = '1'}) =>
    RfidReadingRecord(
      readingNum: 1,
      timestampUtc: time,
      timestampText: '',
      country: '999',
      tag: tag,
      temperatureC: 36.5,
      antenna: antenna,
      source: 'test',
    );

void main() {
  group('liveViewInterval', () {
    test('uses the reader value within dashboard limits', () {
      expect(liveViewInterval(intervalMsRaw: '20000', rfidOnTimeMsRaw: '5000'),
          const Duration(seconds: 20));
      expect(liveViewInterval(intervalMsRaw: '999999'), const Duration(seconds: 300));
    });

    test('never shorter than two read windows plus 2 s', () {
      expect(liveViewInterval(intervalMsRaw: '8000', rfidOnTimeMsRaw: '10000'),
          const Duration(seconds: 22));
      expect(liveViewInterval(), const Duration(seconds: 12));
    });
  });

  group('LiveViewController', () {
    late FakeScheduler scheduler;
    late int reads;
    late bool readerFree;
    late LiveViewController live;

    setUp(() {
      scheduler = FakeScheduler();
      reads = 0;
      readerFree = true;
      live = LiveViewController(
        startRead: () {
          if (!readerFree) return false;
          reads++;
          return true;
        },
        scheduler: scheduler.call,
      );
    });

    test('reads at once, then waits the interval after each read', () {
      live.start(const Duration(seconds: 12));
      expect(reads, 1);
      expect(live.readInProgress, isTrue);
      expect(scheduler.pending, isEmpty);

      live.readFinished(ReadOutcome.success, [reading('ANT1', DateTime.utc(2026))]);
      expect(scheduler.pending.single.$1, const Duration(seconds: 12));
      expect(live.sessionReadings, hasLength(1));

      scheduler.fireNext();
      expect(reads, 2);
      live.readFinished(ReadOutcome.noTag, const []);
      expect(live.cycles, 2);
      expect(live.running, isTrue);
    });

    test('pauses when the reader does not confirm a read', () {
      live.start(const Duration(seconds: 12));
      live.readFinished(ReadOutcome.timeout, const []);
      expect(live.running, isFalse);
      expect(live.message, contains('did not confirm'));
      expect(scheduler.pending, isEmpty);
    });

    test('pauses when the reader blocks reads (idle / low battery)', () {
      live.start(const Duration(seconds: 12));
      live.readFinished(ReadOutcome.blocked, const [], 'battery low');
      expect(live.running, isFalse);
      expect(live.message, contains('battery low'));
    });

    test('retries once after an error, pauses after two in a row', () {
      live.start(const Duration(seconds: 12));
      live.readFinished(ReadOutcome.error, const []);
      expect(live.running, isTrue);
      expect(scheduler.pending.single.$1, LiveViewController.retryDelay);

      scheduler.fireNext();
      live.readFinished(ReadOutcome.error, const []);
      expect(live.running, isFalse);
      expect(live.message, contains('2 failed reads'));
    });

    test('a success resets the failure count', () {
      live.start(const Duration(seconds: 12));
      live.readFinished(ReadOutcome.error, const []);
      scheduler.fireNext();
      live.readFinished(ReadOutcome.success, const []);
      scheduler.fireNext();
      live.readFinished(ReadOutcome.error, const []);
      expect(live.running, isTrue);
    });

    test('waits and retries while the reader is busy', () {
      readerFree = false;
      live.start(const Duration(seconds: 12));
      expect(reads, 0);
      expect(live.readInProgress, isFalse);
      expect(scheduler.pending.single.$1, LiveViewController.retryDelay);

      readerFree = true;
      scheduler.fireNext();
      expect(reads, 1);
    });

    test('stop cancels the next read and ignores late results', () {
      live.start(const Duration(seconds: 12));
      live.readFinished(ReadOutcome.success, const []);
      live.stop();
      expect(scheduler.pending, isEmpty);
      live.readFinished(ReadOutcome.success, [reading('ANT1', null)]);
      expect(live.sessionReadings, isEmpty);
      expect(live.cycles, 1);
    });

    test('a new interval applies from the next cycle', () {
      live.start(const Duration(seconds: 12));
      live.updateInterval(const Duration(seconds: 30));
      live.readFinished(ReadOutcome.success, const []);
      expect(scheduler.pending.single.$1, const Duration(seconds: 30));
    });
  });

  group('updateLatestByAntenna', () {
    test('keeps the newest reading per antenna', () {
      final early = DateTime.utc(2026, 1, 1, 10);
      final late = DateTime.utc(2026, 1, 1, 11);
      var latest = updateLatestByAntenna({}, [
        reading('ANT1', late, tag: 'new'),
        reading('ANT2', early, tag: 'b'),
      ]);
      latest = updateLatestByAntenna(latest, [reading('ANT1', early, tag: 'old')]);

      expect(latest['ANT1']!.tag, 'new');
      expect(latest['ANT2']!.tag, 'b');
    });
  });
}
