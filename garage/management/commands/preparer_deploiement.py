"""Étape de build sur Vercel : migrations, puis démo si demandé et si la base est vide.

    SEED_DEMO=1 et DEMO_PASSWORD=... pour charger le garage de démonstration.
"""

import os

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from garage.models import Client, OrdreReparation


class Command(BaseCommand):
    help = "Applique les migrations et charge la démonstration si SEED_DEMO=1 et que la base est vide."

    def handle(self, *args, **options):
        if settings.DEMO_EPHEMERE:
            self.stdout.write("Pas de base reliée : démo éphémère, créée au démarrage de l'appli.")
            return
        call_command("migrate", interactive=False, verbosity=1)

        if os.environ.get("SEED_DEMO") != "1":
            self.stdout.write("Démonstration non demandée (SEED_DEMO absent).")
            return
        if Client.objects.exists() or OrdreReparation.objects.exists():
            self.stdout.write("La base contient déjà des données : démonstration non rechargée.")
            return
        mot_de_passe = os.environ.get("DEMO_PASSWORD")
        if not mot_de_passe:
            raise CommandError("DEMO_PASSWORD doit être défini pour créer les comptes de démonstration.")
        call_command("seed_demo", mot_de_passe=mot_de_passe)
