"""Pure helpers for the delivered dbf098d USB serial protocol."""
import re

VERSION = "6.2.1"
FIRMWARE_VERSION = "1.5"
FIRMWARE_BRANCH = "main_2Ant"
DASHBOARD_FILENAME = "rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py"
FIRMWARE_BASELINE = "dbf098dbd869d88fe63274aad421fdba6d7ed18a"


def manual_read_finished(response):
    """Only a command-level completion or skip ends a dual-antenna read."""
    return any(
        re.match(r"^\[MANUAL\] RFID read (?:complete(?:\s|$)|skipped(?:\s|$))", line.strip())
        for line in (response or "").splitlines()
    )


def empty_history_response(response):
    lines = [line.strip() for line in (response or "").splitlines()]
    return "No readings stored." in lines and not any(re.match(r"^#\d+:", line) for line in lines)
