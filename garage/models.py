"""Modèles de ShifterSuivi : clients, véhicules et leur passage à l'atelier.

L'ordre de réparation (OR) est la fiche centrale : un OR par passage, avec
l'état à l'entrée, les travaux, les lignes facturables, l'accord du client,
l'historique des statuts, les documents et, à la fin, la facture.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

CENTIME = Decimal("0.01")


def arrondi(montant) -> Decimal:
    return Decimal(montant).quantize(CENTIME, rounding=ROUND_HALF_UP)


def ajouter_annees(jour: date, annees: int) -> date:
    """Ajoute des années en gérant le 29 février."""
    try:
        return jour.replace(year=jour.year + annees)
    except ValueError:
        return jour.replace(year=jour.year + annees, day=28)


def cle_immatriculation(valeur: str) -> str:
    """Clé de recherche : lettres et chiffres seulement, en majuscules."""
    return re.sub(r"[^A-Za-z0-9]", "", valeur or "").upper()


def normaliser_immatriculation(valeur: str) -> str:
    """Met une plaque au format SIV (AB-123-CD) quand c'en est une."""
    cle = cle_immatriculation(valeur)
    if re.fullmatch(r"[A-Z]{2}\d{3}[A-Z]{2}", cle):
        return f"{cle[:2]}-{cle[2:5]}-{cle[5:]}"
    return re.sub(r"\s+", " ", (valeur or "").strip().upper())


def prochain_numero(modele, prefixe: str, annee: int) -> str:
    debut = f"{prefixe}-{annee}-"
    dernier = (
        modele.objects.filter(numero__startswith=debut)
        .order_by("-numero")
        .values_list("numero", flat=True)
        .first()
    )
    rang = int(dernier.rsplit("-", 1)[1]) + 1 if dernier else 1
    return f"{debut}{rang:04d}"


class NumeroteMixin(models.Model):
    """Attribue un numéro continu par année (OR-2026-0001, FA-2026-0001)."""

    prefixe_numero = ""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.numero:
            return super().save(*args, **kwargs)
        annee = timezone.localdate().year
        for _ in range(5):
            self.numero = prochain_numero(type(self), self.prefixe_numero, annee)
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                if type(self).objects.filter(numero=self.numero).exists():
                    self.numero = ""
                    continue
                raise
        raise IntegrityError("Impossible d'attribuer un numéro unique.")


class Horodatage(models.Model):
    cree_le = models.DateTimeField("créé le", auto_now_add=True)
    modifie_le = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Utilisateurs
# ---------------------------------------------------------------------------


class Utilisateur(AbstractUser):
    class Role(models.TextChoices):
        PATRON = "patron", "Patron"
        ACCUEIL = "accueil", "Accueil"
        MECANICIEN = "mecanicien", "Mécanicien"

    role = models.CharField("rôle", max_length=20, choices=Role.choices, default=Role.MECANICIEN)

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        ordering = ["first_name", "last_name", "username"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def est_patron(self) -> bool:
        return self.is_superuser or self.role == self.Role.PATRON

    @property
    def est_mecanicien(self) -> bool:
        return not self.is_superuser and self.role == self.Role.MECANICIEN

    @property
    def gere_l_accueil(self) -> bool:
        """Patron et accueil : clients, réception, devis, factures."""
        return self.est_patron or self.role == self.Role.ACCUEIL

    @property
    def initiales(self) -> str:
        if self.first_name or self.last_name:
            return f"{self.first_name[:1]}{self.last_name[:1]}".upper()
        return self.username[:2].upper()


# ---------------------------------------------------------------------------
# Clients et véhicules
# ---------------------------------------------------------------------------

telephone_valide = RegexValidator(
    r"^[0-9+().\s-]{10,20}$", "Saisissez un numéro de téléphone valide."
)
siret_valide = RegexValidator(r"^\d{14}$", "Le SIRET compte 14 chiffres.")
code_postal_valide = RegexValidator(r"^\d{5}$", "Le code postal compte 5 chiffres.")
vin_valide = RegexValidator(
    r"^[A-HJ-NPR-Z0-9]{17}$",
    "Le VIN compte 17 caractères (lettres I, O et Q exclues).",
)


class Client(Horodatage):
    class Type(models.TextChoices):
        PARTICULIER = "particulier", "Particulier"
        PROFESSIONNEL = "professionnel", "Professionnel"

    class Contact(models.TextChoices):
        APPEL = "appel", "Appel"
        SMS = "sms", "SMS"
        EMAIL = "email", "E-mail"

    type_client = models.CharField("type de client", max_length=20, choices=Type.choices, default=Type.PARTICULIER)
    nom = models.CharField(max_length=80)
    prenom = models.CharField("prénom", max_length=80, blank=True)
    raison_sociale = models.CharField("raison sociale", max_length=120, blank=True)
    siret = models.CharField("SIRET", max_length=14, blank=True, validators=[siret_valide])
    telephone = models.CharField("téléphone", max_length=20, validators=[telephone_valide])
    email = models.EmailField("e-mail", blank=True)
    adresse = models.CharField(max_length=200)
    code_postal = models.CharField("code postal", max_length=5, validators=[code_postal_valide])
    ville = models.CharField(max_length=100)
    contact_prefere = models.CharField("moyen de contact préféré", max_length=10, choices=Contact.choices, default=Contact.APPEL)
    accord_rappels = models.BooleanField(
        "accord pour les rappels d'entretien",
        default=False,
        help_text="Le client accepte de recevoir des rappels (vidange, contrôle technique…).",
    )
    accord_rappels_le = models.DateField("accord donné le", null=True, blank=True)
    notes = models.TextField("notes internes", blank=True)

    class Meta:
        ordering = ["nom", "prenom"]
        indexes = [models.Index(fields=["nom", "prenom"])]

    def __str__(self):
        return self.nom_affiche

    @property
    def nom_affiche(self) -> str:
        personne = f"{self.nom.upper()} {self.prenom}".strip()
        if self.type_client == self.Type.PROFESSIONNEL and self.raison_sociale:
            return self.raison_sociale
        return personne

    @property
    def adresse_complete(self) -> str:
        return f"{self.adresse}\n{self.code_postal} {self.ville}".strip()

    def clean(self):
        if self.type_client == self.Type.PROFESSIONNEL and not self.raison_sociale:
            raise ValidationError({"raison_sociale": "Indiquez la raison sociale d'un client professionnel."})

    def save(self, *args, **kwargs):
        if self.accord_rappels and not self.accord_rappels_le:
            self.accord_rappels_le = timezone.localdate()
        if not self.accord_rappels:
            self.accord_rappels_le = None
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("client_detail", args=[self.pk])


class Vehicule(Horodatage):
    class Energie(models.TextChoices):
        ESSENCE = "essence", "Essence"
        DIESEL = "diesel", "Diesel"
        HYBRIDE = "hybride", "Hybride"
        HYBRIDE_RECHARGEABLE = "hybride_rechargeable", "Hybride rechargeable"
        ELECTRIQUE = "electrique", "Électrique"
        GPL = "gpl", "GPL"
        AUTRE = "autre", "Autre"

    class Boite(models.TextChoices):
        MANUELLE = "manuelle", "Manuelle"
        AUTOMATIQUE = "automatique", "Automatique"

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="vehicules", verbose_name="propriétaire")
    immatriculation = models.CharField("immatriculation (A)", max_length=20)
    immat_cle = models.CharField(max_length=20, unique=True, editable=False)
    vin = models.CharField("numéro VIN (E)", max_length=17, blank=True, validators=[vin_valide])
    marque = models.CharField("marque (D.1)", max_length=60)
    modele = models.CharField("modèle (D.3)", max_length=80)
    version = models.CharField("version / type (D.2)", max_length=120, blank=True)
    date_mise_circulation = models.DateField("1re mise en circulation (B)", null=True, blank=True)
    energie = models.CharField("énergie (P.3)", max_length=25, choices=Energie.choices)
    boite = models.CharField("boîte de vitesses", max_length=15, choices=Boite.choices, blank=True)
    couleur = models.CharField(max_length=40, blank=True)
    kilometrage = models.PositiveIntegerField("kilométrage", default=0)
    puissance_fiscale = models.PositiveSmallIntegerField("puissance fiscale (P.6)", null=True, blank=True)
    cylindree = models.PositiveIntegerField("cylindrée en cm³ (P.1)", null=True, blank=True)
    code_moteur = models.CharField("code moteur", max_length=30, blank=True)
    dimensions_pneus = models.CharField("dimensions des pneus", max_length=30, blank=True)
    date_dernier_ct = models.DateField("dernier contrôle technique", null=True, blank=True)
    notes = models.TextField("notes internes", blank=True)

    class Meta:
        verbose_name = "véhicule"
        ordering = ["immatriculation"]
        constraints = [
            models.UniqueConstraint(fields=["vin"], condition=~Q(vin=""), name="vin_unique_si_renseigne"),
        ]

    def __str__(self):
        return f"{self.immatriculation} {self.marque} {self.modele}"

    @property
    def designation(self) -> str:
        return f"{self.marque} {self.modele}".strip()

    def clean(self):
        cle = cle_immatriculation(self.immatriculation)
        if len(cle) < 2:
            raise ValidationError({"immatriculation": "Saisissez une immatriculation."})
        doublon = Vehicule.objects.filter(immat_cle=cle).exclude(pk=self.pk)
        if doublon.exists():
            raise ValidationError({"immatriculation": "Un véhicule avec cette immatriculation existe déjà."})

    def save(self, *args, **kwargs):
        self.immatriculation = normaliser_immatriculation(self.immatriculation)
        self.immat_cle = cle_immatriculation(self.immatriculation)
        self.vin = (self.vin or "").strip().upper()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("vehicule_detail", args=[self.pk])

    @property
    def prochain_ct(self) -> date | None:
        """1er contrôle avant les 4 ans, puis tous les 2 ans (voiture particulière)."""
        if self.date_dernier_ct:
            return ajouter_annees(self.date_dernier_ct, 2)
        if self.date_mise_circulation:
            return ajouter_annees(self.date_mise_circulation, 4)
        return None

    @property
    def ct_depasse(self) -> bool:
        prochain = self.prochain_ct
        return bool(prochain and prochain < timezone.localdate())

    @property
    def annee(self) -> int | None:
        return self.date_mise_circulation.year if self.date_mise_circulation else None

    @property
    def passage_en_cours(self):
        return self.ordres.exclude(statut=OrdreReparation.Statut.RESTITUE).first()

    def planifier_ct(self):
        """Crée ou met à jour l'échéance du prochain contrôle technique."""
        prochain = self.prochain_ct
        if not prochain:
            return None
        echeance = self.echeances.filter(type=Echeance.Type.CONTROLE_TECHNIQUE).exclude(statut=Echeance.Statut.FAITE).first()
        if echeance:
            if echeance.prevue_le != prochain:
                echeance.prevue_le = prochain
                echeance.save(update_fields=["prevue_le", "modifie_le"])
            return echeance
        return Echeance.objects.create(vehicule=self, type=Echeance.Type.CONTROLE_TECHNIQUE, prevue_le=prochain)


# ---------------------------------------------------------------------------
# Ordre de réparation
# ---------------------------------------------------------------------------


class OrdreReparation(NumeroteMixin, Horodatage):
    prefixe_numero = "OR"

    class Statut(models.TextChoices):
        RECU = "recu", "Reçu"
        DIAGNOSTIC = "diagnostic", "En diagnostic"
        DEVIS_ENVOYE = "devis_envoye", "Devis envoyé"
        DEVIS_ACCEPTE = "devis_accepte", "Devis accepté"
        ATTENTE_PIECES = "attente_pieces", "Attente de pièces"
        EN_COURS = "en_cours", "En réparation"
        TERMINE = "termine", "Terminé"
        PRET = "pret", "Prêt à rendre"
        RESTITUE = "restitue", "Restitué"

    class Urgence(models.TextChoices):
        NORMALE = "normale", "Normale"
        URGENTE = "urgente", "Urgente"

    class Carburant(models.TextChoices):
        VIDE = "vide", "Réserve"
        QUART = "quart", "1/4"
        DEMI = "demi", "1/2"
        TROIS_QUARTS = "trois_quarts", "3/4"
        PLEIN = "plein", "Plein"

    class MoyenAccord(models.TextChoices):
        SIGNATURE = "signature", "Signature au comptoir"
        TELEPHONE = "telephone", "Téléphone"
        EMAIL = "email", "E-mail"
        SMS = "sms", "SMS"

    class ChoixReemploi(models.TextChoices):
        ACCEPTE = "accepte", "Accepte les pièces de réemploi"
        REFUSE = "refuse", "Préfère des pièces neuves"

    numero = models.CharField("numéro d'OR", max_length=20, unique=True, editable=False)
    vehicule = models.ForeignKey(Vehicule, on_delete=models.PROTECT, related_name="ordres", verbose_name="véhicule")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="ordres")
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.RECU)
    statut_depuis = models.DateTimeField("statut depuis", default=timezone.now)
    urgence = models.CharField(max_length=10, choices=Urgence.choices, default=Urgence.NORMALE)

    # Entrée à l'atelier
    arrive_le = models.DateTimeField("arrivé le", default=timezone.now)
    km_entree = models.PositiveIntegerField("kilométrage à l'entrée")
    niveau_carburant = models.CharField("carburant ou batterie", max_length=15, choices=Carburant.choices, blank=True)
    etat_entree = models.TextField("état du véhicule à l'entrée", help_text="Rayures, chocs, voyants allumés…")
    demande_client = models.TextField("demande du client", help_text="Ce que le client décrit, avec ses mots.")
    cles_accessoires = models.CharField("clés et accessoires remis", max_length=200, blank=True)
    objets_laisses = models.CharField("objets laissés dans la voiture", max_length=200, blank=True)
    emplacement = models.CharField(max_length=60, blank=True, help_text="Parking, pont…")
    recu_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="receptions", verbose_name="reçu par")
    fin_prevue_le = models.DateField("fin prévue le", null=True, blank=True)

    # Intervention
    mecanicien = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interventions",
        limit_choices_to={"role": Utilisateur.Role.MECANICIEN, "is_active": True},
        verbose_name="mécanicien",
    )
    travaux_prevus = models.TextField("travaux prévus", blank=True)
    diagnostic = models.TextField(blank=True)
    travaux_supplementaires = models.TextField(
        "travaux supplémentaires découverts",
        blank=True,
        help_text="À faire valider par le client avant de les réaliser.",
    )

    # Accord du client
    accord_client = models.BooleanField("le client a donné son accord", default=False)
    accord_le = models.DateTimeField("accord donné le", null=True, blank=True)
    accord_moyen = models.CharField("moyen de l'accord", max_length=15, choices=MoyenAccord.choices, blank=True)
    reemploi_propose = models.BooleanField("pièces de réemploi proposées", default=False)
    reemploi_choix = models.CharField("choix du client", max_length=10, choices=ChoixReemploi.choices, blank=True)

    # Sortie
    restitue_le = models.DateTimeField("restitué le", null=True, blank=True)
    km_sortie = models.PositiveIntegerField("kilométrage à la sortie", null=True, blank=True)
    travaux_realises = models.TextField("travaux réalisés", blank=True)
    pieces_usagees_rendues = models.BooleanField("pièces usagées rendues au client", default=False)

    notes_internes = models.TextField("notes internes", blank=True)

    class Meta:
        verbose_name = "ordre de réparation"
        verbose_name_plural = "ordres de réparation"
        ordering = ["-arrive_le"]
        indexes = [models.Index(fields=["statut"]), models.Index(fields=["fin_prevue_le"])]

    def __str__(self):
        return f"{self.numero} {self.vehicule.immatriculation}"

    def get_absolute_url(self):
        return reverse("ordre_detail", args=[self.pk])

    # --- Statuts -------------------------------------------------------------

    @property
    def est_actif(self) -> bool:
        return self.statut != self.Statut.RESTITUE

    @property
    def en_retard(self) -> bool:
        return bool(
            self.fin_prevue_le
            and self.fin_prevue_le < timezone.localdate()
            and self.statut not in {self.Statut.PRET, self.Statut.RESTITUE}
        )

    @property
    def est_facture(self) -> bool:
        return hasattr(self, "facture")

    @property
    def rang_statut(self) -> int:
        return list(self.Statut.values).index(self.statut)

    def etape_conseillee(self) -> str | None:
        """L'étape qui suit normalement, celle que l'atelier propose en premier."""
        if self.statut == S.RECU:
            return S.EN_COURS if self.accord_client else S.DIAGNOSTIC
        if self.statut == S.DIAGNOSTIC:
            return S.EN_COURS if self.accord_client else S.DEVIS_ENVOYE
        return {
            S.DEVIS_ENVOYE: S.DEVIS_ACCEPTE,
            S.DEVIS_ACCEPTE: S.EN_COURS,
            S.ATTENTE_PIECES: S.EN_COURS,
            S.EN_COURS: S.TERMINE,
            S.TERMINE: S.PRET,
        }.get(self.statut)

    def transitions_possibles(self, utilisateur=None) -> list[str]:
        suivants = TRANSITIONS.get(self.statut, [])
        if utilisateur is not None and utilisateur.est_mecanicien:
            suivants = [s for s in suivants if s in STATUTS_MECANICIEN]
        # La restitution passe par son propre formulaire.
        suivants = [s for s in suivants if s != self.Statut.RESTITUE]
        conseillee = self.etape_conseillee()
        return sorted(suivants, key=lambda s: s != conseillee)

    def libelle_action(self, cible: str) -> str:
        cas_particuliers = {
            (S.ATTENTE_PIECES, S.EN_COURS): "Pièces reçues, reprendre",
            (S.DEVIS_ENVOYE, S.PRET): "Devis refusé, à rendre",
            (S.TERMINE, S.EN_COURS): "Reprendre les travaux",
        }
        return cas_particuliers.get((self.statut, cible)) or LIBELLES_ACTION.get(cible, S(cible).label)

    def verifier_transition(self, nouveau: str, utilisateur=None) -> str | None:
        """Renvoie la raison du refus, ou None si le changement est permis."""
        if nouveau not in TRANSITIONS.get(self.statut, []):
            return f"Impossible de passer de « {self.get_statut_display()} » à « {self.Statut(nouveau).label} »."
        if utilisateur is not None and utilisateur.est_mecanicien:
            if nouveau not in STATUTS_MECANICIEN:
                return "Ce changement est réservé à l'accueil ou au patron."
            if self.mecanicien_id and self.mecanicien_id != utilisateur.pk:
                return "Ce véhicule est confié à un autre mécanicien."
        if nouveau in STATUTS_EXIGEANT_ACCORD and not self.accord_client:
            return "Enregistrez d'abord l'accord du client sur les travaux."
        if nouveau == self.Statut.RESTITUE and not self.peut_etre_restitue:
            return "Créez la facture avant de rendre le véhicule."
        return None

    @property
    def peut_etre_restitue(self) -> bool:
        if self.statut != self.Statut.PRET:
            return False
        # Sans accord (devis refusé), aucun travail n'a été fait : rien à facturer.
        return self.est_facture or not self.accord_client

    def changer_statut(self, nouveau: str, utilisateur=None, commentaire: str = "") -> None:
        raison = self.verifier_transition(nouveau, utilisateur)
        if raison:
            raise ValidationError(raison)
        ancien = self.statut
        maintenant = timezone.now()
        self.statut = nouveau
        self.statut_depuis = maintenant
        champs = ["statut", "statut_depuis", "modifie_le"]
        if nouveau == self.Statut.RESTITUE:
            self.restitue_le = maintenant
            champs.append("restitue_le")
        if utilisateur is not None and utilisateur.est_mecanicien and not self.mecanicien_id:
            self.mecanicien = utilisateur
            champs.append("mecanicien")
        with transaction.atomic():
            self.save(update_fields=champs)
            HistoriqueStatut.objects.create(ordre=self, ancien=ancien, nouveau=nouveau, par=utilisateur, commentaire=commentaire)

    def enregistrer_accord(self, moyen: str, utilisateur=None) -> None:
        self.accord_client = True
        self.accord_le = timezone.now()
        self.accord_moyen = moyen
        self.save(update_fields=["accord_client", "accord_le", "accord_moyen", "modifie_le"])
        if self.statut == self.Statut.DEVIS_ENVOYE:
            self.changer_statut(self.Statut.DEVIS_ACCEPTE, utilisateur, "Accord du client enregistré")

    # --- Montants ------------------------------------------------------------

    def ventilation_tva(self) -> list[dict]:
        """Bases HT et TVA regroupées par taux, calculées sur les totaux."""
        bases: dict[Decimal, Decimal] = {}
        for ligne in self.lignes.all():
            bases[ligne.taux_tva] = bases.get(ligne.taux_tva, Decimal("0")) + ligne.total_ht
        return [
            {"taux": taux, "base": arrondi(base), "tva": arrondi(base * taux / 100)}
            for taux, base in sorted(bases.items())
        ]

    @property
    def total_ht(self) -> Decimal:
        return arrondi(sum((l.total_ht for l in self.lignes.all()), Decimal("0")))

    @property
    def total_tva(self) -> Decimal:
        return arrondi(sum((v["tva"] for v in self.ventilation_tva()), Decimal("0")))

    @property
    def total_ttc(self) -> Decimal:
        return self.total_ht + self.total_tva


# Chemin normal d'un véhicule, et raccourcis possibles.
S = OrdreReparation.Statut
TRANSITIONS: dict[str, list[str]] = {
    S.RECU: [S.DIAGNOSTIC, S.DEVIS_ENVOYE, S.EN_COURS],
    S.DIAGNOSTIC: [S.DEVIS_ENVOYE, S.ATTENTE_PIECES, S.EN_COURS],
    S.DEVIS_ENVOYE: [S.DEVIS_ACCEPTE, S.PRET],
    S.DEVIS_ACCEPTE: [S.ATTENTE_PIECES, S.EN_COURS],
    S.ATTENTE_PIECES: [S.EN_COURS],
    S.EN_COURS: [S.ATTENTE_PIECES, S.TERMINE],
    S.TERMINE: [S.PRET, S.EN_COURS],
    S.PRET: [S.RESTITUE],
    S.RESTITUE: [],
}
STATUTS_MECANICIEN = {S.DIAGNOSTIC, S.ATTENTE_PIECES, S.EN_COURS, S.TERMINE}
STATUTS_EXIGEANT_ACCORD = {S.DEVIS_ACCEPTE, S.ATTENTE_PIECES, S.EN_COURS, S.TERMINE}
STATUTS_ACTIFS = [s for s in S.values if s != S.RESTITUE]

LIBELLES_ACTION = {
    S.DIAGNOSTIC: "Commencer le diagnostic",
    S.DEVIS_ENVOYE: "Devis envoyé au client",
    S.DEVIS_ACCEPTE: "Devis accepté",
    S.ATTENTE_PIECES: "En attente de pièces",
    S.EN_COURS: "Démarrer la réparation",
    S.TERMINE: "Travaux terminés",
    S.PRET: "Prêt, prévenir le client",
}


class LigneIntervention(models.Model):
    class Type(models.TextChoices):
        PIECE = "piece", "Pièce"
        MAIN_OEUVRE = "main_oeuvre", "Main-d'œuvre"
        FORFAIT = "forfait", "Forfait"

    class Origine(models.TextChoices):
        NEUVE = "neuve", "Neuve"
        REEMPLOI = "reemploi", "Réemploi"
        CLIENT = "client", "Fournie par le client"

    ordre = models.ForeignKey(OrdreReparation, on_delete=models.CASCADE, related_name="lignes")
    type_ligne = models.CharField("type", max_length=15, choices=Type.choices, default=Type.PIECE)
    designation = models.CharField("désignation", max_length=200)
    reference = models.CharField("référence", max_length=60, blank=True)
    origine = models.CharField("origine de la pièce", max_length=10, choices=Origine.choices, blank=True)
    quantite = models.DecimalField("quantité ou heures", max_digits=8, decimal_places=2, default=Decimal("1"))
    prix_unitaire_ht = models.DecimalField("prix unitaire HT (€)", max_digits=10, decimal_places=2)
    taux_tva = models.DecimalField("TVA (%)", max_digits=4, decimal_places=2, default=Decimal("20.00"))
    fournisseur = models.CharField(max_length=100, blank=True)
    commandee_le = models.DateField("commandée le", null=True, blank=True)
    ajoutee_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ligne d'intervention"
        verbose_name_plural = "lignes d'intervention"
        ordering = ["ajoutee_le", "pk"]

    def __str__(self):
        return self.designation

    def clean(self):
        if self.quantite is not None and self.quantite <= 0:
            raise ValidationError({"quantite": "La quantité doit être positive."})
        if self.prix_unitaire_ht is not None and self.prix_unitaire_ht < 0:
            raise ValidationError({"prix_unitaire_ht": "Le prix ne peut pas être négatif."})
        if self.type_ligne != self.Type.PIECE:
            self.origine = ""

    @property
    def total_ht(self) -> Decimal:
        return arrondi(self.quantite * self.prix_unitaire_ht)


class HistoriqueStatut(models.Model):
    ordre = models.ForeignKey(OrdreReparation, on_delete=models.CASCADE, related_name="historique")
    ancien = models.CharField(max_length=20, choices=OrdreReparation.Statut.choices, blank=True)
    nouveau = models.CharField(max_length=20, choices=OrdreReparation.Statut.choices)
    par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    le = models.DateTimeField(default=timezone.now)
    commentaire = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "changement de statut"
        verbose_name_plural = "historique des statuts"
        ordering = ["-le", "-pk"]

    def __str__(self):
        return f"{self.ordre.numero} : {self.get_nouveau_display()}"


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

EXTENSIONS_DOCUMENT = ["jpg", "jpeg", "png", "webp", "pdf"]
EXTENSIONS_IMAGE = {".jpg", ".jpeg", ".png", ".webp"}


def chemin_document(instance, nom_fichier: str) -> str:
    extension = Path(nom_fichier).suffix.lower()
    return f"documents/{timezone.localdate():%Y/%m}/{uuid.uuid4().hex}{extension}"


class Document(models.Model):
    class Type(models.TextChoices):
        PHOTO_ENTREE = "photo_entree", "Photo à l'entrée"
        PHOTO_TRAVAUX = "photo_travaux", "Photo des travaux"
        OR_SIGNE = "or_signe", "OR ou devis signé"
        CARTE_GRISE = "carte_grise", "Carte grise"
        PV_CT = "pv_ct", "Procès-verbal de CT"
        AUTRE = "autre", "Autre"

    vehicule = models.ForeignKey(Vehicule, on_delete=models.CASCADE, related_name="documents")
    ordre = models.ForeignKey(OrdreReparation, on_delete=models.CASCADE, related_name="documents", null=True, blank=True)
    type_document = models.CharField("type", max_length=20, choices=Type.choices, default=Type.PHOTO_ENTREE)
    fichier = models.FileField(upload_to=chemin_document, validators=[FileExtensionValidator(EXTENSIONS_DOCUMENT)])
    nom_original = models.CharField(max_length=200, blank=True)
    ajoute_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    ajoute_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ajoute_le", "-pk"]

    def __str__(self):
        return self.nom_original or Path(self.fichier.name).name

    @property
    def est_image(self) -> bool:
        return Path(self.fichier.name).suffix.lower() in EXTENSIONS_IMAGE


# ---------------------------------------------------------------------------
# Facture
# ---------------------------------------------------------------------------


class Facture(NumeroteMixin, models.Model):
    prefixe_numero = "FA"

    class Paiement(models.TextChoices):
        NON_PAYEE = "non_payee", "Non payée"
        PARTIELLE = "partielle", "Payée en partie"
        PAYEE = "payee", "Payée"

    class Mode(models.TextChoices):
        CARTE = "carte", "Carte bancaire"
        ESPECES = "especes", "Espèces"
        VIREMENT = "virement", "Virement"
        CHEQUE = "cheque", "Chèque"

    numero = models.CharField("numéro de facture", max_length=20, unique=True, editable=False)
    ordre = models.OneToOneField(OrdreReparation, on_delete=models.PROTECT, related_name="facture")
    emise_le = models.DateField("émise le", default=timezone.localdate)
    client_nom = models.CharField("client", max_length=200)
    client_adresse = models.TextField("adresse du client")
    client_siret = models.CharField(max_length=14, blank=True)
    client_professionnel = models.BooleanField(default=False)
    total_ht = models.DecimalField("total HT", max_digits=10, decimal_places=2)
    total_tva = models.DecimalField("TVA", max_digits=10, decimal_places=2)
    total_ttc = models.DecimalField("total TTC", max_digits=10, decimal_places=2)
    statut_paiement = models.CharField("paiement", max_length=12, choices=Paiement.choices, default=Paiement.NON_PAYEE)
    mode_paiement = models.CharField("mode de paiement", max_length=10, choices=Mode.choices, blank=True)
    montant_regle = models.DecimalField("montant réglé", max_digits=10, decimal_places=2, default=Decimal("0"))
    payee_le = models.DateField("réglée le", null=True, blank=True)

    class Meta:
        ordering = ["-emise_le", "-numero"]

    def __str__(self):
        return self.numero

    def get_absolute_url(self):
        return reverse("facture_detail", args=[self.pk])

    @property
    def reste_a_payer(self) -> Decimal:
        return max(self.total_ttc - self.montant_regle, Decimal("0"))

    @classmethod
    def emettre(cls, ordre: OrdreReparation) -> "Facture":
        """Fige les montants de l'OR dans une facture numérotée."""
        if ordre.est_facture:
            raise ValidationError("Cet ordre de réparation est déjà facturé.")
        if ordre.statut not in {S.TERMINE, S.PRET}:
            raise ValidationError("La facture se crée une fois les travaux terminés.")
        if not ordre.accord_client:
            raise ValidationError("Le client n'a pas accepté les travaux : il n'y a rien à facturer.")
        if not ordre.lignes.exists():
            raise ValidationError("Ajoutez au moins une ligne (pièce ou main-d'œuvre) avant de facturer.")
        client = ordre.client
        return cls.objects.create(
            ordre=ordre,
            client_nom=client.nom_affiche,
            client_adresse=client.adresse_complete,
            client_siret=client.siret,
            client_professionnel=client.type_client == Client.Type.PROFESSIONNEL,
            total_ht=ordre.total_ht,
            total_tva=ordre.total_tva,
            total_ttc=ordre.total_ttc,
        )

    def enregistrer_paiement(self, montant: Decimal, mode: str, le: date | None = None) -> None:
        if montant <= 0:
            raise ValidationError("Le montant réglé doit être positif.")
        if montant > self.reste_a_payer:
            raise ValidationError(f"Le montant dépasse le reste à payer ({self.reste_a_payer} €).")
        self.montant_regle = arrondi(self.montant_regle + montant)
        self.mode_paiement = mode
        self.payee_le = le or timezone.localdate()
        self.statut_paiement = self.Paiement.PAYEE if self.reste_a_payer == 0 else self.Paiement.PARTIELLE
        self.save(update_fields=["montant_regle", "mode_paiement", "payee_le", "statut_paiement"])


# ---------------------------------------------------------------------------
# Échéances
# ---------------------------------------------------------------------------


class Echeance(Horodatage):
    class Type(models.TextChoices):
        VIDANGE = "vidange", "Vidange"
        CONTROLE_TECHNIQUE = "controle_technique", "Contrôle technique"
        DISTRIBUTION = "distribution", "Distribution"
        PNEUS = "pneus", "Pneus"
        FREINS = "freins", "Freins"
        AUTRE = "autre", "Autre"

    class Statut(models.TextChoices):
        A_VENIR = "a_venir", "À venir"
        RAPPEL_ENVOYE = "rappel_envoye", "Rappel envoyé"
        FAITE = "faite", "Faite"

    class Canal(models.TextChoices):
        SMS = "sms", "SMS"
        EMAIL = "email", "E-mail"
        APPEL = "appel", "Appel"

    vehicule = models.ForeignKey(Vehicule, on_delete=models.CASCADE, related_name="echeances", verbose_name="véhicule")
    type = models.CharField(max_length=20, choices=Type.choices)
    prevue_le = models.DateField("prévue le", null=True, blank=True)
    km_prevu = models.PositiveIntegerField("kilométrage prévu", null=True, blank=True)
    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.A_VENIR)
    rappel_le = models.DateField("rappel envoyé le", null=True, blank=True)
    rappel_canal = models.CharField("canal du rappel", max_length=10, choices=Canal.choices, blank=True)
    faite_le = models.DateField("faite le", null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "échéance"
        ordering = ["prevue_le", "km_prevu"]

    def __str__(self):
        return f"{self.get_type_display()} {self.vehicule.immatriculation}"

    def clean(self):
        if not self.prevue_le and not self.km_prevu:
            raise ValidationError("Indiquez une date ou un kilométrage.")

    @property
    def en_retard(self) -> bool:
        return bool(self.prevue_le and self.prevue_le < timezone.localdate() and self.statut != self.Statut.FAITE)

    @property
    def jours_restants(self) -> int | None:
        if not self.prevue_le:
            return None
        return (self.prevue_le - timezone.localdate()).days

    def marquer_rappel(self, canal: str) -> None:
        self.statut = self.Statut.RAPPEL_ENVOYE
        self.rappel_le = timezone.localdate()
        self.rappel_canal = canal
        self.save(update_fields=["statut", "rappel_le", "rappel_canal", "modifie_le"])

    def marquer_faite(self, le: date | None = None) -> None:
        self.statut = self.Statut.FAITE
        self.faite_le = le or timezone.localdate()
        self.save(update_fields=["statut", "faite_le", "modifie_le"])
        if self.type == self.Type.CONTROLE_TECHNIQUE:
            vehicule = self.vehicule
            vehicule.date_dernier_ct = self.faite_le
            vehicule.save(update_fields=["date_dernier_ct", "modifie_le"])
            vehicule.planifier_ct()
