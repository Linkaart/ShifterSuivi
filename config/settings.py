"""Réglages Django de ShifterSuivi.

Toutes les valeurs sensibles ou propres au garage se règlent par variables
d'environnement (voir .env.example). Un fichier .env à la racine du projet est
lu automatiquement s'il existe.
"""

import os
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _charger_env(chemin: Path) -> None:
    """Lit un fichier .env simple (CLE=valeur) sans dépendance externe."""
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        os.environ.setdefault(cle.strip(), valeur.strip().strip('"').strip("'"))


_charger_env(BASE_DIR / ".env")


def env(cle: str, defaut: str = "") -> str:
    return os.environ.get(cle, defaut)


def env_bool(cle: str, defaut: bool = False) -> bool:
    return env(cle, str(defaut)).lower() in {"1", "true", "yes", "oui", "on"}


def env_liste(cle: str, defaut: str = "") -> list[str]:
    return [v.strip() for v in env(cle, defaut).split(",") if v.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-uniquement-ne-pas-utiliser-en-production"
    else:
        raise RuntimeError(
            "DJANGO_SECRET_KEY doit être défini en production (voir .env.example)."
        )

ALLOWED_HOSTS = env_liste("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_liste("DJANGO_CSRF_TRUSTED_ORIGINS")

# Vercel définit VERCEL=1 pendant le build et à l'exécution.
SUR_VERCEL = bool(env("VERCEL"))
if SUR_VERCEL:
    ALLOWED_HOSTS += [".vercel.app"]
    CSRF_TRUSTED_ORIGINS += ["https://*.vercel.app"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "garage",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "garage.context_processors.garage",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Base de données : DATABASE_URL (Vercel, Neon…), sinon PostgreSQL par DB_*, sinon SQLite.
if env("DATABASE_URL"):
    _url = urllib.parse.urlparse(env("DATABASE_URL"))
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _url.path.lstrip("/"),
            "USER": urllib.parse.unquote(_url.username or ""),
            "PASSWORD": urllib.parse.unquote(_url.password or ""),
            "HOST": _url.hostname,
            "PORT": _url.port or 5432,
            # sslmode, channel_binding… transmis tels quels au pilote
            "OPTIONS": dict(urllib.parse.parse_qsl(_url.query)),
            # Fonctions serverless + pooler : pas de connexion persistante ni de curseur serveur
            "CONN_MAX_AGE": 0,
            "DISABLE_SERVER_SIDE_CURSORS": True,
        }
    }
elif env("DB_ENGINE") == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "shiftersuivi"),
            "USER": env("DB_USER", "shiftersuivi"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST", "localhost"),
            "PORT": env("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "garage.Utilisateur"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "connexion"
LOGIN_REDIRECT_URL = "tableau_de_bord"
LOGOUT_REDIRECT_URL = "connexion"

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        # Sur Vercel, collectstatic tourne au build et le CDN sert /static/.
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG or SUR_VERCEL
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# Les documents (photos, cartes grises, OR signés) ne sont jamais servis
# directement : ils passent par une vue réservée aux utilisateurs connectés.
MEDIA_ROOT = Path(env("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
if env("BLOB_READ_WRITE_TOKEN"):
    # Vercel n'a pas de disque permanent : documents dans un store Vercel Blob privé.
    STORAGES["default"] = {"BACKEND": "garage.stockage.StockageVercelBlob"}
# Sur Vercel sans store Blob, le disque est en lecture seule : l'envoi de documents est désactivé.
STOCKAGE_DOCUMENTS_DISPONIBLE = not SUR_VERCEL or bool(env("BLOB_READ_WRITE_TOKEN"))
# Vercel refuse les requêtes de plus de 4,5 Mo (les photos sont compressées dans le navigateur).
DOCUMENT_TAILLE_MAX = (4 if SUR_VERCEL else 10) * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sécurité en production
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 12  # une journée de travail
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", False)
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "0"))
    if SUR_VERCEL or env_bool("DJANGO_BEHIND_PROXY", False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Identité du garage : apparaît sur les factures et dans l'interface.
GARAGE = {
    "nom": env("GARAGE_NOM", "Garage Shifter"),
    "adresse": env("GARAGE_ADRESSE", "Adresse à configurer"),
    "code_postal": env("GARAGE_CODE_POSTAL", ""),
    "ville": env("GARAGE_VILLE", ""),
    "telephone": env("GARAGE_TELEPHONE", ""),
    "email": env("GARAGE_EMAIL", ""),
    "siret": env("GARAGE_SIRET", ""),
    "tva_intracom": env("GARAGE_TVA_INTRACOM", ""),
    "taux_horaire_ht": env("GARAGE_TAUX_HORAIRE_HT", "65.00"),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "WARNING")},
}
