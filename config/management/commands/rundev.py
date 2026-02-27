"""
Run the development server using DJANGO_PORT from settings.
"""

from django.conf import settings
from django.core.management.commands.runserver import Command as RunserverCommand


class Command(RunserverCommand):
    def handle(self, *args, **options):
        if not options.get("addrport"):
            port = getattr(settings, "DJANGO_PORT", 8000)
            options["addrport"] = f"0.0.0.0:{port}"
        super().handle(*args, **options)
