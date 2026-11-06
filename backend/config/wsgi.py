"""
Configuración WSGI del proyecto.

Expone el invocable WSGI como la variable de módulo ``application``; Gunicorn lo carga
con ``config.wsgi:application``.

Más información sobre este archivo en
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Si el entorno no define los ajustes, se usan los de producción (el valor más estricto).
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

application = get_wsgi_application()
