import 'package:flutter/material.dart';
// ignore: depend_on_referenced_packages
import 'package:flutter_blue_plus_platform_interface/flutter_blue_plus_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rfid_reader_app/main.dart';

final class FakeFlutterBluePlusPlatform extends FlutterBluePlusPlatform {
  @override
  Stream<BmBluetoothAdapterState> get onAdapterStateChanged =>
      const Stream.empty();

  @override
  Future<BmBluetoothAdapterState> getAdapterState(
    BmBluetoothAdapterStateRequest request,
  ) async {
    return BmBluetoothAdapterState(adapterState: BmAdapterStateEnum.on);
  }
}

void main() {
  testWidgets('RFID reader app renders dashboard shell', (
    WidgetTester tester,
  ) async {
    FlutterBluePlusPlatform.instance = FakeFlutterBluePlusPlatform();

    await tester.pumpWidget(const RFIDReaderApp());
    await tester.pump();

    expect(find.text('Implant RFID Reader'), findsOneWidget);
    expect(find.text('Dashboard'), findsWidgets);
    expect(find.byIcon(Icons.bluetooth_searching), findsOneWidget);
  });

  testWidgets('Configuration tab asks to connect when no reader is connected', (
    WidgetTester tester,
  ) async {
    FlutterBluePlusPlatform.instance = FakeFlutterBluePlusPlatform();

    await tester.pumpWidget(const RFIDReaderApp());
    await tester.pump();
    await tester.tap(find.text('Configuration'));
    await tester.pump();

    expect(
      find.textContaining('Connect to a reader on the Dashboard tab'),
      findsOneWidget,
    );
  });

  testWidgets('Live View switch is off and disabled without a reader', (
    WidgetTester tester,
  ) async {
    FlutterBluePlusPlatform.instance = FakeFlutterBluePlusPlatform();

    await tester.pumpWidget(const RFIDReaderApp());
    await tester.pump();
    await tester.tap(find.text('Filter & Graph'));
    await tester.pump();

    expect(find.text('📡 Live View'), findsOneWidget);
    final liveSwitch = tester.widget<Switch>(find.byType(Switch));
    expect(liveSwitch.value, isFalse);
    expect(liveSwitch.onChanged, isNull);
    expect(find.text('No reading yet'), findsNWidgets(2));
  });
}
