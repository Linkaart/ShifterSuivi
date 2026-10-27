"""Filtres et balises d'affichage : montants, plaques, statuts, icônes."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django import template
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from ..models import OrdreReparation, arrondi

register = template.Library()

ESPACE_FINE = " "
ESPACE_INSECABLE = " "


def _milliers(nombre: int) -> str:
    return f"{nombre:,}".replace(",", ESPACE_FINE)


@register.filter
def euros(valeur):
    """1234.5 → « 1 234,50 € »"""
    if valeur in (None, ""):
        return ""
    try:
        montant = arrondi(valeur)
    except (InvalidOperation, TypeError, ValueError):
        return valeur
    signe = "−" if montant < 0 else ""
    entier, decimales = f"{abs(montant):.2f}".split(".")
    return f"{signe}{_milliers(int(entier))},{decimales}{ESPACE_INSECABLE}€"


@register.filter
def km(valeur):
    if valeur in (None, ""):
        return ""
    return f"{_milliers(int(valeur))}{ESPACE_INSECABLE}km"


@register.filter
def nombre(valeur):
    """Décimal sans zéros inutiles, virgule française : 1.50 → 1,5"""
    if valeur in (None, ""):
        return ""
    try:
        texte = f"{Decimal(valeur).normalize():f}"
    except InvalidOperation:
        return valeur
    return texte.replace(".", ",")


@register.filter
def pourcent(valeur):
    return f"{nombre(valeur)}{ESPACE_INSECABLE}%"


@register.filter
def tel(valeur):
    """Lien tel: à partir d'un numéro saisi librement."""
    return re.sub(r"[^0-9+]", "", valeur or "")


@register.filter
def echeance_relative(jour):
    """Une date proche dite avec des mots : aujourd'hui, demain, dans 5 j, il y a 3 j."""
    if not jour:
        return ""
    if isinstance(jour, datetime):
        jour = timezone.localtime(jour).date()
    ecart = (jour - timezone.localdate()).days
    if ecart == 0:
        return "aujourd'hui"
    if ecart == 1:
        return "demain"
    if ecart == -1:
        return "hier"
    if ecart > 0:
        return f"dans {ecart}{ESPACE_INSECABLE}j"
    return f"il y a {-ecart}{ESPACE_INSECABLE}j"


@register.filter
def duree(depuis):
    """Temps écoulé, en court : 45 min, 3 h, 2 j."""
    if not depuis:
        return ""
    secondes = (timezone.now() - depuis).total_seconds()
    if secondes < 3600:
        return f"{max(int(secondes // 60), 1)}{ESPACE_INSECABLE}min"
    if secondes < 86400:
        return f"{int(secondes // 3600)}{ESPACE_INSECABLE}h"
    return f"{int(secondes // 86400)}{ESPACE_INSECABLE}j"


@register.inclusion_tag("garage/_plaque.html")
def plaque(immatriculation, taille=""):
    return {"immatriculation": immatriculation, "taille": taille}


@register.simple_tag
def statut(valeur, libelle=None):
    if not libelle:
        try:
            libelle = OrdreReparation.Statut(valeur).label
        except ValueError:
            libelle = valeur
    return format_html('<span class="statut statut-{}">{}</span>', valeur, libelle)


# Icônes au trait (24 × 24), dessinées dans l'esprit de Lucide (licence ISC).
ICONES = {
    "tableau": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    "atelier": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    "ordre": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>',
    "vehicule": '<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/>',
    "client": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "echeance": '<path d="M21 7.5V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h3.5"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h5"/><path d="M17.5 17.5 16 16.3V14"/><circle cx="16" cy="16" r="6"/>',
    "facture": '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 17.5v-11"/>',
    "recherche": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "menu": '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>',
    "fermer": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "sortie": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    "photo": '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>',
    "fichier": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>',
    "valide": '<path d="M20 6 9 17l-5-5"/>',
    "alerte": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "horloge": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "telephone": '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
    "courriel": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
    "imprimer": '<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8" rx="1"/>',
    "supprimer": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "modifier": '<path d="M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z"/><path d="m15 5 4 4"/>',
    "reglages": '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    "cle": '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>',
    "carburant": '<path d="M3 22h12"/><path d="M4 9h10"/><path d="M14 22V4a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v18"/><path d="M14 13h2a2 2 0 0 1 2 2v2a2 2 0 0 0 2 2a2 2 0 0 0 2-2V9.83a2 2 0 0 0-.59-1.42L18 5"/>',
    "compteur": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "envoi": '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    "envoyer_fichier": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    "retour": '<path d="m15 18-6-6 6-6"/>',
}


@register.simple_tag
def icone(nom, classe=""):
    trace = ICONES.get(nom, "")
    return mark_safe(
        f'<svg class="icone {classe}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{trace}</svg>'
    )


@register.simple_tag
def logo(classe=""):
    """La grille d'un levier de vitesses : 1-3-5 en haut, 2-4-R en bas."""
    return mark_safe(
        f'<svg class="logo {classe}" viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
        '<g fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round">'
        '<path d="M7 7v18M16 7v18M25 9v16M7 16h18"/></g>'
        '<circle cx="25" cy="6.5" r="4" fill="var(--signal)"/></svg>'
    )


@register.simple_tag(takes_context=True)
def actif(context, *sections):
    return mark_safe('aria-current="page"') if context.get("section") in sections else ""
