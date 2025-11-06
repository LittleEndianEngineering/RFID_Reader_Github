"""
Implant RFID Reader - Multi-Button Dashboard Application
======================================================

PROPRIETARY SOFTWARE
Copyright (c) 2025 Establishment Labs
Developed by Little Endian Engineering

Version: 1.2 (Multi-Button + RGB LED)
Date: September 2025

DESCRIPTION:
Streamlit-based dashboard for Implant RFID Reader ESP32 device with multi-button support and RGB LED status indicators.
Provides real-time data visualization, filtering, and configuration management.
Supports multiple timezones, CSV export functionality, configurable button timings, and hardware LED status monitoring.

FEATURES:
- Real-time serial communication with ESP32
- Multi-button functionality (short press = RFID read, long press = dashboard mode toggle)
- RGB LED status indicators for visual feedback
- Configurable long press timer for dashboard mode activation (1-30 seconds)
- Date range filtering with timezone support
- Interactive data visualization with Plotly
- CSV export functionality
- ESP32 configuration management
- Multi-timezone display support
- Password-protected storage clearing
- Comprehensive User Guide with hardware setup instructions

REQUIREMENTS:
- Python 3.8+
- Streamlit, Pandas, PySerial, Plotly, PyTZ
- ESP32 device with Multi-Button Implant RFID Reader firmware

USAGE:
streamlit run rfid_dashboard_configure_lightsleep_multibutton.py

CONTACT:
Establishment Labs lyu@establishmentlabs.com
Little Endian Engineering info@littleendianengineering.com

CONFIDENTIAL - PROPRIETARY SOFTWARE
"""

import streamlit as st
import pandas as pd
import serial
import serial.tools.list_ports
import time
from datetime import datetime, timedelta, timezone, time as dt_time
import re
import calendar
import plotly.express as px
import pytz

# =============================================================================
# SECURITY CONFIGURATION
# =============================================================================

# Password for clearing storage (change this in production)
if 'CLEAR_PASSWORD' not in globals():
    CLEAR_PASSWORD = "rfidadmin"  # Change this to your desired password

# =============================================================================
# PAGE CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="Implant RFID Reader Multi-Button Dashboard",
    page_icon="📊",
    layout="wide"
)

# =============================================================================
# SESSION STATE INITIALIZATION
# =============================================================================

if 'serial_connection' not in st.session_state:
    st.session_state.serial_connection = None
if 'connected' not in st.session_state:
    st.session_state.connected = False
if 'debug_log' not in st.session_state:
    st.session_state['debug_log'] = []
if 'set_debug_log' not in st.session_state:
    st.session_state['set_debug_log'] = []
if 'general_debug_log' not in st.session_state:
    st.session_state['general_debug_log'] = []
if 'last_df' not in st.session_state:
    st.session_state['last_df'] = None
if 'last_raw_response' not in st.session_state:
    st.session_state['last_raw_response'] = None
if 'selected_timezone' not in st.session_state:
    st.session_state['selected_timezone'] = 'America/Costa_Rica'
# last_ping variable removed - using dashboard mode approach instead
# enable_keepalive variable removed - using dashboard mode approach instead
if 'dashboard_mode' not in st.session_state:
    st.session_state['dashboard_mode'] = False
# Initialize configuration widget defaults
if 'esp32_longPressTime' not in st.session_state:
    st.session_state['esp32_longPressTime'] = 5
if 'esp32_ssid' not in st.session_state:
    st.session_state['esp32_ssid'] = ""
if 'esp32_password' not in st.session_state:
    st.session_state['esp32_password'] = ""
if 'esp32_rfidOnTime' not in st.session_state:
    st.session_state['esp32_rfidOnTime'] = 5
if 'esp32_periodicInterval' not in st.session_state:
    st.session_state['esp32_periodicInterval'] = 60

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

WAKE_DELAY = 0.22  # seconds; first byte wakes ESP32 from light sleep and is typically lost

def log_debug(msg):
    """Log debug messages with automatic cleanup (max 100 entries)"""
    st.session_state['debug_log'].append(msg)
    if len(st.session_state['debug_log']) > 100:
        st.session_state['debug_log'] = st.session_state['debug_log'][-100:]

def log_set_debug(msg):
    """Log set operation debug messages with automatic cleanup (max 100 entries)"""
    st.session_state['set_debug_log'].append(msg)
    if len(st.session_state['set_debug_log']) > 100:
        st.session_state['set_debug_log'] = st.session_state['set_debug_log'][-100:]

def log_general_debug(msg):
    """Log general debug messages (ping, pong, retrieve data, etc.) with automatic cleanup (max 100 entries)"""
    st.session_state['general_debug_log'].append(msg)
    if len(st.session_state['general_debug_log']) > 100:
        st.session_state['general_debug_log'] = st.session_state['general_debug_log'][-100:]

def get_available_ports():
    """Get list of available serial ports"""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def connect_to_arduino(port, baud_rate=115200):
    """Establish serial connection to ESP32 device"""
    try:
        ser = serial.Serial(port, baud_rate, timeout=2)
        # Avoid toggling DTR/RTS which could reset some ESP32 boards
        try:
            ser.dtr = False
            ser.rts = False
        except Exception:
            pass
        time.sleep(2)  # Allow device/USB to settle
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        return ser
    except Exception as e:
        st.error(f"Failed to connect: {e}")
        return None

def _wake_serial(ser, wake_delay=WAKE_DELAY):
    """
    Wake the ESP32 from Light Sleep via UART RX.
    Sends a single newline (likely consumed), waits a beat, then clears any partials.
    """
    try:
        if ser is None:
            return
        ser.write(b"\n")       # wake byte - device will wake but this byte is lost
        ser.flush()
        time.sleep(wake_delay) # give ESP32 time to fully wake clocks
        # REMOVED: ser.reset_input_buffer() - this was clearing responses!
    except Exception as e:
        log_debug(f"[DEBUG] Wake error: {e}")

def _log_filtered_debug(command, line):
    """Filter debug output based on the command being sent"""
    # Always show these important messages
    if any(keyword in line for keyword in ["[DASHBOARD]", "[RFID]", "[ERROR]", "[WARNING]", "CMD_RECEIVED"]):
        log_general_debug(f"[DEBUG] Received: {line}")
        return
    
    # Filter based on specific commands
    if command == "debug":
        # For debug command, only show debug info section
        if any(keyword in line for keyword in ["[DEBUG] --- Device Debug Info ---", "[DEBUG] Reading count:", "[DEBUG] MAX_READINGS:", "[DEBUG] Available slots:", "[DEBUG] Dashboard mode:", "[DEBUG] Current time:", "[DEBUG] Unix timestamp:", "[DEBUG] --- End Debug Info ---"]):
            log_general_debug(f"[DEBUG] Received: {line}")
    
    elif command == "buttonmode":
        # For buttonmode command, only show button status
        if any(keyword in line for keyword in ["[BUTTON] Multi-Button Mode Status", "[BUTTON] Dashboard Mode:", "[BUTTON] Short press:", "[BUTTON] Long press", "[BUTTON] Current button state:"]):
            log_general_debug(f"[DEBUG] Received: {line}")
    
    elif command == "testbutton":
        # For testbutton command, only show test instructions
        if any(keyword in line for keyword in ["[BUTTON] Testing multi-button functionality:", "[BUTTON] Press and hold", "[BUTTON] Short press", "[BUTTON] Current dashboard mode"]):
            log_general_debug(f"[DEBUG] Received: {line}")
    
    elif command == "status":
        # For status command, only show status information
        if any(keyword in line for keyword in ["[STATUS] Current ESP32 Status:", "[STATUS] Dashboard Mode:", "[STATUS] lastCommandTime:", "[STATUS] Serial.available():", "[STATUS] Current time:", "[STATUS] Long press timer:"]):
            log_general_debug(f"[DEBUG] Received: {line}")
    
    elif command.startswith("get "):
        # For get commands, show the response
        if line.startswith("<") and line.endswith("_END>"):
            log_general_debug(f"[DEBUG] Received: {line}")
        elif not any(keyword in line for keyword in ["[DEBUG]", "[SERIAL]", "[UART]", "[LIGHTSLEEP]", "[WATCHDOG]"]):
            log_general_debug(f"[DEBUG] Received: {line}")
    
    elif command.startswith("set "):
        # For set commands, only show confirmation
        if line in ["OK", "ERROR", "Invalid value"]:
            log_general_debug(f"[DEBUG] Received: {line}")
    
    elif command == "print":
        # For print command, show all RFID data
        if any(keyword in line for keyword in ["TAG:", "Reading #", "Time:", "Temperature:"]):
            log_general_debug(f"[DEBUG] Received: {line}")
    
    else:
        # For other commands, show everything
        log_general_debug(f"[DEBUG] Received: {line}")

def _wake_and_send_command(ser, command, wake_delay=WAKE_DELAY, max_retries=3, filter_debug=True):
    """
    Wake the ESP32 and immediately send a command (like button press).
    This ensures the command is processed immediately after wake-up.
    Includes retry mechanism for cases where ESP32 is busy with periodic reads.
    """
    for attempt in range(max_retries):
        try:
            if ser is None:
                return ""
            # Send wake-up byte
            ser.write(b"\n")
            ser.flush()
            time.sleep(wake_delay) # give ESP32 time to fully wake clocks
            
            # Clear any old data before sending new command
            ser.reset_input_buffer()
            
            # Immediately send the command
            ser.write(f"{command}\n".encode())
            ser.flush()
            time.sleep(0.1) # short delay to ensure command is sent
            
            # Wait for response (like the main send_command function)
            response = ""
            bytes_count = 0
            line_count = 0
            start_time = time.time()
            received_any = False
            last_rx_time = None
            end_reason = ""
            quiet_period = 0.6
            hard_timeout = 10  # shorter timeout for dashboard mode commands
            
            # Wait for response with timeout handling
            while True:
                if ser.in_waiting:
                    raw = ser.readline()
                    try:
                        line = raw.decode(errors='ignore').strip()
                    except Exception:
                        line = ""
                    if line:
                        response += line + "\n"
                        bytes_count += len(raw)
                        line_count += 1
                        received_any = True
                        last_rx_time = time.time()
                        # Filter debug output based on command
                        if filter_debug:
                            _log_filtered_debug(command, line)
                        else:
                            log_general_debug(f"[DEBUG] Received: {line}")
                    
                    # Check for end conditions
                    if received_any and last_rx_time is not None and (time.time() - last_rx_time) > quiet_period:
                        end_reason = "quiet_period"
                        log_general_debug("[DEBUG] Quiet period reached; finishing read")
                        break
                
                # Check timeout
                now_ts = time.time()
                if now_ts - start_time > hard_timeout:
                    end_reason = "hard_timeout"
                    log_general_debug(f"[DEBUG] Timeout after {time.time() - start_time:.1f}s")
                    break
            
            duration = time.time() - start_time
            log_general_debug(f"[DEBUG] wake_and_send end: reason={end_reason or 'unknown'} bytes={bytes_count} lines={line_count} duration={duration:.2f}s")
            
            if response.strip():
                return response.strip()  # Success, return response
            else:
                log_debug(f"[DEBUG] No response received (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    time.sleep(0.5) # Wait before retry
                else:
                    return ""  # All retries failed
                    
        except Exception as e:
            log_debug(f"[DEBUG] Wake and send error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(0.5) # Wait before retry
            else:
                return ""  # All retries failed

def send_command(ser, command):
    """Send command to ESP32 and receive response with timeout"""
    try:
        log_general_debug(f"[DEBUG] send_command start: {command}")
        
        # For dashboard mode commands, use immediate wake-and-send approach
        if command in ["dashboardmode on", "dashboardmode off", "status", "debugsimple", "debug", "buttonmode", "testbutton", "print"]:
            response = _wake_and_send_command(ser, command, filter_debug=True)
            if response:
                return response
            else:
                log_general_debug(f"[DEBUG] wake_and_send failed for {command}, falling back to standard method")
                # Fall back to standard method if wake-and-send fails
                _wake_serial(ser)
                ser.reset_input_buffer()
                ser.write(f"{command}\n".encode())
                ser.flush()
        else:
            # For other commands, use the standard wake-then-send approach
            _wake_serial(ser)
            # Clear any old data before sending new command
            ser.reset_input_buffer()
            ser.write(f"{command}\n".encode())
            ser.flush()

        response = ""
        bytes_count = 0
        line_count = 0
        start_time = time.time()
        expect_range = command.strip().startswith("range ")
        received_any = False
        last_rx_time = None
        end_reason = ""
        quiet_period = 1.5 if expect_range else 0.6
        hard_timeout = 30 if expect_range else 20
        
        # Wait for response with better timeout handling
        while True:
            if ser.in_waiting:
                raw = ser.readline()
                try:
                    line = raw.decode(errors='ignore').strip()
                except Exception:
                    line = ""
                if line:
                    response += line + "\n"
                    bytes_count += len(raw)
                    line_count += 1
                    received_any = True
                    last_rx_time = time.time()
                    log_general_debug(f"[DEBUG] Received: {line}")
                # Primary end condition for range responses
                if '</DASHBOARD_DATA>' in line or (expect_range and '---END_READINGS---' in line):
                    end_reason = "end_marker"
                    break
            # Check timeout
            now_ts = time.time()
            if received_any and last_rx_time is not None and (now_ts - last_rx_time) > quiet_period:
                # No new data for quiet period → assume done
                end_reason = "quiet_period"
                log_general_debug("[DEBUG] Quiet period reached; finishing read")
                break
            if now_ts - start_time > hard_timeout:
                end_reason = "hard_timeout"
                log_general_debug(f"[DEBUG] Timeout after {time.time() - start_time:.1f}s")
                break
                
        duration = time.time() - start_time
        log_general_debug(f"[DEBUG] send_command end: reason={end_reason or 'unknown'} bytes={bytes_count} lines={line_count} duration={duration:.2f}s")
        return response.strip()
    except Exception as e:
        log_general_debug(f"[DEBUG] Error in send_command: {e}")
        return ""

# Keep-alive function for dashboard mode - send periodic commands to prevent auto-deactivation
# Keepalive function removed - dashboard mode is now controlled purely by toggle state

def parse_readings(response):
    """Parse RFID readings from ESP32 response"""
    readings = []
    in_block = False
    lines = response.split('\n')
    
    for line in lines:
        if '---BEGIN_READINGS---' in line:
            in_block = True
            continue
        if '---END_READINGS---' in line:
            in_block = False
            continue
        if in_block:
            # Handle both debug and normal formats
            # Debug format: #200: [DEBUG] raw_timestamp=1753247585, converted=2025-07-23 05:13:05, 999, 141004265912, 24.86°C
            # Normal format: #200: 2025-07-23 05:13:05, 999, 141004265912, 24.86°C
            debug_match = re.search(r'#\d+:\s*\[DEBUG\]\s*raw_timestamp=\d+,\s*converted=([\d\-]+\s[\d:]+),\s*([\d]+),\s*([\d]+),\s*([\d.]+)°C', line)
            normal_match = re.search(r'#\d+:\s*([\d\-]+\s[\d:]+),\s*([\d]+),\s*([\d]+),\s*([\d.]+)°C', line)
            
            if debug_match:
                timestamp, value1, tag, temp = debug_match.groups()
                readings.append({
                    'Timestamp': timestamp,
                    'Value1': value1,
                    'Tag': tag,
                    'Temperature_C': temp
                })
            elif normal_match:
                timestamp, value1, tag, temp = normal_match.groups()
                readings.append({
                    'Timestamp': timestamp,
                    'Value1': value1,
                    'Tag': tag,
                    'Temperature_C': temp
                })
    
    return readings

def convert_timestamp_to_timezone(timestamp_str, target_timezone):
    """Convert UTC timestamp string to target timezone for display"""
    try:
        # Parse the UTC timestamp string
        utc_dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        
        # Convert to target timezone
        target_tz = pytz.timezone(target_timezone)
        local_dt = utc_dt.astimezone(target_tz)
        
        return local_dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        st.error(f"Error converting timestamp: {e}")
        return timestamp_str

def get_variable_with_markers(ser, var):
    """Get ESP32 configuration variable using marker-based parsing"""
    # Wake device and clear any old data
    _wake_serial(ser)
    ser.reset_input_buffer()
    
    # Map variable names to marker base
    marker_map = {
        "rfidOnTimeMs": "RFIDONTIME",
        "periodicIntervalMs": "PERIODICINTERVAL",
        "ssid": "SSID",
        "password": "PASSWORD",
        "longPressMs": "LONGPRESSMS"
    }
    marker_base = marker_map.get(var, var.upper())
    start_marker = f"<GET_{marker_base}_BEGIN>"
    end_marker = f"<GET_{marker_base}_END>"
    
    log_debug(f"[DEBUG] Sending get command: get {var}")
    ser.write(f"get {var}\n".encode())
    ser.flush()
    time.sleep(0.05)
    
    lines_between = []
    found = False
    start_time = time.time()
    
    while time.time() - start_time < 4:  # Slightly increased timeout for light-sleep wake
        if ser.in_waiting:
            line = ser.readline().decode(errors='ignore').strip()
            # Filter debug output for get commands
            _log_filtered_debug(f"get {var}", line)
            
            if line == start_marker:
                found = True
                log_debug(f"[DEBUG] Found start marker")
                continue
            if found and line == end_marker:
                log_debug(f"[DEBUG] Found end marker")
                break
            if found:
                lines_between.append(line)
                log_debug(f"[DEBUG] Added to lines_between: {line}")
    
    log_debug(f"[DEBUG] Lines between markers for {var}: {lines_between}")
    value = next((l for l in lines_between if l and l != start_marker and l != end_marker), None)
    log_debug(f"[DEBUG] Final value for {var}: {value}")
    return value

def extract_latest_readings_block(response):
    """Extract the latest readings block from ESP32 response"""
    # If <DASHBOARD_DATA> markers are present, extract only that section
    dashboard_blocks = re.findall(r'<DASHBOARD_DATA>(.*?)</DASHBOARD_DATA>', response, re.DOTALL)
    if dashboard_blocks:
        response = dashboard_blocks[-1]
    # Find all blocks between ---BEGIN_READINGS--- and ---END_READINGS---
    blocks = []
    lines = response.split('\n')
    in_block = False
    current_block = []
    for line in lines:
        if '---BEGIN_READINGS---' in line:
            in_block = True
            current_block = []
            continue
        if '---END_READINGS---' in line:
            in_block = False
            blocks.append('\n'.join(current_block))
            continue
        if in_block:
            current_block.append(line)
    return blocks[-1] if blocks else ""

def test_connection(ser):
    """Test if ESP32 is responsive"""
    try:
        log_general_debug("[DEBUG] Testing connection with 'time' command")
        _wake_serial(ser)
        ser.write(b"time\n")  # Simple command that should always work
        ser.flush()
        
        start_time = time.time()
        while time.time() - start_time < 2:
            if ser.in_waiting:
                response = ser.readline().decode(errors='ignore').strip()
                log_general_debug(f"[DEBUG] Connection test response: {response}")
                if response and "RTC not available" not in response:
                    return True
        log_general_debug("[DEBUG] Connection test timeout - no response")
        return False
    except Exception as e:
        log_general_debug(f"[DEBUG] Connection test failed: {e}")
        return False


# =============================================================================
# MAIN DASHBOARD LAYOUT
# =============================================================================

# Header with logo
st.image("EB_logo.png", width=200)
st.title("Implant RFID Reader Multi-Button Dashboard")
st.markdown("Connect to your ESP32 RFID reader with multi-button support and retrieve readings by date range")


tabs = st.tabs(["RFID Reader Dashboard", "Configuration", "User Guide"])

with tabs[0]:
    st.sidebar.header("🔌 Connection Settings")
    available_ports = get_available_ports()
    if not available_ports:
        st.sidebar.error("No serial ports found!")
    else:
        selected_port = st.sidebar.selectbox(
            "Select Serial Port:",
            available_ports,
            index=0 if available_ports else None
        )
        baud_rate = st.sidebar.selectbox(
            "Baud Rate:",
            [9600, 115200, 230400, 460800],
            index=1
        )
        col1, col2 = st.sidebar.columns(2)
        if not st.session_state.connected:
            if col1.button("🔗 Connect"):
                st.session_state.serial_connection = connect_to_arduino(selected_port, baud_rate)
                if st.session_state.serial_connection:
                    st.session_state.connected = True
                    st.sidebar.success("Connected!")
                else:
                    st.sidebar.error("Connection failed!")
        else:
            if col2.button("❌ Disconnect"):
                if st.session_state.serial_connection:
                    try:
                        st.session_state.serial_connection.close()
                    except Exception as e:
                        log_general_debug(f"[DEBUG] Error closing serial connection: {e}")
                st.session_state.connected = False
                st.session_state.serial_connection = None
                st.sidebar.info("Disconnected!")
        
    if st.session_state.connected:
        st.success("✅ Connected to RFID Reader")
        
        
        # Dashboard Mode Control Instructions
        st.info("""
        **🔘 Dashboard Mode Control:**
        - **Long Press Button**: Toggle Dashboard Mode ON/OFF
        - **Dashboard Mode ON**: ESP32 stays awake, no periodic reads
        - **Dashboard Mode OFF**: ESP32 uses light sleep, periodic reads enabled
        - **Configure Long Press Timer**: Use the Configuration tab below
        """)
        
        # Timezone selection
        st.header("🌍 Display Timezone")
        timezone_options = {
            'America/Costa_Rica': 'Costa Rica (UTC-6)',
            'UTC': 'UTC',
            'America/New_York': 'New York (UTC-5/-4)',
            'America/Los_Angeles': 'Los Angeles (UTC-8/-7)',
            'Europe/London': 'London (UTC+0/+1)',
            'Europe/Paris': 'Paris (UTC+1/+2)',
            'Asia/Tokyo': 'Tokyo (UTC+9)',
            'Australia/Sydney': 'Sydney (UTC+10/+11)'
        }
        
        selected_timezone = st.selectbox(
            "Choose timezone for displaying timestamps:",
            options=list(timezone_options.keys()),
            format_func=lambda x: timezone_options[x],
            index=list(timezone_options.keys()).index(st.session_state['selected_timezone'])
        )
        st.session_state['selected_timezone'] = selected_timezone
        
        st.header("📅 Select Date Range")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "Start Date:",
                value=datetime.now().date() - timedelta(days=7)
            )
            start_time = st.time_input("Start Time:", value=dt_time(0, 0))
        with col2:
            end_date = st.date_input(
                "End Date:",
                value=datetime.now().date()
            )
            end_time = st.time_input("End Time:", value=dt_time(0, 0))
        start_dt = datetime.combine(start_date, start_time)
        end_dt = datetime.combine(end_date, end_time)
        
        # Convert selected timezone to UTC for ESP32 query
        import pytz
        local_tz = pytz.timezone(selected_timezone)
        start_dt_local = local_tz.localize(start_dt)
        end_dt_local = local_tz.localize(end_dt)
        start_epoch = int(start_dt_local.astimezone(pytz.UTC).timestamp())
        end_epoch = int(end_dt_local.astimezone(pytz.UTC).timestamp())

        # Always show Retrieve Data button right below pickers
        retrieve_clicked = st.button("🔍 Retrieve Data", type="primary")

        if retrieve_clicked:
            st.session_state['new_query'] = True
            with st.spinner("Retrieving data from RFID reader..."):
                command = f"range {start_epoch} {end_epoch}"
                response = send_command(st.session_state.serial_connection, command)
                # Always record something so the UI can show a summary area
                st.session_state['last_raw_response'] = response if response is not None else ""
                if response:
                    readings = parse_readings(response)
                    if readings:
                        df = pd.DataFrame(readings)
                        if 'Timestamp' in df.columns:
                            # Convert timestamps to selected timezone
                            df['Timestamp'] = df['Timestamp'].apply(
                                lambda x: convert_timestamp_to_timezone(x, st.session_state['selected_timezone'])
                            )
                            ts_split = df['Timestamp'].apply(lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S'))
                            df = df.assign(
                                Year=ts_split.dt.year,
                                Month=ts_split.dt.month,
                                Day=ts_split.dt.day,
                                Hour=ts_split.dt.hour,
                                Minute=ts_split.dt.minute
                            )
                            # Sort DataFrame by timestamp to ensure chronological order
                            df = df.sort_values('Timestamp')
                        st.session_state['last_df'] = df
                    else:
                        st.session_state['last_df'] = None
                else:
                    st.session_state['last_df'] = None
            st.session_state['new_query'] = False

        # Output below the button (only once)
        if 'last_raw_response' in st.session_state:
            raw_response = st.session_state['last_raw_response'] or ""
            summary_lines = []
            for line in raw_response.split('<DASHBOARD_DATA>')[0].splitlines():
                if line.strip().startswith('Found') or line.strip().startswith('First:') or line.strip().startswith('Last:'):
                    summary_lines.append(line)
            summary = '\n'.join(summary_lines) if summary_lines else "(no summary lines; device returned no markers or timed out)"
            st.text("Raw response from Arduino (summary only):")
            st.code(summary)
        if st.session_state.get('last_df') is not None:
            st.header("📋 RFID Readings")
            st.dataframe(st.session_state['last_df'], use_container_width=True)
            csv = st.session_state['last_df'].to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name="rfid_readings_last.csv",
                mime="text/csv"
            )
            # Plotly line plot: Timestamp vs Temperature_C, one line per Tag
            df = st.session_state['last_df']
            timezone_display = timezone_options.get(st.session_state['selected_timezone'], st.session_state['selected_timezone'])
            
            # Debug: Show data summary
            st.subheader("📊 Data Summary")
            st.write(f"Total records: {len(df)}")
            st.write(f"Unique tags: {df['Tag'].nunique()}")
            st.write(f"Tags found: {sorted(df['Tag'].unique())}")
            st.write(f"Date range: {df['Timestamp'].min()} to {df['Timestamp'].max()}")
            
            if not df.empty:
                # Ensure Temperature_C is numeric
                df['Temperature_C'] = pd.to_numeric(df['Temperature_C'], errors='coerce')
                
                # Remove any rows with NaN temperature values
                df_clean = df.dropna(subset=['Temperature_C'])
                
                if len(df_clean) != len(df):
                    st.warning(f"⚠️ Removed {len(df) - len(df_clean)} rows with invalid temperature data")
                
                fig = px.line(
                    df_clean,
                    x="Timestamp",
                    y="Temperature_C",
                    color="Tag",
                    title=f"Temperature vs Timestamp by Tag ({timezone_display})",
                    labels={"Temperature_C": "Temperature (°C)", "Timestamp": "Timestamp", "Tag": "Tag"}
                )
                
                # Improve plot configuration for better data visibility
                fig.update_layout(
                    xaxis_title="Timestamp", 
                    yaxis_title="Temperature (°C)",
                    hovermode='x unified',  # Show all data points on hover
                    showlegend=True
                )
                
                # Configure x-axis to show more detailed time information
                fig.update_xaxes(
                    tickformat='%Y-%m-%d %H:%M',
                    tickangle=45,
                    nticks=10  # Show more tick marks
                )
                
                # Configure y-axis for better temperature display
                fig.update_yaxes(
                    tickformat='.1f',  # Show one decimal place
                    range=[df_clean['Temperature_C'].min() - 1, df_clean['Temperature_C'].max() + 1]
                )
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                fig = px.line(title=f"Temperature vs Timestamp by Tag ({timezone_display})")
                fig.update_layout(xaxis_title="Timestamp", yaxis_title="Temperature (°C)")
                st.plotly_chart(fig, use_container_width=True)
        else:
            # Show blank plot if no results
            fig = px.line(title="Temperature vs Timestamp by Tag")
            fig.update_layout(xaxis_title="Timestamp", yaxis_title="Temperature (°C)")
            st.plotly_chart(fig, use_container_width=True)
        st.header("⚡ Quick Commands")
        
        # Create single-button-per-row layout for maximum display space
        st.subheader("📊 Data Management")
        
        # Print All Button
        if st.button("📊 Print All", use_container_width=True):
            response = send_command(st.session_state.serial_connection, "print")
            if response:
                st.text("All stored readings:")
                st.code(response)
        
        # Clear Storage Button
        if 'clear_confirm' not in st.session_state:
            st.session_state['clear_confirm'] = False
        if st.button("🗑️ Clear Storage", use_container_width=True):
            st.session_state['clear_confirm'] = True
        if st.session_state['clear_confirm']:
            st.warning("⚠️ **Clear All Data**")
            st.warning("Are you sure you want to clear all stored readings? This action cannot be undone.")
            password = st.text_input("Enter password to confirm:", type="password", key="clear_password")
            if st.button("⚠️ Confirm Clear", key="confirm_clear"):
                if password == CLEAR_PASSWORD:
                    response = send_command(st.session_state.serial_connection, "clear")
                    if response:
                        st.success("✅ Memory Cleared Successfully!")
                        st.info("All stored RFID readings have been permanently deleted from the device.")
                    else:
                        st.error("❌ Failed to clear storage. Please try again.")
                    # Update session state and trigger rerun
                    st.session_state.update({
                        'clear_confirm': False
                    })
                    st.rerun()
                else:
                    st.error("❌ Incorrect password. Storage not cleared.")
        
        st.divider()
        
        st.subheader("🔧 System Diagnostics")
        
        # Debug Info Button
        if st.button("🔢 Debug Info", use_container_width=True):
            response = send_command(st.session_state.serial_connection, "debug")
            if response:
                st.text("Debug information:")
                st.code(response)
        
        # Test Connection Button
        if st.button("🔍 Test Connection", use_container_width=True):
            if test_connection(st.session_state.serial_connection):
                st.success("✅ ESP32 is responsive!")
            else:
                st.error("❌ ESP32 not responding")
        
        st.divider()
        
        st.subheader("🔘 Multi-Button Control")
        
        # Button Mode Button
        if st.button("🔘 Button Mode", use_container_width=True):
            response = send_command(st.session_state.serial_connection, "buttonmode")
            if response:
                st.text("Multi-Button Status:")
                st.code(response)
        
        # Physical Button Testing Info
        st.info("""
        **Physical Button Testing:**
        - **Short Press**: Manual RFID reading
        - **Long Press**: Toggle Dashboard Mode
        - **Duration**: Configure in Settings tab
        """)
    else:
        st.info("🔌 Please connect to your RFID reader using the sidebar.")

with tabs[1]:
    st.title("⚙️ Configuration")
    st.markdown("Set and program ESP32 variables via serial.")
    # Read values from session state if available
    if 'pending_esp32_update' in st.session_state and st.session_state['pending_esp32_update']:
        # Apply pending updates and rerun
        st.session_state.update(st.session_state['pending_esp32_update'])
        st.session_state['pending_esp32_update'] = None
        st.rerun()
    ssid = st.text_input("WiFi SSID", key="esp32_ssid")
    password = st.text_input("WiFi Password", type="password", key="esp32_password")
    rfidOnTime = st.number_input("RFID ON Time (seconds)", min_value=1, max_value=60, key="esp32_rfidOnTime")
    periodicInterval = st.number_input("Periodic Interval (seconds)", min_value=10, max_value=3600, key="esp32_periodicInterval")
    longPressTime = st.number_input("Long Press Timer (seconds)", min_value=1, max_value=30, key="esp32_longPressTime", 
                                   help="Duration to hold button for dashboard mode toggle")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Set Variables on ESP32"):
            st.session_state['set_debug_log'] = []  # Clear previous set debug log
            if st.session_state.connected:
                cmds = [
                    f"set ssid {ssid}",
                    f"set password {password}",
                    f"set rfidOnTimeMs {int(rfidOnTime*1000)}",
                    f"set periodicIntervalMs {int(periodicInterval*1000)}",
                    f"set longPressMs {int(longPressTime*1000)}"
                ]
                for cmd in cmds:
                    log_set_debug(f"[DEBUG] Sending command: {cmd}")
                    resp = send_command(st.session_state.serial_connection, cmd)
                    # Move 'OK' to immediately after 'Response received:' if present
                    if resp:
                        lines = resp.splitlines()
                        ok_lines = [line for line in lines if line.strip() == 'OK']
                        other_lines = [line for line in lines if line.strip() != 'OK']
                        if ok_lines:
                            log_set_debug(f"[DEBUG] Response received:\nOK\n" + "\n".join(other_lines))
                        else:
                            log_set_debug(f"[DEBUG] Response received:\n" + resp)
                    else:
                        log_set_debug(f"[DEBUG] Response received: (empty response)")
            else:
                log_set_debug("[DEBUG] Not connected to ESP32.")
    with col2:
        if st.button("Read Variables from ESP32"):
            st.session_state['debug_log'] = []  # Clear previous read debug log
            if st.session_state.connected:
                vars = ["ssid", "password", "rfidOnTimeMs", "periodicIntervalMs", "longPressMs"]
                updates = {}
                for v in vars:
                    resp = get_variable_with_markers(st.session_state.serial_connection, v)
                    if v == "ssid":
                        updates["esp32_ssid"] = resp or ""
                    elif v == "password":
                        updates["esp32_password"] = resp or ""
                    elif v == "rfidOnTimeMs":
                        try:
                            # Convert milliseconds to seconds for display
                            updates["esp32_rfidOnTime"] = int(resp) / 1000 if resp else 5
                        except:
                            updates["esp32_rfidOnTime"] = 5
                    elif v == "periodicIntervalMs":
                        try:
                            # Convert milliseconds to seconds for display
                            updates["esp32_periodicInterval"] = int(resp) / 1000 if resp else 60
                        except:
                            updates["esp32_periodicInterval"] = 60
                    elif v == "longPressMs":
                        try:
                            # Convert milliseconds to seconds for display
                            updates["esp32_longPressTime"] = int(resp) / 1000 if resp else 5
                        except:
                            updates["esp32_longPressTime"] = 5
                st.session_state['pending_esp32_update'] = updates
                st.rerun()
            else:
                st.warning("Not connected to ESP32.")
    st.markdown("---")

    st.markdown("### SET Debug Log")
    for msg in st.session_state['set_debug_log']:
        for block in msg.split("\n\n"):
            if block.strip():
                st.code(block)
    st.markdown("### READ Debug Log")
    for msg in st.session_state['debug_log']:
        st.code(msg)
    st.markdown("### General Debug Log")
    for msg in st.session_state['general_debug_log']:
        st.code(msg)

with tabs[2]:
    st.title("📖 User Guide")
    st.markdown("Comprehensive guide for using the Implant RFID Reader Multi-Button Dashboard.")
    
    # Connection Guide
    with st.expander("🔌 Connection Setup", expanded=False):
        st.markdown("""
        **Step-by-step connection process:**
        
        1. **Hardware Connection**
           - Connect ESP32 to computer via USB cable
           - Ensure ESP32 is powered on (LED indicators should be active)
           - Check that the RFID module is properly connected
        
        2. **Serial Port Selection**
           - Open the dashboard and navigate to the sidebar
           - Select the correct serial port from the dropdown
           - Common ports: `/dev/ttyUSB0` (Linux), `COM3` (Windows), `/dev/cu.usbserial-*` (macOS)
           - Choose baud rate: **115200** (recommended)
        
        3. **Establish Connection**
           - Click the "🔗 Connect" button
           - Wait for "Connected!" confirmation
           - If connection fails, try different ports or baud rates
        
        4. **Verification**
           - Use "🔍 Test Connection" to verify ESP32 responsiveness
           - Check that you can retrieve data successfully
        """)
    
    # Multi-Button Guide
    with st.expander("🔘 Multi-Button Functionality", expanded=False):
        st.markdown("""
        **Understanding the Multi-Button System:**
        
        **Short Press (Quick Tap)**
        - **Function**: Manual RFID reading
        - **Works in**: Both Dashboard Mode and Normal Mode
        - **LED Feedback**: Green flash when tag detected
        - **Use Case**: Immediate RFID scanning when needed
        
        **Long Press (Hold for configured duration)**
        - **Function**: Toggle Dashboard Mode ON/OFF
        - **Default Duration**: 5 seconds (configurable)
        - **LED Feedback**: 
          - Red LED when Dashboard Mode is ON
          - Blue LED when Dashboard Mode is OFF
        - **Use Case**: Switch between operational modes
        
        **Dashboard Mode States:**
        - **ON**: ESP32 stays awake, no periodic reads, fully responsive to dashboard
        - **OFF**: Light sleep between reads, periodic RFID scanning enabled
        """)
    
    # Data Retrieval Guide
    with st.expander("📊 Data Retrieval & Analysis", expanded=False):
        st.markdown("""
        **Retrieving RFID Data:**
        
        1. **Date Range Selection**
           - Choose start and end dates for your data query
           - Select start and end times (24-hour format)
           - Timezone selection affects display (data stored in UTC)
        
        2. **Data Retrieval Process**
           - Click "🔍 Retrieve Data" to fetch readings
           - ESP32 searches through stored readings for the specified range
           - Data is parsed and displayed in a table format
        
        3. **Data Analysis Features**
           - **CSV Export**: Download data for external analysis
           - **Temperature Plotting**: Visualize temperature trends over time
           - **Tag Filtering**: View data by specific RFID tags
           - **Timezone Conversion**: Display data in your local timezone
        
        4. **Data Visualization**
           - Interactive plots show temperature vs. timestamp
           - Different colors for different RFID tags
           - Hover for detailed information
           - Zoom and pan capabilities
        """)
    
    # Configuration Guide
    with st.expander("⚙️ Configuration Management", expanded=False):
        st.markdown("""
        **ESP32 Configuration Options:**
        
        **WiFi Settings**
        - **SSID**: Network name for ESP32 to connect
        - **Password**: Network password
        - **Purpose**: Enables RTC time synchronization via NTP
        
        **RFID Settings**
        - **RFID ON Time**: Duration RFID module stays active (1-60 seconds)
        - **Periodic Interval**: Time between automatic reads (10-3600 seconds)
        - **Purpose**: Controls power consumption and reading frequency
        
        **Multi-Button Settings**
        - **Long Press Timer**: Duration to hold button for dashboard mode (1-30 seconds)
        - **Purpose**: Prevents accidental dashboard mode activation
        
        **Configuration Process:**
        1. Set desired values in the Configuration tab
        2. Click "Set Variables on ESP32" to apply changes
        3. Use "Read Variables from ESP32" to verify current settings
        4. Changes take effect immediately (no reboot required)
        """)
    
    # Troubleshooting Guide
    with st.expander("🔧 Troubleshooting", expanded=False):
        st.markdown("""
        **Common Issues and Solutions:**
        
        **Connection Problems**
        - **No serial ports found**: Check USB connection, install drivers
        - **Connection failed**: Try different baud rates (9600, 115200, 230400)
        - **ESP32 not responding**: Check power, try reset button
        
        **Data Retrieval Issues**
        - **No data returned**: Check date range, verify readings exist
        - **Timeout errors**: ESP32 may be in deep sleep, try manual wake
        - **Partial data**: Increase timeout in dashboard settings
        
        **Multi-Button Issues**
        - **Button not responding**: Check physical connection, try different press duration
        - **Dashboard mode not toggling**: Verify long press duration setting
        - **LED not changing**: Check LED wiring, verify firmware version
        
        **RFID Reading Problems**
        - **No tags detected**: Check RFID module power, verify tag placement
        - **Communication errors**: Check RFID module wiring, try different power settings
        - **Temperature readings**: Verify tag compatibility, check calibration
        
        **Performance Optimization**
        - **Slow data retrieval**: Reduce date range, optimize periodic interval
        - **High power consumption**: Increase sleep intervals, reduce RFID on-time
        - **Memory issues**: Clear old readings, optimize storage settings
        """)
    
    # Hardware Guide
    with st.expander("🔌 Hardware Setup", expanded=False):
        st.markdown("""
        **Required Components:**
        - ESP32 development board
        - RFID reader module (134.2 kHz)
        - DS1307 RTC module
        - Push button (normally open)
        - RGB LED (common cathode)
        - Power supply (3.3V/5V)
        
        **Pin Connections:**
        - **Button**: GPIO 17 (with pull-up resistor)
        - **RFID Power**: GPIO 16 (active LOW)
        - **RFID TX**: GPIO 15 (UART communication)
        - **RTC**: I2C (SDA/SCL pins)
        - **RGB LED**: GPIO 18 (Red), GPIO 19 (Green), GPIO 4 (Blue)
        
        **Power Requirements:**
        - ESP32: 3.3V, ~240mA active, ~10mA sleep
        - RFID Module: 3.3V-5V, ~50mA when active
        - RTC Module: 3.3V-5V, ~1mA continuous
        - Total: ~300mA active, ~15mA sleep
        
        **LED Status Indicators:**
        - **White**: Booting/initialization
        - **Blue**: Normal sleep mode
        - **Green**: Successful RFID reading (1 second flash)
        - **Red**: Dashboard mode active
        """)
    
    # Software Guide
    with st.expander("💻 Software & Firmware", expanded=False):
        st.markdown("""
        **Firmware Features:**
        - **Light Sleep Mode**: Low power consumption between reads
        - **Multi-Button Support**: Single button for multiple functions
        - **Dashboard Mode**: Stay awake for real-time communication
        - **Configurable Timers**: Adjustable button and reading intervals
        - **Data Storage**: SPIFFS-based reading storage
        - **RTC Integration**: Accurate timestamping with DS1307
        
        **Dashboard Features:**
        - **Real-time Communication**: Serial-based data exchange
        - **Timezone Support**: Multiple timezone display options
        - **Data Visualization**: Interactive plots and charts
        - **CSV Export**: Data export for external analysis
        - **Configuration Management**: Remote ESP32 configuration
        - **Multi-timezone Display**: Convert UTC to local time
        
        **System Requirements:**
        - **Python 3.8+**: Required for dashboard
        - **Streamlit**: Web interface framework
        - **PySerial**: Serial communication
        - **Plotly**: Data visualization
        - **Pandas**: Data manipulation
        - **PyTZ**: Timezone handling
        
        **Installation:**
        ```bash
        pip install streamlit pandas pyserial plotly pytz
        streamlit run rfid_dashboard_configure_lightsleep_multibutton.py
        ```
        """)

# =============================================================================
# COPYRIGHT FOOTER
# =============================================================================

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 12px; padding: 20px;'>
    <p><strong>Implant RFID Reader Multi-Button Dashboard v1.2</strong></p>
    <p>© 2025 Establishment Labs. All rights reserved.</p>
    <p>Developed by <a href='mailto:info@littleendianengineering.com' style='color: #666;'>Little Endian Engineering</a></p>
    <p>Contact: <a href='mailto:lyu@establishmentlabs.com' style='color: #666;'>lyu@establishmentlabs.com</a></p>
    <p style='font-size: 10px; margin-top: 10px;'>CONFIDENTIAL - PROPRIETARY SOFTWARE</p>
</div>
""", unsafe_allow_html=True)
