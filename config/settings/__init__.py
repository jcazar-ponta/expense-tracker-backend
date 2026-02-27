"""
Settings module initialization.
Loads the appropriate settings based on environment variables.
"""

import os
from importlib import import_module

_environment = os.environ.get("ENVIRONMENT", "develop").lower()
_module = os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings")

if _module in ("config.settings", "config.settings.__init__"):
    _module = f"config.settings.{_environment}"

_settings = import_module(_module)
for _setting in dir(_settings):
    if _setting.isupper():
        globals()[_setting] = getattr(_settings, _setting)
