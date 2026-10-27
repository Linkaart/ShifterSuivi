from datetime import date
from decimal import Decimal

from garage.models import Client, LigneIntervention, OrdreReparation, Utilisateur, Vehicule

# Plus petit PNG valide (1 × 1 pixel)
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def creer_utilisateur(identifiant, role):
    return Utilisateur.objects.create_user(identifiant, password="mot-de-passe-test-42", role=role, first_name=identifiant.title())


def creer_client(**kwargs):
    valeurs = {
        "nom": "Durand",
        "prenom": "Claire",
        "telephone": "06 12 34 56 78",
        "adresse": "12 rue des Jardins",
        "code_postal": "57000",
        "ville": "Metz",
    }
    valeurs.update(kwargs)
    return Client.objects.create(**valeurs)


def creer_vehicule(client=None, **kwargs):
    valeurs = {
        "client": client or creer_client(),
        "immatriculation": "ab123cd",
        "marque": "Renault",
        "modele": "Clio V",
        "energie": "essence",
        "kilometrage": 30000,
        "date_mise_circulation": date(2021, 3, 15),
    }
    valeurs.update(kwargs)
    return Vehicule.objects.create(**valeurs)


def creer_ordre(vehicule=None, **kwargs):
    vehicule = vehicule or creer_vehicule()
    valeurs = {
        "vehicule": vehicule,
        "client": vehicule.client,
        "km_entree": vehicule.kilometrage,
        "demande_client": "Bruit au freinage",
        "etat_entree": "Rien à signaler",
    }
    valeurs.update(kwargs)
    return OrdreReparation.objects.create(**valeurs)


def ajouter_ligne(ordre, prix="100.00", quantite="1", taux="20.00", type_ligne=LigneIntervention.Type.PIECE):
    return LigneIntervention.objects.create(
        ordre=ordre,
        type_ligne=type_ligne,
        designation="Pièce",
        quantite=Decimal(quantite),
        prix_unitaire_ht=Decimal(prix),
        taux_tva=Decimal(taux),
    )
