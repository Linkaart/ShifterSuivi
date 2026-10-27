from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
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


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "role", "is_active")
    list_filter = ("role", "is_active")
    fieldsets = UserAdmin.fieldsets + (("Rôle dans le garage", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Identité et rôle", {"fields": ("first_name", "last_name", "email", "role")}),
    )


class VehiculeInline(admin.TabularInline):
    model = Vehicule
    extra = 0
    fields = ("immatriculation", "marque", "modele", "kilometrage")
    show_change_link = True


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("nom_affiche", "telephone", "ville", "type_client", "accord_rappels")
    list_filter = ("type_client", "accord_rappels")
    search_fields = ("nom", "prenom", "raison_sociale", "telephone", "email")
    inlines = [VehiculeInline]


@admin.register(Vehicule)
class VehiculeAdmin(admin.ModelAdmin):
    list_display = ("immatriculation", "marque", "modele", "client", "kilometrage", "date_dernier_ct")
    list_filter = ("energie", "marque")
    search_fields = ("immatriculation", "immat_cle", "vin", "marque", "modele", "client__nom")
    autocomplete_fields = ("client",)


class LigneInline(admin.TabularInline):
    model = LigneIntervention
    extra = 0


class HistoriqueInline(admin.TabularInline):
    model = HistoriqueStatut
    extra = 0
    readonly_fields = ("ancien", "nouveau", "par", "le", "commentaire")
    can_delete = False


@admin.register(OrdreReparation)
class OrdreReparationAdmin(admin.ModelAdmin):
    list_display = ("numero", "vehicule", "client", "statut", "mecanicien", "arrive_le", "fin_prevue_le")
    list_filter = ("statut", "urgence", "mecanicien")
    search_fields = ("numero", "vehicule__immatriculation", "vehicule__immat_cle", "client__nom")
    autocomplete_fields = ("vehicule", "client")
    readonly_fields = ("numero",)
    inlines = [LigneInline, HistoriqueInline]


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ("numero", "client_nom", "emise_le", "total_ttc", "statut_paiement")
    list_filter = ("statut_paiement", "mode_paiement")
    search_fields = ("numero", "client_nom", "ordre__numero")
    readonly_fields = ("numero", "ordre", "client_nom", "client_adresse", "total_ht", "total_tva", "total_ttc")

    def has_delete_permission(self, request, obj=None):
        # La numérotation des factures doit rester continue : pas de suppression.
        return False


@admin.register(Echeance)
class EcheanceAdmin(admin.ModelAdmin):
    list_display = ("vehicule", "type", "prevue_le", "km_prevu", "statut")
    list_filter = ("type", "statut")
    search_fields = ("vehicule__immatriculation", "vehicule__client__nom")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("__str__", "type_document", "vehicule", "ordre", "ajoute_le")
    list_filter = ("type_document",)
