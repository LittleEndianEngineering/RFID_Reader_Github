import 'dart:convert';

final class RfidReadingRecord {
  const RfidReadingRecord({
    required this.readingNum,
    required this.timestampUtc,
    required this.timestampText,
    required this.country,
    required this.tag,
    required this.temperatureC,
    required this.antenna,
    required this.source,
  });

  final int readingNum;
  final DateTime? timestampUtc;
  final String timestampText;
  final String country;
  final String tag;
  final double? temperatureC;
  final String antenna;
  final String source;
}

final class DeviceStatus {
  const DeviceStatus(this.fields);

  final Map<String, String> fields;

  String? operator [](String key) => fields[key.toLowerCase()];

  factory DeviceStatus.parse(String text) {
    final fields = <String, String>{};

    for (final line in text.split(RegExp(r'\r?\n'))) {
      final separator = line.indexOf(':');
      if (separator <= 0) continue;

      final key = line.substring(0, separator).trim().toLowerCase();
      final value = line.substring(separator + 1).trim();
      if (key.isNotEmpty && value.isNotEmpty) {
        fields[key] = value;
      }
    }

    return DeviceStatus(fields);
  }
}

final class ConfigResponse {
  const ConfigResponse({required this.marker, required this.value});

  final String marker;
  final String value;

  static ConfigResponse? parse(String text) {
    final match = RegExp(
      r'<([A-Z0-9_]+)_BEGIN>\s*([\s\S]*?)\s*<\1_END>',
    ).firstMatch(text);

    if (match == null) return null;

    return ConfigResponse(
      marker: match.group(1)!,
      value: match.group(2)!.trim(),
    );
  }
}

enum ManualReadResponseType { pending, success, noTag, error, blocked }

final class ManualReadResponse {
  const ManualReadResponse({
    required this.type,
    this.readings = const [],
    this.message,
  });

  final ManualReadResponseType type;
  final List<RfidReadingRecord> readings;
  final String? message;
}

final class BleProtocolParser {
  static final RegExp _storedReadingRegex = RegExp(
    '#(\\d+):\\s*([^,\\n]+),\\s*(\\d+),\\s*(\\d+),\\s*'
    '((?:[-+]?\\d+(?:\\.\\d+)?\\s*(?:\u00B0C|C)?)|N/A)'
    '(?:,\\s*(ANT[12]))?',
    caseSensitive: false,
  );

  static final RegExp _liveResultRegex = RegExp(
    '\\[RFID_RESULT\\]\\s+stored=true\\s+ant=(ANT[12])\\s+'
    'reading=(\\d+)\\s+ts=(\\d+)\\s+tag=(\\d+)\\s+(\\d+)\\s+'
    'temp=((?:[-+]?\\d+(?:\\.\\d+)?\\s*(?:\u00B0C|C)?)|N/A)',
    caseSensitive: false,
  );

  static List<RfidReadingRecord> parseReadings(String text) {
    return [...parseLiveResults(text), ...parseStoredReadings(text)];
  }

  static ManualReadResponse parseManualReadResponse(String text) {
    if (text.contains('[IDLE] Manual read blocked') ||
        text.contains('[MANUAL] RFID read skipped')) {
      return ManualReadResponse(
        type: ManualReadResponseType.blocked,
        message: text.trim(),
      );
    }
    if (text.startsWith('ERROR:') ||
        text.startsWith('Unknown command:') ||
        text.contains('Read aborted:') ||
        text.contains('[RTC]') ||
        text.contains('Guru Meditation') ||
        text.contains('Rebooting')) {
      return ManualReadResponse(
        type: ManualReadResponseType.error,
        message: text.trim(),
      );
    }

    final liveResults = parseLiveResults(text);
    if (liveResults.isNotEmpty) {
      return ManualReadResponse(
        type: ManualReadResponseType.success,
        readings: liveResults,
      );
    }

    final storedReadings = parseStoredReadings(text);
    if (storedReadings.isNotEmpty) {
      return ManualReadResponse(
        type: ManualReadResponseType.success,
        readings: storedReadings,
      );
    }

    if (text.contains('No tag detected during window')) {
      return const ManualReadResponse(type: ManualReadResponseType.noTag);
    }

    return const ManualReadResponse(type: ManualReadResponseType.pending);
  }

  static List<RfidReadingRecord> parseStoredReadings(String text) {
    final records = <RfidReadingRecord>[];

    for (final match in _storedReadingRegex.allMatches(text)) {
      final timestampText = _normalizeTimestampText(match.group(2)!.trim());
      records.add(
        RfidReadingRecord(
          readingNum: int.parse(match.group(1)!),
          timestampUtc: _parseUtcTimestamp(timestampText),
          timestampText: timestampText,
          country: match.group(3)!.trim(),
          tag: match.group(4)!.trim(),
          temperatureC: _parseTemperature(match.group(5)!.trim()),
          antenna: (match.group(6) ?? 'ANT1').toUpperCase(),
          source: 'stored',
        ),
      );
    }

    return records;
  }

  static List<RfidReadingRecord> parseLiveResults(String text) {
    final records = <RfidReadingRecord>[];

    for (final match in _liveResultRegex.allMatches(text)) {
      final epochSeconds = int.tryParse(match.group(3)!);
      final timestampUtc = epochSeconds == null
          ? null
          : DateTime.fromMillisecondsSinceEpoch(
              epochSeconds * 1000,
              isUtc: true,
            );

      records.add(
        RfidReadingRecord(
          antenna: match.group(1)!.toUpperCase(),
          readingNum: int.parse(match.group(2)!),
          timestampUtc: timestampUtc,
          timestampText: timestampUtc?.toIso8601String() ?? match.group(3)!,
          country: match.group(4)!.trim(),
          tag: match.group(5)!.trim(),
          temperatureC: _parseTemperature(match.group(6)!.trim()),
          source: 'live',
        ),
      );
    }

    return records;
  }

  static RfidReadingRecord? parseLiveResult(String text) {
    final results = parseLiveResults(text);
    return results.isEmpty ? null : results.first;
  }

  static double? _parseTemperature(String value) {
    final normalized = value
        .replaceAll('\u00B0', '')
        .replaceAll('C', '')
        .trim();

    if (normalized.toUpperCase() == 'N/A' || normalized.isEmpty) {
      return null;
    }

    return double.tryParse(normalized);
  }

  static DateTime? _parseUtcTimestamp(String value) {
    final match = RegExp(
      r'^(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{1,2}):(\d{1,2})$',
    ).firstMatch(value.trim());

    if (match == null) return null;

    return DateTime.utc(
      int.parse(match.group(1)!),
      int.parse(match.group(2)!),
      int.parse(match.group(3)!),
      int.parse(match.group(4)!),
      int.parse(match.group(5)!),
      int.parse(match.group(6)!),
    );
  }

  static String _normalizeTimestampText(String value) {
    final match = RegExp(
      r'^(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{1,2}):(\d{1,2})$',
    ).firstMatch(value.trim());

    if (match == null) return value.trim();

    return '${match.group(1)!}-'
        '${match.group(2)!.padLeft(2, '0')}-'
        '${match.group(3)!.padLeft(2, '0')} '
        '${match.group(4)!.padLeft(2, '0')}:'
        "${match.group(5)!.padLeft(2, '0')}:"
        "${match.group(6)!.padLeft(2, '0')}";
  }
}

/// Collects a complete command, rather than treating each antenna as a command.
final class ManualReadSession {
  ManualReadSession({
    required this.expectedAntennas,
    required this.requiresCompletionMarker,
  });

  final Set<String> expectedAntennas;
  final bool requiresCompletionMarker;
  final List<RfidReadingRecord> readings = [];
  final Set<String> _finishedAntennas = {};
  String? _currentAntenna;
  bool isComplete = false;
  int readWindowMs = 5000;

  Duration get timeout => Duration(
    milliseconds:
        readWindowMs * expectedAntennas.length * 2 +
        (expectedAntennas.length == 2 ? 30000 : 20000),
  );

  ManualReadResponse add(String text) {
    if (isComplete) {
      return const ManualReadResponse(type: ManualReadResponseType.pending);
    }
    final window = RegExp(r'read window \((\d+)ms\)').firstMatch(text);
    if (window != null) readWindowMs = int.parse(window.group(1)!);
    final antenna = RegExp(r'\[RFID\]\[(ANT[12])\]').firstMatch(text)?.group(1);
    if (antenna != null) _currentAntenna = antenna;
    final response = BleProtocolParser.parseManualReadResponse(text);
    if (response.type == ManualReadResponseType.error ||
        response.type == ManualReadResponseType.blocked) {
      isComplete = true;
      return ManualReadResponse(
        type: response.type,
        readings: List.of(readings),
        message: response.message,
      );
    }
    for (final record in response.readings) {
      // Older firmware omits the antenna suffix on live # records. Its progress
      // messages identify the antenna that produced them.
      final legacyAntenna =
          record.source == 'stored' &&
              !RegExp(r',\s*ANT[12]\s*$').hasMatch(text)
          ? _currentAntenna
          : null;
      final normalized = legacyAntenna == null
          ? record
          : RfidReadingRecord(
              readingNum: record.readingNum,
              timestampUtc: record.timestampUtc,
              timestampText: record.timestampText,
              country: record.country,
              tag: record.tag,
              temperatureC: record.temperatureC,
              antenna: legacyAntenna,
              source: record.source,
            );
      if (expectedAntennas.contains(normalized.antenna) &&
          !readings.any((old) => old.antenna == normalized.antenna)) {
        readings.add(normalized);
      }
    }
    // Legacy firmware has no command completion marker. Power OFF terminates
    // that antenna's window; no-tag messages alone can precede a recovery retry.
    if (antenna != null && text.contains('Power OFF')) {
      _finishedAntennas.add(antenna);
    }
    final complete = RegExp(
      r'^\[MANUAL\](?: ANT[12])? RFID read complete(?:\s|$)',
    ).hasMatch(text);
    if (complete ||
        (!requiresCompletionMarker &&
            _finishedAntennas.containsAll(expectedAntennas))) {
      isComplete = true;
      return ManualReadResponse(
        type: readings.isEmpty
            ? ManualReadResponseType.noTag
            : ManualReadResponseType.success,
        readings: List.of(readings),
      );
    }
    return const ManualReadResponse(type: ManualReadResponseType.pending);
  }
}

/// V2 firmware frames every response with a newline. Legacy firmware still
/// sends complete notifications; the explicit handshake chooses between them.
final class BleResponseBuffer {
  BleResponseBuffer({bool lineDelimited = false})
    : _lineDelimited = lineDelimited;

  static const protocolMarker = 'RFID_PROTOCOL_V2';
  bool _lineDelimited;
  final List<int> _pending = [];
  bool get usesLineFraming => _lineDelimited;

  List<String> add(List<int> bytes, [String Function(List<int>)? decode]) {
    _pending.addAll(bytes);
    final messages = <String>[];
    final decoder = decode ?? decodeBleText;
    while (true) {
      final newline = _pending.indexOf(10);
      if (newline < 0) break;
      final line = decoder(_pending.sublist(0, newline)).trimRight();
      _pending.removeRange(0, newline + 1);
      if (line == protocolMarker) _lineDelimited = true;
      if (line.trim().isNotEmpty) messages.add(line);
    }
    if (!_lineDelimited && _pending.isNotEmpty) {
      final tail = decoder(_pending);
      if (tail.trim() == protocolMarker) {
        _lineDelimited = true;
        _pending.clear();
        messages.add(protocolMarker);
      } else if (!_looksIncomplete(tail)) {
        _pending.clear();
        if (tail.trim().isNotEmpty) messages.add(tail);
      }
    }
    return messages;
  }

  List<String> addText(String chunk) => add(utf8.encode(chunk));

  void clear() => _pending.clear();

  void reset() {
    clear();
    _lineDelimited = false;
  }

  bool _looksIncomplete(String text) {
    final trimmed = text.trim();
    if (protocolMarker.startsWith(trimmed)) return true;
    if (trimmed.startsWith('#')) {
      return BleProtocolParser.parseStoredReadings(trimmed).isEmpty;
    }
    if (trimmed.startsWith('[RFID_RESULT]')) {
      return BleProtocolParser.parseLiveResults(trimmed).isEmpty;
    }
    return false;
  }
}

String decodeBleText(List<int> bytes) =>
    utf8.decode(bytes, allowMalformed: true);
