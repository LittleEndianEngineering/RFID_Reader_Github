"""
Implant RFID Reader - Multi-Button Dashboard Application (ESP32-S3)
===================================================================

PROPRIETARY SOFTWARE
Copyright (c) 2025 Establishment Labs
Developed by Little Endian Engineering

Version: 3.0 (ESP32-S3 + Dashboard Mode Persistence + macOS Connection Improvements)
Date: November 2025

DESCRIPTION:
Streamlit-based dashboard for Implant RFID Reader ESP32-S3 device with multi-button support and RGB LED status indicators.
Provides real-time data visualization, filtering, and configuration management.
Supports multiple timezones, CSV export functionality, configurable button timings, and hardware LED status monitoring.
Includes Dashboard Mode persistence and improved macOS connection stability.

FEATURES:
- Real-time serial communication with ESP32-S3
- Multi-button functionality (short press = RFID read, long press = dashboard mode toggle)
- RGB LED status indicators for visual feedback
- Configurable long press timer for dashboard mode activation (1-30 seconds)
- Date range filtering with timezone support
- Interactive data visualization with Plotly
- CSV export functionality
- ESP32-S3 configuration management
- Multi-timezone display support
- Password-protected storage clearing
- Comprehensive User Guide with hardware setup instructions
- Dashboard Mode persistence (survives device resets)
- Improved macOS connection handling for ESP32-S3 USB-CDC

REQUIREMENTS:
- Python 3.8+
- Streamlit, Pandas, PySerial, Plotly, PyTZ
- ESP32-S3 device with Multi-Button Implant RFID Reader firmware

USAGE:
streamlit run rfid_dashboard_configure_lightsleep_multibutton_S3.py

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
# termios is only available on Unix-like systems (macOS/Linux), not Windows
try:
    import termios  # For serial error handling on macOS/Linux
    SERIAL_EXCEPTIONS = (OSError, termios.error, AttributeError)
except ImportError:
    termios = None  # Windows doesn't have termios module
    SERIAL_EXCEPTIONS = (OSError, AttributeError)  # Windows-compatible exceptions

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
if 'connected_port' not in st.session_state:
    st.session_state.connected_port = None
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
# Initialize Live View session state
if 'live_view_enabled' not in st.session_state:
    st.session_state['live_view_enabled'] = False
if 'live_view_start_timestamp' not in st.session_state:
    st.session_state['live_view_start_timestamp'] = None
if 'last_live_update' not in st.session_state:
    st.session_state['last_live_update'] = 0
if 'is_auto_refresh' not in st.session_state:
    st.session_state['is_auto_refresh'] = False
if 'last_successful_update' not in st.session_state:
    st.session_state['last_successful_update'] = None
if 'connection_error_count' not in st.session_state:
    st.session_state['connection_error_count'] = 0
if 'last_connection_test' not in st.session_state:
    st.session_state['last_connection_test'] = 0

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

def close_serial_port_if_open(port_name):
    """Attempt to close a serial port if it's open at OS level"""
    """This is useful when page refreshes and port is still open from previous session"""
    try:
        log_general_debug(f"[CLEANUP] Attempting to close port {port_name} if it's open...")
        # Try to open the port with a very short timeout
        test_ser = None
        try:
            test_ser = serial.Serial(port_name, 115200, timeout=0.1)
            if test_ser.is_open:
                log_general_debug(f"[CLEANUP] Port {port_name} was open - closing it")
                test_ser.close()
                time.sleep(0.3)  # Give OS time to release the port
                log_general_debug(f"[CLEANUP] Port {port_name} closed successfully")
                return True
        except serial.SerialException as e:
            error_msg = str(e).lower()
            if "already open" in error_msg or "busy" in error_msg:
                # Port is already open by another process - we can't close it
                log_general_debug(f"[CLEANUP] Port {port_name} is already open by another process - cannot close")
                return False
            # Port is not open or doesn't exist - that's fine
            log_general_debug(f"[CLEANUP] Port {port_name} is not open or doesn't exist")
            return True
        except Exception as e:
            log_general_debug(f"[CLEANUP] Error checking port {port_name}: {e}")
            return False
        finally:
            if test_ser and test_ser.is_open:
                try:
                    test_ser.close()
                except Exception:
                    pass
    except Exception as e:
        log_general_debug(f"[CLEANUP] Unexpected error closing port {port_name}: {e}")
        return False

def connect_to_arduino(port, baud_rate=115200):
    """Establish serial connection to ESP32 device without causing reset"""
    try:
        log_general_debug(f"[CONNECTION] Starting connection to {port}")
        log_general_debug(f"[CONNECTION] Parameters: baud={baud_rate}, dsrdtr=False, rtscts=False")
        
        # CRITICAL: Open serial port with dsrdtr=False and rtscts=False to prevent
        # DTR/RTS toggling during initialization, which causes ESP32 to reset
        # This is especially important when Dashboard Mode is already active
        # 
        # IMPORTANT: On macOS, even with these flags, DTR/RTS may toggle during port opening
        # We need to set them to False immediately and repeatedly to prevent resets
        log_general_debug(f"[CONNECTION] Opening serial port...")
        ser = serial.Serial(
            port, 
            baud_rate, 
            timeout=2,
            dsrdtr=False,  # Disable DSR/DTR flow control (prevents reset)
            rtscts=False,  # Disable RTS/CTS flow control (prevents reset)
            write_timeout=2  # Add write timeout to prevent hanging
        )
        log_general_debug(f"[CONNECTION] Port opened successfully")
        
        # CRITICAL: Set DTR/RTS to False IMMEDIATELY after opening (before any delays or operations)
        # This must happen in a tight loop to ensure they're set before any other operations
        # macOS may toggle these during port opening, so we set them multiple times
        log_general_debug(f"[CONNECTION] Setting DTR/RTS to False (attempt 1/3)...")
        for attempt in range(3):  # Set multiple times to ensure they stick
            try:
                dtr_before = ser.dtr if hasattr(ser, 'dtr') else 'N/A'
                rts_before = ser.rts if hasattr(ser, 'rts') else 'N/A'
                ser.dtr = False
                ser.rts = False
                dtr_after = ser.dtr if hasattr(ser, 'dtr') else 'N/A'
                rts_after = ser.rts if hasattr(ser, 'rts') else 'N/A'
                log_general_debug(f"[CONNECTION] Attempt {attempt+1}/3: DTR {dtr_before}->{dtr_after}, RTS {rts_before}->{rts_after}")
            except Exception as e:
                log_general_debug(f"[CONNECTION] Error setting DTR/RTS on attempt {attempt+1}: {e}")
            time.sleep(0.01)  # Tiny delay between attempts
        
        # Additional delay to ensure DTR/RTS are stable and port is ready
        # This prevents any residual toggling from causing resets
        time.sleep(0.1)
        
        # Verify DTR/RTS are still False (macOS might have toggled them)
        try:
            dtr_state = ser.dtr if hasattr(ser, 'dtr') else 'N/A'
            rts_state = ser.rts if hasattr(ser, 'rts') else 'N/A'
            log_general_debug(f"[CONNECTION] Verification: DTR={dtr_state}, RTS={rts_state}")
            if ser.dtr or ser.rts:
                log_general_debug(f"[CONNECTION] WARNING: DTR/RTS were toggled - resetting to False")
                ser.dtr = False
                ser.rts = False
                time.sleep(0.05)  # Small delay after correction
                log_general_debug(f"[CONNECTION] After correction: DTR={ser.dtr}, RTS={ser.rts}")
        except Exception as e:
            log_general_debug(f"[CONNECTION] Error verifying DTR/RTS: {e}")
        
        # Minimal delay - just enough for USB-CDC to recognize the connection
        # Reduced delay since device is already awake in Dashboard Mode
        log_general_debug(f"[CONNECTION] Waiting for USB-CDC to stabilize...")
        time.sleep(0.1)
        
        # Clear buffers AFTER DTR/RTS are set and port is stable
        # Only clear if port is confirmed open
        # Use flush instead of reset to be gentler on the connection
        try:
            if ser.is_open:
                log_general_debug(f"[CONNECTION] Flushing input/output buffers...")
                ser.flushInput()
                ser.flushOutput()
                log_general_debug(f"[CONNECTION] Buffers flushed successfully")
        except Exception as e:
            log_general_debug(f"[CONNECTION] Buffer flush warning: {e}")
        
        log_general_debug(f"[CONNECTION] Connection established successfully to {port}")
        return ser
    except serial.SerialException as e:
        error_msg = str(e).lower()
        if "already open" in error_msg or "busy" in error_msg or "access denied" in error_msg:
            st.error(f"⚠️ Port {port} is already in use.")
            st.info("💡 **Solution:** This can happen after a page refresh. Wait a few seconds and try again, or close Arduino IDE Serial Monitor if it's open.")
            log_general_debug(f"[CONNECTION] Port busy error: {e}")
            log_general_debug(f"[CONNECTION] Port may be in use by Arduino IDE, another application, or a previous connection")
            log_general_debug(f"[CONNECTION] Suggestion: Wait a moment for the port to be released, then retry")
        else:
            st.error(f"Failed to connect: {e}")
            log_general_debug(f"[CONNECTION] Connection error: {e}")
        return None
    except Exception as e:
        st.error(f"Failed to connect: {e}")
        log_general_debug(f"[DEBUG] Unexpected connection error: {e}")
        return None

def is_serial_valid(ser):
    """Check if serial connection is still valid and can be used"""
    if ser is None:
        return False
    try:
        # Check if port is open
        if not ser.is_open:
            return False
        # Try to read port name to verify it's still accessible
        _ = ser.port
        # Try a gentle operation to verify connection is alive
        # Don't actually read/write, just check if port is accessible
        return True
    except (ValueError,) + SERIAL_EXCEPTIONS:
        return False

def test_connection_quick(ser):
    """Quick connection test - checks if ESP32 responds to a simple command"""
    if not is_serial_valid(ser):
        return False
    try:
        # Clear any pending data
        ser.reset_input_buffer()
        # Send a simple status command
        ser.write(b"status\n")
        ser.flush()
        time.sleep(0.1)  # Short wait for response
        
        # Check if we get any response within timeout
        start_time = time.time()
        while time.time() - start_time < 1.0:  # 1 second timeout
            if ser.in_waiting:
                response = ser.readline().decode(errors='ignore').strip()
                if response and ("CMD_RECEIVED" in response or "Dashboard Mode" in response or "ACTIVE" in response or "INACTIVE" in response):
                    return True
        return False
    except Exception as e:
        log_general_debug(f"[DEBUG] Quick connection test failed: {e}")
        return False

def is_port_already_open(port, existing_connection):
    """Check if a serial port is already open by checking if we have a valid connection to it"""
    # NOTE: We cannot safely check if port is open without opening it (which causes reset)
    # Instead, we rely on our connection object tracking
    # If we have a valid connection object, the port is effectively "open" to us
    if existing_connection and is_serial_valid(existing_connection):
        # Check if it's the same port
        try:
            if existing_connection.port == port:
                return True
        except Exception:
            pass
    return False

def _wake_serial(ser, wake_delay=WAKE_DELAY):
    """
    Wake the ESP32 from Light Sleep via UART RX.
    Sends a single newline (likely consumed), waits a beat, then clears any partials.
    """
    try:
        if ser is None or not is_serial_valid(ser):
            return
        ser.write(b"\n")       # wake byte - device will wake but this byte is lost
        ser.flush()
        time.sleep(wake_delay) # give ESP32 time to fully wake clocks
        # REMOVED: ser.reset_input_buffer() - this was clearing responses!
    except SERIAL_EXCEPTIONS as e:
        log_debug(f"[DEBUG] Wake error: {e}")
        raise  # Re-raise to be handled by caller
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
            # Also handles: #200: 2025-07-23 05:13:05, 999, 141004265912, N/A (for tags without temperature)
            debug_match = re.search(r'#\d+:\s*\[DEBUG\]\s*raw_timestamp=\d+,\s*converted=([\d\-]+\s[\d:]+),\s*([\d]+),\s*([\d]+),\s*((?:[\d.]+°C|N/A))', line)
            normal_match = re.search(r'#\d+:\s*([\d\-]+\s[\d:]+),\s*([\d]+),\s*([\d]+),\s*((?:[\d.]+°C|N/A))', line)
            
            if debug_match:
                timestamp, value1, tag, temp = debug_match.groups()
                # Remove °C suffix if present, keep "N/A" as is
                if temp == 'N/A':
                    temp_value = 'N/A'
                else:
                    temp_value = temp.replace('°C', '')
                readings.append({
                    'Timestamp': timestamp,
                    'Value1': value1,
                    'Tag': tag,
                    'Temperature_C': temp_value
                })
            elif normal_match:
                timestamp, value1, tag, temp = normal_match.groups()
                # Remove °C suffix if present, keep "N/A" as is
                if temp == 'N/A':
                    temp_value = 'N/A'
                else:
                    temp_value = temp.replace('°C', '')
                readings.append({
                    'Timestamp': timestamp,
                    'Value1': value1,
                    'Tag': tag,
                    'Temperature_C': temp_value
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
    # Check if serial connection is still valid
    if not is_serial_valid(ser):
        log_debug(f"[ERROR] Serial connection is invalid for get {var}")
        st.error("⚠️ Serial connection lost. Please reconnect to the device.")
        st.session_state.connected = False
        st.session_state.connected_port = None
        st.session_state.serial_connection = None
        return None
    
    try:
        # Wake device and clear any old data
        _wake_serial(ser)
        ser.reset_input_buffer()
    except SERIAL_EXCEPTIONS as e:
        log_debug(f"[ERROR] Serial error in get_variable_with_markers for {var}: {e}")
        st.error(f"⚠️ Serial communication error: {e}. Please reconnect to the device.")
        st.session_state.connected = False
        st.session_state.connected_port = None
        st.session_state.serial_connection = None
        return None
    
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
    
    try:
        log_debug(f"[DEBUG] Sending get command: get {var}")
        ser.write(f"get {var}\n".encode())
        ser.flush()
        time.sleep(0.05)
        
        lines_between = []
        found = False
        start_time = time.time()
        
        while time.time() - start_time < 4:  # Slightly increased timeout for light-sleep wake
            if not is_serial_valid(ser):
                log_debug(f"[ERROR] Serial connection lost during get {var}")
                st.error("⚠️ Serial connection lost during operation. Please reconnect.")
                st.session_state.connected = False
                st.session_state.connected_port = None
                st.session_state.serial_connection = None
                return None
            
            try:
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
            except SERIAL_EXCEPTIONS as e:
                log_debug(f"[ERROR] Serial read error during get {var}: {e}")
                st.error(f"⚠️ Serial read error: {e}. Please reconnect.")
                st.session_state.connected = False
                st.session_state.connected_port = None
                st.session_state.serial_connection = None
                return None
        
        log_debug(f"[DEBUG] Lines between markers for {var}: {lines_between}")
        value = next((l for l in lines_between if l and l != start_marker and l != end_marker), None)
        log_debug(f"[DEBUG] Final value for {var}: {value}")
        return value
    except SERIAL_EXCEPTIONS as e:
        log_debug(f"[ERROR] Serial error in get_variable_with_markers for {var}: {e}")
        st.error(f"⚠️ Serial communication error: {e}. Please reconnect to the device.")
        st.session_state.connected = False
        st.session_state.connected_port = None
        st.session_state.serial_connection = None
        return None

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
    # Validate connection state on startup - reset if stale
    # Note: When page is refreshed (F5), Streamlit creates a completely new session,
    # so all session state is reset. However, the serial port might still be open
    # at the OS level from the previous session. We handle this by closing the port
    # when the user tries to connect (see Connect button handler below).
    # Note: When browser reconnects after disconnection (screen saver, lock, etc.),
    # Streamlit session state variables are preserved, but the serial connection object
    # cannot be preserved across browser disconnections. We need to detect this and mark as disconnected.
    
    # Check if we have a connection state but no connection object
    if st.session_state.connected:
        if st.session_state.serial_connection is None:
            # Connection object is missing - this happens when:
            # 1. Browser disconnects (screen saver, lock) - session state preserved but connection object lost
            # 2. Page refresh (F5) - new session created, old connection state lost
            # In both cases, ESP32 is still in dashboard mode (which is desired), but we can't communicate with it
            log_general_debug("[DEBUG] Connection state exists but serial connection object is None - marking as disconnected")
            log_general_debug("[DEBUG] NOTE: ESP32 remains in dashboard mode - connection will be restored on reconnect")
            st.session_state.connected = False
            st.session_state.connected_port = None
            st.session_state['connection_error_count'] = 0
            # Keep Live View state enabled - user can reconnect and it will resume
        elif not is_serial_valid(st.session_state.serial_connection):
            # Connection object exists but is invalid - close it properly
            # Note: We keep dashboard mode ON on ESP32 - just close the serial connection
            log_general_debug("[DEBUG] Stale connection detected on startup - closing serial connection")
            log_general_debug("[DEBUG] NOTE: Dashboard mode remains ON on ESP32 - connection will be restored on reconnect")
            try:
                # Close the connection - dashboard mode stays active on ESP32
                st.session_state.serial_connection.close()
                log_general_debug("[DEBUG] Stale serial connection closed successfully")
            except Exception as e:
                log_general_debug(f"[DEBUG] Error closing stale connection: {e}")
            st.session_state.connected = False
            st.session_state.connected_port = None
            st.session_state.serial_connection = None
            st.session_state['connection_error_count'] = 0
        else:
            # Connection is valid - if Live View was enabled, it should resume
            if st.session_state.get('live_view_enabled', False):
                log_general_debug("[DEBUG] Live View was enabled - connection validated, should resume auto-refresh")
    
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
        
        # Use separate button variables to handle state changes properly
        connect_clicked = False
        disconnect_clicked = False
        
        if not st.session_state.connected:
            connect_clicked = col1.button("🔗 Connect")
        else:
            disconnect_clicked = col2.button("❌ Disconnect")
        
        # Handle Connect button
        if connect_clicked:
            # ROBUST CONNECTION HANDLING: Prevent ESP32 resets on macOS
            # CRITICAL: Opening serial ports on macOS with ESP32-S3 USB-CDC causes resets
            # Strategy: Check connection state FIRST, only open port if truly disconnected
            
            # Step 1: Check if we're already connected to the same port
            # This prevents reopening the port on every "Connect" click
            if (st.session_state.connected and 
                st.session_state.connected_port == selected_port and
                st.session_state.serial_connection and
                is_serial_valid(st.session_state.serial_connection)):
                # Already connected to same port with valid connection - REUSE IT (no reset)
                st.sidebar.success("✅ Already connected!")
                st.rerun()
                # Exit early to prevent any port operations
                connect_clicked = False
            
            # Step 2: If marked as connected but connection object is invalid, try to recover
            elif (st.session_state.connected and 
                  st.session_state.connected_port == selected_port and
                  st.session_state.serial_connection):
                # Connection object exists but validation failed - test it
                try:
                    if test_connection(st.session_state.serial_connection):
                        # Connection works! Keep using it
                        st.sidebar.success("✅ Connection recovered")
                        st.rerun()
                        connect_clicked = False
                    else:
                        # Connection is broken - mark as disconnected
                        log_general_debug("[DEBUG] Connection test failed - marking as disconnected")
                        st.session_state.connected = False
                        st.session_state.connected_port = None
                        try:
                            st.session_state.serial_connection.close()
                        except Exception:
                            pass
                        st.session_state.serial_connection = None
                except Exception as e:
                    # Test exception - connection is broken
                    log_general_debug(f"[DEBUG] Connection test exception: {e} - marking as disconnected")
                    st.session_state.connected = False
                    st.session_state.connected_port = None
                    try:
                        st.session_state.serial_connection.close()
                    except Exception:
                        pass
                    st.session_state.serial_connection = None
            
            # Step 3: If we have a connection to a different port, close it first
            if connect_clicked and st.session_state.serial_connection:
                try:
                    current_port = st.session_state.serial_connection.port
                    if current_port != selected_port:
                        log_general_debug(f"[DEBUG] Port changed from {current_port} to {selected_port} - closing old connection")
                        st.session_state.serial_connection.close()
                        st.session_state.serial_connection = None
                        st.session_state.connected = False
                        st.session_state.connected_port = None
                except Exception:
                    st.session_state.serial_connection = None
                    st.session_state.connected = False
                    st.session_state.connected_port = None
            
            # Step 4: Only open NEW connection if we're truly disconnected
            # This should ONLY happen on first connect or after explicit disconnect
            if connect_clicked and not st.session_state.connected:
                log_general_debug(f"[CONNECT] Step 4: Checking if we need to open new connection to {selected_port}")
                # Final check: if we somehow have a valid connection object but weren't marked as connected
                # This can happen if session state was cleared but connection object still exists
                if (st.session_state.serial_connection and 
                    is_serial_valid(st.session_state.serial_connection) and
                    hasattr(st.session_state.serial_connection, 'port') and
                    st.session_state.serial_connection.port == selected_port):
                    # We have a valid connection - just mark as connected (no reset!)
                    log_general_debug(f"[CONNECT] Found existing valid connection - reusing (no port open)")
                    st.session_state.connected = True
                    st.session_state.connected_port = selected_port
                    st.sidebar.success("✅ Connected!")
                    st.rerun()
                else:
                    # Truly need to open a new connection
                    # CRITICAL: Before opening, try to close the port if it's still open from previous session
                    # This handles the case where page was refreshed and port is still open at OS level
                    log_general_debug(f"[CONNECT] Preparing to open new connection to {selected_port}")
                    log_general_debug(f"[CONNECT] Attempting to close port if it's still open from previous session...")
                    port_closed = close_serial_port_if_open(selected_port)
                    if port_closed:
                        log_general_debug(f"[CONNECT] Port {selected_port} was open and has been closed - waiting for OS to release it")
                        time.sleep(0.5)  # Give OS time to fully release the port
                    
                    # NOTE: On macOS with ESP32-S3 USB-CDC, opening the port will cause a reset
                    # This is a platform limitation - DTR/RTS toggle during port opening cannot be prevented
                    # The reset happens during serial.Serial() constructor, before we can set DTR/RTS to False
                    log_general_debug(f"[CONNECT] Opening NEW connection to {selected_port}")
                    log_general_debug(f"[CONNECT] WARNING: On macOS, this will cause ESP32 reset (platform limitation)")
                    log_general_debug(f"[CONNECT] Current session state: connected={st.session_state.connected}, port={st.session_state.connected_port}")
                    
                    # Show info message about expected reset
                    st.sidebar.info("ℹ️ **Note:** On macOS, opening the port will reset the ESP32. This is expected and normal.")
                    
                    # Try to connect (single attempt - retries are handled inside connect_to_arduino if needed)
                    # Note: We don't retry here to avoid multiple ESP32 resets
                    st.session_state.serial_connection = connect_to_arduino(selected_port, baud_rate)
                    connection_success = (st.session_state.serial_connection is not None)
                    if st.session_state.serial_connection:
                        log_general_debug(f"[CONNECT] Connection object created successfully")
                        # Wait a bit for ESP32 to finish booting after reset (if reset occurred)
                        # Note: ESP32 should already be in dashboard mode when connecting
                        log_general_debug(f"[CONNECT] Waiting for ESP32 to stabilize connection...")
                        time.sleep(0.5)  # Brief delay for connection to stabilize
                        
                        st.session_state.connected = True
                        st.session_state.connected_port = selected_port  # Store port name (persists across reruns)
                        st.sidebar.success("✅ Connected!")
                        st.rerun()
                    else:
                        log_general_debug(f"[CONNECT] Connection failed")
                        st.session_state.connected = False
                        st.session_state.connected_port = None
                        # Error message already shown in connect_to_arduino
        
        # Handle Disconnect button
        if disconnect_clicked:
            if st.session_state.serial_connection:
                try:
                    # Close the serial connection - dashboard mode stays active on ESP32
                    # This allows reconnecting later without needing to re-enable dashboard mode
                    if is_serial_valid(st.session_state.serial_connection):
                        st.session_state.serial_connection.close()
                        log_general_debug(f"[DISCONNECT] Serial port closed successfully - dashboard mode remains ON on ESP32")
                    else:
                        log_general_debug(f"[DISCONNECT] Serial connection was already invalid")
                except Exception as e:
                    log_general_debug(f"[DISCONNECT] Error closing serial connection: {e}")
            st.session_state.connected = False
            st.session_state.connected_port = None  # Clear port name
            st.session_state.serial_connection = None
            st.sidebar.info("Disconnected! (Dashboard mode remains active on ESP32)")
            st.rerun()  # Force rerun to update button display
        
    if st.session_state.connected:
        # Validate connection on startup and periodically during Live View
        connection_valid = True
        if st.session_state.get('live_view_enabled', False):
            # Test connection every 30 seconds during Live View
            current_time = time.time()
            if current_time - st.session_state.get('last_connection_test', 0) > 30:
                st.session_state['last_connection_test'] = current_time
                connection_valid = test_connection_quick(st.session_state.serial_connection)
                if not connection_valid:
                    st.session_state['connection_error_count'] = st.session_state.get('connection_error_count', 0) + 1
                    if st.session_state['connection_error_count'] >= 3:
                        # Connection is dead - mark as disconnected
                        st.error("⚠️ **Connection Lost:** ESP32 is not responding. Please reconnect.")
                        st.session_state.connected = False
                        st.session_state.connected_port = None
                        try:
                            if st.session_state.serial_connection:
                                st.session_state.serial_connection.close()
                        except Exception:
                            pass
                        st.session_state.serial_connection = None
                        st.session_state['connection_error_count'] = 0
                        st.rerun()
                else:
                    st.session_state['connection_error_count'] = 0
        
        if st.session_state.connected:
            st.success("✅ Connected to RFID Reader")
            
            # Show connection status and last update time
            if st.session_state.get('live_view_enabled', False):
                col_status1, col_status2 = st.columns(2)
                with col_status1:
                    if st.session_state.get('last_successful_update'):
                        last_update = datetime.fromtimestamp(st.session_state['last_successful_update'])
                        st.caption(f"🕒 Last update: {last_update.strftime('%H:%M:%S')}")
                    else:
                        st.caption("🕒 Last update: Never")
                with col_status2:
                    if st.session_state.get('connection_error_count', 0) > 0:
                        st.warning(f"⚠️ Connection errors: {st.session_state['connection_error_count']}")
        
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
        
        # Date Range Section (always visible, but Retrieve Data button is disabled when Live View is active)
        # Read Live View state - use checkbox state as source of truth since checkbox is processed later
        # Also check stop flag - if stop was requested, Live View is definitely disabled
        # CRITICAL: Read checkbox state directly and check stop flag to determine if Live View is truly enabled
        checkbox_state_for_date_range = st.session_state.get('live_view_checkbox', False)
        stop_requested_for_date_range = st.session_state.get('live_view_stop_requested', False)
        # Live View is enabled only if checkbox is checked AND stop was NOT requested
        # If stop was requested OR checkbox is unchecked, Live View is disabled and button should be enabled
        live_view_enabled_for_date_range = checkbox_state_for_date_range and not stop_requested_for_date_range
        
        # Always show date range section (no longer hidden when Live View is enabled)
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
        # ESP32 stores all readings in UTC, so we need to convert user's local time to UTC
        import pytz
        local_tz = pytz.timezone(selected_timezone)
        # Use localize() to attach timezone info to naive datetime
        # is_dst=None will raise exception on ambiguous times (better than guessing)
        try:
            start_dt_local = local_tz.localize(start_dt, is_dst=None)
            end_dt_local = local_tz.localize(end_dt, is_dst=None)
        except pytz.AmbiguousTimeError:
            # Handle ambiguous time (DST transition) by using the later occurrence
            start_dt_local = local_tz.localize(start_dt, is_dst=False)
            end_dt_local = local_tz.localize(end_dt, is_dst=False)
        except pytz.NonExistentTimeError:
            # Handle non-existent time (DST transition) by using the next valid time
            start_dt_local = local_tz.localize(start_dt, is_dst=True)
            end_dt_local = local_tz.localize(end_dt, is_dst=True)
        # Convert to UTC epoch timestamps for ESP32
        start_epoch = int(start_dt_local.astimezone(pytz.UTC).timestamp())
        end_epoch = int(end_dt_local.astimezone(pytz.UTC).timestamp())

        # Initialize Live View date range variables (used for auto-refresh)
        # These will be recalculated if Live View is enabled
        start_epoch_live = None
        end_epoch_live = None
        
        # Check Live View state BEFORE calculating date range
        # We need to check the checkbox state directly here, not the calculated variable
        # because the checkbox is processed later in the code
        live_view_checkbox_state_for_calc = st.session_state.get('live_view_checkbox', False)
        stop_requested_for_calc = st.session_state.get('live_view_stop_requested', False)
        live_view_truly_enabled_for_calc = live_view_checkbox_state_for_calc and not stop_requested_for_calc
        
        # When Live View is enabled, prepare date range from when checkbox was enabled to now
        # This is used for auto-refresh, not for manual Retrieve Data button
        if live_view_truly_enabled_for_calc:
            # Live View is enabled - prepare date range from when checkbox was enabled to now
            # Always use the stored start timestamp (set when Live View was enabled)
            # If not set, use current time as fallback (shouldn't happen, but safety check)
            live_view_start = st.session_state.get('live_view_start_timestamp')
            if live_view_start is not None:
                start_dt_live = live_view_start
            else:
                # Fallback: use current time if timestamp not set (shouldn't happen)
                start_dt_live = datetime.now()
                # Store it for consistency
                st.session_state['live_view_start_timestamp'] = start_dt_live
            end_dt_live = datetime.now()  # Always use current time as end
            
            # Convert selected timezone to UTC for ESP32 query
            import pytz
            local_tz = pytz.timezone(selected_timezone)
            try:
                start_dt_local_live = local_tz.localize(start_dt_live, is_dst=None)
                end_dt_local_live = local_tz.localize(end_dt_live, is_dst=None)
            except pytz.AmbiguousTimeError:
                start_dt_local_live = local_tz.localize(start_dt_live, is_dst=False)
                end_dt_local_live = local_tz.localize(end_dt_live, is_dst=False)
            except pytz.NonExistentTimeError:
                start_dt_local_live = local_tz.localize(start_dt_live, is_dst=True)
                end_dt_local_live = local_tz.localize(end_dt_live, is_dst=True)
            # Convert to UTC epoch timestamps for ESP32 (used for Live View auto-refresh)
            start_epoch_live = int(start_dt_local_live.astimezone(pytz.UTC).timestamp())
            end_epoch_live = int(end_dt_local_live.astimezone(pytz.UTC).timestamp())

        # Retrieve Data button - disabled when Live View is active
        retrieve_clicked = st.button(
            "🔍 Retrieve Data", 
            type="primary",
            disabled=live_view_enabled_for_date_range,
            help="Disabled while Live View is active. Disable Live View to use this button."
        )
        
        # Auto-refresh logic for Live View
        should_auto_refresh = False
        # Read Live View state - use checkbox state as source of truth since it's updated by user interaction
        # The checkbox state is the authoritative source, session state might be stale at this point in execution
        live_view_checkbox_state = st.session_state.get('live_view_checkbox', False)
        stop_requested_for_refresh = st.session_state.get('live_view_stop_requested', False)
        live_view_enabled_for_refresh = live_view_checkbox_state and not stop_requested_for_refresh
        # CRITICAL: Do NOT sync session state here - it's managed by checkbox processing section
        # The checkbox processing section (later in code) is the authoritative source for state
        # We only use this calculated value for determining if auto-refresh should run
        # Setting session state here can cause conflicts with checkbox processing
        
        # CRITICAL: Only enable auto-refresh if:
        # 1. Live View is enabled
        # 2. Device is connected
        # 3. Live View date range is calculated (start_epoch_live is set)
        # This prevents auto-refresh from running before the Live View timestamp is ready
        # and prevents using picker date range when Live View is first enabled
        if live_view_enabled_for_refresh and st.session_state.connected and start_epoch_live is not None:
            # Validate connection before attempting auto-refresh
            if not is_serial_valid(st.session_state.serial_connection):
                st.error("⚠️ **Connection Lost:** Serial port is no longer valid. Please reconnect.")
                st.session_state.connected = False
                st.session_state.connected_port = None
                st.session_state.serial_connection = None
                st.rerun()
            else:
                current_time = time.time()
                last_update = st.session_state.get('last_live_update', 0)
                time_since_last_update = current_time - last_update
                # Check if 5 seconds have passed OR if last_update is 0 (first fetch after enabling Live View)
                if time_since_last_update >= 5.0 or last_update == 0:
                    # Double-check checkbox state hasn't changed (user might have unchecked during this run)
                    if st.session_state.get('live_view_checkbox', False):
                        should_auto_refresh = True
                        st.session_state['is_auto_refresh'] = True
                        st.session_state['last_live_update'] = current_time
                    else:
                        # Checkbox was unchecked - stop auto-refresh immediately
                        st.session_state['is_auto_refresh'] = False
                        st.session_state['live_view_enabled'] = False
                        st.session_state['last_live_update'] = 0
        
        # Retrieve data (either manual or auto-refresh)
        # IMPORTANT: Only allow manual retrieve if Live View is NOT enabled
        # If Live View is enabled, retrieve_clicked should be False (button is disabled)
        if (retrieve_clicked and not live_view_enabled_for_date_range) or should_auto_refresh:
            if should_auto_refresh:
                # Silent auto-refresh - no spinner to avoid page jumps
                pass
            else:
                st.session_state['new_query'] = True
            
            # Only fetch if connected
            if st.session_state.connected and is_serial_valid(st.session_state.serial_connection):
                if not should_auto_refresh:
                    # Manual retrieve - use picker date range
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
                                st.session_state['last_successful_update'] = time.time()
                            else:
                                # Parsing failed or no data
                                if not response.strip():
                                    st.warning("⚠️ **No Data:** ESP32 returned empty response. Check device connection.")
                                else:
                                    st.info("ℹ️ **No Readings Found:** No data in the selected time range.")
                                # Keep last_df if no new readings (don't clear it)
                                pass
                        else:
                            # No response from ESP32
                            st.error("⚠️ **Connection Error:** ESP32 did not respond. Please check connection and try again.")
                            # Keep last_df if no response (don't clear it)
                            pass
                    st.session_state['new_query'] = False
                else:
                    # Auto-refresh: fetch data silently using Live View date range
                    # CRITICAL: Only proceed if Live View date range is calculated (start_epoch_live is set)
                    # This prevents using picker date range when Live View is first enabled
                    if live_view_enabled_for_refresh and start_epoch_live is not None:
                        # Recalculate end time to current time for each refresh
                        end_dt_live_now = datetime.now()
                        import pytz
                        local_tz = pytz.timezone(selected_timezone)
                        try:
                            end_dt_local_live_now = local_tz.localize(end_dt_live_now, is_dst=None)
                        except pytz.AmbiguousTimeError:
                            end_dt_local_live_now = local_tz.localize(end_dt_live_now, is_dst=False)
                        except pytz.NonExistentTimeError:
                            end_dt_local_live_now = local_tz.localize(end_dt_live_now, is_dst=True)
                        end_epoch_live_now = int(end_dt_local_live_now.astimezone(pytz.UTC).timestamp())
                        command = f"range {start_epoch_live} {end_epoch_live_now}"
                        
                        try:
                            response = send_command(st.session_state.serial_connection, command)
                            st.session_state['last_raw_response'] = response if response is not None else ""
                            
                            if not response or response.strip() == "":
                                # No response - connection might be dead
                                st.session_state['connection_error_count'] = st.session_state.get('connection_error_count', 0) + 1
                                if st.session_state['connection_error_count'] >= 3:
                                    st.error("⚠️ **Connection Error:** ESP32 is not responding. Please check connection.")
                                    st.session_state.connected = False
                                    st.session_state.connected_port = None
                                    try:
                                        if st.session_state.serial_connection:
                                            st.session_state.serial_connection.close()
                                    except Exception:
                                        pass
                                    st.session_state.serial_connection = None
                                    st.session_state['connection_error_count'] = 0
                                    st.rerun()
                            else:
                                # Reset error count on successful response
                                st.session_state['connection_error_count'] = 0
                                readings = parse_readings(response)
                                
                                if not readings:
                                    # Parsing failed or no data - log but don't show error (might be no data in range)
                                    log_general_debug(f"[DEBUG] No readings parsed from response. Response length: {len(response)}")
                                    # Keep existing last_df
                                else:
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
                                    st.session_state['last_successful_update'] = time.time()
                        except Exception as e:
                            # Connection error during auto-refresh
                            log_general_debug(f"[DEBUG] Auto-refresh error: {e}")
                            st.session_state['connection_error_count'] = st.session_state.get('connection_error_count', 0) + 1
                            if st.session_state['connection_error_count'] >= 3:
                                st.error(f"⚠️ **Connection Error:** {str(e)}. Please reconnect.")
                                st.session_state.connected = False
                                st.session_state.connected_port = None
                                try:
                                    if st.session_state.serial_connection:
                                        st.session_state.serial_connection.close()
                                except Exception:
                                    pass
                                st.session_state.serial_connection = None
                                st.session_state['connection_error_count'] = 0
                                st.rerun()
                        
                        # Note: If no response or no readings, keep existing last_df
                        st.session_state['is_auto_refresh'] = False
                    else:
                        # Live View enabled but date range not ready - skip this refresh
                        st.session_state['is_auto_refresh'] = False
                        st.session_state['last_live_update'] = time.time() - 4
            else:
                # Not connected - keep last graph visible, don't try to fetch
                if should_auto_refresh:
                    st.session_state['is_auto_refresh'] = False
                    # Reset last_live_update to try again next cycle
                    st.session_state['last_live_update'] = time.time() - 5  # Wait 5 seconds before next attempt
                    if live_view_enabled:
                        st.warning("⚠️ **Not Connected:** Please connect to the device to enable Live View updates.")

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
        
        st.header("📡 Live View")
        
        previous_live_view_state = st.session_state.get('live_view_enabled', False)
        
        if 'live_view_stop_requested' not in st.session_state:
            st.session_state['live_view_stop_requested'] = False
        
        if 'live_view_checkbox_previous' not in st.session_state:
            st.session_state['live_view_checkbox_previous'] = False
        
        live_view_checkbox_value = st.checkbox(
            "Enable Live View",
            key="live_view_checkbox",
            help="Automatically refresh graph every 5 seconds with new readings"
        )
        
        stop_requested_check = st.session_state.get('live_view_stop_requested', False)
        
        # Detect checkbox state transition (user interaction)
        checkbox_was_checked = st.session_state.get('live_view_checkbox_previous', False)
        checkbox_changed = (live_view_checkbox_value != checkbox_was_checked)
        st.session_state['live_view_checkbox_previous'] = live_view_checkbox_value
        
        # Stop flag is authoritative - if set, Live View stays disabled until checkbox transitions to checked
        if stop_requested_check:
            if live_view_checkbox_value and checkbox_changed and not checkbox_was_checked:
                st.session_state['live_view_stop_requested'] = False
                live_view_enabled = True
                st.session_state['live_view_enabled'] = True
            else:
                live_view_enabled = False
                st.session_state['live_view_enabled'] = False
        elif live_view_checkbox_value:
            live_view_enabled = True
            st.session_state['live_view_enabled'] = True
        else:
            if checkbox_changed:
                st.session_state['live_view_stop_requested'] = True
            else:
                st.session_state['live_view_stop_requested'] = True
            live_view_enabled = False
            st.session_state['live_view_enabled'] = False
        
        # Capture timestamp when Live View is enabled
        if live_view_enabled and not previous_live_view_state:
            current_timestamp = datetime.now()
            st.session_state['live_view_start_timestamp'] = current_timestamp
            st.session_state['last_live_update'] = 0
            st.session_state['last_df'] = None
            st.session_state['last_raw_response'] = None
            st.session_state['last_successful_update'] = None
            st.session_state['is_auto_refresh'] = False
            st.rerun()
        elif not live_view_enabled and previous_live_view_state:
            st.session_state['live_view_stop_requested'] = True
            st.session_state['live_view_start_timestamp'] = None
            st.session_state['last_live_update'] = 0
            st.session_state['is_auto_refresh'] = False
        
        # Show status message based on Live View state
        # Use the same logic as the button to determine if Live View is truly enabled
        live_view_status_checkbox = st.session_state.get('live_view_checkbox', False)
        live_view_status_stop = st.session_state.get('live_view_stop_requested', False)
        live_view_status_enabled = live_view_status_checkbox and not live_view_status_stop
        
        if live_view_status_enabled:
            if st.session_state.connected:
                st.info("🔄 **Live View Active:** Graph will auto-update every 5 seconds from when Live View was enabled to now.")
            else:
                # Live View is enabled but connection was lost (possibly due to browser disconnection)
                st.warning("⚠️ **Live View Enabled but Not Connected:** Please reconnect to the device to resume auto-updates. Live View will continue from where it left off once reconnected.")
        else:
            st.info("💡 Enable Live View to automatically refresh the temperature graph with new readings.")
        
        if st.session_state.get('last_df') is not None:
            st.header("📋 RFID Readings")
            df_display = st.session_state['last_df']
            if df_display.empty:
                st.warning("⚠️ **No Data Available:** The data frame is empty. Please retrieve data or check device connection.")
            else:
                st.dataframe(df_display, use_container_width=True)
            csv = st.session_state['last_df'].to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name="rfid_readings_last.csv",
                mime="text/csv"
            )
            # Plotly line plot: Timestamp vs Temperature_C, one line per Tag
            # Use container to prevent page scrolling during updates
            graph_container = st.container()
            with graph_container:
                df = st.session_state['last_df']
                timezone_display = timezone_options.get(st.session_state['selected_timezone'], st.session_state['selected_timezone'])
                
                # Debug: Show data summary
                st.subheader("📊 Data Summary")
                st.write(f"Total records: {len(df)}")
                st.write(f"Unique tags: {df['Tag'].nunique()}")
                st.write(f"Tags found: {sorted(df['Tag'].unique())}")
                st.write(f"Date range: {df['Timestamp'].min()} to {df['Timestamp'].max()}")
                
                if not df.empty:
                    # Count rows with N/A temperature
                    na_count = (df['Temperature_C'] == 'N/A').sum() if 'Temperature_C' in df.columns else 0
                    
                    # Create a copy for numeric conversion (keep original for table display)
                    df_chart = df.copy()
                    
                    # Convert Temperature_C to numeric, keeping "N/A" as NaN
                    df_chart['Temperature_C'] = pd.to_numeric(df_chart['Temperature_C'], errors='coerce')
                    
                    # Remove any rows with NaN temperature values (includes "N/A" and invalid values)
                    df_clean = df_chart.dropna(subset=['Temperature_C'])
                    
                    if na_count > 0:
                        st.info(f"ℹ️ {na_count} reading(s) have no temperature data (N/A) and are excluded from the chart but shown in the table below.")
                    
                    if len(df_clean) != len(df_chart) and na_count == 0:
                        # Only show warning if there are invalid numeric values (not just N/A)
                        invalid_count = len(df_chart) - len(df_clean) - na_count
                        if invalid_count > 0:
                            st.warning(f"⚠️ Removed {invalid_count} row(s) with invalid temperature data")
                    
                    if not df_clean.empty:
                        fig = px.line(
                            df_clean,
                            x="Timestamp",
                            y="Temperature_C",
                            color="Tag",
                            title=f"Temperature vs Timestamp by Tag ({timezone_display})",
                            labels={"Temperature_C": "Temperature (°C)", "Timestamp": "Timestamp", "Tag": "Tag"}
                        )
                        
                        # Add markers (dots) to each reading point
                        fig.update_traces(mode='lines+markers', marker=dict(size=5, symbol='circle'))
                        
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
                        # All readings have N/A temperature
                        st.warning("⚠️ No temperature data available for charting (all readings show N/A)")
                        fig = px.line(title=f"Temperature vs Timestamp by Tag ({timezone_display})")
                        fig.update_layout(xaxis_title="Timestamp", yaxis_title="Temperature (°C)")
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    # DataFrame is empty
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
    else:
        st.info("🔌 Please connect to your RFID reader using the sidebar.")
    
    # Auto-rerun for Live View (refreshes every 5 seconds)
    # Live View continues even when browser disconnects (screen saver, lock, etc.)
    # WebSocket errors are expected and handled gracefully - Live View state persists
    session_state_live_view = st.session_state.get('live_view_enabled', False)
    stop_requested = st.session_state.get('live_view_stop_requested', False)
    
    if session_state_live_view and not stop_requested and st.session_state.connected:
        try:
            time.sleep(0.1)
            st.rerun()
        except Exception as e:
            # Handle WebSocket disconnection errors gracefully (screen saver, lock, browser close)
            # These errors are expected when browser disconnects and can be safely ignored
            # The Streamlit server continues running, so Live View state is preserved
            # When browser reconnects, Live View automatically resumes
            error_type = type(e).__name__
            error_msg = str(e).lower()
            error_module = type(e).__module__.lower() if hasattr(type(e), '__module__') else ''
            
            # Catch all WebSocket/Stream/Tornado related errors
            # These occur when browser disconnects (screen saver, lock, etc.)
            # Background tasks may raise these errors, but they don't affect Live View state
            if any(keyword in error_type.lower() or keyword in error_msg or keyword in error_module 
                   for keyword in ['websocket', 'stream', 'closed', 'tornado', 'iostream']):
                # Browser disconnected - this is expected and normal
                # Don't raise or log - just stop the rerun loop gracefully
                # Live View state is preserved in session state
                pass
            else:
                # Unexpected error - silently ignore to prevent dashboard crash
                # Live View will resume when browser reconnects
                pass
    else:
        if session_state_live_view and not stop_requested:
            st.session_state['live_view_stop_requested'] = True
        st.session_state['is_auto_refresh'] = False
        st.session_state['last_live_update'] = 0

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
    <p><strong>Implant RFID Reader Multi-Button Dashboard v3.0</strong></p>
    <p>© 2025 Establishment Labs. All rights reserved.</p>
    <p>Developed by <a href='mailto:info@littleendianengineering.com' style='color: #666;'>Little Endian Engineering</a></p>
    <p>Contact: <a href='mailto:lyu@establishmentlabs.com' style='color: #666;'>lyu@establishmentlabs.com</a></p>
    <p style='font-size: 10px; margin-top: 10px;'>CONFIDENTIAL - PROPRIETARY SOFTWARE</p>
</div>
""", unsafe_allow_html=True)
