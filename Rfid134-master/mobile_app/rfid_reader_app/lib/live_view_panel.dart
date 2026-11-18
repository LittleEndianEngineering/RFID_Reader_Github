import 'package:flutter/material.dart';

import 'ble_protocol.dart';
import 'live_view.dart';

/// Live View switch, latest reading per antenna, and this session's reads.
class LiveViewPanel extends StatelessWidget {
  const LiveViewPanel({
    super.key,
    required this.controller,
    required this.latestByAntenna,
    required this.isConnected,
    required this.onToggle,
    required this.formatTime,
  });

  final LiveViewController controller;
  final Map<String, RfidReadingRecord> latestByAntenna;
  final bool isConnected;
  final ValueChanged<bool> onToggle;

  /// Formats a UTC time in the time zone chosen by the user.
  final String Function(DateTime utc) formatTime;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final running = controller.running;
        final session = controller.sessionReadings;
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        '📡 Live View',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ),
                    Switch(
                      value: running,
                      onChanged: isConnected || running ? onToggle : null,
                    ),
                  ],
                ),
                Text(
                  _subtitle(),
                  style: const TextStyle(fontSize: 12, color: Colors.grey),
                ),
                if (running && controller.readInProgress) ...[
                  const SizedBox(height: 8),
                  const LinearProgressIndicator(),
                ],
                if (controller.message != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    controller.message!,
                    style: TextStyle(
                      fontSize: 13,
                      color: running ? Colors.grey[700] : Colors.orange[800],
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                Text('Latest reading', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 8),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: _AntennaCard(
                        antenna: 'ANT1',
                        reading: latestByAntenna['ANT1'],
                        formatTime: formatTime,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _AntennaCard(
                        antenna: 'ANT2',
                        reading: latestByAntenna['ANT2'],
                        formatTime: formatTime,
                      ),
                    ),
                  ],
                ),
                if (session.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(
                    'This Live View session: ${session.length} reading(s)',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  const SizedBox(height: 4),
                  for (final r in session.reversed.take(5))
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Text(
                        '${r.antenna}  ${r.country} ${r.tag}  ${_temp(r)}  '
                        '${r.timestampUtc == null ? r.timestampText : formatTime(r.timestampUtc!)}',
                        style: const TextStyle(fontSize: 12, fontFamily: 'monospace'),
                      ),
                    ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  String _subtitle() {
    if (!controller.running) {
      return 'Reads both antennas again and again, like the USB dashboard. '
          'The time between reads is the Live View interval on the Device tab.';
    }
    final parts = <String>['Every ${controller.interval.inSeconds} s', '${controller.cycles} read(s)'];
    final next = controller.nextReadAt;
    if (controller.readInProgress) {
      parts.add('reading now…');
    } else if (next != null) {
      parts.add('next at ${_clock(next)}');
    }
    return parts.join(' · ');
  }

  static String _clock(DateTime t) =>
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}:'
      '${t.second.toString().padLeft(2, '0')}';
}

String _temp(RfidReadingRecord r) =>
    r.temperatureC == null ? 'N/A' : '${r.temperatureC!.toStringAsFixed(2)} °C';

class _AntennaCard extends StatelessWidget {
  const _AntennaCard({
    required this.antenna,
    required this.reading,
    required this.formatTime,
  });

  final String antenna;
  final RfidReadingRecord? reading;
  final String Function(DateTime utc) formatTime;

  @override
  Widget build(BuildContext context) {
    final r = reading;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: (r == null ? Colors.grey : Colors.green).withValues(alpha: 0.08),
        border: Border.all(
          color: (r == null ? Colors.grey : Colors.green).withValues(alpha: 0.4),
        ),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(antenna, style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          if (r == null)
            const Text('No reading yet', style: TextStyle(fontSize: 12, color: Colors.grey))
          else ...[
            Text(
              _temp(r),
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
            ),
            Text('${r.country} ${r.tag}', style: const TextStyle(fontSize: 12)),
            Text(
              r.timestampUtc == null ? r.timestampText : formatTime(r.timestampUtc!),
              style: const TextStyle(fontSize: 11, color: Colors.grey),
            ),
          ],
        ],
      ),
    );
  }
}
