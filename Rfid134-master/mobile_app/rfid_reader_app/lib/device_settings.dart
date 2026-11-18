import 'dart:async';

import 'package:flutter/foundation.dart';

/// How a firmware configuration value is shown and edited in the app.
enum SettingKind {
  /// Firmware stores milliseconds; the app shows and edits seconds.
  milliseconds,

  /// Firmware stores `0` or `1`.
  flag,

  /// Firmware stores a decimal number (volts or percent).
  decimal,
}

/// One configuration variable exposed over BLE by firmware 1.6.0-dev.1.
///
/// Limits follow the USB dashboard, because firmware does not range-check
/// every value itself.
final class DeviceSettingSpec {
  const DeviceSettingSpec({
    required this.key,
    required this.marker,
    required this.label,
    required this.group,
    required this.kind,
    this.unit = '',
    this.min,
    this.max,
    this.decimals = 0,
    this.help,
  });

  /// Firmware variable name used in `get <key>` / `set <key> <value>`.
  final String key;

  /// Marker name in `<MARKER_BEGIN> value <MARKER_END>` replies.
  final String marker;
  final String label;
  final String group;
  final SettingKind kind;
  final String unit;
  final double? min;
  final double? max;
  final int decimals;
  final String? help;

  /// Firmware raw value to the value shown to the user.
  double? toDisplay(String raw) {
    final value = double.tryParse(raw.trim());
    if (value == null) return null;
    return kind == SettingKind.milliseconds ? value / 1000 : value;
  }

  String formatDisplay(String? raw) {
    if (raw == null) return '—';
    if (kind == SettingKind.flag) return isOn(raw) ? 'On' : 'Off';
    final value = toDisplay(raw);
    if (value == null) return raw;
    final text = value.toStringAsFixed(decimals);
    return unit.isEmpty ? text : '$text $unit';
  }

  bool isOn(String raw) => raw.trim() == '1' || raw.trim() == 'true';

  /// User value to the firmware text sent with `set`.
  String toFirmware(double display) {
    return switch (kind) {
      SettingKind.milliseconds => (display * 1000).round().toString(),
      SettingKind.flag => display != 0 ? '1' : '0',
      SettingKind.decimal => display.toStringAsFixed(2),
    };
  }

  /// Returns an error message, or null when the value is allowed.
  String? validate(double value) {
    if (value.isNaN || value.isInfinite) return 'Enter a number';
    if (min != null && value < min!) return 'Minimum is ${_fmt(min!)} $unit'.trim();
    if (max != null && value > max!) return 'Maximum is ${_fmt(max!)} $unit'.trim();
    return null;
  }

  String _fmt(double v) => v == v.roundToDouble() ? v.toStringAsFixed(0) : '$v';
}

const List<DeviceSettingSpec> kDeviceSettings = [
  DeviceSettingSpec(
    key: 'rfidOnTimeMs',
    marker: 'GET_RFIDONTIME',
    label: 'RFID on time',
    group: 'Reading',
    kind: SettingKind.milliseconds,
    unit: 's',
    min: 3,
    max: 60,
    help: 'How long each antenna listens for a tag.',
  ),
  DeviceSettingSpec(
    key: 'periodicIntervalMs',
    marker: 'GET_PERIODICINTERVAL',
    label: 'Periodic interval',
    group: 'Reading',
    kind: SettingKind.milliseconds,
    unit: 's',
    min: 10,
    max: 3600,
    help: 'Time between automatic reads.',
  ),
  DeviceSettingSpec(
    key: 'liveViewAutoReadIntervalMs',
    marker: 'GET_LIVEVIEWAUTOREADINTERVALMS',
    label: 'Live View interval',
    group: 'Reading',
    kind: SettingKind.milliseconds,
    unit: 's',
    min: 8,
    max: 300,
  ),
  DeviceSettingSpec(
    key: 'longPressMs',
    marker: 'GET_LONGPRESSMS',
    label: 'Long press time',
    group: 'Button',
    kind: SettingKind.milliseconds,
    unit: 's',
    min: 1,
    max: 30,
    help: 'Button hold time that toggles Dashboard Mode on the device.',
  ),
  DeviceSettingSpec(
    key: 'socLowIdleEnabled',
    marker: 'GET_SOCLOWIDLEENABLED',
    label: 'Low battery idle',
    group: 'Battery',
    kind: SettingKind.flag,
    help: 'Stop reading when the battery is low.',
  ),
  DeviceSettingSpec(
    key: 'socLowThresholdPercent',
    marker: 'GET_SOCLOWTHRESHOLDPERCENT',
    label: 'Low battery threshold',
    group: 'Battery',
    kind: SettingKind.decimal,
    unit: '%',
    min: 0,
    max: 100,
    decimals: 1,
  ),
  DeviceSettingSpec(
    key: 'lowSocUsbRecoveryWindowMs',
    marker: 'GET_LOWSOCUSBRECOVERYWINDOWMS',
    label: 'USB recovery window',
    group: 'Battery',
    kind: SettingKind.milliseconds,
    unit: 's',
    min: 0,
    max: 300,
  ),
  DeviceSettingSpec(
    key: 'batteryMinVoltage',
    marker: 'GET_BATTERYMINVOLTAGE',
    label: 'Battery minimum voltage',
    group: 'Battery',
    kind: SettingKind.decimal,
    unit: 'V',
    min: 2.5,
    max: 4.2,
    decimals: 2,
  ),
  DeviceSettingSpec(
    key: 'batteryMaxVoltage',
    marker: 'GET_BATTERYMAXVOLTAGE',
    label: 'Battery maximum voltage',
    group: 'Battery',
    kind: SettingKind.decimal,
    unit: 'V',
    min: 3.5,
    max: 4.5,
    decimals: 2,
  ),
  DeviceSettingSpec(
    key: 'ledHeartbeatIntervalMs',
    marker: 'GET_LEDHEARTBEATINTERVALMS',
    label: 'LED heartbeat interval',
    group: 'LED',
    kind: SettingKind.milliseconds,
    unit: 's',
    min: 1,
    max: 120,
    decimals: 1,
  ),
  DeviceSettingSpec(
    key: 'ledHeartbeatOnMs',
    marker: 'GET_LEDHEARTBEATONMS',
    label: 'LED heartbeat on time',
    group: 'LED',
    kind: SettingKind.milliseconds,
    unit: 's',
    min: 0.1,
    max: 10,
    decimals: 1,
  ),
  DeviceSettingSpec(
    key: 'verbose',
    marker: 'GET_VERBOSE',
    label: 'Verbose serial logs',
    group: 'Diagnostics',
    kind: SettingKind.flag,
  ),
];

DeviceSettingSpec? deviceSettingByKey(String key) {
  for (final spec in kDeviceSettings) {
    if (spec.key == key) return spec;
  }
  return null;
}

/// Typed view of the `status` reply.
final class DeviceStatusSummary {
  const DeviceStatusSummary(this.fields);

  /// Lower-case field name to raw value.
  final Map<String, String> fields;

  static const statusKeys = {
    'dashboard mode',
    'idle mode',
    'idle reason',
    'low soc idle',
    'low soc usb recovery',
    'usb recovery remaining',
    'reading count',
    'led status',
    'battery voltage',
    'battery soc',
  };

  /// Returns the normalised `(key, value)` of a status line, or null.
  /// Accepts `Dashboard Mode: X`, `[DASHBOARD] Dashboard Mode: X`,
  /// `Idle mode: X` and `[IDLE] Mode: X`.
  static (String, String)? parseLine(String line) {
    var text = line.trim();
    final tag = RegExp(r'^\[([A-Z]+)\]\s*').firstMatch(text);
    if (tag != null) text = text.substring(tag.end);
    final separator = text.indexOf(':');
    if (separator <= 0) return null;
    var key = text.substring(0, separator).trim().toLowerCase();
    final value = text.substring(separator + 1).trim();
    if (tag?.group(1) == 'IDLE' && key == 'mode') key = 'idle mode';
    if (!statusKeys.contains(key) || value.isEmpty) return null;
    return (key, value);
  }

  bool? _flag(String key, String onWord) {
    final value = fields[key];
    if (value == null) return null;
    return value.toUpperCase().startsWith(onWord);
  }

  bool? get dashboardModeActive => _flag('dashboard mode', 'ACTIVE');
  bool? get idleModeActive => _flag('idle mode', 'ACTIVE');
  String? get idleReason => fields['idle reason'];
  bool? get lowSocIdleEnabled => _flag('low soc idle', 'ENABLED');
  bool? get usbRecoveryActive => _flag('low soc usb recovery', 'ACTIVE');
  int? get usbRecoveryRemainingSeconds =>
      int.tryParse((fields['usb recovery remaining'] ?? '').replaceAll('s', ''));
  int? get readingCount => int.tryParse(fields['reading count'] ?? '');
  String? get ledStatus => fields['led status'];
  double? get batteryVoltage => double.tryParse(fields['battery voltage'] ?? '');
  double? get batterySocPercent => double.tryParse(fields['battery soc'] ?? '');

  bool get isEmpty => fields.isEmpty;
}

enum _RequestKind { status, get, set }

final class _Request {
  _Request(this.kind, this.command, {this.spec});

  final _RequestKind kind;
  final String command;
  final DeviceSettingSpec? spec;
  final Completer<String?> completer = Completer<String?>();
  final Map<String, String> statusFields = {};
  bool insideValue = false;
  final List<String> valueLines = [];
}

/// Sends `status`, `get` and `set` commands one at a time and collects their
/// replies from the shared BLE response stream.
///
/// The main screen passes every received line to [handleLine]. Lines that
/// belong to the active request are consumed, so they never reach the
/// readings parser.
class DeviceSettingsController extends ChangeNotifier {
  DeviceSettingsController({
    required Future<void> Function(String command) send,
    required bool Function() canSend,
    this.timeout = const Duration(seconds: 4),
  }) : _send = send,
       _canSend = canSend;

  final Future<void> Function(String command) _send;
  final bool Function() _canSend;
  final Duration timeout;

  final Map<String, String> _values = {};
  DeviceStatusSummary _status = const DeviceStatusSummary({});
  DateTime? _statusUpdatedAt;
  String? _message;
  bool _messageIsError = false;
  bool _busy = false;
  _Request? _active;
  Timer? _timer;
  bool _disposed = false;
  int _generation = 0;

  Map<String, String> get values => Map.unmodifiable(_values);
  DeviceStatusSummary get status => _status;
  DateTime? get statusUpdatedAt => _statusUpdatedAt;
  bool get busy => _busy;
  bool get hasSettings => _values.isNotEmpty;

  /// Latest result for the user, e.g. "Saved" or an error.
  String? get message => _message;
  bool get messageIsError => _messageIsError;

  /// Forget everything about the previous reader (call on disconnect).
  void reset() {
    _generation++;
    _finish(null);
    _values.clear();
    _status = const DeviceStatusSummary({});
    _statusUpdatedAt = null;
    _message = null;
    _messageIsError = false;
    _busy = false;
    _notify();
  }

  Future<bool> refreshStatus() async {
    if (!_begin()) return false;
    try {
      final ok = await _run(_Request(_RequestKind.status, 'status')) != null;
      _setMessage(ok ? null : 'The reader did not send its status.', !ok);
      return ok;
    } finally {
      _end();
    }
  }

  Future<bool> loadSettings() async {
    if (!_begin()) return false;
    var failures = 0;
    final generation = _generation;
    try {
      for (final spec in kDeviceSettings) {
        if (generation != _generation) return false;
        final value = await _run(
          _Request(_RequestKind.get, 'get ${spec.key}', spec: spec),
        );
        if (value == null) {
          failures++;
        } else {
          _values[spec.key] = value;
          _notify();
        }
      }
      if (failures == 0) {
        _setMessage(null, false);
      } else {
        _setMessage('$failures setting(s) could not be read.', true);
      }
      return failures == 0;
    } finally {
      _end();
    }
  }

  /// Checks cross-field rules before sending.
  String? validate(DeviceSettingSpec spec, double display) {
    final error = spec.validate(display);
    if (error != null) return error;
    double? other(String key) {
      final raw = _values[key];
      return raw == null ? null : deviceSettingByKey(key)!.toDisplay(raw);
    }

    if (spec.key == 'batteryMinVoltage') {
      final max = other('batteryMaxVoltage');
      if (max != null && display >= max) return 'Must be below the maximum voltage';
    } else if (spec.key == 'batteryMaxVoltage') {
      final min = other('batteryMinVoltage');
      if (min != null && display <= min) return 'Must be above the minimum voltage';
    } else if (spec.key == 'ledHeartbeatOnMs') {
      final interval = other('ledHeartbeatIntervalMs');
      if (interval != null && display >= interval) {
        return 'Must be shorter than the heartbeat interval';
      }
    } else if (spec.key == 'ledHeartbeatIntervalMs') {
      final on = other('ledHeartbeatOnMs');
      if (on != null && display <= on) return 'Must be longer than the on time';
    }
    return null;
  }

  /// Sends `set`, then reads the value back to confirm it was stored.
  Future<bool> saveSetting(DeviceSettingSpec spec, double display) async {
    final error = validate(spec, display);
    if (error != null) {
      _setMessage(error, true);
      return false;
    }
    if (!_begin()) return false;
    final generation = _generation;
    try {
      final reply = await _run(
        _Request(
          _RequestKind.set,
          'set ${spec.key} ${spec.toFirmware(display)}',
          spec: spec,
        ),
      );
      if (reply != 'OK') {
        _setMessage(
          reply == null ? 'No answer from the reader.' : _friendlyError(reply),
          true,
        );
        return false;
      }
      if (generation != _generation) return false;
      final confirmed = await _run(
        _Request(_RequestKind.get, 'get ${spec.key}', spec: spec),
      );
      if (confirmed != null) _values[spec.key] = confirmed;
      _setMessage('${spec.label} saved.', false);
      return true;
    } finally {
      _end();
    }
  }

  /// Returns true when [line] was part of a status/get/set reply.
  bool handleLine(String line) {
    final request = _active;
    final text = line.trim();
    if (text.isEmpty) return false;

    if (request == null) {
      // Status replies triggered elsewhere (e.g. the Status button) still
      // refresh the cards, but are left for the debug log as well.
      final field = DeviceStatusSummary.parseLine(text);
      if (field != null) _updateStatus({field.$1: field.$2});
      return false;
    }

    switch (request.kind) {
      case _RequestKind.status:
        final field = DeviceStatusSummary.parseLine(text);
        if (field == null) return false;
        request.statusFields[field.$1] = field.$2;
        _updateStatus({field.$1: field.$2});
        // `Battery SoC` is the last status line sent by firmware.
        if (field.$1 == 'battery soc') _finish('ok');
        return true;
      case _RequestKind.get:
        final marker = request.spec!.marker;
        if (text == '<${marker}_BEGIN>') {
          request.insideValue = true;
          return true;
        }
        if (text == '<${marker}_END>') {
          _finish(request.valueLines.join('\n').trim());
          return true;
        }
        if (request.insideValue) {
          request.valueLines.add(text);
          return true;
        }
        if (_isErrorReply(text)) {
          _finish(null);
          return true;
        }
        return false;
      case _RequestKind.set:
        if (text == 'OK' || _isErrorReply(text)) {
          _finish(text);
          return true;
        }
        return false;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _finish(null);
    super.dispose();
  }

  bool _begin() {
    if (_busy) return false;
    if (!_canSend()) {
      _setMessage('The reader is busy. Try again when the current task ends.', true);
      return false;
    }
    _busy = true;
    _notify();
    return true;
  }

  void _end() {
    if (_disposed) return;
    _busy = false;
    _notify();
  }

  Future<String?> _run(_Request request) async {
    _active = request;
    _timer?.cancel();
    _timer = Timer(timeout, () {
      // A partial status reply is still useful.
      if (request.kind == _RequestKind.status && request.statusFields.isNotEmpty) {
        _finish('partial');
      } else {
        _finish(null);
      }
    });
    try {
      await _send(request.command);
    } catch (_) {
      _finish(null);
    }
    return request.completer.future;
  }

  void _finish(String? result) {
    final request = _active;
    _active = null;
    _timer?.cancel();
    _timer = null;
    if (request != null && !request.completer.isCompleted) {
      request.completer.complete(result);
    }
  }

  void _updateStatus(Map<String, String> fields) {
    _status = DeviceStatusSummary({..._status.fields, ...fields});
    _statusUpdatedAt = DateTime.now();
    _notify();
  }

  void _setMessage(String? message, bool isError) {
    _message = message;
    _messageIsError = isError;
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  static bool _isErrorReply(String text) =>
      text.startsWith('ERROR') || text.toLowerCase().contains('unknown command');

  static String _friendlyError(String reply) =>
      reply.startsWith('ERROR:') ? reply.substring(6).trim() : reply;
}
