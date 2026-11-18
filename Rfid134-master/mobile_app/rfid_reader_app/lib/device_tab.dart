import 'package:flutter/material.dart';

import 'app_info.dart';
import 'device_settings.dart';

/// Reader status cards and configuration, matching the USB dashboard's
/// status and configuration sections.
class DeviceTab extends StatelessWidget {
  const DeviceTab({
    super.key,
    required this.controller,
    required this.isConnected,
    required this.supportsSettings,
  });

  final DeviceSettingsController controller;
  final bool isConnected;

  /// True when the reader answered `protocol` with `RFID_PROTOCOL_V2`.
  final bool supportsSettings;

  @override
  Widget build(BuildContext context) {
    if (!isConnected) {
      return const _EmptyState(
        icon: Icons.bluetooth_disabled,
        text: 'Connect to a reader on the Dashboard tab to see its status and settings.',
      );
    }

    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        return ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
          children: [
            if (controller.busy) const LinearProgressIndicator(),
            if (controller.message != null) ...[
              const SizedBox(height: 8),
              _MessageBanner(
                text: controller.message!,
                isError: controller.messageIsError,
              ),
            ],
            const SizedBox(height: 8),
            _StatusCard(controller: controller),
            const SizedBox(height: 16),
            if (supportsSettings)
              _SettingsCard(controller: controller)
            else
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(16),
                  child: Text(
                    'Settings need reader firmware $kPairedFirmwareVersion. '
                    'This reader uses older firmware, so only its status is shown.',
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            Text(text, textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

class _MessageBanner extends StatelessWidget {
  const _MessageBanner({required this.text, required this.isError});

  final String text;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    final color = isError ? Colors.red : Colors.green;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        border: Border.all(color: color.withValues(alpha: 0.4)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(isError ? Icons.error_outline : Icons.check_circle_outline, color: color),
          const SizedBox(width: 8),
          Expanded(child: Text(text)),
        ],
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.controller});

  final DeviceSettingsController controller;

  @override
  Widget build(BuildContext context) {
    final status = controller.status;
    final updated = controller.statusUpdatedAt;
    final soc = status.batterySocPercent;
    final volts = status.batteryVoltage;
    final recovery = status.usbRecoveryActive;
    final remaining = status.usbRecoveryRemainingSeconds;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'Reader status',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                ),
                if (updated != null)
                  Text(
                    'Updated ${_time(updated)}',
                    style: const TextStyle(fontSize: 12, color: Colors.grey),
                  ),
                IconButton(
                  tooltip: 'Refresh status',
                  icon: const Icon(Icons.refresh),
                  onPressed: controller.busy ? null : controller.refreshStatus,
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (status.isEmpty)
              const Text('No status yet. Tap refresh.')
            else
              LayoutBuilder(
                builder: (context, constraints) {
                  final columns = constraints.maxWidth >= 600 ? 3 : 2;
                  final width = (constraints.maxWidth - (columns - 1) * 8) / columns;
                  final tiles = [
                    _StatusTile(
                      icon: _batteryIcon(soc),
                      color: _batteryColor(soc),
                      label: 'Battery',
                      value: soc == null ? 'N/A' : '${soc.toStringAsFixed(0)} %',
                      detail: volts == null ? null : '${volts.toStringAsFixed(2)} V',
                    ),
                    _StatusTile(
                      icon: Icons.storage,
                      label: 'Stored readings',
                      value: status.readingCount?.toString() ?? '—',
                    ),
                    _StatusTile(
                      icon: Icons.bluetooth_connected,
                      label: 'Dashboard mode',
                      value: _onOff(status.dashboardModeActive, 'Active', 'Inactive'),
                    ),
                    _StatusTile(
                      icon: Icons.bedtime,
                      color: status.idleModeActive == true ? Colors.orange : null,
                      label: 'Idle mode',
                      value: _onOff(status.idleModeActive, 'Active', 'Inactive'),
                      detail: status.idleModeActive == true ? status.idleReason : null,
                    ),
                    _StatusTile(
                      icon: Icons.battery_alert,
                      label: 'Low battery idle',
                      value: _onOff(status.lowSocIdleEnabled, 'Enabled', 'Disabled'),
                    ),
                    _StatusTile(
                      icon: Icons.usb,
                      label: 'USB recovery',
                      value: _onOff(recovery, 'Active', 'Inactive'),
                      detail: recovery == true && remaining != null ? '$remaining s left' : null,
                    ),
                    _StatusTile(
                      icon: Icons.lightbulb_outline,
                      label: 'LED',
                      value: (status.ledStatus ?? '—').replaceAll('_', ' '),
                    ),
                  ];
                  return Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [for (final t in tiles) SizedBox(width: width, child: t)],
                  );
                },
              ),
          ],
        ),
      ),
    );
  }

  static String _time(DateTime t) =>
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}:'
      '${t.second.toString().padLeft(2, '0')}';

  static String _onOff(bool? value, String on, String off) =>
      value == null ? '—' : (value ? on : off);

  static IconData _batteryIcon(double? soc) {
    if (soc == null) return Icons.battery_unknown;
    if (soc >= 80) return Icons.battery_full;
    if (soc >= 50) return Icons.battery_5_bar;
    if (soc >= 20) return Icons.battery_3_bar;
    return Icons.battery_1_bar;
  }

  static Color? _batteryColor(double? soc) {
    if (soc == null) return null;
    if (soc < 20) return Colors.red;
    if (soc < 50) return Colors.orange;
    return Colors.green;
  }
}

class _StatusTile extends StatelessWidget {
  const _StatusTile({
    required this.icon,
    required this.label,
    required this.value,
    this.detail,
    this.color,
  });

  final IconData icon;
  final String label;
  final String value;
  final String? detail;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.grey.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color ?? Colors.blueGrey),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
                Text(value, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                if (detail != null)
                  Text(detail!, style: const TextStyle(fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SettingsCard extends StatelessWidget {
  const _SettingsCard({required this.controller});

  final DeviceSettingsController controller;

  @override
  Widget build(BuildContext context) {
    final groups = <String, List<DeviceSettingSpec>>{};
    for (final spec in kDeviceSettings) {
      groups.putIfAbsent(spec.group, () => []).add(spec);
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'Settings',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                ),
                TextButton.icon(
                  onPressed: controller.busy ? null : controller.loadSettings,
                  icon: const Icon(Icons.download),
                  label: Text(controller.hasSettings ? 'Reload' : 'Load'),
                ),
              ],
            ),
            const Text(
              'Changes are saved on the reader right away.',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
            if (!controller.hasSettings && !controller.busy)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: Text('Tap Load to read the settings from the reader.'),
              ),
            if (controller.hasSettings)
              for (final entry in groups.entries) ...[
                Padding(
                  padding: const EdgeInsets.only(top: 16, bottom: 4),
                  child: Text(
                    entry.key,
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                  ),
                ),
                for (final spec in entry.value)
                  _SettingRow(controller: controller, spec: spec),
              ],
          ],
        ),
      ),
    );
  }
}

class _SettingRow extends StatelessWidget {
  const _SettingRow({required this.controller, required this.spec});

  final DeviceSettingsController controller;
  final DeviceSettingSpec spec;

  @override
  Widget build(BuildContext context) {
    final raw = controller.values[spec.key];
    final enabled = !controller.busy && raw != null;

    if (spec.kind == SettingKind.flag) {
      return SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(spec.label),
        subtitle: spec.help == null ? null : Text(spec.help!),
        value: raw != null && spec.isOn(raw),
        onChanged: enabled
            ? (on) => controller.saveSetting(spec, on ? 1 : 0)
            : null,
      );
    }

    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(spec.label),
      subtitle: spec.help == null ? null : Text(spec.help!),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            spec.formatDisplay(raw),
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
          const SizedBox(width: 4),
          Icon(Icons.edit, size: 18, color: enabled ? null : Colors.grey),
        ],
      ),
      enabled: enabled,
      onTap: enabled ? () => _edit(context, raw) : null,
    );
  }

  Future<void> _edit(BuildContext context, String raw) async {
    final initial = spec.toDisplay(raw);
    final text = TextEditingController(
      text: initial == null ? '' : initial.toStringAsFixed(spec.decimals),
    );
    final range = [
      if (spec.min != null) 'min ${spec.min}',
      if (spec.max != null) 'max ${spec.max}',
    ].join(', ');

    final value = await showDialog<double>(
      context: context,
      builder: (dialogContext) {
        String? error;
        return StatefulBuilder(
          builder: (dialogContext, setDialogState) {
            void submit() {
              final parsed = double.tryParse(text.text.trim().replaceAll(',', '.'));
              final problem = parsed == null
                  ? 'Enter a number'
                  : controller.validate(spec, parsed);
              if (problem != null) {
                setDialogState(() => error = problem);
                return;
              }
              Navigator.of(dialogContext).pop(parsed);
            }

            return AlertDialog(
              title: Text(spec.label),
              content: TextField(
                controller: text,
                autofocus: true,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(
                  suffixText: spec.unit,
                  helperText: range.isEmpty ? null : 'Allowed: $range',
                  errorText: error,
                ),
                onSubmitted: (_) => submit(),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(dialogContext).pop(),
                  child: const Text('Cancel'),
                ),
                FilledButton(onPressed: submit, child: const Text('Save')),
              ],
            );
          },
        );
      },
    );
    // `text` is not disposed here: the dialog may still be animating out.
    if (value != null) await controller.saveSetting(spec, value);
  }
}
