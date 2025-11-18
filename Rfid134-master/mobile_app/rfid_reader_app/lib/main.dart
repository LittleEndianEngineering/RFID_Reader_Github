import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:fl_chart/fl_chart.dart';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:async';
import 'dart:ui' as ui;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:flutter/rendering.dart';
import 'package:gallery_saver/gallery_saver.dart';
import 'package:timezone/timezone.dart' as tz;
import 'package:timezone/data/latest_all.dart' as tz_data;

void main() {
  // Initialize timezone data
  tz_data.initializeTimeZones();
  runApp(const RFIDReaderApp());
}

class RFIDReaderApp extends StatelessWidget {
  const RFIDReaderApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'RFID Reader',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.blue,
          brightness: Brightness.light,
        ),
        appBarTheme: const AppBarTheme(
          centerTitle: true,
          elevation: 2,
        ),
        cardTheme: CardThemeData(
          elevation: 2,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          ),
        ),
      ),
      home: const RFIDReaderScreen(),
    );
  }
}

class RFIDReaderScreen extends StatefulWidget {
  const RFIDReaderScreen({super.key});

  @override
  State<RFIDReaderScreen> createState() => _RFIDReaderScreenState();
}

class _RFIDReaderScreenState extends State<RFIDReaderScreen> {
  List<ScanResult> scanResults = [];
  BluetoothDevice? connectedDevice;
  BluetoothCharacteristic? commandCharacteristic;
  BluetoothCharacteristic? responseCharacteristic;
  BluetoothCharacteristic? statusCharacteristic;
  List<String> rfidReadings = [];
  bool isScanning = false;
  bool isConnected = false;
  int _currentIndex = 0;
  final GlobalKey _chartKey = GlobalKey();
  final ScrollController _horizontalScrollController = ScrollController();
  
  // Date/Time filtering (matching dashboard functionality)
  DateTime startDate = DateTime.now().subtract(const Duration(days: 7));
  DateTime endDate = DateTime.now();
  TimeOfDay startTime = const TimeOfDay(hour: 0, minute: 0);
  TimeOfDay endTime = const TimeOfDay(hour: 23, minute: 59);
  String selectedTimezone = 'America/Costa_Rica';
  
  // Parsed readings for filtering
  List<Map<String, dynamic>> parsedReadings = [];
  bool isLoadingData = false;
  
  // Manual read status
  bool isReadingRFID = false;
  String? lastReadResult; // "success" or "no_tag" or null
  Map<String, dynamic>? lastReadData; // The actual reading data if successful
  Timer? _readTimeoutTimer; // Timeout timer for Read Now button

  // BLE Service and Characteristic UUIDs (matching ESP32 firmware)
  static const String SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b";
  static const String COMMAND_CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8";
  static const String RESPONSE_CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a9";
  static const String STATUS_CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26aa";
  static const String DEVICE_NAME = "RFID Reader";

  @override
  void initState() {
    super.initState();
    _initializeBLE();
  }

  void _initializeBLE() {
    // Request Bluetooth permissions
    FlutterBluePlus.adapterState.listen((state) {
      if (state == BluetoothAdapterState.on) {
        print("Bluetooth is on");
      } else {
        print("Bluetooth is off: $state");
      }
    });
  }

  void _startScan() async {
    if (isScanning) return;

    setState(() {
      isScanning = true;
      scanResults.clear();
    });

    try {
      await FlutterBluePlus.startScan(
        timeout: const Duration(seconds: 10),
        withServices: [],
      );

      FlutterBluePlus.scanResults.listen((results) {
        for (ScanResult result in results) {
          if (result.device.name.contains(DEVICE_NAME) || 
              result.advertisementData.localName.contains(DEVICE_NAME)) {
            setState(() {
              if (!scanResults.any((element) => element.device.remoteId == result.device.remoteId)) {
                scanResults.add(result);
              }
            });
          }
        }
      });
    } catch (e) {
      print("Error starting scan: $e");
    } finally {
      setState(() {
        isScanning = false;
      });
    }
  }

  void _connectToDevice(BluetoothDevice device) async {
    try {
      await device.connect();
      
      setState(() {
        connectedDevice = device;
        isConnected = true;
      });

      // Note: iOS doesn't support manual MTU negotiation via requestMtu()
      // iOS automatically negotiates MTU (typically 185 bytes on iOS)
      // The ESP32 will request 512 bytes MTU on connection, and iOS will negotiate automatically
      // We rely on the ESP32's setMTU() call in onConnect() to handle MTU negotiation

      // Discover services
      List<BluetoothService> services = await device.discoverServices();
      
      for (BluetoothService service in services) {
        if (service.uuid.toString().toUpperCase() == SERVICE_UUID.toUpperCase()) {
          for (BluetoothCharacteristic characteristic in service.characteristics) {
            String charUuid = characteristic.uuid.toString().toUpperCase();
            
            if (charUuid == COMMAND_CHAR_UUID.toUpperCase()) {
              commandCharacteristic = characteristic;
            } else if (charUuid == RESPONSE_CHAR_UUID.toUpperCase()) {
              responseCharacteristic = characteristic;
              await characteristic.setNotifyValue(true);
              characteristic.lastValueStream.listen(_handleESP32Response);
            } else if (charUuid == STATUS_CHAR_UUID.toUpperCase()) {
              statusCharacteristic = characteristic;
              await characteristic.setNotifyValue(true);
              characteristic.lastValueStream.listen(_handleESP32Status);
            }
          }
        }
      }
      
      print("Connected to device: ${device.name}");
    } catch (e) {
      print("Error connecting to device: $e");
    }
  }

  // Debug counters for "All Readings" tracking
  int _printResponseCount = 0;
  int _totalReadingsReceived = 0;
  int _lastParsedCount = 0;
  
  // Pagination state for chunked reading retrieval
  int _currentChunkIndex = 0;
  int _totalChunks = 0;
  bool _isFetchingChunks = false;

  void _handleESP32Response(List<int> value) {
    String response = utf8.decode(value);
    
    // Log empty responses to help diagnose BLE issues
    if (response.isEmpty || response.trim().isEmpty) {
      print("⚠️ Received EMPTY ESP32 response (length: ${value.length}) - possible BLE buffer issue");
      return; // Don't process empty responses
    }
    
    // Track "print" command responses
    if (response.contains('---BEGIN_READINGS---') || 
        response.contains('Printing') || 
        response.contains('---END_READINGS---') ||
        (response.startsWith('#') && (response.contains('°C') || response.contains('N/A')))) {
      _printResponseCount++;
      print("📊 [PRINT DEBUG] Response #$_printResponseCount | Length: ${response.length} bytes | Preview: ${response.length > 100 ? response.substring(0, 100) + '...' : response}");
    }
    
    print("🔍 Received ESP32 response: $response (length: ${response.length}, bytes: ${value.length})");
    
    setState(() {
      rfidReadings.add(response);
    });
    
    // Check for error responses that indicate device reset or failure
    if (isReadingRFID && (response.contains('[RTC]') || response.contains('Guru Meditation') || response.contains('Rebooting'))) {
      print("⚠️ Device error detected during read");
      _readTimeoutTimer?.cancel();
      setState(() {
        isReadingRFID = false;
        lastReadResult = "error";
        lastReadData = null;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Device error detected. Check RTC connection and power.'),
          backgroundColor: Colors.red,
          duration: Duration(seconds: 3),
        ),
      );
    }
    
    // Check for manual RFID read results
    if (isReadingRFID) {
      if (response.contains('[RFID] Tag detected and stored') || 
          response.contains('Tag detected and stored')) {
        print("✅ RFID TAG DETECTED!");
        _readTimeoutTimer?.cancel(); // Cancel timeout - we got a response
        setState(() {
          isReadingRFID = false;
          lastReadResult = "success";
        });
        // The actual reading data will come in the next response
      } else if (response.contains('[RFID] No tag detected during window') ||
                 response.contains('No tag detected during window')) {
        print("❌ NO RFID TAG DETECTED");
        _readTimeoutTimer?.cancel(); // Cancel timeout - we got a response
        setState(() {
          isReadingRFID = false;
          lastReadResult = "no_tag";
          lastReadData = null;
        });
      } else if (response.startsWith('#') && (response.contains('°C') || response.contains('N/A')) && lastReadResult == "success") {
        // This is the reading data after a successful tag detection
        // NOTE: The reading is already stored on ESP32 by powerOnAndReadTagWindow()
        // We parse it here for display only - it will appear in "All Readings" when retrieved
        // Handles both temperature values and "N/A" for tags without temperature
        print("📊 PARSING LIVE READING DATA");
        _readTimeoutTimer?.cancel(); // Cancel timeout - we got the reading data
        _parseReadings(response);
        // Extract the reading data from parsedReadings for display
        if (parsedReadings.isNotEmpty) {
          setState(() {
            lastReadData = parsedReadings.last;
            // Clear parsedReadings for manual read (we only want to show the last one)
            // The reading is stored on ESP32, so it will appear in "All Readings"
            parsedReadings.clear();
            parsedReadings.add(lastReadData!);
          });
        }
      }
    }
    
    // Check if this is the start of a new query (clear previous readings)
    // Only clear on ---BEGIN_READINGS--- or Found, NOT on "Printing X stored readings:"
    // because "Printing" comes AFTER ---BEGIN_READINGS--- and would clear already-parsed readings
    // IMPORTANT: For pagination, only clear on first chunk (when not fetching chunks)
    if ((response.contains('---BEGIN_READINGS---') || response.contains('Found')) && !_isFetchingChunks) {
      print("✅ DETECTED NEW QUERY START - clearing previous readings");
      setState(() {
        parsedReadings.clear();
      });
    } else if (response.contains('---BEGIN_READINGS---') && _isFetchingChunks) {
      print("✅ DETECTED BEGIN_READINGS during pagination - NOT clearing (appending to existing ${parsedReadings.length} readings)");
    }
    
    // Check if this is the start of a range response or "print" command response
    if (response.contains('---BEGIN_READINGS---') || response.contains('Found')) {
      print("✅ DETECTED RANGE/PRINT RESPONSE START - calling _parseReadings");
      _lastParsedCount = parsedReadings.length;
      _parseReadings(response);
      print("📊 [PARSE DEBUG] After BEGIN: ${parsedReadings.length} readings (was $_lastParsedCount)");
    } else if (response.contains('---CHUNK_COMPLETE---')) {
      // Chunk completed - automatically request next chunk
      print("✅ DETECTED CHUNK COMPLETE - requesting next chunk");
      _lastParsedCount = parsedReadings.length;
      _parseReadings(response);
      print("📊 [PARSE DEBUG] After CHUNK_COMPLETE: ${parsedReadings.length} readings (was $_lastParsedCount)");
      
      // Request next chunk automatically
      _currentChunkIndex++;
      if (_currentChunkIndex < _totalChunks) {
        print("📥 Requesting next chunk: $_currentChunkIndex/$_totalChunks");
        Future.delayed(const Duration(milliseconds: 500), () {
          // Small delay to ensure previous chunk is fully processed
          _sendCommand('print_chunk $_currentChunkIndex');
        });
      } else {
        print("✅ All chunks received - pagination complete");
        _isFetchingChunks = false;
        _currentChunkIndex = 0;
        _totalChunks = 0;
      }
    } else if (response.contains('---END_READINGS---')) {
      print("✅ DETECTED RANGE/PRINT RESPONSE END - calling _parseReadings");
      _lastParsedCount = parsedReadings.length;
      _parseReadings(response);
      print("📊 [PARSE DEBUG] After END: ${parsedReadings.length} readings (was $_lastParsedCount) | Total responses received: $_printResponseCount");
      
      // Pagination complete - reset state
      _isFetchingChunks = false;
      _currentChunkIndex = 0;
      _totalChunks = 0;
      
      // Reset counter after completion
      _printResponseCount = 0;
      _totalReadingsReceived = 0;
    } else if (response.contains('Printing') && response.contains('stored readings')) {
      // This is the "Printing X stored readings:" line from "print" command
      // Extract the count from the message
      final countMatch = RegExp(r'Printing (\d+) stored readings').firstMatch(response);
      if (countMatch != null) {
        final expectedCount = int.tryParse(countMatch.group(1) ?? '0') ?? 0;
        print("📊 [PRINT DEBUG] ESP32 reports $expectedCount stored readings | Current parsed: ${parsedReadings.length}");
      }
      
      // Check if this is a paginated response (contains chunk info)
      final chunkMatch = RegExp(r'chunk (\d+)/(\d+)').firstMatch(response);
      if (chunkMatch != null) {
        final currentChunk = int.tryParse(chunkMatch.group(1) ?? '0') ?? 0;
        final totalChunks = int.tryParse(chunkMatch.group(2) ?? '0') ?? 0;
        _currentChunkIndex = currentChunk - 1; // Convert to 0-based index
        _totalChunks = totalChunks;
        _isFetchingChunks = true;
        print("📊 [PAGINATION] Detected chunk $currentChunk/$totalChunks | Starting pagination");
      }
      
      print("✅ DETECTED PRINT COMMAND RESPONSE - ready to parse readings");
    } else if (response.contains('Chunk ') && response.contains('/')) {
      // Subsequent chunk header (not first chunk)
      final chunkMatch = RegExp(r'Chunk (\d+)/(\d+)').firstMatch(response);
      if (chunkMatch != null) {
        final currentChunk = int.tryParse(chunkMatch.group(1) ?? '0') ?? 0;
        final totalChunks = int.tryParse(chunkMatch.group(2) ?? '0') ?? 0;
        _currentChunkIndex = currentChunk - 1; // Convert to 0-based index
        _totalChunks = totalChunks;
        print("📊 [PAGINATION] Processing chunk $currentChunk/$totalChunks");
      }
    } else if (response.startsWith('#') && (response.contains('°C') || response.contains('N/A')) && !isReadingRFID) {
      // Individual reading line from "print" or "range" command
      // Count how many readings are in this response
      final readingCount = RegExp(r'#\d+:').allMatches(response).length;
      _totalReadingsReceived += readingCount;
      _lastParsedCount = parsedReadings.length;
      print("✅ DETECTED INDIVIDUAL READING - calling _parseReadings | Readings in this response: $readingCount | Total received so far: $_totalReadingsReceived | Current parsed: $_lastParsedCount");
      _parseReadings(response);
      print("📊 [PARSE DEBUG] After parsing: ${parsedReadings.length} readings (added ${parsedReadings.length - _lastParsedCount})");
    } else if (response.startsWith('#') && (response.contains('°C') || response.contains('N/A')) && isReadingRFID) {
      // Individual reading from "Read Now" - already handled above, skip here
      print("⏭️ Skipping individual reading parsing (already handled for Read Now)");
    } else {
      print("❌ Not a reading response - skipping _parseReadings");
    }
  }

  void _handleESP32Status(List<int> value) {
    String status = utf8.decode(value);
    print("Received ESP32 status: $status");
  }

  void _sendCommand(String command) {
    if (commandCharacteristic != null) {
      // Clear previous readings when starting a new query
      // NOTE: For 'print' (All Readings), we clear to get fresh data from ESP32
      // The ESP32 stores all readings including those from "Read Now", so they will be included
      // NOTE: For pagination, only clear on first chunk (print), not on subsequent chunks (print_chunk)
      if (command == 'print' || command.startsWith('range ')) {
        print("🧹 Clearing previous readings for new query: $command");
        setState(() {
          parsedReadings.clear();
        });
        // Reset debug counters for new query
        _printResponseCount = 0;
        _totalReadingsReceived = 0;
        _lastParsedCount = 0;
        // Reset pagination state
        _currentChunkIndex = 0;
        _totalChunks = 0;
        _isFetchingChunks = false;
        print("📊 [PRINT DEBUG] Reset counters for new 'print' query");
      } else if (command.startsWith('print_chunk ')) {
        // Pagination: don't clear readings, just append to existing list
        print("📥 Requesting chunk: $command (will append to existing ${parsedReadings.length} readings)");
      }
      // NOTE: For 'readnow', we don't clear parsedReadings - the new reading will be added
      // and will appear in "All Readings" since it's stored on ESP32
      
      List<int> bytes = utf8.encode(command);
      commandCharacteristic!.write(bytes);
      print("Sent command: $command");
    }
  }

  void _triggerManualRead() {
    if (!isConnected || isReadingRFID) return;
    
    setState(() {
      isReadingRFID = true;
      lastReadResult = null;
      lastReadData = null;
      parsedReadings.clear(); // Clear previous readings for manual read display
      // NOTE: The reading will be stored on ESP32 and will appear in "All Readings"
    });
    
    // Start timeout timer (15 seconds - enough for RFID read window + processing)
    _readTimeoutTimer?.cancel();
    _readTimeoutTimer = Timer(const Duration(seconds: 15), () {
      if (isReadingRFID) {
        print("⏱️ Read Now timeout - no response received");
        setState(() {
          isReadingRFID = false;
          lastReadResult = "timeout";
          lastReadData = null;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Read timeout: No response from device. Device may have reset.'),
            backgroundColor: Colors.orange,
            duration: Duration(seconds: 3),
          ),
        );
      }
    });
    
    _sendCommand('readnow');
  }

  void _disconnect() async {
    if (connectedDevice != null) {
      await connectedDevice!.disconnect();
      setState(() {
        connectedDevice = null;
        isConnected = false;
        commandCharacteristic = null;
        responseCharacteristic = null;
        statusCharacteristic = null;
        rfidReadings.clear();
      });
    }
  }

  void _clearResponses() {
    setState(() {
      rfidReadings.clear();
    });
  }

  Future<void> _exportToCSV() async {
    if (parsedReadings.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No data to export')),
      );
      return;
    }

    try {
      // Create CSV content
      String csvContent = 'Reading #,Timestamp,Country,Tag ID,Temperature (°C)\n';
      for (var reading in parsedReadings) {
        final tempStr = reading['temperature'] != null
            ? (reading['temperature'] as double).toStringAsFixed(2)
            : 'N/A';
        csvContent += '${reading['readingNum']},${reading['timestamp']},${reading['country']},${reading['tag']},$tempStr\n';
      }

      // iOS: Use application documents directory (cache directory isn't shareable)
      final directory = await getApplicationDocumentsDirectory();
      final fileName = 'rfid_readings_${DateTime.now().millisecondsSinceEpoch}.csv';
      final filePath = '${directory.path}/$fileName';
      final file = File(filePath);
      
      // Write file and ensure it exists
      await file.writeAsString(csvContent);
      
      // Verify file exists and is readable
      if (!await file.exists()) {
        throw Exception('File was not created successfully');
      }

      // Get screen size for sharePositionOrigin (required on iOS/iPadOS)
      final mediaQuery = MediaQuery.of(context);
      final screenSize = mediaQuery.size;
      final screenWidth = screenSize.width;
      final screenHeight = mediaQuery.padding.top + 56; // Approximate button position (top-right)
      
      // Use a small rectangle near the top-right corner where the button is
      final shareRect = Rect.fromLTWH(
        screenWidth - 100, // Near right edge
        screenHeight, // Near top
        80, // Button width
        40, // Button height
      );

      // Share the file with position for iOS/iPadOS compatibility
      await Share.shareXFiles(
        [XFile(filePath, name: fileName)],
        sharePositionOrigin: shareRect,
      );
      
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('CSV file exported successfully')),
      );
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Export failed: $e')),
      );
    }
  }

  Future<void> _saveChartAsImage() async {
    if (parsedReadings.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No chart data to save')),
      );
      return;
    }

    try {
      // Capture the chart widget as an image
      RenderRepaintBoundary boundary = _chartKey.currentContext!.findRenderObject() as RenderRepaintBoundary;
      ui.Image chartImage = await boundary.toImage(pixelRatio: 3.0);
      
      // Add padding around the image to prevent cropping
      // Increased padding significantly to prevent axis label cropping
      const padding = 200.0; // 66.7px padding * 3 (pixelRatio) - increased for better margins
      const titleHeight = 120.0; // Space for title and subtitle
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      
      // Format date/time range for subtitle
      final startDateTime = DateTime(startDate.year, startDate.month, startDate.day, startTime.hour, startTime.minute);
      final endDateTime = DateTime(endDate.year, endDate.month, endDate.day, endTime.hour, endTime.minute);
      final dateFormat = 'yyyy-MM-dd';
      final timeFormat = 'HH:mm';
      final startDateStr = '${startDateTime.year}-${startDateTime.month.toString().padLeft(2, '0')}-${startDateTime.day.toString().padLeft(2, '0')}';
      final startTimeStr = '${startDateTime.hour.toString().padLeft(2, '0')}:${startDateTime.minute.toString().padLeft(2, '0')}';
      final endDateStr = '${endDateTime.year}-${endDateTime.month.toString().padLeft(2, '0')}-${endDateTime.day.toString().padLeft(2, '0')}';
      final endTimeStr = '${endDateTime.hour.toString().padLeft(2, '0')}:${endDateTime.minute.toString().padLeft(2, '0')}';
      final subtitleText = 'From: $startDateStr $startTimeStr  To: $endDateStr $endTimeStr';
      
      // Calculate final image size
      final finalWidth = chartImage.width + padding * 2;
      final finalHeight = chartImage.height + padding * 2 + titleHeight;
      
      // Draw white background
      final backgroundPaint = Paint()..color = Colors.white;
      canvas.drawRect(
        Rect.fromLTWH(0, 0, finalWidth, finalHeight),
        backgroundPaint,
      );
      
      // Draw title "Temperature Chart"
      final titlePainter = TextPainter(
        text: TextSpan(
          text: 'Temperature Chart',
          style: TextStyle(
            color: Colors.black,
            fontSize: 32.0,
            fontWeight: FontWeight.bold,
          ),
        ),
        textDirection: TextDirection.ltr,
      );
      titlePainter.layout();
      final titleY = padding / 2 - 20;
      titlePainter.paint(
        canvas,
        Offset((finalWidth - titlePainter.width) / 2, titleY),
      );
      
      // Draw subtitle with date/time range
      final subtitlePainter = TextPainter(
        text: TextSpan(
          text: subtitleText,
          style: TextStyle(
            color: Colors.grey[700]!,
            fontSize: 18.0,
            fontWeight: FontWeight.normal,
          ),
        ),
        textDirection: TextDirection.ltr,
      );
      subtitlePainter.layout();
      final subtitleY = titleY + titlePainter.height + 10;
      subtitlePainter.paint(
        canvas,
        Offset((finalWidth - subtitlePainter.width) / 2, subtitleY),
      );
      
      // Draw the chart image with padding (below title and subtitle)
      canvas.drawImage(
        chartImage,
        Offset(padding, padding + titleHeight),
        Paint(),
      );
      
      // Convert to image
      final picture = recorder.endRecording();
      final paddedImage = await picture.toImage(
        finalWidth.toInt(),
        finalHeight.toInt(),
      );
      
      // Convert to PNG bytes
      ByteData? byteData = await paddedImage.toByteData(format: ui.ImageByteFormat.png);
      Uint8List pngBytes = byteData!.buffer.asUint8List();
      
      // Dispose text painters
      titlePainter.dispose();
      subtitlePainter.dispose();

      // Save to temporary directory first
      final directory = await getTemporaryDirectory();
      final fileName = 'temperature_chart_${DateTime.now().millisecondsSinceEpoch}.png';
      final filePath = '${directory.path}/$fileName';
      final file = File(filePath);
      
      // Write file and ensure it exists
      await file.writeAsBytes(pngBytes);
      
      // Dispose images to free memory
      chartImage.dispose();
      paddedImage.dispose();
      
      // Verify file exists and is readable
      if (!await file.exists()) {
        throw Exception('File was not created successfully');
      }

      // Save to gallery instead of sharing
      final success = await GallerySaver.saveImage(filePath, albumName: 'RFID Reader');
      
      if (success == true) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Chart saved to gallery successfully')),
        );
      } else {
        throw Exception('Failed to save to gallery');
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Save failed: $e')),
      );
    }
  }

  // Helper functions for date/time filtering (based on dashboard functionality)
  int _getEpochFromDateTime(DateTime date, TimeOfDay time) {
    final combined = DateTime(date.year, date.month, date.day, time.hour, time.minute);
    return combined.millisecondsSinceEpoch ~/ 1000; // Convert to Unix timestamp
  }

  // Convert UTC timestamp string to selected timezone for display
  String _convertUtcToTimezone(String utcTimestamp) {
    try {
      // Parse the UTC timestamp (format: "2025-10-22 4:29:52")
      // Fix timestamp format for DateTime parsing
      String fixedTimestamp = utcTimestamp;
      if (fixedTimestamp.contains(' ')) {
        List<String> parts = fixedTimestamp.split(' ');
        if (parts.length == 2) {
          String datePart = parts[0];
          String timePart = parts[1];
          List<String> timeComponents = timePart.split(':');
          if (timeComponents.length == 3) {
            String hour = timeComponents[0].padLeft(2, '0');
            String minute = timeComponents[1].padLeft(2, '0');
            String second = timeComponents[2].padLeft(2, '0');
            fixedTimestamp = '$datePart $hour:$minute:$second';
          }
        }
      }
      
      // Parse as UTC DateTime
      final utcDateTime = DateTime.parse(fixedTimestamp.replaceAll(' ', 'T') + 'Z');
      
      // Convert to selected timezone
      final timeZoneLocation = tz.getLocation(selectedTimezone);
      final localDateTime = tz.TZDateTime.from(utcDateTime, timeZoneLocation);
      
      // Format back to string (format: "2025-10-22 04:29:52")
      final year = localDateTime.year.toString();
      final month = localDateTime.month.toString().padLeft(2, '0');
      final day = localDateTime.day.toString().padLeft(2, '0');
      final hour = localDateTime.hour.toString().padLeft(2, '0');
      final minute = localDateTime.minute.toString().padLeft(2, '0');
      final second = localDateTime.second.toString().padLeft(2, '0');
      
      return '$year-$month-$day $hour:$minute:$second';
    } catch (e) {
      print("❌ Error converting UTC to timezone: $e");
      return utcTimestamp; // Return original if conversion fails
    }
  }

  void _parseReadings(String response) {
    final initialCount = parsedReadings.length;
    print("🔧 ENTERING _parseReadings | Initial count: $initialCount | Response length: ${response.length} chars");
    
    // Handle individual reading responses (format: #X: timestamp, country, tag, temperature)
    // IMPORTANT: Handle concatenated readings (multiple #X: patterns in one response)
    // Also handles "N/A" for temperature when sensor is not enabled
    if (response.contains('#') && (response.contains('°C') || response.contains('N/A'))) {
      print("🔧 Processing reading(s): '${response.length > 200 ? response.substring(0, 200) + '...' : response}'");
      
      // Use flexible regex to find ALL readings in the response (handles concatenated readings)
      // Pattern: #(\d+):\s*([^,]+),\s*(\d+),\s*(\d+),\s*((?:[\d.]+°C|N/A))
      // This matches either a temperature value with °C or "N/A"
      final flexibleRegex = RegExp(r'#(\d+):\s*([^,]+),\s*(\d+),\s*(\d+),\s*((?:[\d.]+°C|N/A))');
      final allMatches = flexibleRegex.allMatches(response);
      
      print("🔧 Found ${allMatches.length} reading(s) in response | Initial parsedReadings: $initialCount");
      
      if (allMatches.isEmpty) {
        print("❌ No readings found in response: '$response'");
        return;
      }
      
      // Collect all valid readings from this batch before updating UI
      // This is more efficient and ensures batched readings (with newlines) are handled correctly
      List<Map<String, dynamic>> newReadings = [];
      
      // Process each match (handles concatenated readings and batched readings with newlines)
      for (var match in allMatches) {
        try {
          final readingNum = match.group(1)!;
          final timestamp = match.group(2)!.trim();
          final country = match.group(3)!;
          final tag = match.group(4)!;
          final tempStr = match.group(5)!;
          
          // Check if temperature is "N/A" or a numeric value
          double? temperature;
          if (tempStr == 'N/A') {
            temperature = null; // null indicates temperature not available
            print("⚠️ Temperature not available for reading #$readingNum");
          } else {
            // Extract numeric value (remove °C)
            final tempValue = tempStr.replaceAll('°C', '');
            temperature = double.tryParse(tempValue);
            if (temperature == null) {
              print("⚠️ Could not parse temperature '$tempStr' for reading #$readingNum");
              temperature = null;
            }
          }
          
          // Validate timestamp - must be RTC format (YYYY-MM-DD HH:MM:SS), not ms timestamp
          // RTC timestamps start with a year (4 digits), ms timestamps are just numbers
          if (!timestamp.contains('-') || !timestamp.contains(':')) {
            print("⚠️ Skipping reading #$readingNum: Invalid timestamp format (likely ms timestamp): '$timestamp'");
            continue; // Skip this reading but continue with others
          }
          
          // Check if timestamp looks like RTC format (YYYY-MM-DD HH:MM:SS)
          // Allow single-digit hours, minutes, and seconds (they'll be padded later)
          final rtcPattern = RegExp(r'^\d{4}-\d{1,2}-\d{1,2}\s\d{1,2}:\d{1,2}:\d{1,2}');
          if (!rtcPattern.hasMatch(timestamp)) {
            print("⚠️ Skipping reading #$readingNum: Timestamp doesn't match RTC format: '$timestamp'");
            continue; // Skip this reading but continue with others
          }
          
          if (temperature != null) {
            print("✅ PARSED READING: #$readingNum, $timestamp, $temperature°C");
          } else {
            print("✅ PARSED READING: #$readingNum, $timestamp, N/A");
          }
          
          // Fix timestamp format for DateTime parsing (add leading zeros)
          String fixedTimestamp = timestamp;
          if (fixedTimestamp.contains(' ')) {
            List<String> parts = fixedTimestamp.split(' ');
            if (parts.length == 2) {
              String datePart = parts[0];
              String timePart = parts[1];
              List<String> timeComponents = timePart.split(':');
              if (timeComponents.length == 3) {
                String hour = timeComponents[0].padLeft(2, '0');
                String minute = timeComponents[1].padLeft(2, '0');
                String second = timeComponents[2].padLeft(2, '0');
                fixedTimestamp = '$datePart $hour:$minute:$second';
              }
            }
          }
          
          print("🔧 Fixed timestamp: $fixedTimestamp");
          
          // Convert UTC timestamp to selected timezone for display
          final displayTimestamp = _convertUtcToTimezone(fixedTimestamp);
          
          // Parse UTC DateTime for sorting and chart (keep as UTC internally)
          final utcDateTime = DateTime.parse(fixedTimestamp.replaceAll(' ', 'T') + 'Z');
          
          // Check for duplicates before adding (same reading number, timestamp, country, and tag)
          bool isDuplicate = parsedReadings.any((existing) =>
            existing['readingNum'] == readingNum &&
            existing['country'] == country &&
            existing['tag'] == tag &&
            (existing['dateTime'] as DateTime).difference(utcDateTime).inSeconds.abs() < 1 // Same timestamp (within 1 second)
          );
          
          // Also check for duplicates within the current batch
          if (!isDuplicate) {
            isDuplicate = newReadings.any((newReading) =>
              newReading['readingNum'] == readingNum &&
              newReading['country'] == country &&
              newReading['tag'] == tag &&
              (newReading['dateTime'] as DateTime).difference(utcDateTime).inSeconds.abs() < 1
            );
          }
          
          if (isDuplicate) {
            print("⚠️ DUPLICATE READING DETECTED - skipping: #$readingNum, $timestamp, $country, $tag");
            continue; // Skip duplicate reading
          }
          
          // Add to newReadings list (will be added to parsedReadings in one setState call)
          newReadings.add({
            'readingNum': readingNum,
            'timestamp': displayTimestamp, // Display in selected timezone
            'country': country,
            'tag': tag,
            'temperature': temperature, // Can be null for N/A
            'dateTime': utcDateTime, // Keep UTC for sorting
          });
        } catch (e) {
          print("❌ Error parsing reading: $e");
          // Continue with next reading even if this one fails
          continue;
        }
      }
      
      // Add all new readings from this batch in one setState call (more efficient)
      if (newReadings.isNotEmpty) {
        setState(() {
          parsedReadings.addAll(newReadings);
        });
        print("🎯 ADDED ${newReadings.length} reading(s) from batch to parsedReadings. Total: ${parsedReadings.length} (was $initialCount)");
      }
      return;
    }
    
    // Handle range responses (like dashboard does)
    print("🔧 Processing range response with ${response.length} characters | Initial parsedReadings: $initialCount");
    
    // If this is just "---BEGIN_READINGS---", clear existing readings (start of new query)
    // IMPORTANT: For pagination, only clear on first chunk (when not fetching chunks)
    if ((response.trim() == '---BEGIN_READINGS---' || (response.contains('---BEGIN_READINGS---') && !response.contains('#'))) && !_isFetchingChunks) {
      print("✅ Found BEGIN_READINGS marker - clearing existing readings for new query (was $initialCount)");
      setState(() {
        parsedReadings.clear();
      });
      return; // Don't process further - individual readings will come separately
    } else if ((response.trim() == '---BEGIN_READINGS---' || (response.contains('---BEGIN_READINGS---') && !response.contains('#'))) && _isFetchingChunks) {
      print("✅ Found BEGIN_READINGS marker during pagination - NOT clearing (appending to existing $initialCount readings)");
      return; // Don't process further - individual readings will come separately
    }
    
    // If this is just "---CHUNK_COMPLETE---", don't do anything (readings already parsed, handled in _handleESP32Response)
    if (response.trim() == '---CHUNK_COMPLETE---' || (response.contains('---CHUNK_COMPLETE---') && !response.contains('#'))) {
      print("✅ Found CHUNK_COMPLETE marker - chunk complete, keeping existing ${parsedReadings.length} readings (was $initialCount)");
      return; // Don't process further - chunk already parsed, next chunk will be requested automatically
    }
    
    // If this is just "---END_READINGS---", don't do anything (readings already parsed)
    if (response.trim() == '---END_READINGS---' || (response.contains('---END_READINGS---') && !response.contains('#'))) {
      print("✅ Found END_READINGS marker - query complete, keeping existing ${parsedReadings.length} readings (was $initialCount)");
      return; // Don't process further - all readings already parsed
    }
    
    // Check if this response contains readings (batched or individual)
    // Batched readings from range queries will have multiple #X: patterns separated by newlines
    if (response.contains('#') && (response.contains('°C') || response.contains('N/A'))) {
      // Use the same efficient batching approach as individual readings
      // This handles both single readings and batched readings (with newlines) from range queries
      print("🔧 Processing batched range readings using efficient regex matching");
      
      // Use flexible regex to find ALL readings in the entire response (handles newlines)
      final flexibleRegex = RegExp(r'#(\d+):\s*([^,]+),\s*(\d+),\s*(\d+),\s*((?:[\d.]+°C|N/A))');
      final allMatches = flexibleRegex.allMatches(response);
      
      print("🔧 Found ${allMatches.length} reading(s) in range response | Initial parsedReadings: $initialCount");
      
      if (allMatches.isEmpty) {
        print("❌ No readings found in range response: '$response'");
        return;
      }
      
      List<Map<String, dynamic>> newReadings = [];
      
      // Process each match (handles batched readings with newlines)
      for (var match in allMatches) {
        try {
          final readingNum = match.group(1)!;
          final timestamp = match.group(2)!.trim();
          final country = match.group(3)!;
          final tag = match.group(4)!;
          final tempStr = match.group(5)!;
          
          // Check if temperature is "N/A" or a numeric value
          double? temperature;
          if (tempStr == 'N/A') {
            temperature = null; // null indicates temperature not available
            print("⚠️ Temperature not available for reading #$readingNum");
          } else {
            // Extract numeric value (remove °C)
            final tempValue = tempStr.replaceAll('°C', '');
            temperature = double.tryParse(tempValue);
            if (temperature == null) {
              print("⚠️ Could not parse temperature '$tempStr' for reading #$readingNum");
              temperature = null;
            }
          }
          
          // Validate timestamp - must be RTC format (YYYY-MM-DD HH:MM:SS), not ms timestamp
          if (!timestamp.contains('-') || !timestamp.contains(':')) {
            print("⚠️ Skipping reading #$readingNum: Invalid timestamp format (likely ms timestamp): '$timestamp'");
            continue; // Skip this reading but continue with others
          }
          
          // Check if timestamp looks like RTC format (YYYY-MM-DD HH:MM:SS)
          // Allow single-digit hours, minutes, and seconds (they'll be padded later)
          final rtcPattern = RegExp(r'^\d{4}-\d{1,2}-\d{1,2}\s\d{1,2}:\d{1,2}:\d{1,2}');
          if (!rtcPattern.hasMatch(timestamp)) {
            print("⚠️ Skipping reading #$readingNum: Timestamp doesn't match RTC format: '$timestamp'");
            continue; // Skip this reading but continue with others
          }
          
          if (temperature != null) {
            print("✅ PARSED READING: #$readingNum, $timestamp, $temperature°C");
          } else {
            print("✅ PARSED READING: #$readingNum, $timestamp, N/A");
          }
          
          // Fix timestamp format for DateTime parsing (add leading zeros)
          String fixedTimestamp = timestamp;
          if (fixedTimestamp.contains(' ')) {
            List<String> parts = fixedTimestamp.split(' ');
            if (parts.length == 2) {
              String datePart = parts[0];
              String timePart = parts[1];
              List<String> timeComponents = timePart.split(':');
              if (timeComponents.length == 3) {
                String hour = timeComponents[0].padLeft(2, '0');
                String minute = timeComponents[1].padLeft(2, '0');
                String second = timeComponents[2].padLeft(2, '0');
                fixedTimestamp = '$datePart $hour:$minute:$second';
              }
            }
          }
          
          // Convert UTC timestamp to selected timezone for display
          final displayTimestamp = _convertUtcToTimezone(fixedTimestamp);
          
          // Parse UTC DateTime for sorting and chart (keep as UTC internally)
          final utcDateTime = DateTime.parse(fixedTimestamp.replaceAll(' ', 'T') + 'Z');
          
          // Check for duplicates before adding
          bool isDuplicate = parsedReadings.any((existing) =>
            existing['readingNum'] == readingNum &&
            existing['country'] == country &&
            existing['tag'] == tag &&
            (existing['dateTime'] as DateTime).difference(utcDateTime).inSeconds.abs() < 1
          );
          
          // Also check for duplicates within the current batch
          if (!isDuplicate) {
            isDuplicate = newReadings.any((newReading) =>
              newReading['readingNum'] == readingNum &&
              newReading['country'] == country &&
              newReading['tag'] == tag &&
              (newReading['dateTime'] as DateTime).difference(utcDateTime).inSeconds.abs() < 1
            );
          }
          
          if (isDuplicate) {
            print("⚠️ DUPLICATE READING DETECTED in range response - skipping: #$readingNum, $timestamp, $country, $tag");
            continue;
          }
          
          newReadings.add({
            'readingNum': readingNum,
            'timestamp': displayTimestamp, // Display in selected timezone
            'country': country,
            'tag': tag,
            'temperature': temperature, // Can be null for N/A
            'dateTime': utcDateTime, // Keep UTC for sorting
          });
        } catch (e) {
          print("❌ Error parsing reading: $e");
          // Continue with next reading even if this one fails
          continue;
        }
      }
      
      // Add all new readings from this batch in one setState call (more efficient)
      if (newReadings.isNotEmpty) {
        setState(() {
          // Filter out duplicates before appending
          final filteredNewReadings = newReadings.where((newReading) {
            bool isDuplicate = parsedReadings.any((existing) =>
              existing['readingNum'] == newReading['readingNum'] &&
              existing['country'] == newReading['country'] &&
              existing['tag'] == newReading['tag'] &&
              (existing['dateTime'] as DateTime).difference(newReading['dateTime'] as DateTime).inSeconds.abs() < 1
            );
            if (isDuplicate) {
              print("⚠️ DUPLICATE READING DETECTED in range batch - skipping: #${newReading['readingNum']}, ${newReading['timestamp']}, ${newReading['country']}, ${newReading['tag']}");
            }
            return !isDuplicate;
          }).toList();
          
          final beforeAdd = parsedReadings.length;
          parsedReadings.addAll(filteredNewReadings);
          print("📊 [PARSE DEBUG] Added ${filteredNewReadings.length} new readings from range batch (${newReadings.length - filteredNewReadings.length} duplicates skipped) | Total: ${parsedReadings.length} (was $beforeAdd)");
        });
      }
      return; // Exit early since we processed batched readings
    }
    
    // Fallback: Handle range responses line by line (for non-batched or legacy format)
    final lines = response.split('\n');
    bool inBlock = false;
    List<Map<String, dynamic>> newReadings = [];
    
    for (String line in lines) {
      if (line.contains('---BEGIN_READINGS---')) {
        inBlock = true;
        print("✅ Found BEGIN_READINGS marker - entering block");
        continue;
      }
      if (line.contains('---END_READINGS---')) {
        inBlock = false;
        print("✅ Found END_READINGS marker - exiting block");
        continue;
      }
      if (inBlock && line.trim().isNotEmpty) {
        print("🔧 Processing line in block: '$line'");
        
        // Handle concatenated readings (multiple #X: patterns in one line)
        // Use flexible regex to find ALL readings in the line
        // Pattern matches either temperature with °C or "N/A"
        final flexibleRegex = RegExp(r'#(\d+):\s*([^,]+),\s*(\d+),\s*(\d+),\s*((?:[\d.]+°C|N/A))');
        final allMatches = flexibleRegex.allMatches(line);
        
        if (allMatches.isEmpty) {
          print("❌ Line did not match regex: '$line'");
          continue;
        }
        
        // Process each match (handles concatenated readings)
        for (var match in allMatches) {
          try {
            final readingNum = match.group(1)!;
            final timestamp = match.group(2)!.trim();
            final country = match.group(3)!;
            final tag = match.group(4)!;
            final tempStr = match.group(5)!;
            
            // Check if temperature is "N/A" or a numeric value
            double? temperature;
            if (tempStr == 'N/A') {
              temperature = null; // null indicates temperature not available
              print("⚠️ Temperature not available for reading #$readingNum");
            } else {
              // Extract numeric value (remove °C)
              final tempValue = tempStr.replaceAll('°C', '');
              temperature = double.tryParse(tempValue);
              if (temperature == null) {
                print("⚠️ Could not parse temperature '$tempStr' for reading #$readingNum");
                temperature = null;
              }
            }
            
            // Validate timestamp - must be RTC format (YYYY-MM-DD HH:MM:SS), not ms timestamp
            if (!timestamp.contains('-') || !timestamp.contains(':')) {
              print("⚠️ Skipping reading #$readingNum: Invalid timestamp format (likely ms timestamp): '$timestamp'");
              continue; // Skip this reading but continue with others
            }
            
            // Check if timestamp looks like RTC format (YYYY-MM-DD HH:MM:SS)
            // Allow single-digit hours, minutes, and seconds (they'll be padded later)
            final rtcPattern = RegExp(r'^\d{4}-\d{1,2}-\d{1,2}\s\d{1,2}:\d{1,2}:\d{1,2}');
            if (!rtcPattern.hasMatch(timestamp)) {
              print("⚠️ Skipping reading #$readingNum: Timestamp doesn't match RTC format: '$timestamp'");
              continue; // Skip this reading but continue with others
            }
            
            if (temperature != null) {
              print("✅ PARSED READING: #$readingNum, $timestamp, $temperature°C");
            } else {
              print("✅ PARSED READING: #$readingNum, $timestamp, N/A");
            }
            
            // Fix timestamp format for DateTime parsing (add leading zeros)
            String fixedTimestamp = timestamp;
            if (fixedTimestamp.contains(' ')) {
              List<String> parts = fixedTimestamp.split(' ');
              if (parts.length == 2) {
                String datePart = parts[0];
                String timePart = parts[1];
                List<String> timeComponents = timePart.split(':');
                if (timeComponents.length == 3) {
                  String hour = timeComponents[0].padLeft(2, '0');
                  String minute = timeComponents[1].padLeft(2, '0');
                  String second = timeComponents[2].padLeft(2, '0');
                  fixedTimestamp = '$datePart $hour:$minute:$second';
                }
              }
            }
            
            // Convert UTC timestamp to selected timezone for display
            final displayTimestamp = _convertUtcToTimezone(fixedTimestamp);
            
            // Parse UTC DateTime for sorting and chart (keep as UTC internally)
            final utcDateTime = DateTime.parse(fixedTimestamp.replaceAll(' ', 'T') + 'Z');
            
            newReadings.add({
              'readingNum': readingNum,
              'timestamp': displayTimestamp, // Display in selected timezone
              'country': country,
              'tag': tag,
              'temperature': temperature, // Can be null for N/A
              'dateTime': utcDateTime, // Keep UTC for sorting
            });
          } catch (e) {
            print("❌ Error parsing reading: $e");
            // Continue with next reading even if this one fails
            continue;
          }
        }
      }
    }
    
    // Only update if we found new readings AND we're processing a multi-line response
    // Don't overwrite if this is just a marker line (BEGIN/END) without actual readings
    if (newReadings.isNotEmpty) {
      setState(() {
        // Append new readings instead of replacing (for multi-line responses)
        // But if this is a fresh range response, replace to avoid duplicates
        if (response.contains('---BEGIN_READINGS---') && !response.contains('---END_READINGS---')) {
          // This is the start of a new range - replace existing readings
          parsedReadings = newReadings;
          print("📊 [PARSE DEBUG] Replaced with ${newReadings.length} readings (was $initialCount)");
        } else {
          // This is continuation or end - filter out duplicates before appending
          final filteredNewReadings = newReadings.where((newReading) {
            bool isDuplicate = parsedReadings.any((existing) =>
              existing['readingNum'] == newReading['readingNum'] &&
              existing['country'] == newReading['country'] &&
              existing['tag'] == newReading['tag'] &&
              (existing['dateTime'] as DateTime).difference(newReading['dateTime'] as DateTime).inSeconds.abs() < 1
            );
            if (isDuplicate) {
              print("⚠️ DUPLICATE READING DETECTED in range response - skipping: #${newReading['readingNum']}, ${newReading['timestamp']}, ${newReading['country']}, ${newReading['tag']}");
            }
            return !isDuplicate;
          }).toList();
          
          final beforeAdd = parsedReadings.length;
          parsedReadings.addAll(filteredNewReadings);
          print("📊 [PARSE DEBUG] Added ${filteredNewReadings.length} new readings (${newReadings.length - filteredNewReadings.length} duplicates skipped) | Total: ${parsedReadings.length} (was $beforeAdd)");
        }
        print("🎯 UPDATED parsedReadings with ${parsedReadings.length} total readings (added ${newReadings.length} from range response, was $initialCount)");
      });
    } else {
      // No new readings found - don't overwrite existing parsedReadings
      // This prevents "---END_READINGS---" from wiping out already-parsed readings
      print("⚠️ No new readings found in range response - keeping existing ${parsedReadings.length} readings (was $initialCount)");
    }
  }

  void _retrieveFilteredData() async {
    if (!isConnected) return;
    
    setState(() {
      isLoadingData = true;
      parsedReadings.clear(); // Clear existing readings before new query
      print("🧹 Cleared parsedReadings before new range query");
    });
    
    try {
      // Get the selected timezone location
      final timeZoneLocation = tz.getLocation(selectedTimezone);
      
      // Create DateTime objects in the selected timezone
      final startLocalDateTime = tz.TZDateTime(
        timeZoneLocation,
        startDate.year,
        startDate.month,
        startDate.day,
        startTime.hour,
        startTime.minute,
      );
      
      final endLocalDateTime = tz.TZDateTime(
        timeZoneLocation,
        endDate.year,
        endDate.month,
        endDate.day,
        endTime.hour,
        endTime.minute,
      );
      
      // Convert to UTC for the ESP32 (which stores readings in UTC)
      final startUtcDateTime = tz.TZDateTime.from(startLocalDateTime, tz.UTC);
      final endUtcDateTime = tz.TZDateTime.from(endLocalDateTime, tz.UTC);
      
      // Convert to Unix epoch (UTC)
      final startEpoch = startUtcDateTime.millisecondsSinceEpoch ~/ 1000;
      final endEpoch = endUtcDateTime.millisecondsSinceEpoch ~/ 1000;
      
      print("🕐 Timezone conversion: $selectedTimezone");
      print("🕐 Start: ${startLocalDateTime.toString()} (local) -> ${startUtcDateTime.toString()} (UTC) -> $startEpoch");
      print("🕐 End: ${endLocalDateTime.toString()} (local) -> ${endUtcDateTime.toString()} (UTC) -> $endEpoch");
      
      // Send range command to ESP32
      final command = 'range $startEpoch $endEpoch';
      _sendCommand(command);
    } catch (e) {
      print("❌ Error converting timezone: $e");
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Timezone conversion error: $e')),
      );
    }
    
    setState(() {
      isLoadingData = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        toolbarHeight: 80,
        flexibleSpace: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                Colors.grey[800]!,
                Colors.grey[700]!,
              ],
            ),
            border: Border(
              bottom: BorderSide(
                color: Colors.grey[600]!,
                width: 1,
              ),
            ),
          ),
          child: SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 12.0),
              child: Row(
                children: [
                  // Icon section - modern, no shadow, white color
                  Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(14),
                      color: Colors.transparent,
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(14),
                      child: ColorFiltered(
                        colorFilter: const ColorFilter.mode(
                          Colors.white,
                          BlendMode.srcIn,
                        ),
                        child: Image.asset(
                          'assets/images/EB_icon.png',
                          fit: BoxFit.contain,
                          errorBuilder: (context, error, stackTrace) {
                            return Container(
                              color: Colors.transparent,
                              child: const Icon(
                                Icons.business,
                                size: 28,
                                color: Colors.white,
                              ),
                            );
                          },
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  // Title section
                  Expanded(
        child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Text(
                          'Implant RFID Reader',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w600,
                            color: Colors.white,
                            letterSpacing: -0.5,
                          ),
                        ),
                        const SizedBox(height: 2),
            Text(
                          'Multi-Button Dashboard',
                          style: TextStyle(
                            fontSize: 13,
                            color: Colors.grey[300],
                            fontWeight: FontWeight.w400,
                            letterSpacing: 0.2,
                          ),
            ),
          ],
        ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
      body: _getCurrentTab(),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        type: BottomNavigationBarType.fixed,
        backgroundColor: Colors.grey[800],
        selectedItemColor: Colors.white,
        unselectedItemColor: Colors.grey[400],
        selectedLabelStyle: const TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w600,
        ),
        unselectedLabelStyle: TextStyle(
          color: Colors.grey[400],
        ),
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.dashboard),
            label: 'Dashboard',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.filter_list),
            label: 'Filter & Graph',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.info),
            label: 'About',
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: isConnected ? _disconnect : _startScan,
        tooltip: isConnected ? 'Disconnect' : 'Scan for devices',
        child: Icon(isConnected ? Icons.bluetooth_disabled : Icons.bluetooth_searching),
      ),
    );
  }

  Widget _getCurrentTab() {
    switch (_currentIndex) {
      case 0:
        return _buildDashboardTab();
      case 1:
        return _buildFilterGraphTab();
      case 2:
        return _buildAboutTab();
      default:
        return _buildDashboardTab();
    }
  }

  Widget _buildDashboardTab() {
    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Status Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Status:',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                        decoration: BoxDecoration(
                          color: isConnected ? Colors.green : Colors.red,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          isConnected ? 'Connected' : 'Disconnected',
                          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                        ),
                      ),
                    ],
                  ),
                  if (connectedDevice != null) ...[
                    const SizedBox(height: 8),
                    Text('Device:\n${connectedDevice!.name}'),
                    const SizedBox(height: 8),
                    Text('Address:\n${connectedDevice!.remoteId}'),
                  ],
                ],
              ),
            ),
          ),
          
          const SizedBox(height: 16),
          
          // Scan Results
          if (!isConnected) ...[
            Text(
              'Available Devices:',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Expanded(
              child: ListView.builder(
                itemCount: scanResults.length,
                itemBuilder: (context, index) {
                  ScanResult result = scanResults[index];
                  return Card(
                    child: ListTile(
                      title: Text(result.device.name.isEmpty 
                        ? 'Unknown Device' 
                        : result.device.name),
                      subtitle: Text(result.device.remoteId.toString()),
                      trailing: ElevatedButton(
                        onPressed: () => _connectToDevice(result.device),
                        child: const Text('Connect'),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
          
          // ESP32 Commands
          if (isConnected) ...[
            Text(
              'ESP32 Commands:',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            
            // Command buttons in a grid
            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              childAspectRatio: 3,
              children: [
                ElevatedButton(
                  onPressed: () => _sendCommand('status'),
                  child: const Text('Status'),
                ),
                ElevatedButton(
                  onPressed: () => _sendCommand('debugsimple'),
                  child: const Text('Debug'),
                ),
              ],
            ),
            
            const SizedBox(height: 16),
            
            // Clear Responses button
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: rfidReadings.isNotEmpty ? _clearResponses : null,
                icon: const Icon(Icons.clear_all),
                label: const Text('Clear Responses'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orange,
                  foregroundColor: Colors.white,
                ),
              ),
            ),
            
            const SizedBox(height: 16),
            
            Text(
              'ESP32 Responses:',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Expanded(
              child: rfidReadings.isEmpty
                ? const Center(
                    child: Text(
                      'No responses yet.\nSend commands to ESP32 to see data here.',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 16, color: Colors.grey),
                    ),
                  )
                : ListView.builder(
                    itemCount: rfidReadings.length,
                    itemBuilder: (context, index) {
                      // Reverse index to show latest messages on top
                      final reversedIndex = rfidReadings.length - 1 - index;
                      return Card(
                        child: Padding(
                          padding: const EdgeInsets.all(12.0),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  Text(
                                    'Response ${index + 1}',
                                    style: const TextStyle(fontWeight: FontWeight.bold),
                                  ),
                                  Text(
                                    DateTime.now().toString().substring(11, 19),
                                    style: const TextStyle(color: Colors.grey),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 8),
                              Container(
                                padding: const EdgeInsets.all(8),
                                decoration: BoxDecoration(
                                  color: Colors.grey[100],
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(
                                  rfidReadings[reversedIndex],
                                  style: const TextStyle(fontFamily: 'monospace'),
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildFilterGraphTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16.0, 16.0, 16.0, 80.0), // Extra bottom padding
      child: Column(
        children: [
          // Date/Time Selection Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '📅 Select Date Range',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 16),
                  
                  // Date pickers
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Start Date:'),
                            const SizedBox(height: 4),
                            InkWell(
                              onTap: () async {
                                DateTime? picked = await showDatePicker(
                                  context: context,
                                  initialDate: startDate,
                                  firstDate: DateTime(2020),
                                  lastDate: DateTime.now(),
                                );
                                if (picked != null) {
                                  setState(() {
                                    startDate = picked;
                                  });
                                }
                              },
                              child: Container(
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(
                                  border: Border.all(color: Colors.grey),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(startDate.toString().split(' ')[0]),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('End Date:'),
                            const SizedBox(height: 4),
                            InkWell(
                              onTap: () async {
                                DateTime? picked = await showDatePicker(
                                  context: context,
                                  initialDate: endDate,
                                  firstDate: DateTime(2020),
                                  lastDate: DateTime.now(),
                                );
                                if (picked != null) {
                                  setState(() {
                                    endDate = picked;
                                  });
                                }
                              },
                              child: Container(
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(
                                  border: Border.all(color: Colors.grey),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(endDate.toString().split(' ')[0]),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  
                  const SizedBox(height: 16),
                  
                  // Time pickers
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Start Time:'),
                            const SizedBox(height: 4),
                            InkWell(
                              onTap: () async {
                                TimeOfDay? picked = await showTimePicker(
                                  context: context,
                                  initialTime: startTime,
                                );
                                if (picked != null) {
                                  setState(() {
                                    startTime = picked;
                                  });
                                }
                              },
                              child: Container(
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(
                                  border: Border.all(color: Colors.grey),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(startTime.format(context)),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('End Time:'),
                            const SizedBox(height: 4),
                            InkWell(
                              onTap: () async {
                                TimeOfDay? picked = await showTimePicker(
                                  context: context,
                                  initialTime: endTime,
                                );
                                if (picked != null) {
                                  setState(() {
                                    endTime = picked;
                                  });
                                }
                              },
                              child: Container(
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(
                                  border: Border.all(color: Colors.grey),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(endTime.format(context)),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  
                  const SizedBox(height: 16),
                  
                  // Timezone selection
                  const Text('Timezone:'),
                  const SizedBox(height: 4),
                  DropdownButtonFormField<String>(
                    value: selectedTimezone,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    ),
                    items: const [
                      DropdownMenuItem(value: 'America/Costa_Rica', child: Text('Costa Rica (UTC-6)')),
                      DropdownMenuItem(value: 'UTC', child: Text('UTC')),
                      DropdownMenuItem(value: 'America/New_York', child: Text('New York (UTC-5/-4)')),
                      DropdownMenuItem(value: 'America/Los_Angeles', child: Text('Los Angeles (UTC-8/-7)')),
                      DropdownMenuItem(value: 'Europe/London', child: Text('London (UTC+0/+1)')),
                      DropdownMenuItem(value: 'Europe/Paris', child: Text('Paris (UTC+1/+2)')),
                      DropdownMenuItem(value: 'Asia/Tokyo', child: Text('Tokyo (UTC+9)')),
                      DropdownMenuItem(value: 'Australia/Sydney', child: Text('Sydney (UTC+10/+11)')),
                    ],
                    onChanged: (value) {
                      if (value != null) {
                        setState(() {
                          selectedTimezone = value;
                        });
                      }
                    },
                  ),
                  
                  const SizedBox(height: 16),
                  
                  // Retrieve Data Button
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: isLoadingData ? null : _retrieveFilteredData,
                      icon: isLoadingData 
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.search),
                      label: Text(isLoadingData ? 'Loading...' : 'Retrieve Data'),
                    ),
                  ),
                ],
              ),
            ),
          ),
          
          const SizedBox(height: 16),
          
          // Quick Actions Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '⚡ Quick Actions',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 16),
                  
                  // Quick action buttons in a grid
                  GridView.count(
                    crossAxisCount: 3,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    childAspectRatio: 2.2, // Reduced to give more vertical space for text
                    mainAxisSpacing: 8,
                    crossAxisSpacing: 8,
                    children: [
                      ElevatedButton.icon(
                        onPressed: isReadingRFID ? null : _triggerManualRead,
                        icon: isReadingRFID 
                          ? const SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.radio_button_checked, size: 16),
                        label: Text(
                          isReadingRFID ? 'Reading...' : 'Read Now',
                          style: const TextStyle(fontSize: 10),
                          textAlign: TextAlign.center,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.green,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
                        ),
                      ),
                      ElevatedButton.icon(
                        onPressed: () => _sendCommand('last'),
                        icon: const Icon(Icons.history, size: 16),
                        label: const Text(
                          'Last\nReading',
                          style: TextStyle(fontSize: 10),
                          textAlign: TextAlign.center,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.blue,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
                        ),
                      ),
                      ElevatedButton.icon(
                        onPressed: () => _sendCommand('print'),
                        icon: const Icon(Icons.list, size: 16),
                        label: const Text(
                          'All\nReadings',
                          style: TextStyle(fontSize: 10),
                          textAlign: TextAlign.center,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.purple,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          
          // Manual Read Result Display
          if (lastReadResult != null) ...[
            const SizedBox(height: 16),
            Card(
              color: lastReadResult == "success" 
                  ? Colors.green[50] 
                  : (lastReadResult == "timeout" || lastReadResult == "error")
                      ? Colors.red[50]
                      : Colors.orange[50],
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                          lastReadResult == "success" 
                              ? Icons.check_circle 
                              : (lastReadResult == "timeout" || lastReadResult == "error")
                                  ? Icons.error
                                  : Icons.info,
                          color: lastReadResult == "success" 
                              ? Colors.green 
                              : (lastReadResult == "timeout" || lastReadResult == "error")
                                  ? Colors.red
                                  : Colors.orange,
                          size: 24,
                        ),
                        const SizedBox(width: 8),
                        Text(
                          lastReadResult == "success" 
                              ? 'RFID Tag Detected!' 
                              : lastReadResult == "timeout"
                                  ? 'Read Timeout'
                                  : lastReadResult == "error"
                                      ? 'Device Error'
                                      : 'No RFID Tag Detected',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                            color: lastReadResult == "success" 
                                ? Colors.green[700] 
                                : (lastReadResult == "timeout" || lastReadResult == "error")
                                    ? Colors.red[700]
                                    : Colors.orange[700],
                          ),
                        ),
                      ],
                    ),
                    if (lastReadResult == "timeout" || lastReadResult == "error") ...[
                      const SizedBox(height: 8),
                      Text(
                        lastReadResult == "timeout"
                            ? 'No response received from device within 15 seconds. The device may have reset.'
                            : 'Device error detected.',
                        style: TextStyle(
                          fontSize: 14,
                          color: Colors.red[700],
                        ),
                      ),
                    ],
                    if (lastReadResult == "success" && lastReadData != null) ...[
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Temperature:',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: Colors.grey[600],
                                  ),
                                ),
                                Text(
                                  lastReadData!['temperature'] != null
                                      ? '${(lastReadData!['temperature'] as double).toStringAsFixed(1)}°C'
                                      : 'N/A',
                                  style: TextStyle(
                                    fontSize: 18,
                                    fontWeight: FontWeight.bold,
                                    color: lastReadData!['temperature'] != null ? Colors.red : Colors.grey,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Tag ID:',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: Colors.grey[600],
                                  ),
                                ),
                                Text(
                                  lastReadData!['tag'],
                                  style: const TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Timestamp: ${lastReadData!['timestamp']}',
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.grey[600],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
          
          const SizedBox(height: 16),
          
          // Data Summary Card
          if (parsedReadings.isNotEmpty) ...[
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                  children: [
                    Column(
                      children: [
                        Text(
                          '${parsedReadings.length}',
                          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Colors.blue),
                        ),
                        const Text('Readings Found'),
                      ],
                    ),
                    Column(
                      children: [
                        Text(
                          () {
                            final validTemps = parsedReadings
                                .where((r) => r['temperature'] != null)
                                .map((r) => r['temperature'] as double)
                                .toList();
                            if (validTemps.isEmpty) {
                              return 'N/A';
                            }
                            return validTemps.reduce((a, b) => a > b ? a : b).toStringAsFixed(1) + '°C';
                          }(),
                          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Colors.red),
                        ),
                        const Text('Max Temp'),
                      ],
                    ),
                    Column(
                      children: [
                        Text(
                          () {
                            final validTemps = parsedReadings
                                .where((r) => r['temperature'] != null)
                                .map((r) => r['temperature'] as double)
                                .toList();
                            if (validTemps.isEmpty) {
                              return 'N/A';
                            }
                            return validTemps.reduce((a, b) => a < b ? a : b).toStringAsFixed(1) + '°C';
                          }(),
                          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Colors.green),
                        ),
                        const Text('Min Temp'),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Filtered Readings (${parsedReadings.length} found):',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        IconButton(
                          onPressed: parsedReadings.isNotEmpty ? _exportToCSV : null,
                          icon: const Icon(Icons.download, size: 20),
                          tooltip: 'Export CSV',
                          style: IconButton.styleFrom(
                            backgroundColor: Colors.green,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.all(8),
                            minimumSize: const Size(36, 36),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    // Responsive layout: Expand on tablets, use fixed widths with scroll on phones
                    LayoutBuilder(
                      builder: (context, constraints) {
                        final screenWidth = MediaQuery.of(context).size.width;
                        final isTablet = screenWidth > 600; // Tablet/large screen threshold
                        
                        // For tablets, use Expanded widgets to fill available width
                        // For phones, use fixed widths with horizontal scroll
                        Widget buildTableContent() {
                          return ConstrainedBox(
                            constraints: const BoxConstraints(maxHeight: 300),
                            child: SingleChildScrollView(
                              scrollDirection: Axis.vertical,
                              child: Column(
                                children: [
                                  // Header row
                                  Padding(
                                    padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8.0),
                                    child: Row(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        SizedBox(width: isTablet ? 40 : 24), // Wider on tablets
                                        const SizedBox(width: 12),
                                        if (isTablet)
                                          Expanded(
                                            flex: 2,
                                            child: const Text('Temperature', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                                          )
                                        else
                                          SizedBox(width: 80, child: const Text('Temperature', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold))),
                                        const SizedBox(width: 16),
                                        if (isTablet)
                                          Expanded(
                                            flex: 1,
                                            child: const Text('Country', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                                          )
                                        else
                                          SizedBox(width: 60, child: const Text('Country', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold))),
                                        const SizedBox(width: 16),
                                        if (isTablet)
                                          Expanded(
                                            flex: 3,
                                            child: const Text('Tag ID', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                                          )
                                        else
                                          SizedBox(width: 140, child: const Text('Tag ID', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold))),
                                        const SizedBox(width: 16),
                                        if (isTablet)
                                          Expanded(
                                            flex: 4,
                                            child: const Text('Timestamp', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                                          )
                                        else
                                          SizedBox(width: 180, child: const Text('Timestamp', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold))),
                                        const SizedBox(width: 8),
                                      ],
                                    ),
                                  ),
                                  // Readings rows
                                  ...parsedReadings.asMap().entries.map((entry) {
                                    final index = entry.key;
                                    final reading = entry.value;
                                    return Card(
                                      margin: const EdgeInsets.only(bottom: 8, left: 12, right: 12),
                                      child: Padding(
                                        padding: const EdgeInsets.all(12.0),
                                        child: Row(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            Container(
                                              width: isTablet ? 40 : 24,
                                              height: isTablet ? 40 : 24,
                                              decoration: BoxDecoration(
                                                color: Colors.grey[200],
                                                borderRadius: BorderRadius.circular(4),
                                              ),
                                              child: Center(
                                                child: Text(
                                                  '${index + 1}',
                                                  style: TextStyle(
                                                    color: Colors.black,
                                                    fontWeight: FontWeight.bold,
                                                    fontSize: isTablet ? 14 : 12,
                                                  ),
                                                ),
                                              ),
                                            ),
                                            const SizedBox(width: 12),
                                            if (isTablet)
                                              Expanded(
                                                flex: 2,
                                                child: Column(
                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                  children: [
                                                    Text(
                                                      reading['temperature'] != null
                                                          ? '${(reading['temperature'] as double).toStringAsFixed(1)}°C'
                                                          : 'N/A',
                                                      style: TextStyle(
                                                        fontSize: 14,
                                                        fontWeight: FontWeight.bold,
                                                        color: reading['temperature'] != null ? Colors.red : Colors.grey,
                                                      ),
                                                    ),
                                                    const SizedBox(height: 2),
                                                    Text(
                                                      'Temperature',
                                                      style: TextStyle(
                                                        fontSize: 11,
                                                        color: Colors.grey[600],
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                              )
                                            else
                                              SizedBox(
                                                width: 80,
                                                child: Column(
                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                  children: [
                                                    Text(
                                                      reading['temperature'] != null
                                                          ? '${(reading['temperature'] as double).toStringAsFixed(1)}°C'
                                                          : 'N/A',
                                                      style: TextStyle(
                                                        fontSize: 12,
                                                        fontWeight: FontWeight.bold,
                                                        color: reading['temperature'] != null ? Colors.red : Colors.grey,
                                                      ),
                                                    ),
                                                    const SizedBox(height: 2),
                                                    Text(
                                                      'Temperature',
                                                      style: TextStyle(
                                                        fontSize: 10,
                                                        color: Colors.grey[600],
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                              ),
                                            const SizedBox(width: 16),
                                            if (isTablet)
                                              Expanded(
                                                flex: 1,
                                                child: Column(
                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                  children: [
                                                    Text(
                                                      reading['country'].toString(),
                                                      style: const TextStyle(
                                                        fontSize: 12,
                                                        fontWeight: FontWeight.w500,
                                                      ),
                                                    ),
                                                    const SizedBox(height: 2),
                                                    Text(
                                                      'Country',
                                                      style: TextStyle(
                                                        fontSize: 11,
                                                        color: Colors.grey[600],
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                              )
                                            else
                                              SizedBox(
                                                width: 60,
                                                child: Column(
                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                  children: [
                                                    Text(
                                                      reading['country'].toString(),
                                                      style: const TextStyle(
                                                        fontSize: 10,
                                                        fontWeight: FontWeight.w500,
                                                      ),
                                                    ),
                                                    const SizedBox(height: 2),
                                                    Text(
                                                      'Country',
                                                      style: TextStyle(
                                                        fontSize: 10,
                                                        color: Colors.grey[600],
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                              ),
                                            const SizedBox(width: 16),
                                            if (isTablet)
                                              Expanded(
                                                flex: 3,
                                                child: Column(
                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                  children: [
                                                    Text(
                                                      reading['tag'],
                                                      style: const TextStyle(
                                                        fontSize: 12,
                                                        fontWeight: FontWeight.w500,
                                                      ),
                                                    ),
                                                    const SizedBox(height: 2),
                                                    Text(
                                                      'Tag ID',
                                                      style: TextStyle(
                                                        fontSize: 11,
                                                        color: Colors.grey[600],
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                              )
                                            else
                                              SizedBox(
                                                width: 140,
                                                child: Column(
                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                  children: [
                                                    Text(
                                                      reading['tag'],
                                                      style: const TextStyle(
                                                        fontSize: 10,
                                                        fontWeight: FontWeight.w500,
                                                      ),
                                                    ),
                                                    const SizedBox(height: 2),
                                                    Text(
                                                      'Tag ID',
                                                      style: TextStyle(
                                                        fontSize: 10,
                                                        color: Colors.grey[600],
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                              ),
                                            const SizedBox(width: 16),
                                            if (isTablet)
                                              Expanded(
                                                flex: 4,
                                                child: Column(
                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                  children: [
                                                    Text(
                                                      reading['timestamp'],
                                                      style: const TextStyle(
                                                        fontSize: 12,
                                                        fontWeight: FontWeight.w500,
                                                      ),
                                                    ),
                                                    const SizedBox(height: 2),
                                                    Text(
                                                      'Timestamp',
                                                      style: TextStyle(
                                                        fontSize: 11,
                                                        color: Colors.grey[600],
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                              )
                                            else
                                              SizedBox(
                                                width: 180,
                                                child: Column(
                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                  children: [
                                                    Text(
                                                      reading['timestamp'],
                                                      style: const TextStyle(
                                                        fontSize: 10,
                                                        fontWeight: FontWeight.w500,
                                                      ),
                                                    ),
                                                    const SizedBox(height: 2),
                                                    Text(
                                                      'Timestamp',
                                                      style: TextStyle(
                                                        fontSize: 10,
                                                        color: Colors.grey[600],
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                              ),
                                            const SizedBox(width: 8),
                                          ],
                                        ),
                                      ),
                                    );
                                  }).toList(),
                                ],
                              ),
                            ),
                          );
                        }
                        
                        // Wrap with horizontal scroll only on phones
                        final tableContent = buildTableContent();
                        if (isTablet) {
                          return tableContent;
                        } else {
                          return SingleChildScrollView(
                            scrollDirection: Axis.horizontal,
                            controller: _horizontalScrollController,
                            child: tableContent,
                          );
                        }
                      },
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          '📈 Temperature Chart',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        IconButton(
                          onPressed: parsedReadings.isNotEmpty ? _saveChartAsImage : null,
                          icon: const Icon(Icons.save_alt, size: 20),
                          tooltip: 'Save Image',
                          style: IconButton.styleFrom(
                            backgroundColor: Colors.purple,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.all(8),
                            minimumSize: const Size(36, 36),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    // Responsive chart height: taller on tablets
                    LayoutBuilder(
                      builder: (context, constraints) {
                        final screenWidth = MediaQuery.of(context).size.width;
                        final isTablet = screenWidth > 600;
                        final chartHeight = isTablet ? 350.0 : 250.0;
                        
                        return SizedBox(
                          height: chartHeight,
                          width: double.infinity, // Ensure chart fills available width
                          child: RepaintBoundary(
                            key: _chartKey,
                            child: _buildTemperatureChart(),
                          ),
                        );
                      },
                    ),
                  ],
                ),
              ),
            ),
          ] else ...[
            Card(
              child: Padding(
                padding: const EdgeInsets.all(32.0),
                child: Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.show_chart,
                        size: 64,
                        color: Colors.grey[400],
                      ),
                      const SizedBox(height: 16),
                      Text(
                        'No data available.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 16,
                          color: Colors.grey[600],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildAboutTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Company Logo Section - centered at top
          Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 24.0),
              child: Container(
                width: 120,
                height: 120,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12),
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: Image.asset(
                    'assets/images/EB_logo.png',
                    fit: BoxFit.contain,
                    errorBuilder: (context, error, stackTrace) {
                      return Container(
                        color: Colors.grey[100],
                        child: const Icon(
                          Icons.business,
                          size: 48,
                          color: Colors.grey,
                        ),
                      );
                    },
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
          // App Information
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '📱 App Information',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  _buildInfoRow('Version', '1.2 (Multi-Button + RGB LED)'),
                  _buildInfoRow('Build', 'September 2025'),
                  _buildInfoRow('Platform', 'Flutter (macOS/iOS/Android)'),
                  _buildInfoRow('BLE Support', 'ESP32-S3 Compatible'),
                ],
              ),
            ),
          ),
          
          const SizedBox(height: 16),
          
          // Company Details
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '🏢 Company Details',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  _buildInfoRow('Company', 'Establishment Labs'),
                  _buildInfoRow('Developer', 'Little Endian Engineering'),
                  _buildInfoRow('Industry', 'Medical Device & RFID Solutions'),
                  _buildInfoRow('Contact', 'lyu@establishmentlabs.com'),
                ],
              ),
            ),
          ),
          
          const SizedBox(height: 16),
          
          // Usage Instructions
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '📖 Usage Instructions',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    '1. Connect to ESP32-S3 RFID Reader via BLE (tap the Bluetooth button)\n'
                    '2. Dashboard Tab: Send commands (Status, Debug) and view responses\n'
                    '3. Filter & Graph Tab: Set date/time range and timezone, then click "Retrieve Data"\n'
                    '4. Quick Actions: Use "Read Now" for manual RFID reading, "Last Reading" for latest data, or "All Readings" for complete history\n'
                    '5. View filtered readings in the table with horizontal scrolling\n'
                    '6. Analyze temperature trends in the interactive chart\n'
                    '7. Export filtered readings as CSV using the Export CSV button\n'
                    '8. Save temperature chart as image to your gallery using the Save Image button',
                    style: TextStyle(fontSize: 14),
                  ),
                ],
              ),
            ),
          ),
          
          const SizedBox(height: 16),
          
          // Contact Information
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '📞 Contact Information',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  _buildInfoRow('Email', 'lyu@establishmentlabs.com'),
                  _buildInfoRow('Developer', 'info@littleendianengineering.com'),
                  _buildInfoRow('Support', 'Available 24/7'),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
  
  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 80,
            child: Text(
              '$label:',
              style: const TextStyle(
                fontWeight: FontWeight.w500,
                color: Colors.grey,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontSize: 14),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTemperatureChart() {
    if (parsedReadings.isEmpty) {
      return const Center(
        child: Text('No data to display'),
      );
    }

    // Filter out readings with null temperature (N/A)
    final validReadings = parsedReadings.where((r) => r['temperature'] != null).toList();
    
    if (validReadings.isEmpty) {
      return const Center(
        child: Text('No temperature data available'),
      );
    }

    // Sort readings by timestamp
    final sortedReadings = List<Map<String, dynamic>>.from(validReadings);
    sortedReadings.sort((a, b) => (a['dateTime'] as DateTime).compareTo(b['dateTime'] as DateTime));

    // Group readings by tag (country + tag ID)
    final Map<String, List<Map<String, dynamic>>> readingsByTag = {};
    for (var reading in sortedReadings) {
      final tagKey = '${reading['country']}_${reading['tag']}';
      if (!readingsByTag.containsKey(tagKey)) {
        readingsByTag[tagKey] = [];
      }
      readingsByTag[tagKey]!.add(reading);
    }

    // Calculate proper Y-axis range with symmetrical padding (rounded to integers)
    final temperatures = sortedReadings.map((r) => r['temperature'] as double).toList();
    final minTemp = temperatures.reduce((a, b) => a < b ? a : b);
    final maxTemp = temperatures.reduce((a, b) => a > b ? a : b);
    
    // Calculate symmetrical range with equal padding above and below
    final tempRange = maxTemp - minTemp;
    final padding = (tempRange * 0.2).ceil().toDouble(); // 20% padding for better symmetry
    
    // Round to integers with equal padding above and below
    final minY = (minTemp - padding).floor().toDouble();
    final maxY = (maxTemp + padding).ceil().toDouble();

    // Define colors for different tags (cycle through if more tags than colors)
    final List<Color> tagColors = [
      Colors.blue,
      Colors.red,
      Colors.green,
      Colors.orange,
      Colors.purple,
      Colors.teal,
      Colors.pink,
      Colors.amber,
    ];

    // Create line chart data for each tag
    final List<LineChartBarData> lineBarsData = [];
    int colorIndex = 0;
    
    readingsByTag.forEach((tagKey, tagReadings) {
      final List<FlSpot> spots = [];
      
      // Create spots for this tag, using the index in the sorted readings
      // Only include readings with valid temperature (not null)
      for (var tagReading in tagReadings) {
        if (tagReading['temperature'] != null) {
          final indexInSorted = sortedReadings.indexOf(tagReading);
          if (indexInSorted >= 0) {
            final temperature = tagReading['temperature'] as double;
            spots.add(FlSpot(indexInSorted.toDouble(), temperature));
          }
        }
      }
      
      // Get color for this tag
      final color = tagColors[colorIndex % tagColors.length];
      colorIndex++;
      
      // Create tag label (country + last 4 digits of tag ID)
      final tagLabel = tagReadings.isNotEmpty 
          ? '${tagReadings.first['country']}-${tagReadings.first['tag'].toString().substring(tagReadings.first['tag'].toString().length - 4)}'
          : tagKey;
      
      lineBarsData.add(
        LineChartBarData(
          spots: spots,
          isCurved: true,
          color: color,
          barWidth: 3,
          isStrokeCapRound: true,
          dotData: FlDotData(show: true),
          belowBarData: BarAreaData(
            show: false, // Disable area fill for multiple lines
          ),
        ),
      );
    });
    
    return LineChart(
      LineChartData(
        backgroundColor: Colors.white, // Ensure white background for image export
        minY: minY,
        maxY: maxY,
        gridData: FlGridData(show: true),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 50,
              getTitlesWidget: (value, meta) {
                return Text(
                  '${value.toStringAsFixed(1)}°C',
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
                );
              },
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              getTitlesWidget: (value, meta) {
                if (value.toInt() < sortedReadings.length) {
                  final reading = sortedReadings[value.toInt()];
                  final timestamp = reading['timestamp'] as String;
                  
                  // Dynamic label spacing based on number of readings
                  int interval = 1;
                  if (sortedReadings.length > 20) {
                    interval = 3; // Show every 3rd label for many readings
                  } else if (sortedReadings.length > 10) {
                    interval = 2; // Show every 2nd label for moderate readings
                  }
                  
                  // Only show label if it's at the right interval
                  if (value.toInt() % interval == 0) {
                    final timePart = timestamp.split(' ')[1].substring(0, 5);
                    return Text(
                      timePart, 
                      style: const TextStyle(fontSize: 10),
                    );
                  }
                }
                return const Text('');
              },
            ),
          ),
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        borderData: FlBorderData(show: true),
        lineBarsData: lineBarsData,
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipItems: (touchedSpots) {
              return touchedSpots.map((spot) {
                final index = spot.x.toInt();
                if (index < sortedReadings.length) {
                  final reading = sortedReadings[index];
                  final tagLabel = '${reading['country']}-${reading['tag'].toString().substring(reading['tag'].toString().length - 4)}';
                  final tempStr = reading['temperature'] != null
                      ? '${(reading['temperature'] as double).toStringAsFixed(1)}°C'
                      : 'N/A';
                  return LineTooltipItem(
                    'Tag: $tagLabel\n$tempStr\n${reading['timestamp']}',
                    const TextStyle(color: Colors.white),
                  );
                }
                return null;
              }).toList();
            },
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _readTimeoutTimer?.cancel();
    _horizontalScrollController.dispose();
    _disconnect();
    super.dispose();
  }
}