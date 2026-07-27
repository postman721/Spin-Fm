"""Application identity and persistent-settings keys.

Keeping these values in one Qt-free module prevents the command-line bootstrap,
main window, and file-browser widgets from silently drifting apart.
"""

from __future__ import annotations

APP_NAME = "Spin FM"
APP_ID = "net.techtimejourney.SpinFM"
ORGANIZATION_NAME = "Spin"
ORGANIZATION_DOMAIN = "techtimejourney.net"

# QSettings uses the organization/application pair to locate the config file.
SETTINGS_ORGANIZATION = ORGANIZATION_NAME
SETTINGS_APPLICATION = APP_NAME
