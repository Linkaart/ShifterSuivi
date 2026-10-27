"""Démo éphémère : sur Vercel sans base reliée, la base SQLite vit dans /tmp.

Elle est créée et remplie au démarrage de chaque instance de l'appli. Les
modifications faites pendant la démo disparaissent au prochain redémarrage.
Relier une base (DATABASE_URL) désactive ce mode.
"""

import io
import os


def preparer_demo_ephemere():
    from django.core.management import call_command

    from garage.models import Client

    call_command("migrate", interactive=False, verbosity=0)
    if not Client.objects.exists():
        mot_de_passe = os.environ.get("DEMO_PASSWORD") or "atelier2026"
        call_command("seed_demo", mot_de_passe=mot_de_passe, stdout=io.StringIO())
