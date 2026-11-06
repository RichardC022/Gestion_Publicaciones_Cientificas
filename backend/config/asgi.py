"""
Configuración ASGI del proyecto.

Expone el invocable ASGI como la variable de módulo ``application``.

Más información sobre este archivo en
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# Si el entorno no define los ajustes, se usan los de producción (el valor más estricto).
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

application = get_asgi_application()
