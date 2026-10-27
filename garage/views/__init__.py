from .clients import client_detail, client_list, client_modifier, client_nouveau
from .documents import document_voir
from .echeances import echeance_faite, echeance_list, echeance_modifier, echeance_nouveau, echeance_rappel
from .factures import facture_detail, facture_list, facture_paiement
from .ordres import (
    ligne_ajouter,
    ligne_supprimer,
    ordre_accord,
    ordre_detail,
    ordre_documents,
    ordre_facturer,
    ordre_intervention,
    ordre_list,
    ordre_modifier,
    ordre_restitution,
    ordre_statut,
    reception,
)
from .tableau import atelier, recherche, tableau_de_bord
from .vehicules import vehicule_detail, vehicule_documents, vehicule_list, vehicule_modifier, vehicule_nouveau

__all__ = [
    "atelier",
    "client_detail",
    "client_list",
    "client_modifier",
    "client_nouveau",
    "document_voir",
    "echeance_faite",
    "echeance_list",
    "echeance_modifier",
    "echeance_nouveau",
    "echeance_rappel",
    "facture_detail",
    "facture_list",
    "facture_paiement",
    "ligne_ajouter",
    "ligne_supprimer",
    "ordre_accord",
    "ordre_detail",
    "ordre_documents",
    "ordre_facturer",
    "ordre_intervention",
    "ordre_list",
    "ordre_modifier",
    "ordre_restitution",
    "ordre_statut",
    "reception",
    "recherche",
    "tableau_de_bord",
    "vehicule_detail",
    "vehicule_documents",
    "vehicule_list",
    "vehicule_modifier",
    "vehicule_nouveau",
]
