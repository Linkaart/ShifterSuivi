"""Droits par rôle.

- Patron : tout, y compris le chiffre d'affaires.
- Accueil : clients, réception, devis, accords, factures.
- Mécanicien : atelier, diagnostic, lignes et statuts techniques de ses véhicules.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def accueil_requis(vue):
    """Réservé au patron et à l'accueil."""

    @login_required
    @wraps(vue)
    def enveloppe(request, *args, **kwargs):
        if not request.user.gere_l_accueil:
            raise PermissionDenied("Réservé à l'accueil et au patron.")
        return vue(request, *args, **kwargs)

    return enveloppe


def patron_requis(vue):
    @login_required
    @wraps(vue)
    def enveloppe(request, *args, **kwargs):
        if not request.user.est_patron:
            raise PermissionDenied("Réservé au patron.")
        return vue(request, *args, **kwargs)

    return enveloppe


def peut_travailler_sur(utilisateur, ordre) -> bool:
    """Un mécanicien agit sur ses véhicules ou sur ceux qui ne sont pas encore attribués."""
    if utilisateur.gere_l_accueil:
        return True
    return ordre.mecanicien_id in (None, utilisateur.pk)
