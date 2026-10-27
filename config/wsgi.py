import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

from django.conf import settings  # noqa: E402

if settings.DEMO_EPHEMERE:
    from garage.demo import preparer_demo_ephemere  # noqa: E402

    preparer_demo_ephemere()
