from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.tableau_de_bord, name="tableau_de_bord"),
    path(
        "connexion/",
        auth_views.LoginView.as_view(template_name="registration/login.html", redirect_authenticated_user=True),
        name="connexion",
    ),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="deconnexion"),
    path("atelier/", views.atelier, name="atelier"),
    path("recherche/", views.recherche, name="recherche"),
    # Ordres de réparation
    path("ordres/", views.ordre_list, name="ordre_list"),
    path("ordres/reception/", views.reception, name="reception"),
    path("ordres/<int:pk>/", views.ordre_detail, name="ordre_detail"),
    path("ordres/<int:pk>/entree/", views.ordre_modifier, name="ordre_modifier"),
    path("ordres/<int:pk>/statut/", views.ordre_statut, name="ordre_statut"),
    path("ordres/<int:pk>/intervention/", views.ordre_intervention, name="ordre_intervention"),
    path("ordres/<int:pk>/lignes/", views.ligne_ajouter, name="ligne_ajouter"),
    path("ordres/<int:pk>/lignes/<int:ligne_pk>/supprimer/", views.ligne_supprimer, name="ligne_supprimer"),
    path("ordres/<int:pk>/accord/", views.ordre_accord, name="ordre_accord"),
    path("ordres/<int:pk>/documents/", views.ordre_documents, name="ordre_documents"),
    path("ordres/<int:pk>/facturer/", views.ordre_facturer, name="ordre_facturer"),
    path("ordres/<int:pk>/restitution/", views.ordre_restitution, name="ordre_restitution"),
    # Véhicules
    path("vehicules/", views.vehicule_list, name="vehicule_list"),
    path("vehicules/nouveau/", views.vehicule_nouveau, name="vehicule_nouveau"),
    path("vehicules/<int:pk>/", views.vehicule_detail, name="vehicule_detail"),
    path("vehicules/<int:pk>/modifier/", views.vehicule_modifier, name="vehicule_modifier"),
    path("vehicules/<int:pk>/documents/", views.vehicule_documents, name="vehicule_documents"),
    # Clients
    path("clients/", views.client_list, name="client_list"),
    path("clients/nouveau/", views.client_nouveau, name="client_nouveau"),
    path("clients/<int:pk>/", views.client_detail, name="client_detail"),
    path("clients/<int:pk>/modifier/", views.client_modifier, name="client_modifier"),
    # Échéances
    path("echeances/", views.echeance_list, name="echeance_list"),
    path("echeances/nouvelle/", views.echeance_nouveau, name="echeance_nouveau"),
    path("echeances/<int:pk>/modifier/", views.echeance_modifier, name="echeance_modifier"),
    path("echeances/<int:pk>/rappel/", views.echeance_rappel, name="echeance_rappel"),
    path("echeances/<int:pk>/faite/", views.echeance_faite, name="echeance_faite"),
    # Factures
    path("factures/", views.facture_list, name="facture_list"),
    path("factures/<int:pk>/", views.facture_detail, name="facture_detail"),
    path("factures/<int:pk>/paiement/", views.facture_paiement, name="facture_paiement"),
    # Documents (accès protégé)
    path("documents/<int:pk>/", views.document_voir, name="document_voir"),
]
