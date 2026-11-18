import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import 'ble_protocol.dart';

/// How one Read Now cycle ended, as reported by the main screen.
enum ReadOutcome { success, noTag, blocked, error, timeout, notStarted }

ReadOutcome readOutcomeFromResult(String? result) => switch (result) {
  'success' => ReadOutcome.success,
  'no_tag' => ReadOutcome.noTag,
  'blocked' => ReadOutcome.blocked,
  'timeout' => ReadOutcome.timeout,
  _ => ReadOutcome.error,
};

/// Live View interval rules shared with the USB dashboard: 8–300 s, and at
/// least two read windows plus 2 s so a dual-antenna read can finish.
Duration liveViewInterval({String? intervalMsRaw, String? rfidOnTimeMsRaw}) {
  final requestedMs = double.tryParse(intervalMsRaw ?? '') ?? 8000;
  final rfidOnMs = double.tryParse(rfidOnTimeMsRaw ?? '') ?? 5000;
  final minimumMs = math.max(8000.0, rfidOnMs * 2 + 2000);
  final ms = requestedMs.clamp(minimumMs, 300000.0);
  return Duration(milliseconds: ms.round());
}

typedef LiveViewScheduler = Timer Function(Duration delay, void Function() callback);

/// Repeats Read Now while running, like the dashboard's Live View.
///
/// The main screen starts the actual read in [startRead] (returning false
/// when the reader is busy) and reports the end with [readFinished].
class LiveViewController extends ChangeNotifier {
  LiveViewController({
    required bool Function() startRead,
    LiveViewScheduler? scheduler,
    DateTime Function()? clock,
  }) : _startRead = startRead,
       _schedule = scheduler ?? Timer.new,
       _now = clock ?? DateTime.now;

  static const int failureLimit = 2;
  static const Duration retryDelay = Duration(seconds: 5);
  static const int maxSessionReadings = 500;

  final bool Function() _startRead;
  final LiveViewScheduler _schedule;
  final DateTime Function() _now;

  bool _running = false;
  bool _readInProgress = false;
  Duration _interval = const Duration(seconds: 12);
  Timer? _timer;
  DateTime? _startedAt;
  DateTime? _nextReadAt;
  int _cycles = 0;
  int _failures = 0;
  String? _message;
  bool _disposed = false;
  final List<RfidReadingRecord> _sessionReadings = [];

  bool get running => _running;
  bool get readInProgress => _readInProgress;
  Duration get interval => _interval;
  DateTime? get startedAt => _startedAt;
  DateTime? get nextReadAt => _nextReadAt;
  int get cycles => _cycles;

  /// Why Live View paused, or the last cycle's note.
  String? get message => _message;

  /// Readings received since Live View was started, newest last.
  List<RfidReadingRecord> get sessionReadings => List.unmodifiable(_sessionReadings);

  void start(Duration interval) {
    if (_running) return;
    _running = true;
    _interval = interval;
    _startedAt = _now();
    _cycles = 0;
    _failures = 0;
    _message = null;
    _sessionReadings.clear();
    _notify();
    _runCycle();
  }

  /// Takes effect from the next cycle.
  void updateInterval(Duration interval) {
    _interval = interval;
    _notify();
  }

  void stop([String? reason]) {
    if (!_running && reason == null) return;
    _running = false;
    _readInProgress = false;
    _timer?.cancel();
    _timer = null;
    _nextReadAt = null;
    _message = reason;
    _notify();
  }

  void readFinished(ReadOutcome outcome, List<RfidReadingRecord> readings, [String? detail]) {
    if (!_running || !_readInProgress) return;
    _readInProgress = false;
    _cycles++;
    _sessionReadings.addAll(readings);
    if (_sessionReadings.length > maxSessionReadings) {
      _sessionReadings.removeRange(0, _sessionReadings.length - maxSessionReadings);
    }

    switch (outcome) {
      case ReadOutcome.success:
      case ReadOutcome.noTag:
        _failures = 0;
        _message = outcome == ReadOutcome.noTag ? 'Last read: no tag found.' : null;
        _scheduleNext(_interval);
      case ReadOutcome.timeout:
        stop('Live View paused: the reader did not confirm the read. '
            'Readings already received were kept.');
      case ReadOutcome.blocked:
        stop('Live View paused: ${detail ?? 'the reader blocked the read'}.');
      case ReadOutcome.error:
      case ReadOutcome.notStarted:
        _failures++;
        if (_failures >= failureLimit) {
          stop('Live View paused after $_failures failed reads in a row'
              '${detail == null ? '' : ': $detail'}.');
        } else {
          _message = 'Read failed; trying again in ${retryDelay.inSeconds} s.';
          _scheduleNext(retryDelay);
        }
    }
    _notify();
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }

  void _runCycle() {
    _timer = null;
    _nextReadAt = null;
    if (!_running) return;
    _readInProgress = true;
    _notify();
    if (!_startRead()) {
      // The reader is busy with something else; wait and retry.
      _readInProgress = false;
      _message = 'Reader busy; trying again in ${retryDelay.inSeconds} s.';
      _scheduleNext(retryDelay);
      _notify();
    }
  }

  void _scheduleNext(Duration delay) {
    _timer?.cancel();
    _nextReadAt = _now().add(delay);
    _timer = _schedule(delay, _runCycle);
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }
}

/// Keeps the newest reading seen for each antenna.
Map<String, RfidReadingRecord> updateLatestByAntenna(
  Map<String, RfidReadingRecord> latest,
  Iterable<RfidReadingRecord> readings,
) {
  final updated = Map<String, RfidReadingRecord>.of(latest);
  for (final reading in readings) {
    final current = updated[reading.antenna];
    final newTime = reading.timestampUtc;
    final oldTime = current?.timestampUtc;
    if (current == null ||
        oldTime == null ||
        (newTime != null && !newTime.isBefore(oldTime))) {
      updated[reading.antenna] = reading;
    }
  }
  return updated;
}
