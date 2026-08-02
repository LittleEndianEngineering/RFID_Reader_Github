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
}
