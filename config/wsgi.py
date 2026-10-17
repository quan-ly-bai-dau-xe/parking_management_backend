"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Set default settings module to local development
# Can be overridden by setting DJANGO_SETTINGS_MODULE environment variable
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

application = get_wsgi_application()