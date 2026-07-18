"""
Implant RFID Reader - Multi-Button Dashboard Application (ESP32-S3)
===================================================================

PROPRIETARY SOFTWARE
Copyright (c) 2025 Establishment Labs
Developed by Little Endian Engineering

Version: 6.1 (ESP32-S3 + Dual Antenna + Low-SoC Service Access)
Date: July 2026

DESCRIPTION:
Streamlit-based dashboard for Implant RFID Reader ESP32-S3 device with multi-button support and RGB LED status indicators.
Provides real-time data visualization, filtering, and configuration management.
Supports multiple timezones, CSV export functionality, configurable button timings, and hardware LED status monitoring.
Includes Dashboard Mode persistence, improved macOS connection stability, dual-antenna parsing,
live data retrieval, idle-mode visibility, low-SoC controls, battery calibration, LED heartbeat
configuration, low-SoC USB recovery access, Dashboard Mode service latch control,
firmware debug toggles, manual Read Now, and latest-reading highlighting.

FEATURES:
- Real-time serial communication with ESP32-S3
- Multi-button functionality (short press = RFID read, long press = dashboard mode toggle)
- RGB LED status indicators for visual feedback
- Configurable long press timer for dashboard mode activation (1-30 seconds)
- Date range filtering with timezone support
- Interactive data visualization with Plotly
- CSV export functionality
- ESP32-S3 configuration management
- Advanced firmware configuration for low-SoC idle, USB recovery access, battery calibration, Dashboard Mode service access, verbose logging, and LED heartbeat timing
- Multi-timezone display support
- Password-protected storage clearing
- Current User Guide for connection, Live View, configuration, data display, and troubleshooting
- Dashboard Mode service latch persistence (survives device resets)
- Improved macOS connection handling for ESP32-S3 USB-CDC
- Dual-antenna ANT1/ANT2 parsing and display
- Manual Read Now command with latest ANT1/ANT2 result cards
- Idle mode status, reason, and low-SoC USB recovery visibility

REQUIREMENTS:
- Python 3.8+
- Streamlit, Pandas, PySerial, Plotly, PyTZ
- ESP32-S3 device with Multi-Button Implant RFID Reader firmware

USAGE:
streamlit run rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py

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

st.markdown(
    """
    <style>
    div.stButton > button,
    div.stDownloadButton > button,
    button[kind],
    button[data-testid="baseButton-secondary"],
    button[data-testid="baseButton-primary"] {
        background-color: #ae851e !important;
        color: #ffffff !important;
        border: 1px solid #ae851e !important;
    }

    div.stButton > button *,
    div.stDownloadButton > button *,
    button[kind] *,
    button[data-testid="baseButton-secondary"] *,
    button[data-testid="baseButton-primary"] * {
        color: #ffffff !important;
    }

    div.stButton > button:hover,
    div.stDownloadButton > button:hover,
    button[kind]:hover,
    button[data-testid="baseButton-secondary"]:hover,
    button[data-testid="baseButton-primary"]:hover {
        background-color: #8f6d18 !important;
        color: #ffffff !important;
        border-color: #8f6d18 !important;
    }

    div.stButton > button:disabled,
    div.stDownloadButton > button:disabled,
    button[kind]:disabled,
    button[data-testid="baseButton-secondary"]:disabled,
    button[data-testid="baseButton-primary"]:disabled {
        background-color: #ae851e !important;
        color: #ffffff !important;
        border-color: #ae851e !important;
        opacity: 0.45 !important;
    }

    button[role="tab"][aria-selected="true"],
    button[role="tab"][aria-selected="true"] * {
        color: #ae851e !important;
    }

    div[data-baseweb="tab-highlight"] {
        background-color: #ae851e !important;
    }

    input[type="checkbox"],
    input[type="radio"],
    input[type="range"] {
        accent-color: #ae851e !important;
    }

    div[data-baseweb="checkbox"] div[aria-checked="true"],
    div[data-baseweb="radio"] div[aria-checked="true"],
    div[data-baseweb="switch"] div[aria-checked="true"] {
        background-color: #ae851e !important;
        border-color: #ae851e !important;
    }

    div[data-baseweb="input"]:focus-within,
    div[data-baseweb="textarea"]:focus-within,
    div[data-baseweb="select"]:focus-within {
        border-color: #ae851e !important;
        box-shadow: 0 0 0 1px #ae851e !important;
    }

    ul[role="listbox"] li[aria-selected="true"] {
        background-color: rgba(174, 133, 30, 0.14) !important;
        color: #ae851e !important;
    }

    div[data-testid="stSlider"] div[role="slider"] {
        background-color: #ae851e !important;
        border-color: #ae851e !important;
    }
    </style>
    """,
    unsafe_allow_html=True
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
if 'read_now_latest_records' not in st.session_state:
    st.session_state['read_now_latest_records'] = []
if 'read_now_latest_status' not in st.session_state:
    st.session_state['read_now_latest_status'] = ""
if 'read_now_latest_message' not in st.session_state:
    st.session_state['read_now_latest_message'] = ""
if 'read_now_latest_at' not in st.session_state:
    st.session_state['read_now_latest_at'] = None
if 'read_now_latest_response' not in st.session_state:
    st.session_state['read_now_latest_response'] = ""
if 'selected_timezone' not in st.session_state:
    st.session_state['selected_timezone'] = 'America/Costa_Rica'
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
if 'esp32_socLowIdleEnabled' not in st.session_state:
    st.session_state['esp32_socLowIdleEnabled'] = True
if 'esp32_lowSocUsbRecoveryWindow' not in st.session_state:
    st.session_state['esp32_lowSocUsbRecoveryWindow'] = 15.0
if 'esp32_socLowThresholdPercent' not in st.session_state:
    st.session_state['esp32_socLowThresholdPercent'] = 10.0
if 'esp32_batteryMinVoltage' not in st.session_state:
    st.session_state['esp32_batteryMinVoltage'] = 3.52
if 'esp32_batteryMaxVoltage' not in st.session_state:
    st.session_state['esp32_batteryMaxVoltage'] = 4.15
if 'esp32_verbose' not in st.session_state:
    st.session_state['esp32_verbose'] = False
if 'esp32_dashboardModeActive' not in st.session_state:
    st.session_state['esp32_dashboardModeActive'] = False
if 'esp32_ledHeartbeatInterval' not in st.session_state:
    st.session_state['esp32_ledHeartbeatInterval'] = 20.0
if 'esp32_ledHeartbeatOn' not in st.session_state:
    st.session_state['esp32_ledHeartbeatOn'] = 1.0
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
if 'dashboard_fetch_timeout_s' not in st.session_state:
    st.session_state['dashboard_fetch_timeout_s'] = 30
if 'live_view_refresh_interval_s' not in st.session_state:
    st.session_state['live_view_refresh_interval_s'] = 8.0
if 'live_view_start_epoch' not in st.session_state:
    st.session_state['live_view_start_epoch'] = None
if 'live_view_last_fetch_epoch' not in st.session_state:
    st.session_state['live_view_last_fetch_epoch'] = None
if 'live_view_last_new_rows' not in st.session_state:
    st.session_state['live_view_last_new_rows'] = 0
if 'live_view_last_range' not in st.session_state:
    st.session_state['live_view_last_range'] = None
if 'live_view_fragment_tick_at' not in st.session_state:
    st.session_state['live_view_fragment_tick_at'] = 0
if 'last_live_readnow_response' not in st.session_state:
    st.session_state['last_live_readnow_response'] = ""
if 'live_view_empty_response_count' not in st.session_state:
    st.session_state['live_view_empty_response_count'] = 0
if 'live_view_backoff_until' not in st.session_state:
    st.session_state['live_view_backoff_until'] = 0
if 'live_view_last_error' not in st.session_state:
    st.session_state['live_view_last_error'] = ""
if 'connection_error_count' not in st.session_state:
    st.session_state['connection_error_count'] = 0
if 'last_connection_test' not in st.session_state:
    st.session_state['last_connection_test'] = 0
if 'device_dashboard_mode' not in st.session_state:
    st.session_state['device_dashboard_mode'] = False
if 'idle_mode_active' not in st.session_state:
    st.session_state['idle_mode_active'] = False
if 'idle_mode_reason' not in st.session_state:
    st.session_state['idle_mode_reason'] = ""
if 'idle_recovery_active' not in st.session_state:
    st.session_state['idle_recovery_active'] = False
if 'idle_recovery_remaining_s' not in st.session_state:
    st.session_state['idle_recovery_remaining_s'] = 0
if 'idle_recovery_updated_at' not in st.session_state:
    st.session_state['idle_recovery_updated_at'] = 0
if 'last_status_poll' not in st.session_state:
    st.session_state['last_status_poll'] = 0
if 'status_state_initialized' not in st.session_state:
    st.session_state['status_state_initialized'] = False
if 'status_retry_count' not in st.session_state:
    st.session_state['status_retry_count'] = 0

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

WAKE_DELAY = 0.22  # seconds; first byte wakes ESP32 from light sleep and is typically lost
STATUS_POLL_INTERVAL_SECONDS = 300  # 5 minutes
RECOVERY_STATUS_POLL_INTERVAL_SECONDS = 1
MIN_RFID_ON_TIME_SECONDS = 3  # Safety minimum to keep dual-antenna windows reliable
DEFAULT_LIVE_VIEW_REFRESH_INTERVAL_SECONDS = 8.0
MIN_LIVE_VIEW_REFRESH_INTERVAL_SECONDS = 8.0
MAX_LIVE_VIEW_REFRESH_INTERVAL_SECONDS = 300.0
MIN_DASHBOARD_FETCH_TIMEOUT_SECONDS = 10
MAX_DASHBOARD_FETCH_TIMEOUT_SECONDS = 180
DEFAULT_DASHBOARD_FETCH_TIMEOUT_SECONDS = 30
LIVE_VIEW_EMPTY_RESPONSE_LIMIT = 2
LIVE_VIEW_EMPTY_RESPONSE_BACKOFF_SECONDS = 5
VERBOSE = True

def log_debug(msg):
    """Log debug messages with automatic cleanup (max 100 entries)"""
    if not VERBOSE:
        return
    st.session_state['debug_log'].append(msg)
    if len(st.session_state['debug_log']) > 100:
        st.session_state['debug_log'] = st.session_state['debug_log'][-100:]

def log_set_debug(msg):
    """Log set operation debug messages with automatic cleanup (max 100 entries)"""
    if not VERBOSE:
        return
    st.session_state['set_debug_log'].append(msg)
    if len(st.session_state['set_debug_log']) > 100:
        st.session_state['set_debug_log'] = st.session_state['set_debug_log'][-100:]

def log_general_debug(msg):
    """Log general debug messages (ping, pong, retrieve data, etc.) with automatic cleanup (max 100 entries)"""
    if not VERBOSE:
        return
    try:
        print(msg, flush=True)
    except Exception:
        pass
    st.session_state['general_debug_log'].append(msg)
    if len(st.session_state['general_debug_log']) > 100:
        st.session_state['general_debug_log'] = st.session_state['general_debug_log'][-100:]

def get_latest_soc_line(*texts):
    """Return latest [SOC] line from provided texts or session logs."""
    soc_pattern = re.compile(r'(\[SOC\].*)')

    for text in texts:
        if not text:
            continue
        matches = soc_pattern.findall(text)
        if matches:
            return matches[-1].strip()

    for msg in reversed(st.session_state.get('general_debug_log', [])):
        if not msg:
            continue
        matches = soc_pattern.findall(msg)
        if matches:
            return matches[-1].strip()

    return None

def get_available_ports():
    """Get list of available serial ports"""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def get_serial_port_metadata(port_name):
    """Return pyserial list_ports metadata for a selected device."""
    for port_info in serial.tools.list_ports.comports():
        if port_info.device == port_name:
            return {
                "device": port_info.device,
                "name": getattr(port_info, "name", None),
                "description": getattr(port_info, "description", None),
                "hwid": getattr(port_info, "hwid", None),
                "manufacturer": getattr(port_info, "manufacturer", None),
                "product": getattr(port_info, "product", None),
                "interface": getattr(port_info, "interface", None),
                "vid": getattr(port_info, "vid", None),
                "pid": getattr(port_info, "pid", None),
                "serial_number": getattr(port_info, "serial_number", None),
                "location": getattr(port_info, "location", None),
            }
    return None

def format_serial_port_metadata(metadata):
    """Format serial metadata for debug logs and UI."""
    if not metadata:
        return "not found in serial.tools.list_ports"

    fields = []
    for key in [
        "device",
        "description",
        "manufacturer",
        "product",
        "interface",
        "hwid",
        "vid",
        "pid",
        "serial_number",
        "location",
    ]:
        value = metadata.get(key)
        if value not in (None, ""):
            fields.append(f"{key}={value}")
    return "; ".join(fields) if fields else "metadata empty"

def should_skip_cleanup_probe(port_name):
    """Avoid pre-opening CP210x ports; some macOS drivers return EINVAL on probes."""
    metadata = get_serial_port_metadata(port_name)
    if not metadata:
        return False

    manufacturer = str(metadata.get("manufacturer") or "").lower()
    product = str(metadata.get("product") or "").lower()
    description = str(metadata.get("description") or "").lower()
    vid = metadata.get("vid")
    pid = metadata.get("pid")

    return (
        "silicon labs" in manufacturer or
        "cp210" in product or
        "cp210" in description or
        (vid == 0x10C4 and pid == 0xEA60)
    )

def close_serial_port_if_open(port_name):
    """Attempt to close a serial port if it's open at OS level"""
    # Useful when page refreshes and the port is still open from a previous session.
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
            if is_invalid_argument_serial_error(e):
                log_general_debug(
                    f"[CLEANUP] Cleanup probe got EINVAL for {port_name}; "
                    "skipping cleanup open for this driver"
                )
                return False
            error_msg = str(e).lower()
            if "already open" in error_msg or "busy" in error_msg:
                # Port is already open by another process - we can't close it
                log_general_debug(f"[CLEANUP] Port {port_name} is already open by another process - cannot close")
                return False
            # Port is not open or doesn't exist - that's fine
            log_general_debug(f"[CLEANUP] Port {port_name} is not open or doesn't exist")
            return True
        except Exception as e:
            if is_invalid_argument_serial_error(e):
                log_general_debug(
                    f"[CLEANUP] Cleanup probe got EINVAL for {port_name}; "
                    "skipping cleanup open for this driver"
                )
                return False
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

def is_invalid_argument_serial_error(error):
    """Detect macOS driver EINVAL failures from pyserial."""
    error_text = str(error).lower()
    return (
        "invalid argument" in error_text or
        "errno 22" in error_text or
        "(22," in error_text
    )

def open_serial_original_then_fallback(port, baud_rate):
    """Open serial using the historic profile first, then EINVAL-only fallbacks."""
    try:
        log_general_debug("[CONNECTION] Opening serial port with original profile")
        ser = serial.Serial(
            port,
            baud_rate,
            timeout=2,
            dsrdtr=False,  # Disable DSR/DTR flow control (prevents reset)
            rtscts=False,  # Disable RTS/CTS flow control (prevents reset)
            write_timeout=2  # Add write timeout to prevent hanging
        )
        return ser, "original"
    except Exception as first_error:
        if not is_invalid_argument_serial_error(first_error):
            raise
        log_general_debug(f"[CONNECTION] Original serial open got EINVAL: {first_error}")

        fallback_profiles = [
            (
                "no-flow-args",
                lambda: serial.Serial(
                    port,
                    baud_rate,
                    timeout=2,
                    write_timeout=2
                )
            ),
            (
                "staged-open",
                lambda: _open_serial_staged(port, baud_rate)
            ),
        ]

        last_error = first_error
        for profile_name, open_fn in fallback_profiles:
            try:
                log_general_debug(f"[CONNECTION] Opening serial port with fallback profile={profile_name}")
                ser = open_fn()
                return ser, profile_name
            except Exception as fallback_error:
                last_error = fallback_error
                log_general_debug(f"[CONNECTION] Fallback profile {profile_name} failed: {fallback_error}")
                if not is_invalid_argument_serial_error(fallback_error):
                    raise

        raise last_error

def _open_serial_staged(port, baud_rate):
    """Open a serial port through property assignment for picky macOS drivers."""
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud_rate
    ser.timeout = 2
    ser.write_timeout = 2
    ser.open()
    return ser

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
        ser, open_profile = open_serial_original_then_fallback(port, baud_rate)
        log_general_debug(f"[CONNECTION] Port opened successfully profile={open_profile}")
        
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
            if is_invalid_argument_serial_error(e):
                st.info("macOS rejected the serial open call with Invalid argument after all open profiles. Try unplugging/replugging the USB adapter, closing Arduino Serial Monitor, or selecting the other `/dev/cu.*` port.")
            log_general_debug(f"[CONNECTION] Connection error: {e}")
        return None
    except Exception as e:
        st.error(f"Failed to connect: {e}")
        if is_invalid_argument_serial_error(e):
            st.info("macOS rejected the serial open call with Invalid argument after all open profiles. Try unplugging/replugging the USB adapter, closing Arduino Serial Monitor, or selecting the other `/dev/cu.*` port.")
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
        log_general_debug(f"[HOSTDBG] wake_serial start t={time.time():.3f} delay={wake_delay:.3f}")
        ser.write(b"\n")       # wake byte - device will wake but this byte is lost
        ser.flush()
        time.sleep(wake_delay) # give ESP32 time to fully wake clocks
        # REMOVED: ser.reset_input_buffer() - this was clearing responses!
        log_general_debug(f"[HOSTDBG] wake_serial end t={time.time():.3f}")
    except SERIAL_EXCEPTIONS as e:
        log_debug(f"[DEBUG] Wake error: {e}")
        raise  # Re-raise to be handled by caller
    except Exception as e:
        log_debug(f"[DEBUG] Wake error: {e}")

def _log_filtered_debug(command, line):
    """Filter debug output based on the command being sent"""
    # Always show these important messages
    if any(keyword in line for keyword in ["[DASHBOARD]", "[RFID]", "[IDLE]", "[ERROR]", "[WARNING]", "CMD_RECEIVED"]):
        log_general_debug(f"[DEBUG] Received: {line}")
        return
    
    # Filter based on specific commands
    if command == "debug":
        # For debug command, only show debug info section
        if any(keyword in line for keyword in ["[DEBUG] --- Device Debug Info ---", "[DEBUG] Reading count:", "[DEBUG] MAX_READINGS:", "[DEBUG] Available slots:", "[DEBUG] Dashboard mode:", "[DEBUG] Idle mode:", "[DEBUG] Idle reason:", "[DEBUG] Current time:", "[DEBUG] Unix timestamp:", "[SOC] Latest:", "[DEBUG] --- End Debug Info ---"]):
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
        # For status command, show dashboard and idle state lines
        if any(keyword in line for keyword in ["[DASHBOARD] Dashboard Mode:", "[IDLE] Mode:", "[IDLE] Latest reason:", "[STATUS] Dashboard Mode:", "[STATUS] Current ESP32 Status:"]):
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
            log_general_debug(f"[HOSTDBG] wake_send start t={time.time():.3f} cmd={command} attempt={attempt+1}/{max_retries}")
            # Send wake-up byte
            ser.write(b"\n")
            ser.flush()
            time.sleep(wake_delay) # give ESP32 time to fully wake clocks
            
            # Clear stale buffered data before sending a new command.
            log_general_debug(f"[HOSTDBG] reset_input_buffer before cmd t={time.time():.3f} cmd={command}")
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
            expect_readings = command.strip() == "print"
            quiet_period = 2.0 if expect_readings else 0.6
            hard_timeout = 180 if expect_readings else 10
            
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
                    
                    if expect_readings and '---END_READINGS---' in line:
                        end_reason = "end_marker"
                        break
                
                # Check for quiet period even when no bytes are currently waiting.
                # Otherwise, completed responses can incorrectly run until hard timeout.
                now_ts = time.time()
                if received_any and last_rx_time is not None and (now_ts - last_rx_time) > quiet_period:
                    end_reason = "quiet_period"
                    log_general_debug("[DEBUG] Quiet period reached; finishing read")
                    break
                
                # Check timeout
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

def send_command(ser, command, range_timeout_seconds=None):
    """Send command to ESP32 and receive response with timeout"""
    try:
        log_general_debug(f"[DEBUG] send_command start: {command}")
        log_general_debug(f"[HOSTDBG] send_command t={time.time():.3f} cmd={command}")
        
        # For dashboard mode commands, use immediate wake-and-send approach
        if command in ["dashboardmode on", "dashboardmode off", "status", "debugsimple", "debug", "buttonmode", "testbutton", "print"]:
            response = _wake_and_send_command(ser, command, filter_debug=True)
            if response:
                return response
            else:
                log_general_debug(f"[DEBUG] wake_and_send failed for {command}, falling back to standard method")
                # Fall back to standard method if wake-and-send fails
                _wake_serial(ser)
                log_general_debug(f"[HOSTDBG] reset_input_buffer before cmd t={time.time():.3f} cmd={command}")
                ser.reset_input_buffer()
                ser.write(f"{command}\n".encode())
                ser.flush()
        else:
            # For other commands, use the standard wake-then-send approach
            _wake_serial(ser)
            # Clear stale buffered data before sending a new command.
            log_general_debug(f"[HOSTDBG] reset_input_buffer before cmd t={time.time():.3f} cmd={command}")
            ser.reset_input_buffer()
            ser.write(f"{command}\n".encode())
            ser.flush()

        response = ""
        bytes_count = 0
        line_count = 0
        start_time = time.time()
        stripped_command = command.strip()
        expect_range = stripped_command.startswith("range ")
        expect_print_all = stripped_command == "print"
        expect_readnow = stripped_command == "readnow"
        expect_readings = expect_range or expect_print_all
        received_any = False
        last_rx_time = None
        end_reason = ""
        quiet_period = 2.0 if (expect_readings or expect_readnow) else 0.6
        range_timeout = int(range_timeout_seconds or st.session_state.get(
            'dashboard_fetch_timeout_s',
            DEFAULT_DASHBOARD_FETCH_TIMEOUT_SECONDS
        ))
        range_timeout = max(
            MIN_DASHBOARD_FETCH_TIMEOUT_SECONDS,
            min(MAX_DASHBOARD_FETCH_TIMEOUT_SECONDS, range_timeout)
        )
        readnow_timeout = max(15, int(st.session_state.get('esp32_rfidOnTime', 5) * 2 + 10))
        hard_timeout = 180 if expect_print_all else (
            range_timeout if expect_range else (readnow_timeout if expect_readnow else 20)
        )
        
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
                # Primary end condition for reading responses
                if '</DASHBOARD_DATA>' in line or (expect_readings and '---END_READINGS---' in line):
                    end_reason = "end_marker"
                    break
                if expect_readnow and ('[MANUAL] RFID read complete' in line or '[MANUAL] RFID read skipped' in line):
                    end_reason = "readnow_done"
                    break
            # Check timeout
            now_ts = time.time()
            if (
                not expect_readnow and
                received_any and
                last_rx_time is not None and
                (now_ts - last_rx_time) > quiet_period
            ):
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
        log_general_debug(f"[HOSTDBG] send_command_done t={time.time():.3f} cmd={command} reason={end_reason or 'unknown'} bytes={bytes_count} lines={line_count}")
        return response.strip()
    except Exception as e:
        log_general_debug(f"[DEBUG] Error in send_command: {e}")
        return ""

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
            # Normal format: #200: 2025-07-23 05:13:05, 999, 141004265912, 24.86°C, ANT1
            # Older entries may omit antenna (defaults to ANT1 for backward compatibility)
            debug_match = re.search(r'#\d+:\s*\[DEBUG\]\s*raw_timestamp=\d+,\s*converted=([\d\-]+\s[\d:]+),\s*([\d]+),\s*([\d]+),\s*((?:[\d.]+°C|N/A))(?:,\s*(ANT[12]))?', line)
            normal_match = re.search(r'#\d+:\s*([\d\-]+\s[\d:]+),\s*([\d]+),\s*([\d]+),\s*((?:[\d.]+°C|N/A))(?:,\s*(ANT[12]))?', line)
            
            if debug_match:
                timestamp, value1, tag, temp, antenna = debug_match.groups()
                # Remove °C suffix if present, keep "N/A" as is
                if temp == 'N/A':
                    temp_value = 'N/A'
                else:
                    temp_value = temp.replace('°C', '')
                antenna_value = antenna if antenna else 'ANT1'
                readings.append({
                    'Timestamp': timestamp,
                    'Value1': value1,
                    'Tag': tag,
                    'Temperature_C': temp_value,
                    'Antenna': antenna_value
                })
            elif normal_match:
                timestamp, value1, tag, temp, antenna = normal_match.groups()
                # Remove °C suffix if present, keep "N/A" as is
                if temp == 'N/A':
                    temp_value = 'N/A'
                else:
                    temp_value = temp.replace('°C', '')
                antenna_value = antenna if antenna else 'ANT1'
                readings.append({
                    'Timestamp': timestamp,
                    'Value1': value1,
                    'Tag': tag,
                    'Temperature_C': temp_value,
                    'Antenna': antenna_value
                })
    
    return readings

def parse_live_readnow_results(response, timestamp_epoch=None):
    """Parse live RFID_RESULT lines emitted by the readnow command."""
    readings = []
    if not response:
        return readings

    fallback_epoch = time.time() if timestamp_epoch is None else timestamp_epoch

    for line in response.splitlines():
        match = re.search(
            r'\[RFID_RESULT\]\s+stored=true\s+ant=(ANT[12])\s+reading=\d+\s+(?:ts=(\d+)\s+)?tag=(\d+)\s+(\d+)\s+temp=([^\s]+)',
            line
        )
        if not match:
            continue

        antenna, stored_epoch, country, tag, temp = match.groups()
        reading_epoch = int(stored_epoch) if stored_epoch else fallback_epoch
        timestamp_str = datetime.fromtimestamp(reading_epoch, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        temp_value = 'N/A' if temp == 'N/A' else temp.replace('°C', '').replace('C', '')
        readings.append({
            'Timestamp': timestamp_str,
            'Value1': country,
            'Tag': tag,
            'Temperature_C': temp_value,
            'Antenna': antenna
        })

    return readings

def extract_live_readnow_epochs(response):
    """Return stored UTC epochs reported by live RFID_RESULT lines."""
    if not response:
        return []
    epochs = []
    for line in response.splitlines():
        match = re.search(r'\[RFID_RESULT\].*?\sts=(\d+)\s+', line)
        if match:
            epochs.append(int(match.group(1)))
    return epochs

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

def readings_to_dataframe(readings, selected_timezone):
    """Convert parsed RFID readings to the dashboard dataframe format."""
    df = pd.DataFrame(readings)
    if df.empty or 'Timestamp' not in df.columns:
        return df

    df['Timestamp'] = df['Timestamp'].apply(
        lambda x: convert_timestamp_to_timezone(x, selected_timezone)
    )
    ts_split = df['Timestamp'].apply(lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S'))
    df = df.assign(
        Year=ts_split.dt.year,
        Month=ts_split.dt.month,
        Day=ts_split.dt.day,
        Hour=ts_split.dt.hour,
        Minute=ts_split.dt.minute
    )
    return df.sort_values('Timestamp')

def merge_live_view_dataframe(existing_df, new_df):
    """Merge incremental Live View results while removing overlap duplicates."""
    if new_df is None or new_df.empty:
        return existing_df, 0
    if existing_df is None or existing_df.empty:
        return new_df.sort_values('Timestamp'), len(new_df)

    before_count = len(existing_df)
    merged = pd.concat([existing_df, new_df], ignore_index=True)
    dedupe_cols = [
        col for col in ['Timestamp', 'Value1', 'Tag', 'Temperature_C', 'Antenna']
        if col in merged.columns
    ]
    if dedupe_cols:
        merged = merged.drop_duplicates(subset=dedupe_cols, keep='last')
    merged = merged.sort_values('Timestamp')
    return merged, max(0, len(merged) - before_count)

def clear_read_now_latest_state():
    """Clear the dashboard-side latest manual read highlight."""
    st.session_state['read_now_latest_records'] = []
    st.session_state['read_now_latest_status'] = ""
    st.session_state['read_now_latest_message'] = ""
    st.session_state['read_now_latest_at'] = None
    st.session_state['read_now_latest_response'] = ""

def clear_display_state():
    """Clear dashboard-side display data without deleting device storage."""
    st.session_state['last_df'] = None
    st.session_state['last_raw_response'] = None
    st.session_state['last_live_readnow_response'] = ""
    st.session_state['last_successful_update'] = None
    st.session_state['live_view_last_new_rows'] = 0
    st.session_state['live_view_last_range'] = None
    st.session_state['new_query'] = False
    clear_read_now_latest_state()

def render_latest_read_now_panel():
    """Render the highlighted latest manual Read Now result."""
    status = st.session_state.get('read_now_latest_status', "")
    records = st.session_state.get('read_now_latest_records', [])
    message = st.session_state.get('read_now_latest_message', "")
    latest_at = st.session_state.get('read_now_latest_at')

    if not status:
        return

    with st.container(border=True):
        st.markdown("#### Latest Reading")
        if latest_at:
            st.caption(f"Read Now completed at {latest_at.strftime('%Y-%m-%d %H:%M:%S')}")

        if status == "readings" and records:
            st.success(message or f"{len(records)} tag reading(s) stored and added to the graph.")
            records_by_antenna = {
                str(record.get('Antenna', '')).upper(): record
                for record in records
            }
            card_columns = st.columns(2)
            for idx, antenna in enumerate(["ANT1", "ANT2"]):
                record = records_by_antenna.get(antenna)
                with card_columns[idx]:
                    with st.container(border=True):
                        if record:
                            st.markdown(f"**{antenna} · Tag {record.get('Tag', 'N/A')}**")
                            temp_value = record.get('Temperature_C', 'N/A')
                            temp_label = "N/A" if str(temp_value) == "N/A" else f"{temp_value} °C"
                            st.metric("Temperature", temp_label)
                            st.write(f"**Timestamp:** {record.get('Timestamp', 'N/A')}")
                            st.write(f"**Country:** {record.get('Value1', 'N/A')}")
                        else:
                            st.markdown(f"**{antenna}**")
                            st.metric("Temperature", "No tag")
                            st.write("**Tag:** Not detected")
                            st.write("**Timestamp:** N/A")
        elif status == "no_tag":
            st.info(message or "No tag detected during the manual read window.")
            card_columns = st.columns(2)
            for idx, antenna in enumerate(["ANT1", "ANT2"]):
                with card_columns[idx]:
                    with st.container(border=True):
                        st.markdown(f"**{antenna}**")
                        st.metric("Temperature", "No tag")
                        st.write("**Tag:** Not detected")
                        st.write("**Timestamp:** N/A")
        elif status == "skipped":
            st.warning(message or "Manual read was skipped by the device.")
        elif status == "empty":
            st.error(message or "The device did not respond to the Read Now command.")
        else:
            st.info(message)

def get_live_view_refresh_interval():
    """Return the bounded Live View polling interval in seconds."""
    try:
        interval = float(st.session_state.get(
            'live_view_refresh_interval_s',
            DEFAULT_LIVE_VIEW_REFRESH_INTERVAL_SECONDS
        ))
    except (TypeError, ValueError):
        interval = DEFAULT_LIVE_VIEW_REFRESH_INTERVAL_SECONDS
    try:
        rfid_window_s = float(st.session_state.get('esp32_rfidOnTime', 5))
    except (TypeError, ValueError):
        rfid_window_s = 5
    read_safe_minimum = max(
        MIN_LIVE_VIEW_REFRESH_INTERVAL_SECONDS,
        (rfid_window_s * 2) + 2
    )
    return max(
        read_safe_minimum,
        min(MAX_LIVE_VIEW_REFRESH_INTERVAL_SECONDS, interval)
    )

def schedule_next_live_view_attempt(backoff_seconds=0):
    """Reset Live View timers so stalled cycles do not immediately retrigger."""
    next_base = time.time() + max(0, backoff_seconds)
    st.session_state['last_live_update'] = next_base
    st.session_state['live_view_fragment_tick_at'] = next_base

def pause_live_view_after_errors(message):
    """Pause dashboard-commanded Live View without closing the serial connection."""
    st.session_state['live_view_enabled'] = False
    st.session_state['live_view_checkbox'] = False
    st.session_state['live_view_stop_requested'] = True
    st.session_state['is_auto_refresh'] = False
    st.session_state['live_view_last_error'] = message
    st.session_state['live_view_empty_response_count'] = 0
    schedule_next_live_view_attempt()

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
        # Wake device and clear stale buffered data.
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
        "liveViewAutoReadIntervalMs": "LIVEVIEWAUTOREADINTERVALMS",
        "ssid": "SSID",
        "password": "PASSWORD",
        "longPressMs": "LONGPRESSMS",
        "socLowIdleEnabled": "SOCLOWIDLEENABLED",
        "lowSocUsbRecoveryWindowMs": "LOWSOCUSBRECOVERYWINDOWMS",
        "socLowThresholdPercent": "SOCLOWTHRESHOLDPERCENT",
        "batteryMinVoltage": "BATTERYMINVOLTAGE",
        "batteryMaxVoltage": "BATTERYMAXVOLTAGE",
        "verbose": "VERBOSE",
        "dashboardModeActive": "DASHBOARDMODEACTIVE",
        "ledHeartbeatIntervalMs": "LEDHEARTBEATINTERVALMS",
        "ledHeartbeatOnMs": "LEDHEARTBEATONMS"
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

def wait_for_device_ready(ser, max_wait=8.0):
    """Probe status until the ESP32 is ready after USB serial open/reset."""
    if ser is None or not is_serial_valid(ser):
        return False

    deadline = time.time() + max_wait
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            log_general_debug(f"[CONNECT] Readiness probe attempt {attempt}")
            if hasattr(ser, "reset_input_buffer"):
                ser.reset_input_buffer()
            ser.write(b"\n")
            ser.flush()
            time.sleep(0.12)
            if hasattr(ser, "reset_input_buffer"):
                ser.reset_input_buffer()
            ser.write(b"status\n")
            ser.flush()

            probe_deadline = time.time() + 1.0
            response_lines = []
            while time.time() < probe_deadline:
                if ser.in_waiting:
                    line = ser.readline().decode(errors='ignore').strip()
                    if line:
                        response_lines.append(line)
                        log_general_debug(f"[CONNECT] Readiness probe received: {line}")
                        if ("Dashboard Mode:" in line or
                            "[IDLE] Mode:" in line or
                            "CMD_RECEIVED" in line):
                            log_general_debug("[CONNECT] ESP32 readiness confirmed")
                            return True
                else:
                    time.sleep(0.02)

            if response_lines:
                joined = "\n".join(response_lines)
                parsed = parse_status_response(joined)
                if parsed["dashboard_mode"] is not None or parsed["idle_mode"] is not None:
                    log_general_debug("[CONNECT] ESP32 readiness confirmed from parsed status")
                    return True
        except SERIAL_EXCEPTIONS as e:
            log_general_debug(f"[CONNECT] Readiness probe serial error: {e}")
            return False
        except Exception as e:
            log_general_debug(f"[CONNECT] Readiness probe warning: {e}")

        time.sleep(0.35)

    log_general_debug("[CONNECT] ESP32 readiness probe timed out")
    return False

def send_range_command_with_retry(ser, command, context_label, retries=1, timeout_seconds=None):
    """Send a range command and retry briefly if Windows/USB timing returns empty."""
    response = send_command(ser, command, range_timeout_seconds=timeout_seconds)
    if response and response.strip():
        return response

    for attempt in range(retries):
        log_general_debug(f"[HOSTDBG] {context_label}_empty_retry attempt={attempt+1}/{retries} t={time.time():.3f}")
        time.sleep(0.8)
        response = send_command(ser, command, range_timeout_seconds=timeout_seconds)
        if response and response.strip():
            return response

    return response

def parse_status_response(response):
    """Parse status response lines into dashboard/idle state."""
    status = {
        "dashboard_mode": None,
        "idle_mode": None,
        "idle_reason": "",
        "idle_recovery_active": None,
        "idle_recovery_remaining_s": None
    }

    for raw_line in response.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line_lower = line.lower()

        if "dashboard mode:" in line_lower:
            line_upper = line.upper()
            if "INACTIVE" in line_upper or " OFF" in line_upper:
                status["dashboard_mode"] = False
            elif "ACTIVE" in line_upper or " ON" in line_upper:
                status["dashboard_mode"] = True

        if "[idle] mode:" in line_lower or "idle mode:" in line_lower:
            line_upper = line.upper()
            if "INACTIVE" in line_upper:
                status["idle_mode"] = False
            elif "ACTIVE" in line_upper:
                status["idle_mode"] = True

        if "[idle] latest reason:" in line_lower or "idle reason:" in line_lower:
            parts = line.split(":", 1)
            if len(parts) == 2:
                status["idle_reason"] = parts[1].strip()

        if "low soc usb recovery:" in line_lower:
            line_upper = line.upper()
            if "INACTIVE" in line_upper:
                status["idle_recovery_active"] = False
            elif "ACTIVE" in line_upper:
                status["idle_recovery_active"] = True

            match = re.search(r"(\d+)\s*s\s+remaining", line_lower)
            if match:
                status["idle_recovery_remaining_s"] = int(match.group(1))

        if "[idle] usb recovery remaining:" in line_lower:
            parts = line.split(":", 1)
            if len(parts) == 2:
                match = re.search(r"(\d+)", parts[1])
                if match:
                    status["idle_recovery_remaining_s"] = int(match.group(1))

    # Defensive fallback: if device reported a concrete idle reason but no explicit idle mode
    # line was parsed, infer active idle mode from reason.
    if status["idle_mode"] is None and status["idle_reason"]:
        reason_upper = status["idle_reason"].upper()
        if reason_upper.startswith("IDLE_") and reason_upper != "IDLE_NONE":
            status["idle_mode"] = True

    return status

def expire_idle_recovery_state():
    """Expire the low-SoC recovery banner locally between device status polls."""
    if not st.session_state.get('idle_recovery_active', False):
        return

    updated_at = st.session_state.get('idle_recovery_updated_at', 0)
    remaining_s = st.session_state.get('idle_recovery_remaining_s', 0)
    if updated_at <= 0 or remaining_s <= 0:
        st.session_state['idle_recovery_active'] = False
        st.session_state['idle_recovery_remaining_s'] = 0
        return

    elapsed_s = time.time() - updated_at
    current_remaining = max(0, int(remaining_s - elapsed_s + 0.999))
    st.session_state['idle_recovery_remaining_s'] = current_remaining
    if current_remaining <= 0:
        st.session_state['idle_recovery_active'] = False

def apply_parsed_status(parsed):
    """Apply parsed status/debug fields to session state."""
    now_ts = time.time()
    if parsed["dashboard_mode"] is not None:
        st.session_state['device_dashboard_mode'] = parsed["dashboard_mode"]
        if parsed["dashboard_mode"]:
            st.session_state['idle_recovery_active'] = False
            st.session_state['idle_recovery_remaining_s'] = 0
            st.session_state['idle_recovery_updated_at'] = 0
    if parsed["idle_mode"] is not None:
        st.session_state['idle_mode_active'] = parsed["idle_mode"]
    if parsed["idle_reason"]:
        st.session_state['idle_mode_reason'] = parsed["idle_reason"]
    if st.session_state.get('device_dashboard_mode', False):
        st.session_state['idle_recovery_active'] = False
        st.session_state['idle_recovery_remaining_s'] = 0
        st.session_state['idle_recovery_updated_at'] = 0
    elif parsed["idle_recovery_active"] is not None:
        st.session_state['idle_recovery_active'] = parsed["idle_recovery_active"]
        st.session_state['idle_recovery_updated_at'] = now_ts
        if not parsed["idle_recovery_active"]:
            st.session_state['idle_recovery_remaining_s'] = 0
    if not st.session_state.get('device_dashboard_mode', False) and parsed["idle_recovery_remaining_s"] is not None:
        st.session_state['idle_recovery_remaining_s'] = parsed["idle_recovery_remaining_s"]
        st.session_state['idle_recovery_updated_at'] = now_ts
        if parsed["idle_recovery_remaining_s"] <= 0:
            st.session_state['idle_recovery_active'] = False

def poll_device_status_if_due():
    """Poll status from ESP32 every 5 minutes while connected."""
    if not st.session_state.connected or not is_serial_valid(st.session_state.serial_connection):
        return
    if st.session_state.get('live_view_enabled', False):
        return

    expire_idle_recovery_state()

    now_ts = time.time()
    poll_interval = RECOVERY_STATUS_POLL_INTERVAL_SECONDS if st.session_state.get('idle_recovery_active', False) else STATUS_POLL_INTERVAL_SECONDS
    if now_ts - st.session_state.get('last_status_poll', 0) < poll_interval:
        return

    log_general_debug(f"[HOSTDBG] status_poll_start t={time.time():.3f}")
    response = send_command(st.session_state.serial_connection, "status")

    if not response:
        log_general_debug("[DEBUG] status poll returned empty response")
        return

    parsed = parse_status_response(response)
    parsed_any = (
        parsed["dashboard_mode"] is not None or
        parsed["idle_mode"] is not None or
        bool(parsed["idle_reason"]) or
        parsed["idle_recovery_active"] is not None or
        parsed["idle_recovery_remaining_s"] is not None
    )

    if not parsed_any:
        log_general_debug("[DEBUG] status poll returned no parseable status fields; will retry soon")
        # On fresh connect, boot logs can drown out the first status response.
        # Force a few quick rerun retries until we capture a valid status block.
        if not st.session_state.get('status_state_initialized', False):
            retries = st.session_state.get('status_retry_count', 0)
            if retries < 4:
                st.session_state['status_retry_count'] = retries + 1
                time.sleep(0.2)
                st.rerun()
        return

    st.session_state['last_status_poll'] = now_ts
    st.session_state['status_state_initialized'] = True
    st.session_state['status_retry_count'] = 0
    apply_parsed_status(parsed)
    log_general_debug(f"[HOSTDBG] status_poll_done t={time.time():.3f} dashboard={st.session_state.get('device_dashboard_mode')} idle={st.session_state.get('idle_mode_active')} recovery={st.session_state.get('idle_recovery_active')}")


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
        selected_port_metadata = get_serial_port_metadata(selected_port)
        with st.sidebar.expander("Selected Port Details"):
            st.caption(format_serial_port_metadata(selected_port_metadata))
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
            log_general_debug(
                f"[CONNECT] Selected port metadata: "
                f"{format_serial_port_metadata(get_serial_port_metadata(selected_port))}"
            )
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
                    if should_skip_cleanup_probe(selected_port):
                        log_general_debug(
                            f"[CONNECT] Skipping cleanup probe for {selected_port}; "
                            "Silicon Labs CP210x driver can reject probe opens with EINVAL"
                        )
                    else:
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
                        # Wait for ESP32 to finish booting after reset/enumeration before marking it connected.
                        # Windows can take longer than macOS to deliver the first reliable USB-CDC response.
                        log_general_debug(f"[CONNECT] Waiting for ESP32 readiness handshake...")
                        device_ready = wait_for_device_ready(st.session_state.serial_connection)
                        if not device_ready:
                            log_general_debug("[CONNECT] ESP32 did not answer readiness probes; closing connection")
                            try:
                                st.session_state.serial_connection.close()
                            except Exception:
                                pass
                            st.session_state.serial_connection = None
                            st.session_state.connected = False
                            st.session_state.connected_port = None
                            st.sidebar.error("⚠️ ESP32 did not respond. Confirm Dashboard Mode is active and try again.")
                            st.stop()
                        
                        st.session_state.connected = True
                        st.session_state.connected_port = selected_port  # Store port name (persists across reruns)
                        st.session_state['last_status_poll'] = 0  # Force fresh status poll after connect
                        st.session_state['status_state_initialized'] = False
                        st.session_state['status_retry_count'] = 0
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
            st.session_state['device_dashboard_mode'] = False
            st.session_state['idle_mode_active'] = False
            st.session_state['idle_mode_reason'] = ""
            st.session_state['idle_recovery_active'] = False
            st.session_state['idle_recovery_remaining_s'] = 0
            st.session_state['idle_recovery_updated_at'] = 0
            st.session_state['status_state_initialized'] = False
            st.session_state['status_retry_count'] = 0
            st.sidebar.info("Disconnected! (Dashboard mode remains active on ESP32)")
            st.rerun()  # Force rerun to update button display
        
    if st.session_state.connected:
        # Validate connection on startup and periodically during Live View
        connection_valid = True
        if st.session_state.get('live_view_enabled', False):
            # Live View readnow cycles are the liveness probe. Avoid injecting
            # separate status commands into the same serial stream while reads run.
            if not is_serial_valid(st.session_state.serial_connection):
                st.error("⚠️ **Connection Lost:** Serial port is no longer valid. Please reconnect.")
                st.session_state.connected = False
                st.session_state.connected_port = None
                st.session_state.serial_connection = None
                st.session_state['connection_error_count'] = 0
                st.rerun()
        
        if st.session_state.connected:
            poll_device_status_if_due()
            expire_idle_recovery_state()
            st.success("✅ Connected to RFID Reader")

            if st.session_state.get('idle_mode_active', False):
                idle_reason = st.session_state.get('idle_mode_reason', '').strip() or "Unknown reason"
                if st.session_state.get('device_dashboard_mode', False):
                    st.warning(f"🟨 **Idle Mode Active:** {idle_reason}. USB dashboard data retrieval and configuration remain available; RFID reads stay blocked while idle is active.")
                elif st.session_state.get('idle_recovery_active', False):
                    recovery_remaining = st.session_state.get('idle_recovery_remaining_s', 0)
                    st.warning(f"🟨 **Idle Mode Active:** {idle_reason}. USB recovery window active ({recovery_remaining}s remaining); dashboard data/config access is available and RFID reads stay blocked.")
                else:
                    st.warning(f"🟨 **Idle Mode Active:** {idle_reason}")
            
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
                    else:
                        st.caption(f"➕ Rows added last refresh: {st.session_state.get('live_view_last_new_rows', 0)}")
        
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
            end_time = st.time_input("End Time:", value=dt_time(23, 59, 59))
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
            # Live View uses UTC epoch timestamps internally so changing the display timezone
            # cannot shift the device query window.
            start_epoch_live = st.session_state.get('live_view_start_epoch')
            if start_epoch_live is None:
                start_epoch_live = int(time.time())
                st.session_state['live_view_start_epoch'] = start_epoch_live
                st.session_state['live_view_start_timestamp'] = datetime.fromtimestamp(start_epoch_live)
            end_epoch_live = int(time.time())

        # Retrieve Data button - disabled when Live View is active
        retrieve_clicked = st.button(
            "🔍 Retrieve Data", 
            type="primary",
            disabled=live_view_enabled_for_date_range,
            help="Disabled while Live View is active. Disable Live View to use this button."
        )
        
        # Auto-refresh logic for Live View
        should_auto_refresh = False
        live_view_refresh_interval = get_live_view_refresh_interval()
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
                backoff_until = st.session_state.get('live_view_backoff_until', 0)
                time_since_last_update = current_time - last_update
                # Check if 5 seconds have passed OR if last_update is 0 (first fetch after enabling Live View)
                if current_time < backoff_until:
                    st.session_state['is_auto_refresh'] = False
                elif time_since_last_update >= live_view_refresh_interval or last_update == 0:
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
                        log_general_debug(f"[HOSTDBG] manual_range_start t={time.time():.3f} start={start_epoch} end={end_epoch}")
                        response = send_range_command_with_retry(
                            st.session_state.serial_connection,
                            command,
                            "manual_range",
                            retries=1,
                            timeout_seconds=st.session_state.get('dashboard_fetch_timeout_s')
                        )
                        # Always record something so the UI can show a summary area
                        st.session_state['last_raw_response'] = response if response is not None else ""
                        if response:
                            readings = parse_readings(response)
                            if readings:
                                df = readings_to_dataframe(readings, st.session_state['selected_timezone'])
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
                        log_general_debug(f"[HOSTDBG] manual_range_done t={time.time():.3f} response_len={len(response) if response else 0}")
                    st.session_state['new_query'] = False
                else:
                    # Auto-refresh: fetch data silently using Live View date range
                    # CRITICAL: Only proceed if Live View date range is calculated (start_epoch_live is set)
                    # This prevents using picker date range when Live View is first enabled
                    if live_view_enabled_for_refresh and start_epoch_live is not None:
                        log_general_debug(
                            f"[HOSTDBG] live_readnow_start t={time.time():.3f} "
                            f"interval={live_view_refresh_interval:.1f}s"
                        )
                        readnow_response = send_command(st.session_state.serial_connection, "readnow")
                        st.session_state['last_live_readnow_response'] = readnow_response if readnow_response is not None else ""
                        log_general_debug(
                            f"[HOSTDBG] live_readnow_done t={time.time():.3f} "
                            f"response_len={len(readnow_response) if readnow_response else 0}"
                        )
                        live_readnow_new_rows = 0
                        live_readnow_readings = parse_live_readnow_results(readnow_response, time.time())
                        if live_readnow_readings:
                            readnow_df = readings_to_dataframe(
                                live_readnow_readings,
                                st.session_state['selected_timezone']
                            )
                            merged_df, live_readnow_new_rows = merge_live_view_dataframe(
                                st.session_state.get('last_df'),
                                readnow_df
                            )
                            st.session_state['last_df'] = merged_df
                            st.session_state['live_view_last_new_rows'] = live_readnow_new_rows
                            st.session_state['last_successful_update'] = time.time()
                            log_general_debug(
                                f"[HOSTDBG] live_readnow_merge parsed={len(live_readnow_readings)} "
                                f"new_rows={live_readnow_new_rows} total_rows={len(merged_df)}"
                            )

                        readnow_epochs = extract_live_readnow_epochs(readnow_response)
                        if readnow_epochs:
                            st.session_state['live_view_last_fetch_epoch'] = max(readnow_epochs)
                        else:
                            st.session_state['live_view_last_fetch_epoch'] = int(time.time())

                        # Live View plots directly from the readnow result. Avoid a follow-up range
                        # fetch every cycle; those flash reads can block long enough to drop serial.
                        st.session_state['live_view_last_range'] = None
                        if readnow_response and readnow_response.strip():
                            st.session_state['connection_error_count'] = 0
                            st.session_state['live_view_empty_response_count'] = 0
                            st.session_state['live_view_backoff_until'] = 0
                            st.session_state['live_view_last_error'] = ""
                            schedule_next_live_view_attempt()
                            if "[MANUAL] RFID read skipped" in readnow_response:
                                st.session_state['live_view_last_new_rows'] = 0
                                log_general_debug("[HOSTDBG] live_readnow_skipped; range fetch skipped")
                            elif not live_readnow_readings:
                                st.session_state['live_view_last_new_rows'] = 0
                                log_general_debug("[HOSTDBG] live_readnow_no_result; range fetch skipped")
                        else:
                            empty_count = st.session_state.get('live_view_empty_response_count', 0) + 1
                            st.session_state['live_view_empty_response_count'] = empty_count
                            st.session_state['connection_error_count'] = empty_count
                            st.session_state['live_view_last_new_rows'] = 0
                            if empty_count >= LIVE_VIEW_EMPTY_RESPONSE_LIMIT:
                                message = (
                                    "Live View paused after repeated empty read responses. "
                                    "The serial port stayed open; disable/enable Live View or use Test Connection before reconnecting."
                                )
                                pause_live_view_after_errors(message)
                                st.warning(f"⚠️ **Live View Paused:** {message}")
                                log_general_debug(
                                    f"[HOSTDBG] live_readnow_paused empty_count={empty_count} "
                                    f"t={time.time():.3f}"
                                )
                            else:
                                st.session_state['live_view_last_error'] = (
                                    "Live View read returned no serial bytes; waiting before the next auto-read."
                                )
                                st.session_state['live_view_backoff_until'] = (
                                    time.time() + LIVE_VIEW_EMPTY_RESPONSE_BACKOFF_SECONDS
                                )
                                schedule_next_live_view_attempt(LIVE_VIEW_EMPTY_RESPONSE_BACKOFF_SECONDS)
                                log_general_debug(
                                    f"[HOSTDBG] live_readnow_empty_backoff empty_count={empty_count} "
                                    f"backoff={LIVE_VIEW_EMPTY_RESPONSE_BACKOFF_SECONDS}s "
                                    f"t={time.time():.3f}"
                                )
                        log_general_debug(
                            f"[HOSTDBG] live_range_skipped t={time.time():.3f} "
                            f"reason=direct_readnow new_rows={live_readnow_new_rows}"
                        )
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
                    st.session_state['last_live_update'] = time.time() - live_view_refresh_interval
                    if live_view_enabled_for_refresh:
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
            help="Command an RFID read at the configured Live View interval, then refresh the graph"
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
            current_epoch = int(time.time())
            current_timestamp = datetime.fromtimestamp(current_epoch)
            st.session_state['live_view_start_timestamp'] = current_timestamp
            st.session_state['live_view_start_epoch'] = current_epoch
            st.session_state['live_view_last_fetch_epoch'] = None
            st.session_state['live_view_last_new_rows'] = 0
            st.session_state['live_view_last_range'] = None
            st.session_state['live_view_fragment_tick_at'] = time.time()
            st.session_state['last_live_update'] = 0
            st.session_state['last_live_readnow_response'] = ""
            st.session_state['live_view_empty_response_count'] = 0
            st.session_state['live_view_backoff_until'] = 0
            st.session_state['live_view_last_error'] = ""
            st.session_state['is_auto_refresh'] = False
            st.rerun()
        elif not live_view_enabled and previous_live_view_state:
            st.session_state['live_view_stop_requested'] = True
            st.session_state['live_view_start_timestamp'] = None
            st.session_state['live_view_start_epoch'] = None
            st.session_state['live_view_last_fetch_epoch'] = None
            st.session_state['live_view_last_new_rows'] = 0
            st.session_state['live_view_last_range'] = None
            st.session_state['live_view_fragment_tick_at'] = 0
            st.session_state['last_live_readnow_response'] = ""
            st.session_state['last_live_update'] = 0
            st.session_state['live_view_empty_response_count'] = 0
            st.session_state['live_view_backoff_until'] = 0
            st.session_state['live_view_last_error'] = ""
            st.session_state['is_auto_refresh'] = False
        
        # Show status message based on Live View state
        # Use the same logic as the button to determine if Live View is truly enabled
        live_view_status_checkbox = st.session_state.get('live_view_checkbox', False)
        live_view_status_stop = st.session_state.get('live_view_stop_requested', False)
        live_view_status_enabled = live_view_status_checkbox and not live_view_status_stop
        
        if live_view_status_enabled:
            if st.session_state.connected:
                st.info(f"🔄 **Live View Active:** Dashboard will command an RFID read every {get_live_view_refresh_interval():.0f} seconds, then update the graph.")
                if st.session_state.get('live_view_last_error'):
                    st.warning(f"⚠️ {st.session_state['live_view_last_error']}")
            else:
                # Live View is enabled but connection was lost (possibly due to browser disconnection)
                st.warning("⚠️ **Live View Enabled but Not Connected:** Please reconnect to the device to resume auto-updates. Live View will continue from where it left off once reconnected.")
        else:
            if st.session_state.get('live_view_last_error'):
                st.warning(f"⚠️ {st.session_state['live_view_last_error']}")
            st.info("💡 Enable Live View to command RFID reads and refresh the temperature graph automatically.")
        
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
            # Plotly line plot: Timestamp vs Temperature_C, one line per antenna/tag pair.
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
                if 'Antenna' in df.columns:
                    st.write(f"Antennas found: {sorted(df['Antenna'].dropna().unique())}")
                st.write(f"Date range: {df['Timestamp'].min()} to {df['Timestamp'].max()}")
                
                if not df.empty:
                    # Count rows with N/A temperature
                    na_count = (df['Temperature_C'] == 'N/A').sum() if 'Temperature_C' in df.columns else 0
                    
                    # Create a copy for numeric conversion (keep original for table display)
                    df_chart = df.copy()
                    
                    # Convert Temperature_C to numeric, keeping "N/A" as NaN
                    df_chart['Temperature_C'] = pd.to_numeric(df_chart['Temperature_C'], errors='coerce')
                    if 'Antenna' not in df_chart.columns:
                        df_chart['Antenna'] = 'ANT?'
                    df_chart['Antenna'] = df_chart['Antenna'].fillna('ANT?').astype(str)
                    df_chart['Antenna_Tag'] = df_chart['Antenna'] + " · " + df_chart['Tag'].astype(str)
                    
                    # Remove any rows with NaN temperature values (includes "N/A" and invalid values)
                    df_clean = df_chart.dropna(subset=['Temperature_C'])
                    
                    if na_count > 0:
                        st.info(f"ℹ️ {na_count} reading(s) have no temperature data (N/A) and are excluded from the chart but shown in the table below.")
                    
                    if len(df_clean) != len(df_chart) and na_count == 0:
                        # Only show warning if there are invalid numeric values (not just N/A)
                        invalid_count = len(df_chart) - len(df_clean) - na_count
                        if invalid_count > 0:
                            st.warning(f"⚠️ Filtered out {invalid_count} row(s) with invalid temperature data")
                    
                    if not df_clean.empty:
                        fig = px.line(
                            df_clean,
                            x="Timestamp",
                            y="Temperature_C",
                            color="Antenna_Tag",
                            title=f"Temperature vs Timestamp by Antenna and Tag ({timezone_display})",
                            labels={
                                "Temperature_C": "Temperature (°C)",
                                "Timestamp": "Timestamp",
                                "Antenna_Tag": "Antenna · Tag",
                                "Antenna": "Antenna",
                                "Tag": "Tag"
                            },
                            hover_data=["Antenna", "Tag"]
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
                        fig = px.line(title=f"Temperature vs Timestamp by Antenna and Tag ({timezone_display})")
                        fig.update_layout(xaxis_title="Timestamp", yaxis_title="Temperature (°C)")
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    # DataFrame is empty
                    fig = px.line(title=f"Temperature vs Timestamp by Antenna and Tag ({timezone_display})")
                    fig.update_layout(xaxis_title="Timestamp", yaxis_title="Temperature (°C)")
                    st.plotly_chart(fig, use_container_width=True)
        else:
            # Show blank plot if no results
            fig = px.line(title="Temperature vs Timestamp by Antenna and Tag")
            fig.update_layout(xaxis_title="Timestamp", yaxis_title="Temperature (°C)")
            st.plotly_chart(fig, use_container_width=True)

        clear_display_cols = st.columns([0.78, 0.22])
        with clear_display_cols[1]:
            if st.button(
                "Clear Display",
                use_container_width=True,
                disabled=st.session_state.get('last_df') is None and not st.session_state.get('last_raw_response'),
                help="Clear only the dashboard table and graph. Stored readings on the device are not changed."
            ):
                clear_display_state()
                st.rerun()

        st.header("⚡ Quick Commands")
        
        # Create single-button-per-row layout for maximum display space
        st.subheader("📡 Manual Read")

        live_view_active_for_read_now = (
            st.session_state.get('live_view_checkbox', False) and
            not st.session_state.get('live_view_stop_requested', False)
        )
        read_now_clicked = st.button(
            "📡 Read Now",
            use_container_width=True,
            disabled=live_view_active_for_read_now,
            help="Trigger one RFID read cycle like pressing the physical read button. Disabled while Live View is active."
        )
        if read_now_clicked:
            with st.spinner("Commanding RFID read..."):
                log_general_debug(f"[HOSTDBG] manual_readnow_start t={time.time():.3f}")
                readnow_response = send_command(st.session_state.serial_connection, "readnow")
                st.session_state['read_now_latest_response'] = readnow_response if readnow_response is not None else ""
                st.session_state['read_now_latest_at'] = datetime.now()
                log_general_debug(
                    f"[HOSTDBG] manual_readnow_done t={time.time():.3f} "
                    f"response_len={len(readnow_response) if readnow_response else 0}"
                )

                if readnow_response and readnow_response.strip():
                    readnow_readings = parse_live_readnow_results(readnow_response, time.time())
                    if readnow_readings:
                        readnow_df = readings_to_dataframe(
                            readnow_readings,
                            st.session_state['selected_timezone']
                        )
                        merged_df, new_rows = merge_live_view_dataframe(
                            st.session_state.get('last_df'),
                            readnow_df
                        )
                        st.session_state['last_df'] = merged_df
                        st.session_state['last_successful_update'] = time.time()
                        st.session_state['read_now_latest_records'] = readnow_df.to_dict('records')
                        st.session_state['read_now_latest_status'] = "readings"
                        st.session_state['read_now_latest_message'] = (
                            f"{len(readnow_readings)} antenna reading(s) captured; "
                            f"{new_rows} new row(s) added to the display."
                        )
                    elif "[MANUAL] RFID read skipped" in readnow_response:
                        st.session_state['read_now_latest_records'] = []
                        st.session_state['read_now_latest_status'] = "skipped"
                        skipped_lines = [
                            line for line in readnow_response.splitlines()
                            if "blocked" in line.lower() or "skipped" in line.lower()
                        ]
                        st.session_state['read_now_latest_message'] = (
                            " ".join(skipped_lines) if skipped_lines else
                            "The device skipped the manual read."
                        )
                    elif "[MANUAL] RFID read complete" in readnow_response:
                        st.session_state['read_now_latest_records'] = []
                        st.session_state['read_now_latest_status'] = "no_tag"
                        st.session_state['read_now_latest_message'] = (
                            "No tag was detected during this Read Now cycle. "
                            "Existing graph data was kept unchanged."
                        )
                    else:
                        st.session_state['read_now_latest_records'] = []
                        st.session_state['read_now_latest_status'] = "skipped"
                        st.session_state['read_now_latest_message'] = (
                            "Read Now returned a response, but no stored tag result was found."
                        )
                else:
                    st.session_state['read_now_latest_records'] = []
                    st.session_state['read_now_latest_status'] = "empty"
                    st.session_state['read_now_latest_message'] = (
                        "The device returned no serial bytes for Read Now. "
                        "The dashboard connection was left open."
                    )
                st.rerun()

        render_latest_read_now_panel()

        st.subheader("📊 Data Management")
        
        # Print All Button
        if st.button("📊 Print All", use_container_width=True):
            response = send_command(st.session_state.serial_connection, "print")
            if response:
                st.text("All stored readings:")
                if "---END_READINGS---" not in response:
                    st.warning("Print All response ended before ---END_READINGS---. The output below may be incomplete.")
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
                parsed_debug_status = parse_status_response(response)
                apply_parsed_status(parsed_debug_status)
                st.text("Debug information:")
                if "[SOC] Latest:" in response:
                    st.code(response)
                else:
                    latest_soc = get_latest_soc_line(response)
                    if latest_soc:
                        st.code(f"{response}\n\n[LATEST_SOC] {latest_soc}")
                    else:
                        st.code(f"{response}\n\n[LATEST_SOC] N/A")
        
        # Test Connection Button
        if st.button("🔍 Test Connection", use_container_width=True):
            if test_connection(st.session_state.serial_connection):
                st.success("✅ ESP32 is responsive!")
            else:
                st.error("❌ ESP32 not responding")
        
        st.divider()
    else:
        st.info("🔌 Please connect to your RFID reader using the sidebar.")
    
    # Auto-rerun for Live View. Use Streamlit's non-blocking fragment timer; do not
    # sleep in the main script, because that disables the whole page while it runs.
    session_state_live_view = st.session_state.get('live_view_enabled', False)
    stop_requested = st.session_state.get('live_view_stop_requested', False)
    
    if session_state_live_view and not stop_requested and st.session_state.connected:
        if hasattr(st, "fragment"):
            refresh_interval = get_live_view_refresh_interval()

            @st.fragment(run_every=refresh_interval)
            def live_view_autorefresh_tick():
                now_ts = time.time()
                last_tick = st.session_state.get('live_view_fragment_tick_at', 0)
                backoff_until = st.session_state.get('live_view_backoff_until', 0)
                if now_ts < backoff_until:
                    return
                if now_ts - last_tick >= refresh_interval:
                    st.session_state['live_view_fragment_tick_at'] = now_ts
                    log_general_debug(
                        f"[HOSTDBG] live_autorefresh_tick t={now_ts:.3f} "
                        f"interval={refresh_interval:.1f}s"
                    )
                    st.rerun()

            live_view_autorefresh_tick()
        else:
            st.warning("Live View auto-refresh requires Streamlit 1.37 or newer.")
    else:
        st.session_state['is_auto_refresh'] = False
        if session_state_live_view and not stop_requested and not st.session_state.connected:
            # Preserve Live View intent across disconnects; fetch immediately after reconnect.
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
    st.markdown("### Network")
    ssid = st.text_input("WiFi SSID", key="esp32_ssid")
    st.caption("Network name used only when the RTC must be restored from NTP.")
    password = st.text_input("WiFi Password", type="password", key="esp32_password")
    st.caption("Network password saved on the device for RTC/NTP recovery.")

    st.markdown("### Reading and Button Timing")
    rfidOnTime = st.number_input("RFID ON Time (seconds)", min_value=MIN_RFID_ON_TIME_SECONDS, max_value=60, key="esp32_rfidOnTime")
    st.caption(f"How long the RFID reader stays powered during each read window. Minimum allowed: {MIN_RFID_ON_TIME_SECONDS}s for stable dual-antenna reads.")
    periodicInterval = st.number_input("Periodic Interval (seconds)", min_value=10, max_value=3600, key="esp32_periodicInterval")
    st.caption("Delay between automatic periodic RFID read attempts when dashboard mode and idle mode are inactive.")
    longPressTime = st.number_input("Long Press Timer (seconds)", min_value=1, max_value=30, key="esp32_longPressTime")
    st.caption("Button hold duration required to toggle Dashboard Mode service access from the device.")

    st.markdown("### Live View")
    live_view_min_interval = max(
        MIN_LIVE_VIEW_REFRESH_INTERVAL_SECONDS,
        (float(rfidOnTime) * 2) + 2
    )
    if st.session_state.get('live_view_refresh_interval_s', DEFAULT_LIVE_VIEW_REFRESH_INTERVAL_SECONDS) < live_view_min_interval:
        st.session_state['live_view_refresh_interval_s'] = live_view_min_interval
    st.number_input(
        "Live View Auto-Read Interval (seconds)",
        min_value=live_view_min_interval,
        max_value=MAX_LIVE_VIEW_REFRESH_INTERVAL_SECONDS,
        step=1.0,
        format="%.0f",
        key="live_view_refresh_interval_s"
    )
    requested_live_view_interval = float(st.session_state.get(
        'live_view_refresh_interval_s',
        DEFAULT_LIVE_VIEW_REFRESH_INTERVAL_SECONDS
    ))
    effective_live_view_interval = get_live_view_refresh_interval()
    if effective_live_view_interval > requested_live_view_interval:
        st.caption(
            f"Dashboard-requested auto-read interval. Current safe minimum is "
            f"{live_view_min_interval:.0f}s for the dual-antenna RFID ON time, "
            f"so Live View will run every {effective_live_view_interval:.0f}s."
        )
    else:
        st.caption(
            f"Dashboard-requested auto-read interval. Current safe minimum is "
            f"{live_view_min_interval:.0f}s for the dual-antenna RFID ON time."
        )
    st.number_input(
        "Stored-Reading Fetch Timeout (seconds)",
        min_value=MIN_DASHBOARD_FETCH_TIMEOUT_SECONDS,
        max_value=MAX_DASHBOARD_FETCH_TIMEOUT_SECONDS,
        step=5,
        key="dashboard_fetch_timeout_s"
    )
    st.caption("Used for stored-reading range fetches such as manual filtered retrieval. Normal Live View graph updates directly from the auto-read result.")

    st.markdown("### Power and Idle Mode")
    socLowIdleEnabled = st.checkbox("Enable Low SoC Idle Mode", key="esp32_socLowIdleEnabled")
    st.caption("Allows measured low battery percentage to place the device in idle mode.")
    lowSocUsbRecoveryWindow = st.number_input("Low SoC USB Recovery Window (seconds)", min_value=0.0, max_value=300.0, step=1.0, format="%.0f", key="esp32_lowSocUsbRecoveryWindow")
    st.caption("Temporary wake window after low-SoC idle so USB can connect and enable Dashboard Mode. Once Dashboard Mode is active, this countdown is no longer relevant.")
    socLowThresholdPercent = st.number_input("Low SoC Threshold (%)", min_value=0.0, max_value=100.0, step=0.5, format="%.1f", key="esp32_socLowThresholdPercent")
    st.caption("Battery percentage at or below which low-SoC idle mode becomes active.")
    batteryMinVoltage = st.number_input("Battery Minimum Voltage", min_value=2.5, max_value=4.2, step=0.01, format="%.2f", key="esp32_batteryMinVoltage")
    st.caption("Voltage treated as 0% battery for the linear SoC calculation.")
    batteryMaxVoltage = st.number_input("Battery Maximum Voltage", min_value=3.5, max_value=4.5, step=0.01, format="%.2f", key="esp32_batteryMaxVoltage")
    st.caption("Voltage treated as 100% battery for the linear SoC calculation.")

    st.markdown("### Diagnostics and Runtime")
    verbose = st.checkbox("Verbose Serial Prints", key="esp32_verbose")
    st.caption("Enables detailed firmware debug logs over serial; leave off for normal dashboard use.")
    dashboardModeActive = st.checkbox("Dashboard Mode Active", key="esp32_dashboardModeActive")
    st.caption("Service mode latch. Keep ON while using USB dashboard access; turn OFF only when releasing the device back to normal light-sleep operation.")

    st.markdown("### LED Heartbeat")
    ledHeartbeatInterval = st.number_input("LED Heartbeat Interval (seconds)", min_value=1.0, max_value=120.0, step=0.5, format="%.1f", key="esp32_ledHeartbeatInterval")
    st.caption("Off-time between status heartbeat blinks for sleep, dashboard, and idle states.")
    ledHeartbeatOn = st.number_input("LED Heartbeat On Duration (seconds)", min_value=0.1, max_value=10.0, step=0.1, format="%.1f", key="esp32_ledHeartbeatOn")
    st.caption("How long the LED stays on for each heartbeat blink.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Set Variables on ESP32"):
            st.session_state['set_debug_log'] = []  # Clear previous set debug log
            if st.session_state.connected:
                valid_config = True
                if batteryMaxVoltage <= batteryMinVoltage:
                    valid_config = False
                    st.error("Battery maximum voltage must be greater than battery minimum voltage.")
                    log_set_debug("[ERROR] Battery maximum voltage must be greater than battery minimum voltage.")
                if ledHeartbeatOn >= ledHeartbeatInterval:
                    valid_config = False
                    st.error("LED heartbeat on duration must be shorter than the heartbeat interval.")
                    log_set_debug("[ERROR] LED heartbeat on duration must be shorter than the heartbeat interval.")

                if valid_config:
                    cmds = [
                        f"set ssid {ssid}",
                        f"set password {password}",
                        f"set rfidOnTimeMs {int(rfidOnTime*1000)}",
                        f"set periodicIntervalMs {int(periodicInterval*1000)}",
                        f"set liveViewAutoReadIntervalMs {int(requested_live_view_interval*1000)}",
                        f"set longPressMs {int(longPressTime*1000)}",
                        f"set socLowIdleEnabled {1 if socLowIdleEnabled else 0}",
                        f"set lowSocUsbRecoveryWindowMs {int(lowSocUsbRecoveryWindow*1000)}",
                        f"set socLowThresholdPercent {socLowThresholdPercent:.2f}",
                        f"set batteryMinVoltage {batteryMinVoltage:.2f}",
                        f"set batteryMaxVoltage {batteryMaxVoltage:.2f}",
                        f"set verbose {1 if verbose else 0}",
                        f"set dashboardModeActive {1 if dashboardModeActive else 0}",
                        f"set ledHeartbeatIntervalMs {int(ledHeartbeatInterval*1000)}",
                        f"set ledHeartbeatOnMs {int(ledHeartbeatOn*1000)}"
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
                vars = [
                    "ssid",
                    "password",
                    "rfidOnTimeMs",
                    "periodicIntervalMs",
                    "liveViewAutoReadIntervalMs",
                    "longPressMs",
                    "socLowIdleEnabled",
                    "lowSocUsbRecoveryWindowMs",
                    "socLowThresholdPercent",
                    "batteryMinVoltage",
                    "batteryMaxVoltage",
                    "verbose",
                    "dashboardModeActive",
                    "ledHeartbeatIntervalMs",
                    "ledHeartbeatOnMs"
                ]
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
                    elif v == "liveViewAutoReadIntervalMs":
                        try:
                            updates["live_view_refresh_interval_s"] = int(resp) / 1000 if resp else DEFAULT_LIVE_VIEW_REFRESH_INTERVAL_SECONDS
                        except:
                            updates["live_view_refresh_interval_s"] = DEFAULT_LIVE_VIEW_REFRESH_INTERVAL_SECONDS
                    elif v == "longPressMs":
                        try:
                            # Convert milliseconds to seconds for display
                            updates["esp32_longPressTime"] = int(resp) / 1000 if resp else 5
                        except:
                            updates["esp32_longPressTime"] = 5
                    elif v == "socLowIdleEnabled":
                        updates["esp32_socLowIdleEnabled"] = str(resp).strip() == "1"
                    elif v == "lowSocUsbRecoveryWindowMs":
                        try:
                            updates["esp32_lowSocUsbRecoveryWindow"] = int(resp) / 1000 if resp else 15.0
                        except:
                            updates["esp32_lowSocUsbRecoveryWindow"] = 15.0
                    elif v == "socLowThresholdPercent":
                        try:
                            updates["esp32_socLowThresholdPercent"] = float(resp) if resp else 10.0
                        except:
                            updates["esp32_socLowThresholdPercent"] = 10.0
                    elif v == "batteryMinVoltage":
                        try:
                            updates["esp32_batteryMinVoltage"] = float(resp) if resp else 3.52
                        except:
                            updates["esp32_batteryMinVoltage"] = 3.52
                    elif v == "batteryMaxVoltage":
                        try:
                            updates["esp32_batteryMaxVoltage"] = float(resp) if resp else 4.15
                        except:
                            updates["esp32_batteryMaxVoltage"] = 4.15
                    elif v == "verbose":
                        updates["esp32_verbose"] = str(resp).strip() == "1"
                    elif v == "dashboardModeActive":
                        updates["esp32_dashboardModeActive"] = str(resp).strip() == "1"
                    elif v == "ledHeartbeatIntervalMs":
                        try:
                            updates["esp32_ledHeartbeatInterval"] = int(resp) / 1000 if resp else 20.0
                        except:
                            updates["esp32_ledHeartbeatInterval"] = 20.0
                    elif v == "ledHeartbeatOnMs":
                        try:
                            updates["esp32_ledHeartbeatOn"] = int(resp) / 1000 if resp else 1.0
                        except:
                            updates["esp32_ledHeartbeatOn"] = 1.0
                st.session_state['pending_esp32_update'] = updates
                st.rerun()
            else:
                st.warning("Not connected to ESP32.")
    st.markdown("---")

    with st.expander(f"SET Debug Log ({len(st.session_state['set_debug_log'])} entries)", expanded=False):
        set_blocks = [
            block.strip()
            for msg in st.session_state['set_debug_log']
            for block in msg.split("\n\n")
            if block.strip()
        ]
        if set_blocks:
            st.text("\n\n".join(set_blocks))
        else:
            st.caption("No SET debug messages yet.")

    with st.expander(f"READ Debug Log ({len(st.session_state['debug_log'])} entries)", expanded=False):
        if st.session_state['debug_log']:
            st.text("\n\n".join(st.session_state['debug_log']))
        else:
            st.caption("No READ debug messages yet.")

    with st.expander(f"General Debug Log ({len(st.session_state['general_debug_log'])} entries)", expanded=False):
        if st.session_state['general_debug_log']:
            st.text("\n\n".join(st.session_state['general_debug_log']))
        else:
            st.caption("No general debug messages yet.")

with tabs[2]:
    st.title("📖 User Guide")
    st.markdown("Current operating notes for the dashboard, Live View, stored readings, and device configuration.")

    with st.expander("🔌 Connection", expanded=False):
        st.markdown("""
        1. Connect the device over USB.
        2. Select the serial port in the sidebar. On macOS, use the `/dev/cu.*` entry. Windows uses `COM` ports.
        3. Keep the baud rate at **115200** unless you are intentionally testing another rate.
        4. Click **Connect**.
        5. Use **Test Connection** in Quick Commands if you want to confirm the ESP32 is responsive after connecting.

        For Silicon Labs CP210x adapters, the dashboard skips the extra cleanup probe because that driver can reject probe opens on macOS. If both `/dev/cu.usbserial-*` and `/dev/cu.SLAB_USBtoUART` are shown with the same serial number, they are aliases for the same adapter.
        """)

    with st.expander("📡 Live View", expanded=False):
        st.markdown("""
        Live View is controlled by the dashboard. When enabled, the dashboard sends `readnow` automatically at the configured interval.

        **Timing**
        - **Live View Auto-Read Interval**: requested delay between dashboard-commanded read cycles. This value is saved to device flash as `liveViewAutoReadIntervalMs`.
        - **RFID ON Time**: maximum antenna read window duration.
        - **Safe minimum**: the requested value cannot be below 8 seconds. The dashboard may enforce a higher effective minimum of `2 * RFID ON Time + 2 seconds` so both antennas have time to run.
        - **Stored-Reading Fetch Timeout**: used for manual stored-reading range fetches, not for the normal Live View graph update path.

        **Graph updates**
        - New Live View points are plotted directly from `[RFID_RESULT]` lines returned by `readnow`.
        - The firmware includes the stored UTC timestamp (`ts=...`) in those lines.
        - Normal Live View cycles skip the follow-up `range` fetch to avoid slow flash reads and serial stalls.
        - If data was already retrieved manually, enabling Live View keeps that graph and appends new live points.
        """)

    with st.expander("📊 Data Display", expanded=False):
        st.markdown("""
        **Manual retrieval**
        - Select a date/time range and click **Retrieve Data**.
        - Stored readings are queried by UTC epoch internally.
        - The table and graph display timestamps in the selected timezone.

        **Display controls**
        - **Read Now** commands one immediate RFID read, appends any stored antenna results to the displayed graph/table, and highlights the latest ANT1 and ANT2 results in separate cards.
        - **Download CSV** exports the currently displayed table.
        - **Clear Display** clears only the dashboard table and graph. It does not delete readings stored on the device.
        - **Clear Storage** permanently deletes stored readings from the device after password confirmation.
        - **Print All** shows the raw stored-reading output from the device.
        """)

    with st.expander("⚙️ Configuration", expanded=False):
        st.markdown("""
        Use **Set Variables on ESP32** to write the displayed values to device flash. Use **Read Variables from ESP32** to reload the values currently stored on the device.

        **Main settings**
        - **WiFi SSID / Password**: used when RTC time must be restored from NTP.
        - **RFID ON Time**: read window duration. Minimum is 3 seconds for stable dual-antenna reads.
        - **Periodic Interval**: autonomous device read interval when dashboard mode and idle mode are inactive.
        - **Long Press Timer**: button hold duration required to toggle Dashboard Mode.
        - **Live View Auto-Read Interval**: dashboard-commanded Live View interval, saved in flash.
        - **Stored-Reading Fetch Timeout**: maximum wait for stored-reading range responses.
        - **Dashboard Mode Active**: keeps USB dashboard access available.
        - **Verbose Serial Prints**: enables detailed firmware logs.
        - **Low SoC / battery settings**: configure low-battery idle behavior and SoC calibration.
        - **LED Heartbeat settings**: configure heartbeat interval and on duration.
        """)

    with st.expander("🔘 Button and Device Behavior", expanded=False):
        st.markdown("""
        **Short press**
        - Commands a manual RFID read when reads are allowed.

        **Long press**
        - Toggles Dashboard Mode service access.

        **Dashboard Mode**
        - ON: keeps the device available for USB dashboard service, configuration, and data retrieval.
        - OFF: allows normal light-sleep behavior and autonomous periodic reading when idle conditions allow.

        **Idle mode**
        - Low-SoC idle can block RFID reads until the configured recovery behavior allows service access.
        """)

    with st.expander("🔧 Troubleshooting", expanded=False):
        st.markdown("""
        **Connection**
        - If macOS reports `(22, Invalid argument)` for a CP210x adapter, reset or unplug/replug the device, then reconnect.
        - Close Arduino Serial Monitor or any other serial program before connecting.
        - The sidebar **Selected Port Details** helps confirm the adapter, VID/PID, and serial number.

        **Live View**
        - Expected terminal signs of a healthy cycle: `live_readnow_start`, `live_readnow_merge`, and `live_range_skipped`.
        - If no graph point appears but `readnow` completes, check whether the read output contains `[RFID_RESULT] stored=true`.
        - If no tag is present, Live View keeps the existing graph unchanged.

        **Data**
        - If manual retrieval returns no readings, verify the selected date range and timezone.
        - Stored timestamps are UTC; only the dashboard display timezone changes.
        """)

    with st.expander("💻 Software", expanded=False):
        st.markdown("""
        **Dashboard requirements**
        - Python 3.8+
        - Streamlit
        - PySerial
        - Pandas
        - Plotly
        - PyTZ

        **Run**
        ```bash
        streamlit run rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py
        ```

        Firmware must include the current `readnow`, `[RFID_RESULT] ts=...`, and `liveViewAutoReadIntervalMs` support for all Live View features and flash-backed interval storage.
        """)

# =============================================================================
# COPYRIGHT FOOTER
# =============================================================================

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 12px; padding: 20px;'>
    <p><strong>Implant RFID Reader Multi-Button Dashboard v6.0</strong></p>
    <p>© 2025 Establishment Labs. All rights reserved.</p>
    <p>Developed by <a href='mailto:info@littleendianengineering.com' style='color: #666;'>Little Endian Engineering</a></p>
    <p>Contact: <a href='mailto:lyu@establishmentlabs.com' style='color: #666;'>lyu@establishmentlabs.com</a></p>
    <p style='font-size: 10px; margin-top: 10px;'>CONFIDENTIAL - PROPRIETARY SOFTWARE</p>
</div>
""", unsafe_allow_html=True)
