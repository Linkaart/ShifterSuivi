from decimal import Decimal
from pathlib import Path

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    EXTENSIONS_DOCUMENT,
    Client,
    Document,
    Echeance,
    Facture,
    LigneIntervention,
    OrdreReparation,
    Utilisateur,
    Vehicule,
)


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%d")


class Zone(forms.Textarea):
    def __init__(self, lignes=3, attrs=None):
        attrs = {"rows": lignes, **(attrs or {})}
        super().__init__(attrs=attrs)


# ---------------------------------------------------------------------------
# Envoi de fichiers
# ---------------------------------------------------------------------------

SIGNATURES = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
}


def valider_fichier(fichier) -> None:
    """Vérifie l'extension, la taille et le contenu réel du fichier."""
    if not settings.STOCKAGE_DOCUMENTS_DISPONIBLE:
        raise ValidationError("L'envoi de photos et documents n'est pas encore activé sur ce serveur (stockage à relier).")
    extension = Path(fichier.name).suffix.lower()
    if extension.lstrip(".") not in EXTENSIONS_DOCUMENT:
        raise ValidationError(f"« {fichier.name} » : format refusé. Formats acceptés : JPG, PNG, WEBP ou PDF.")
    if fichier.size > settings.DOCUMENT_TAILLE_MAX:
        taille_mo = settings.DOCUMENT_TAILLE_MAX // (1024 * 1024)
        raise ValidationError(f"« {fichier.name} » dépasse {taille_mo} Mo.")
    debut = fichier.read(12)
    fichier.seek(0)
    contenu_ok = any(debut.startswith(signature) for signature in SIGNATURES[extension])
    if extension == ".webp":
        contenu_ok = contenu_ok and debut[8:12] == b"WEBP"
    if not contenu_ok:
        raise ValidationError(f"« {fichier.name} » ne correspond pas à son format annoncé.")


class EnvoiMultiple(forms.ClearableFileInput):
    allow_multiple_selected = True


class FichiersField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", EnvoiMultiple(attrs={"accept": "image/jpeg,image/png,image/webp,application/pdf"}))
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            if self.required:
                raise ValidationError("Choisissez au moins un fichier.")
            return []
        fichiers = data if isinstance(data, (list, tuple)) else [data]
        propres = [super(FichiersField, self).clean(f, initial) for f in fichiers]
        for fichier in propres:
            valider_fichier(fichier)
        return propres


# ---------------------------------------------------------------------------
# Clients et véhicules
# ---------------------------------------------------------------------------


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "type_client",
            "nom",
            "prenom",
            "raison_sociale",
            "siret",
            "telephone",
            "email",
            "adresse",
            "code_postal",
            "ville",
            "contact_prefere",
            "accord_rappels",
            "notes",
        ]
        widgets = {
            "type_client": forms.RadioSelect,
            "contact_prefere": forms.RadioSelect,
            "notes": Zone(2),
            "telephone": forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "off"}),
            "code_postal": forms.TextInput(attrs={"inputmode": "numeric"}),
            "siret": forms.TextInput(attrs={"inputmode": "numeric"}),
        }


class ClientChoixForm(forms.Form):
    client = forms.ModelChoiceField(queryset=Client.objects.all(), label="Client", empty_label="Choisir un client…")


CHAMPS_VEHICULE = [
    "immatriculation",
    "marque",
    "modele",
    "version",
    "energie",
    "boite",
    "date_mise_circulation",
    "vin",
    "couleur",
    "kilometrage",
    "puissance_fiscale",
    "cylindree",
    "code_moteur",
    "dimensions_pneus",
    "date_dernier_ct",
    "notes",
]


class VehiculeForm(forms.ModelForm):
    class Meta:
        model = Vehicule
        fields = ["client", *CHAMPS_VEHICULE]
        widgets = {
            "immatriculation": forms.TextInput(attrs={"autocapitalize": "characters", "placeholder": "AB-123-CD"}),
            "vin": forms.TextInput(attrs={"autocapitalize": "characters", "maxlength": 17}),
            "date_mise_circulation": DateInput,
            "date_dernier_ct": DateInput,
            "notes": Zone(2),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        libelles_vides = {"client": "Choisir le propriétaire…", "energie": "Choisir…", "boite": "Non précisée"}
        for nom, libelle in libelles_vides.items():
            if nom not in self.fields:
                continue
            champ = self.fields[nom]
            if hasattr(champ, "empty_label"):
                champ.empty_label = libelle
            else:
                champ.choices = [("", libelle), *[c for c in champ.choices if c[0]]]


class VehiculeReceptionForm(VehiculeForm):
    """Véhicule saisi pendant la réception : le kilométrage vient de l'OR."""

    class Meta(VehiculeForm.Meta):
        fields = [
            "immatriculation",
            "marque",
            "modele",
            "version",
            "energie",
            "boite",
            "date_mise_circulation",
            "vin",
            "couleur",
            "date_dernier_ct",
        ]


# ---------------------------------------------------------------------------
# Ordre de réparation
# ---------------------------------------------------------------------------


def _mecaniciens():
    return Utilisateur.objects.filter(role=Utilisateur.Role.MECANICIEN, is_active=True)


class EntreeForm(forms.ModelForm):
    """Ce que l'accueil note quand le client laisse sa voiture."""

    class Meta:
        model = OrdreReparation
        fields = [
            "km_entree",
            "niveau_carburant",
            "demande_client",
            "etat_entree",
            "travaux_prevus",
            "cles_accessoires",
            "objets_laisses",
            "emplacement",
            "fin_prevue_le",
            "mecanicien",
            "urgence",
        ]
        widgets = {
            "km_entree": forms.NumberInput(attrs={"inputmode": "numeric", "min": 0}),
            "niveau_carburant": forms.RadioSelect,
            "demande_client": Zone(3, {"placeholder": "« Bruit au freinage à l'avant depuis une semaine »"}),
            "etat_entree": Zone(3, {"placeholder": "Rayure aile arrière gauche, voyant moteur allumé…"}),
            "travaux_prevus": Zone(2),
            "fin_prevue_le": DateInput,
            "urgence": forms.RadioSelect,
        }

    def __init__(self, *args, vehicule=None, **kwargs):
        self.vehicule = vehicule
        super().__init__(*args, **kwargs)
        self.fields["mecanicien"].queryset = _mecaniciens()
        self.fields["mecanicien"].empty_label = "Pas encore attribué"
        self.fields["niveau_carburant"].choices = [c for c in self.fields["niveau_carburant"].choices if c[0]]

    def clean_km_entree(self):
        km = self.cleaned_data["km_entree"]
        if self.vehicule and self.vehicule.kilometrage and km < self.vehicule.kilometrage:
            raise ValidationError(
                f"Inférieur au dernier kilométrage connu ({self.vehicule.kilometrage:,} km). Vérifiez le compteur.".replace(",", " ")
            )
        return km

    def clean_fin_prevue_le(self):
        jour = self.cleaned_data.get("fin_prevue_le")
        if jour and not self.instance.pk and jour < timezone.localdate():
            raise ValidationError("La date de fin prévue est déjà passée.")
        return jour


class ReceptionForm(EntreeForm):
    accord_immediat = forms.BooleanField(
        label="Le client accepte déjà les travaux prévus",
        required=False,
        help_text="Pour un entretien simple. Sinon, envoyez un devis après le diagnostic.",
    )
    accord_moyen = forms.ChoiceField(
        label="Comment",
        choices=OrdreReparation.MoyenAccord.choices,
        initial=OrdreReparation.MoyenAccord.SIGNATURE,
        required=False,
    )
    reemploi_propose = forms.BooleanField(label="Pièces de réemploi proposées au client", required=False)
    photos = FichiersField(label="Photos de l'état à l'entrée", help_text="JPG, PNG ou WEBP. Les photos sont allégées avant l'envoi.")

    def clean(self):
        donnees = super().clean()
        if donnees.get("accord_immediat") and not donnees.get("travaux_prevus"):
            self.add_error("travaux_prevus", "Décrivez les travaux que le client accepte.")
        return donnees


class InterventionForm(forms.ModelForm):
    class Meta:
        model = OrdreReparation
        fields = ["mecanicien", "travaux_prevus", "diagnostic", "travaux_supplementaires", "notes_internes"]
        widgets = {
            "travaux_prevus": Zone(2),
            "diagnostic": Zone(3),
            "travaux_supplementaires": Zone(2),
            "notes_internes": Zone(2),
        }

    def __init__(self, *args, utilisateur=None, **kwargs):
        super().__init__(*args, **kwargs)
        if utilisateur is not None and utilisateur.est_mecanicien:
            del self.fields["mecanicien"]
        else:
            self.fields["mecanicien"].queryset = _mecaniciens()
            self.fields["mecanicien"].empty_label = "Pas encore attribué"


class LigneForm(forms.ModelForm):
    class Meta:
        model = LigneIntervention
        fields = [
            "type_ligne",
            "designation",
            "reference",
            "origine",
            "quantite",
            "prix_unitaire_ht",
            "taux_tva",
            "fournisseur",
            "commandee_le",
        ]
        widgets = {
            "quantite": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}),
            "prix_unitaire_ht": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"}),
            "taux_tva": forms.NumberInput(attrs={"step": "0.1", "min": "0", "inputmode": "decimal"}),
            "commandee_le": DateInput,
        }


class AccordForm(forms.Form):
    accord_moyen = forms.ChoiceField(label="Accord reçu par", choices=OrdreReparation.MoyenAccord.choices)
    reemploi_propose = forms.BooleanField(label="Pièces de réemploi proposées", required=False)
    reemploi_choix = forms.ChoiceField(
        label="Choix du client",
        choices=[("", "Pas concerné"), *OrdreReparation.ChoixReemploi.choices],
        required=False,
    )


class RestitutionForm(forms.ModelForm):
    class Meta:
        model = OrdreReparation
        fields = ["km_sortie", "travaux_realises", "pieces_usagees_rendues"]
        widgets = {
            "km_sortie": forms.NumberInput(attrs={"inputmode": "numeric", "min": 0}),
            "travaux_realises": Zone(3),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["km_sortie"].required = True
        self.fields["travaux_realises"].required = True

    def clean_km_sortie(self):
        km = self.cleaned_data["km_sortie"]
        if km is not None and km < self.instance.km_entree:
            raise ValidationError(f"Inférieur au kilométrage d'entrée ({self.instance.km_entree} km).")
        return km


class DocumentForm(forms.Form):
    type_document = forms.ChoiceField(label="Type", choices=Document.Type.choices)
    fichiers = FichiersField(label="Fichiers", required=True)


# ---------------------------------------------------------------------------
# Factures et échéances
# ---------------------------------------------------------------------------


class PaiementForm(forms.Form):
    montant = forms.DecimalField(label="Montant réglé (€)", max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    mode = forms.ChoiceField(label="Mode", choices=Facture.Mode.choices)
    le = forms.DateField(label="Réglé le", widget=DateInput, initial=timezone.localdate)


class EcheanceForm(forms.ModelForm):
    class Meta:
        model = Echeance
        fields = ["vehicule", "type", "prevue_le", "km_prevu", "notes"]
        widgets = {"prevue_le": DateInput, "km_prevu": forms.NumberInput(attrs={"inputmode": "numeric"})}

    def __init__(self, *args, vehicule=None, **kwargs):
        super().__init__(*args, **kwargs)
        if vehicule is not None:
            del self.fields["vehicule"]
            self.instance.vehicule = vehicule
        else:
            self.fields["vehicule"].queryset = Vehicule.objects.select_related("client")


class RappelForm(forms.Form):
    canal = forms.ChoiceField(label="Canal", choices=Echeance.Canal.choices)
