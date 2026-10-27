"""Remplit la base avec un garage de démonstration crédible.

    python manage.py seed_demo                 # base vide uniquement
    python manage.py seed_demo --reinitialiser # efface les données du garage d'abord
"""

import io
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from garage.models import (
    Client,
    Document,
    Echeance,
    Facture,
    HistoriqueStatut,
    LigneIntervention,
    OrdreReparation,
    Utilisateur,
    Vehicule,
)

S = OrdreReparation.Statut
P = LigneIntervention.Type.PIECE
MO = LigneIntervention.Type.MAIN_OEUVRE
FORFAIT = LigneIntervention.Type.FORFAIT
TAUX = Decimal("65.00")

EQUIPE = [
    ("patron", "Marc", "Lefèvre", Utilisateur.Role.PATRON),
    ("accueil", "Sophie", "Muller", Utilisateur.Role.ACCUEIL),
    ("yanis", "Yanis", "Benali", Utilisateur.Role.MECANICIEN),
    ("thomas", "Thomas", "Klein", Utilisateur.Role.MECANICIEN),
    ("lucas", "Lucas", "Schmitt", Utilisateur.Role.MECANICIEN),
]

CLIENTS = [
    # clé, type, nom, prénom, raison sociale, rue, CP, ville, contact, accord rappels
    ("durand", "particulier", "Durand", "Claire", "", "12 rue des Jardins", "57000", "Metz", "sms", True),
    ("martin", "particulier", "Martin", "Julien", "", "4 allée des Tilleuls", "57950", "Montigny-lès-Metz", "appel", True),
    ("nguyen", "particulier", "Nguyen", "Thi Lan", "", "27 avenue de Strasbourg", "57000", "Metz", "email", True),
    ("ozturk", "particulier", "Öztürk", "Emre", "", "8 rue du Moulin", "57140", "Woippy", "appel", False),
    ("becker", "particulier", "Becker", "Anne", "", "15 rue Saint-Pierre", "57155", "Marly", "sms", True),
    ("laurent", "particulier", "Laurent", "Paul", "", "3 place de la Gare", "57000", "Metz", "appel", False),
    ("hoffmann", "particulier", "Hoffmann", "Céline", "", "51 rue de Verdun", "57950", "Montigny-lès-Metz", "email", True),
    ("roussel", "particulier", "Roussel", "Nadia", "", "9 impasse des Lilas", "57140", "Woippy", "sms", True),
    ("petit", "particulier", "Petit", "Hugo", "", "22 rue Mazelle", "57000", "Metz", "sms", False),
    ("schneider", "particulier", "Schneider", "Marc", "", "6 rue des Vignes", "57155", "Marly", "appel", True),
    ("weber", "professionnel", "Weber", "Laurent", "Boulangerie Weber", "40 rue Serpenoise", "57000", "Metz", "appel", True),
    ("taxis", "professionnel", "Fontaine", "Léa", "Taxis du Graoully", "2 rue Pasteur", "57000", "Metz", "appel", True),
]

# clé, client, marque, modèle, version, énergie, boîte, année-mois 1re MEC, km, couleur, préfixe VIN, dernier CT (mois avant aujourd'hui)
VEHICULES = [
    ("clio", "durand", "Renault", "Clio V", "1.0 TCe 90", "essence", "manuelle", (2021, 3), 38200, "Bleu Iron", "VF1", 19),
    ("golf", "martin", "Volkswagen", "Golf VII", "2.0 TDI 150 Carat", "diesel", "automatique", (2017, 9), 146500, "Gris Urano", "WVW", 23),
    ("zoe", "nguyen", "Renault", "Zoé", "R110 Zen", "electrique", "automatique", (2020, 11), 52100, "Blanc Glacier", "VF1", 11),
    ("p3008", "ozturk", "Peugeot", "3008", "1.5 BlueHDi 130 Allure", "diesel", "manuelle", (2019, 6), 98700, "Noir Perla", "VF3", 16),
    ("megane", "becker", "Renault", "Mégane IV", "1.5 dCi 115 Business", "diesel", "manuelle", (2018, 2), 131800, "Gris Titanium", "VF1", 7),
    ("octavia", "taxis", "Skoda", "Octavia", "2.0 TDI 150 Style", "diesel", "automatique", (2019, 1), 287400, "Noir Magic", "TMB", 22),
    ("sandero", "laurent", "Dacia", "Sandero", "TCe 90 Stepway", "essence", "manuelle", (2018, 10), 112300, "Orange Atacama", "UU1", 10),
    ("partner", "weber", "Peugeot", "Partner", "1.5 BlueHDi 100 Premium", "diesel", "manuelle", (2020, 4), 74600, "Blanc Banquise", "VF3", 6),
    ("p208", "hoffmann", "Peugeot", "208", "1.2 PureTech 100 Active", "essence", "manuelle", (2022, 11), 27400, "Rouge Elixir", "VF3", None),
    ("yaris", "roussel", "Toyota", "Yaris", "Hybride 116h Design", "hybride", "automatique", (2021, 1), 41900, "Gris Platine", "VNK", 20),
    ("c3", "petit", "Citroën", "C3", "BlueHDi 100 Feel", "diesel", "manuelle", (2016, 7), 168200, "Blanc Banquise", "VF7", 12),
    ("corsa", "schneider", "Opel", "Corsa", "1.2 Turbo 100 Elegance", "essence", "manuelle", (2020, 9), 45300, "Bleu Voltaique", "VXK", 13),
    ("fiat500", "durand", "Fiat", "500", "1.0 Hybrid 70 Dolcevita", "hybride", "manuelle", (2023, 1), 22800, "Vert Rugiada", "ZFA", None),
    ("prius", "taxis", "Toyota", "Prius+", "136h Dynamic", "hybride", "automatique", (2018, 11), 312600, "Noir Attitude", "JTD", 21),
    ("fiesta", "becker", "Ford", "Fiesta", "1.0 EcoBoost 100 Titanium", "essence", "manuelle", (2017, 4), 89300, "Gris Magnetic", "WF0", 2),
    ("kangoo", "weber", "Renault", "Kangoo", "Blue dCi 95 Grand Confort", "diesel", "manuelle", (2019, 3), 118900, "Blanc Minéral", "VF1", 19),
]

LETTRES_PLAQUE = "ABCDEFGHJKLMNPQRSTVWXYZ"
CARACTERES_VIN = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"


class Command(BaseCommand):
    help = "Crée un garage de démonstration : équipe, clients, véhicules, ordres de réparation, factures et échéances."

    def add_arguments(self, parser):
        parser.add_argument("--reinitialiser", action="store_true", help="Efface d'abord toutes les données du garage.")
        parser.add_argument("--mot-de-passe", default="atelier2026", help="Mot de passe des comptes de démonstration.")

    def handle(self, *args, **options):
        if OrdreReparation.objects.exists() or Client.objects.exists():
            if not options["reinitialiser"]:
                raise CommandError("La base contient déjà des données. Relancez avec --reinitialiser pour tout effacer.")
            self._vider()
        self.rng = random.Random(2026)
        self.maintenant = timezone.now()
        with transaction.atomic():
            self.equipe = self._creer_equipe(options["mot_de_passe"])
            self.clients = self._creer_clients()
            self.vehicules = self._creer_vehicules()
            self._creer_historique_ancien()
            self._creer_atelier_du_jour()
            self._creer_echeances()
        self.stdout.write(self.style.SUCCESS("Garage de démonstration prêt."))
        mot = options["mot_de_passe"]
        affiche = mot if mot == "atelier2026" else "celui fourni en paramètre"
        self.stdout.write(f"Comptes : patron, accueil, yanis, thomas, lucas. Mot de passe : {affiche}")

    # ------------------------------------------------------------------ outils

    def _vider(self):
        Document.objects.all().delete()
        Facture.objects.all().delete()
        OrdreReparation.objects.all().delete()
        Echeance.objects.all().delete()
        Vehicule.objects.all().delete()
        Client.objects.all().delete()
        Utilisateur.objects.filter(username__in=[u for u, *_ in EQUIPE]).delete()

    def _il_y_a(self, jours=0, heures=0, minutes=0):
        return self.maintenant - timedelta(days=jours, hours=heures, minutes=minutes)

    def _jour(self, decalage):
        return timezone.localdate() + timedelta(days=decalage)

    def _a_heure(self, jours_avant, heure, minute=0):
        jour = timezone.localdate() - timedelta(days=jours_avant)
        return timezone.make_aware(datetime.combine(jour, time(heure, minute)))

    def _plaque(self):
        l = lambda: "".join(self.rng.choice(LETTRES_PLAQUE) for _ in range(2))  # noqa: E731
        return f"{l()}-{self.rng.randint(100, 989):03d}-{l()}"

    def _vin(self, prefixe):
        return prefixe + "".join(self.rng.choice(CARACTERES_VIN) for _ in range(17 - len(prefixe)))

    def _telephone(self):
        return "0" + str(self.rng.choice([6, 7])) + " " + " ".join(f"{self.rng.randint(0, 99):02d}" for _ in range(4))

    # ----------------------------------------------------------------- données

    def _creer_equipe(self, mot_de_passe):
        equipe = {}
        for identifiant, prenom, nom, role in EQUIPE:
            utilisateur = Utilisateur(username=identifiant, first_name=prenom, last_name=nom, role=role, email=f"{identifiant}@garage.example")
            if role == Utilisateur.Role.PATRON:
                utilisateur.is_staff = True
                utilisateur.is_superuser = True
            utilisateur.set_password(mot_de_passe)
            utilisateur.save()
            equipe[identifiant] = utilisateur
        return equipe

    def _creer_clients(self):
        clients = {}
        for cle, type_client, nom, prenom, raison, rue, cp, ville, contact, accord in CLIENTS:
            client = Client.objects.create(
                type_client=type_client,
                nom=nom,
                prenom=prenom,
                raison_sociale=raison,
                siret="".join(str(self.rng.randint(0, 9)) for _ in range(14)) if raison else "",
                telephone=self._telephone(),
                email=f"{prenom.split()[0].lower()}.{nom.lower()}@exemple.fr".replace("ö", "o").replace("ü", "u").replace("é", "e"),
                adresse=rue,
                code_postal=cp,
                ville=ville,
                contact_prefere=contact,
                accord_rappels=accord,
            )
            Client.objects.filter(pk=client.pk).update(cree_le=self._il_y_a(jours=self.rng.randint(90, 900)))
            clients[cle] = client
        return clients

    def _creer_vehicules(self):
        vehicules = {}
        for cle, client, marque, modele, version, energie, boite, (annee, mois), km, couleur, wmi, ct_mois in VEHICULES:
            mise_en_circulation = timezone.localdate().replace(year=annee, month=mois, day=min(15, 28))
            dernier_ct = None
            if ct_mois is not None:
                dernier_ct = timezone.localdate() - timedelta(days=int(ct_mois * 30.4) + self.rng.randint(0, 9))
            vehicules[cle] = Vehicule.objects.create(
                client=self.clients[client],
                immatriculation=self._plaque(),
                vin=self._vin(wmi),
                marque=marque,
                modele=modele,
                version=version,
                energie=energie,
                boite=boite,
                date_mise_circulation=mise_en_circulation,
                kilometrage=km,
                couleur=couleur,
                date_dernier_ct=dernier_ct,
                dimensions_pneus=self.rng.choice(["185/65 R15", "195/55 R16", "205/55 R16", "215/60 R17"]),
            )
        return vehicules

    def _ordre(self, cle_vehicule, *, arrive, statuts, demande, etat, travaux="", mecanicien=None, accord=None,
               fin=None, urgence=False, lignes=(), diagnostic="", supplementaires="", emplacement="", cles="", carburant="demi"):
        """Crée un OR et rejoue son historique de statuts. `statuts` = [(statut, date), ...]"""
        vehicule = self.vehicules[cle_vehicule]
        km = vehicule.kilometrage
        ordre = OrdreReparation(
            vehicule=vehicule,
            client=vehicule.client,
            arrive_le=arrive,
            km_entree=km,
            niveau_carburant=carburant,
            demande_client=demande,
            etat_entree=etat,
            travaux_prevus=travaux,
            diagnostic=diagnostic,
            travaux_supplementaires=supplementaires,
            cles_accessoires=cles or "1 clé",
            emplacement=emplacement,
            recu_par=self.equipe["accueil"],
            mecanicien=self.equipe[mecanicien] if mecanicien else None,
            fin_prevue_le=fin,
            urgence=OrdreReparation.Urgence.URGENTE if urgence else OrdreReparation.Urgence.NORMALE,
            statut=S.RECU,
            statut_depuis=arrive,
        )
        if accord:
            moyen, quand = accord
            ordre.accord_client = True
            ordre.accord_moyen = moyen
            ordre.accord_le = quand
        ordre.save()
        HistoriqueStatut.objects.create(ordre=ordre, ancien="", nouveau=S.RECU, par=self.equipe["accueil"], le=arrive, commentaire="Réception du véhicule")
        for type_ligne, designation, quantite, prix, extra in lignes:
            LigneIntervention.objects.create(
                ordre=ordre,
                type_ligne=type_ligne,
                designation=designation,
                quantite=Decimal(str(quantite)),
                prix_unitaire_ht=Decimal(str(prix)),
                **extra,
            )
        ancien = S.RECU
        for statut, quand in statuts:
            auteur = self.equipe[mecanicien] if mecanicien and statut in {S.DIAGNOSTIC, S.EN_COURS, S.TERMINE, S.ATTENTE_PIECES} else self.equipe["accueil"]
            HistoriqueStatut.objects.create(ordre=ordre, ancien=ancien, nouveau=statut, par=auteur, le=quand)
            ordre.statut = statut
            ordre.statut_depuis = quand
            ancien = statut
        ordre.save(update_fields=["statut", "statut_depuis"])
        return ordre

    def _facturer(self, ordre, emise_le, paye=True, partiel=None, mode="carte"):
        facture = Facture.emettre(ordre)
        facture.emise_le = emise_le
        facture.save(update_fields=["emise_le"])
        if paye:
            facture.enregistrer_paiement(facture.total_ttc, mode, emise_le)
        elif partiel:
            facture.enregistrer_paiement(Decimal(partiel), mode, emise_le)
        return facture

    def _restituer(self, ordre, quand, travaux):
        ordre.statut = S.RESTITUE
        ordre.statut_depuis = quand
        ordre.restitue_le = quand
        ordre.km_sortie = ordre.km_entree + self.rng.randint(2, 12)
        ordre.travaux_realises = travaux
        ordre.save()
        HistoriqueStatut.objects.create(ordre=ordre, ancien=S.PRET, nouveau=S.RESTITUE, par=self.equipe["accueil"], le=quand, commentaire="Véhicule rendu au client")

    def _creer_historique_ancien(self):
        """Passages terminés des semaines précédentes."""
        anciens = [
            ("fiesta", 52, "Révision des 90 000 km", "yanis", [
                (FORFAIT, "Révision constructeur", 1, 129.00, {}),
                (P, "Huile 5W30 (4,5 l)", 1, 42.50, {"reference": "5W30-C2", "origine": "neuve"}),
                (P, "Filtre à huile", 1, 11.90, {"reference": "OC 1176", "origine": "neuve"}),
            ], "carte", True),
            ("kangoo", 38, "Remplacement des plaquettes et disques avant", "thomas", [
                (P, "Disques de frein avant (paire)", 1, 96.00, {"reference": "DF6820", "origine": "neuve"}),
                (P, "Plaquettes de frein avant", 1, 48.00, {"reference": "GDB1748", "origine": "neuve"}),
                (MO, "Main-d'œuvre freinage", 1.5, TAUX, {}),
            ], "virement", True),
            ("golf", 24, "Remplacement de la batterie", "lucas", [
                (P, "Batterie 12 V 70 Ah AGM", 1, 168.00, {"origine": "neuve"}),
                (MO, "Pose et codage batterie", 0.5, TAUX, {}),
            ], "carte", True),
            ("p3008", 13, "Vidange et filtre à air", "yanis", [
                (P, "Huile 0W20 (5 l)", 1, 54.00, {"origine": "neuve"}),
                (P, "Filtre à air", 1, 19.50, {"origine": "neuve"}),
                (MO, "Vidange", 0.8, TAUX, {}),
            ], "cheque", True),
            ("prius", 9, "Bruit de roulement à l'arrière droit", "thomas", [
                (P, "Roulement de roue arrière droit", 1, 88.00, {"origine": "neuve"}),
                (MO, "Remplacement roulement", 1.2, TAUX, {}),
            ], "virement", False),
            ("clio", 6, "Rétroviseur gauche cassé", "lucas", [
                (P, "Rétroviseur extérieur gauche", 1, 74.00, {"origine": "reemploi", "fournisseur": "Centre VHU agréé"}),
                (MO, "Pose rétroviseur", 0.6, TAUX, {}),
            ], "carte", True),
        ]
        for cle, jours, travaux, meca, lignes, mode, paye in anciens:
            arrive = self._a_heure(jours, 8, 15)
            ordre = self._ordre(
                cle,
                arrive=arrive,
                statuts=[
                    (S.EN_COURS, arrive + timedelta(hours=1)),
                    (S.TERMINE, arrive + timedelta(hours=5)),
                    (S.PRET, arrive + timedelta(hours=6)),
                ],
                demande=travaux,
                etat="Rien à signaler.",
                travaux=travaux,
                mecanicien=meca,
                accord=("signature", arrive),
                fin=(arrive + timedelta(days=1)).date(),
                lignes=lignes,
            )
            ordre.vehicule.kilometrage += self.rng.randint(800, 4000)
            ordre.vehicule.save(update_fields=["kilometrage"])
            self._facturer(ordre, (arrive + timedelta(hours=6)).date(), paye=paye, partiel=None if paye else "100.00", mode=mode)
            self._restituer(ordre, arrive + timedelta(hours=9), travaux)

    def _creer_atelier_du_jour(self):
        mt = timedelta
        # 1. Reçu ce matin, pas encore attribué
        self._ordre(
            "clio", arrive=self._a_heure(0, 8, 10), statuts=[],
            demande="Voyant moteur orange allumé depuis hier soir, la voiture broute un peu à froid.",
            etat="Bon état général. Petite rayure sur le bouclier avant droit.",
            fin=self._jour(1), emplacement="Parking, place 3", carburant="quart",
        )
        # 2. Reçu ce matin, révision acceptée au comptoir
        self._ordre(
            "fiat500", arrive=self._a_heure(0, 9, 25), statuts=[],
            demande="Révision des 20 000 km et contrôle des freins.",
            etat="Jante avant gauche frottée.",
            travaux="Révision constructeur, contrôle des freins.",
            mecanicien="lucas", accord=("signature", self._a_heure(0, 9, 25)), fin=self._jour(0),
            lignes=[(FORFAIT, "Révision constructeur", 1, 119.00, {})],
        )
        # 3. Diagnostic en cours
        self._ordre(
            "golf", arrive=self._a_heure(0, 7, 45), statuts=[(S.DIAGNOSTIC, self._il_y_a(heures=3))],
            demande="Claquement à l'avant gauche dans les dos-d'âne.",
            etat="Pare-brise impacté côté passager.",
            mecanicien="thomas", fin=self._jour(2), emplacement="Pont 2", cles="2 clés, écrou antivol dans la boîte à gants",
        )
        # 4. Diagnostic en retard
        self._ordre(
            "zoe", arrive=self._a_heure(3, 14, 0), statuts=[(S.DIAGNOSTIC, self._il_y_a(jours=2, heures=2))],
            demande="La charge s'arrête toute seule vers 80 %, sur la borne comme à la maison.",
            etat="Rien à signaler. Câble de charge laissé dans le coffre.",
            mecanicien="yanis", fin=self._jour(-1), carburant="demi",
            diagnostic="Mise à jour du chargeur embarqué disponible. Attente de l'outil constructeur.",
        )
        # 5. Devis envoyé, sans réponse
        self._ordre(
            "p3008", arrive=self._a_heure(2, 8, 30),
            statuts=[(S.DIAGNOSTIC, self._a_heure(2, 10, 0)), (S.DEVIS_ENVOYE, self._a_heure(2, 15, 40))],
            demande="Bruit de frottement métallique au freinage.",
            etat="Rayure sur le hayon. Siège bébé à l'arrière.",
            mecanicien="thomas", fin=self._jour(1),
            diagnostic="Plaquettes avant usées jusqu'au témoin, disques marqués (épaisseur sous la cote mini).",
            travaux="Remplacement des disques et plaquettes avant.",
            lignes=[
                (P, "Disques de frein avant (paire)", 1, 112.00, {"reference": "DF4386", "origine": "neuve"}),
                (P, "Plaquettes de frein avant", 1, 54.00, {"reference": "GDB2041", "origine": "neuve"}),
                (MO, "Main-d'œuvre freinage avant", 1.5, TAUX, {}),
            ],
        )
        # 6. Devis accepté
        self._ordre(
            "megane", arrive=self._a_heure(1, 8, 0),
            statuts=[(S.DIAGNOSTIC, self._a_heure(1, 9, 30)), (S.DEVIS_ENVOYE, self._a_heure(1, 11, 0)), (S.DEVIS_ACCEPTE, self._il_y_a(heures=20))],
            demande="La pédale d'embrayage est dure et les vitesses craquent.",
            etat="Bon état. 2 clés remises.",
            mecanicien="yanis", accord=("telephone", self._il_y_a(heures=20)), fin=self._jour(3),
            diagnostic="Kit d'embrayage en fin de vie, butée hydraulique bruyante.",
            travaux="Remplacement du kit d'embrayage et de la butée.",
            lignes=[
                (P, "Kit d'embrayage 3 pièces", 1, 289.00, {"reference": "LuK 623 3412 33", "origine": "neuve"}),
                (P, "Butée hydraulique", 1, 98.00, {"origine": "neuve"}),
                (MO, "Dépose et repose boîte, embrayage", 6, TAUX, {}),
            ],
        )
        # 7. Attente de pièces, client professionnel, urgent
        self._ordre(
            "octavia", arrive=self._a_heure(1, 7, 30),
            statuts=[(S.DIAGNOSTIC, self._a_heure(1, 8, 0)), (S.DEVIS_ENVOYE, self._a_heure(1, 10, 0)),
                     (S.DEVIS_ACCEPTE, self._a_heure(1, 10, 20)), (S.ATTENTE_PIECES, self._a_heure(1, 10, 40))],
            demande="Perte de puissance et fumée bleue à l'accélération. Taxi : besoin du véhicule au plus vite.",
            etat="Usure normale de taxi, sellerie arrière tachée.",
            mecanicien="thomas", accord=("telephone", self._a_heure(1, 10, 20)), fin=self._jour(1), urgence=True,
            diagnostic="Turbo avec jeu axial important, fuite d'huile côté admission.",
            travaux="Remplacement du turbo et des joints.",
            lignes=[
                (P, "Turbocompresseur", 1, 645.00, {"origine": "neuve", "fournisseur": "Distributeur pièces auto", "commandee_le": self._jour(-1)}),
                (P, "Kit de joints turbo", 1, 38.00, {"origine": "neuve", "fournisseur": "Distributeur pièces auto", "commandee_le": self._jour(-1)}),
                (MO, "Remplacement turbo", 3.5, TAUX, {}),
            ],
        )
        # 8. En réparation
        self._ordre(
            "sandero", arrive=self._a_heure(1, 13, 0),
            statuts=[(S.EN_COURS, self._il_y_a(heures=4))],
            demande="Distribution à faire, préconisation constructeur atteinte.",
            etat="Bosse sur la portière arrière gauche.",
            travaux="Remplacement du kit de distribution et de la pompe à eau.",
            mecanicien="lucas", accord=("signature", self._a_heure(1, 13, 0)), fin=self._jour(0),
            lignes=[
                (P, "Kit de distribution avec pompe à eau", 1, 189.00, {"origine": "neuve"}),
                (P, "Liquide de refroidissement (5 l)", 1, 24.00, {"origine": "neuve"}),
                (MO, "Distribution", 3, TAUX, {}),
            ],
        )
        # 9. En réparation, urgent, professionnel
        self._ordre(
            "partner", arrive=self._a_heure(0, 7, 15), statuts=[(S.EN_COURS, self._il_y_a(heures=2))],
            demande="Freins qui grincent, véhicule de livraison : à récupérer ce soir.",
            etat="Carrosserie marquée sur les flancs (utilitaire).",
            travaux="Plaquettes arrière, purge du liquide de frein.",
            mecanicien="yanis", accord=("signature", self._a_heure(0, 7, 15)), fin=self._jour(0), urgence=True,
            supplementaires="Pneu avant droit usé sur l'intérieur : géométrie à vérifier.",
            lignes=[
                (P, "Plaquettes de frein arrière", 1, 46.00, {"origine": "neuve"}),
                (P, "Liquide de frein DOT 4 (1 l)", 1, 14.00, {"origine": "neuve"}),
                (MO, "Freinage arrière et purge", 1.2, TAUX, {}),
            ],
        )
        # 10. Terminé, pas encore facturé
        self._ordre(
            "p208", arrive=self._a_heure(1, 9, 0),
            statuts=[(S.EN_COURS, self._a_heure(1, 10, 0)), (S.TERMINE, self._il_y_a(heures=1, minutes=10))],
            demande="Révision des 30 000 km.",
            etat="Rien à signaler.",
            travaux="Révision constructeur, remplacement du filtre d'habitacle.",
            mecanicien="lucas", accord=("signature", self._a_heure(1, 9, 0)), fin=self._jour(0),
            lignes=[
                (FORFAIT, "Révision constructeur", 1, 135.00, {}),
                (P, "Filtre d'habitacle à charbon actif", 1, 27.00, {"origine": "neuve"}),
            ],
        )
        # 11. Prêt, facturé, en attente du client
        yaris = self._ordre(
            "yaris", arrive=self._a_heure(1, 8, 40),
            statuts=[(S.EN_COURS, self._a_heure(1, 9, 30)), (S.TERMINE, self._il_y_a(heures=3)), (S.PRET, self._il_y_a(heures=2, minutes=30))],
            demande="Changer les deux pneus avant, la voiture tire à droite.",
            etat="Enjoliveur arrière gauche manquant.",
            travaux="Deux pneus avant, équilibrage, parallélisme.",
            mecanicien="thomas", accord=("signature", self._a_heure(1, 8, 40)), fin=self._jour(0),
            lignes=[
                (P, "Pneu 185/65 R15 88H été", 2, 79.00, {"origine": "neuve"}),
                (FORFAIT, "Montage et équilibrage (2 roues)", 1, 30.00, {}),
                (FORFAIT, "Réglage du parallélisme", 1, 69.00, {}),
            ],
        )
        self._facturer(yaris, timezone.localdate(), paye=False)
        # 12. Devis refusé, à rendre sans facture
        self._ordre(
            "c3", arrive=self._a_heure(2, 10, 0),
            statuts=[(S.DIAGNOSTIC, self._a_heure(2, 11, 0)), (S.DEVIS_ENVOYE, self._a_heure(2, 16, 0)), (S.PRET, self._il_y_a(heures=5))],
            demande="Bruit de soufflerie à l'avant, surtout en ville.",
            etat="Usure générale, rétroviseur droit scotché.",
            mecanicien="yanis", fin=self._jour(-1),
            diagnostic="Fuite à l'échappement au niveau du flexible. Remplacement conseillé.",
            lignes=[
                (P, "Flexible d'échappement", 1, 64.00, {"origine": "neuve"}),
                (MO, "Remplacement flexible", 1, TAUX, {}),
            ],
        )
        # 13. Climatisation en cours, non urgent
        self._ordre(
            "corsa", arrive=self._a_heure(0, 10, 5), statuts=[(S.EN_COURS, self._il_y_a(minutes=50))],
            demande="La climatisation ne fait plus de froid.",
            etat="Rien à signaler.",
            travaux="Contrôle d'étanchéité et recharge de climatisation.",
            mecanicien="thomas", accord=("signature", self._a_heure(0, 10, 5)), fin=self._jour(1),
            lignes=[(FORFAIT, "Recharge climatisation R1234yf", 1, 119.00, {})],
        )
        self._ajouter_photos()

    def _ajouter_photos(self):
        """Quelques photos d'état à l'entrée, si Pillow est installé."""
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            return
        exemples = [
            ("clio", "Bouclier avant droit", (58, 74, 92)),
            ("clio", "Compteur à l'arrivée", (40, 44, 52)),
            ("golf", "Impact pare-brise", (70, 82, 70)),
            ("partner", "Flanc gauche", (90, 86, 78)),
        ]
        for cle, legende, couleur in exemples:
            vehicule = self.vehicules[cle]
            ordre = vehicule.ordres.exclude(statut=S.RESTITUE).first()
            image = Image.new("RGB", (800, 600), couleur)
            dessin = ImageDraw.Draw(image)
            for i in range(0, 600, 6):
                teinte = tuple(max(0, min(255, c + (i % 60) // 6 - 5)) for c in couleur)
                dessin.line([(0, i), (800, i)], fill=teinte, width=6)
            dessin.rounded_rectangle([60, 210, 740, 390], radius=24, outline=(230, 228, 220), width=4)
            dessin.text((80, 285), f"Photo de démonstration : {legende}", fill=(236, 233, 226))
            tampon = io.BytesIO()
            image.save(tampon, format="JPEG", quality=82)
            Document.objects.create(
                vehicule=vehicule,
                ordre=ordre,
                type_document=Document.Type.PHOTO_ENTREE,
                fichier=ContentFile(tampon.getvalue(), name="photo.jpg"),
                nom_original=f"{legende}.jpg",
                ajoute_par=self.equipe["accueil"],
            )

    def _creer_echeances(self):
        for vehicule in self.vehicules.values():
            vehicule.planifier_ct()
        # Quelques entretiens à venir
        Echeance.objects.create(vehicule=self.vehicules["golf"], type=Echeance.Type.DISTRIBUTION, km_prevu=150000, prevue_le=self._jour(12), notes="Courroie à 150 000 km ou 5 ans")
        Echeance.objects.create(vehicule=self.vehicules["prius"], type=Echeance.Type.VIDANGE, km_prevu=315000, prevue_le=self._jour(6))
        Echeance.objects.create(vehicule=self.vehicules["fiesta"], type=Echeance.Type.VIDANGE, prevue_le=self._jour(-4), km_prevu=105000)
        Echeance.objects.create(vehicule=self.vehicules["kangoo"], type=Echeance.Type.PNEUS, prevue_le=self._jour(21), notes="Pneus hiver à monter")
        rappel = Echeance.objects.create(vehicule=self.vehicules["p3008"], type=Echeance.Type.VIDANGE, prevue_le=self._jour(9))
        rappel.marquer_rappel(Echeance.Canal.SMS)
