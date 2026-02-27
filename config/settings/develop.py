"""
Development settings for expense tracker backend.
"""

from .base import *  # noqa

DEBUG = True
ENVIRONMENT = "develop"

ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = []

LOGGING["handlers"]["console"]["formatter"] = "verbose"
