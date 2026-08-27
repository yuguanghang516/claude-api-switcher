"""Single source of truth for the Claude API Switcher application version.

Every place that needs the version string (window title, logging, build.spec
metadata, README, exported config version) imports from here so the app can
never show two different versions.
"""
APP_NAME = "Claude API Switcher"
APP_VERSION = "4.3.2"
APP_VERSION_NAME = "V4.3.2"
__version__ = APP_VERSION

# Metadata attached to exported config files so older/newer builds can tell
# which version produced them.
CONFIG_VERSION_METADATA = {
    "app_name": APP_NAME,
    "app_version": APP_VERSION,
    "config_version": 4,
}


def app_title() -> str:
    """Return the full, human-readable application title for window titles."""
    return f"{APP_NAME} {APP_VERSION_NAME}"


def build_version_string() -> str:
    """Return the version string used by build.spec product_version / logging."""
    return APP_VERSION
