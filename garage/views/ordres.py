from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..forms import (
    AccordForm,
    ClientChoixForm,
    ClientForm,
    DocumentForm,
    EntreeForm,
    InterventionForm,
    LigneForm,
    ReceptionForm,
    RestitutionForm,
    VehiculeReceptionForm,
)
from ..models import (
    STATUTS_ACTIFS,
    Document,
    Facture,
    HistoriqueStatut,
    LigneIntervention,
    OrdreReparation,
    Utilisateur,
    Vehicule,
    cle_immatriculation,
    normaliser_immatriculation,
)
from ..permissions import accueil_requis, peut_travailler_sur
from .outils import enregistrer_documents, paginer, retour_securise

S = OrdreReparation.Statut


@login_required
def ordre_list(request):
    ordres = OrdreReparation.objects.select_related("vehicule", "client", "mecanicien")
    statut = request.GET.get("statut", "actifs")
    if statut == "actifs":
        ordres = ordres.filter(statut__in=STATUTS_ACTIFS)
    elif statut in S.values:
        ordres = ordres.filter(statut=statut)
    mecanicien = request.GET.get("mecanicien", "")
    if mecanicien.isdigit():
        ordres = ordres.filter(mecanicien_id=int(mecanicien))
    q = request.GET.get("q", "").strip()
    if q:
        cle = cle_immatriculation(q)
        filtre = Q(numero__icontains=q) | Q(client__nom__icontains=q) | Q(client__raison_sociale__icontains=q)
        if cle:
            filtre |= Q(vehicule__immat_cle__contains=cle)
        ordres = ordres.filter(filtre)
    return render(
        request,
        "garage/ordre_list.html",
        {
            "page": paginer(request, ordres),
            "statut": statut,
            "statuts": S.choices,
            "mecanicien": mecanicien,
            "mecaniciens": Utilisateur.objects.filter(role=Utilisateur.Role.MECANICIEN),
            "q": q,
        },
    )


@accueil_requis
def reception(request):
    """Nouvelle réception : retrouver ou créer le véhicule (et son client), puis ouvrir l'OR."""
    vehicule = None
    vehicule_id = request.POST.get("vehicule_id") or request.GET.get("vehicule")
    if vehicule_id:
        vehicule = get_object_or_404(Vehicule.objects.select_related("client"), pk=vehicule_id)

    immat = request.GET.get("immat", "").strip()
    resultats = []
    nouveau = request.method == "POST" or request.GET.get("nouveau") == "1"
    if immat and not vehicule and request.method == "GET":
        cle = cle_immatriculation(immat)
        resultats = list(Vehicule.objects.filter(immat_cle__contains=cle).select_related("client")[:8]) if cle else []
        exact = [v for v in resultats if v.immat_cle == cle]
        if exact and len(resultats) == 1:
            vehicule = exact[0]
        elif not resultats:
            nouveau = True

    if vehicule:
        etape = "ordre"
    elif nouveau:
        etape = "nouveau"
    else:
        etape = "recherche"

    deja_a_l_atelier = vehicule.passage_en_cours if vehicule else None
    client_choix = request.POST.get("client_choix", "nouveau")
    form_ordre = form_vehicule = form_client = form_choix = None

    if etape in {"ordre", "nouveau"}:
        donnees = request.POST if request.method == "POST" else None
        fichiers = request.FILES if request.method == "POST" else None
        form_ordre = ReceptionForm(donnees, fichiers, vehicule=vehicule, prefix="o")
        if etape == "nouveau":
            initial = {"immatriculation": normaliser_immatriculation(immat)} if immat else {}
            form_vehicule = VehiculeReceptionForm(donnees, prefix="v", initial=initial)
            form_client = ClientForm(donnees if client_choix == "nouveau" else None, prefix="c")
            form_choix = ClientChoixForm(donnees if client_choix == "existant" else None, prefix="cc")

    if request.method == "POST" and form_ordre is not None:
        if deja_a_l_atelier:
            messages.error(request, f"Ce véhicule est déjà à l'atelier ({deja_a_l_atelier.numero}).")
            return redirect(deja_a_l_atelier)
        formulaires = [form_ordre]
        if etape == "nouveau":
            formulaires.append(form_vehicule)
            formulaires.append(form_client if client_choix == "nouveau" else form_choix)
        if all(f.is_valid() for f in formulaires):
            ordre = _creer_reception(request, vehicule, form_ordre, form_vehicule, form_client, form_choix, client_choix)
            messages.success(request, f"{ordre.vehicule.immatriculation} est enregistré à l'atelier ({ordre.numero}).")
            return redirect(ordre)

    return render(
        request,
        "garage/reception.html",
        {
            "etape": etape,
            "immat": immat,
            "resultats": resultats,
            "vehicule": vehicule,
            "deja_a_l_atelier": deja_a_l_atelier,
            "form_ordre": form_ordre,
            "form_vehicule": form_vehicule,
            "form_client": form_client,
            "form_choix": form_choix,
            "client_choix": client_choix,
        },
    )


@transaction.atomic
def _creer_reception(request, vehicule, form_ordre, form_vehicule, form_client, form_choix, client_choix):
    donnees = form_ordre.cleaned_data
    if vehicule is None:
        client = form_client.save() if client_choix == "nouveau" else form_choix.cleaned_data["client"]
        vehicule = form_vehicule.save(commit=False)
        vehicule.client = client
        vehicule.kilometrage = donnees["km_entree"]
        vehicule.save()
        vehicule.planifier_ct()
    elif donnees["km_entree"] > vehicule.kilometrage:
        vehicule.kilometrage = donnees["km_entree"]
        vehicule.save(update_fields=["kilometrage", "modifie_le"])

    ordre = form_ordre.save(commit=False)
    ordre.vehicule = vehicule
    ordre.client = vehicule.client
    ordre.recu_par = request.user
    ordre.reemploi_propose = donnees.get("reemploi_propose", False)
    if donnees.get("accord_immediat"):
        ordre.accord_client = True
        ordre.accord_moyen = donnees.get("accord_moyen") or OrdreReparation.MoyenAccord.SIGNATURE
        ordre.accord_le = ordre.arrive_le
    ordre.save()
    HistoriqueStatut.objects.create(ordre=ordre, ancien="", nouveau=S.RECU, par=request.user, commentaire="Réception du véhicule")
    enregistrer_documents(
        donnees.get("photos") or [],
        vehicule=vehicule,
        ordre=ordre,
        type_document=Document.Type.PHOTO_ENTREE,
        utilisateur=request.user,
    )
    return ordre


def _etapes(ordre):
    rang = ordre.rang_statut
    return [
        {"valeur": valeur, "libelle": libelle, "etat": "fait" if i < rang else "actuel" if i == rang else "a_venir"}
        for i, (valeur, libelle) in enumerate(S.choices)
    ]


@login_required
def ordre_detail(request, pk):
    ordre = get_object_or_404(
        OrdreReparation.objects.select_related("vehicule", "client", "mecanicien", "recu_par"), pk=pk
    )
    utilisateur = request.user
    peut_agir = peut_travailler_sur(utilisateur, ordre)
    verrouille = ordre.est_facture or not ordre.est_actif

    actions = []
    if peut_agir:
        conseillee = ordre.etape_conseillee()
        for statut in ordre.transitions_possibles(utilisateur):
            if statut == S.DEVIS_ACCEPTE and not ordre.accord_client and utilisateur.gere_l_accueil:
                continue  # remplacé par le bouton « Enregistrer l'accord du client »
            actions.append(
                {
                    "statut": statut,
                    "libelle": ordre.libelle_action(statut),
                    "raison": ordre.verifier_transition(statut, utilisateur),
                    "conseillee": statut == conseillee,
                }
            )
    for action in actions:
        action["principal"] = action["conseillee"] and not action["raison"]
    raisons = list(dict.fromkeys(a["raison"] for a in actions if a["raison"]))

    facture = getattr(ordre, "facture", None) if ordre.est_facture else None
    lignes = list(ordre.lignes.all())
    documents = list(ordre.documents.select_related("ajoute_par"))
    contexte = {
        "ordre": ordre,
        "vehicule": ordre.vehicule,
        "client": ordre.client,
        "etapes": _etapes(ordre),
        "actions": actions,
        "raisons": raisons,
        "peut_agir": peut_agir,
        "peut_modifier_lignes": peut_agir and not verrouille,
        "lignes": lignes,
        "ventilation": ordre.ventilation_tva(),
        "photos": [d for d in documents if d.est_image],
        "fichiers": [d for d in documents if not d.est_image],
        "nb_documents": len(documents),
        "historique": ordre.historique.select_related("par"),
        "facture": facture,
        "form_ligne": LigneForm(),
        "form_intervention": InterventionForm(instance=ordre, utilisateur=utilisateur),
        "form_accord": AccordForm(initial={"reemploi_propose": ordre.reemploi_propose, "reemploi_choix": ordre.reemploi_choix}),
        "form_document": DocumentForm(initial={"type_document": Document.Type.PHOTO_TRAVAUX}),
        "form_restitution": RestitutionForm(
            instance=ordre,
            initial={"travaux_realises": ordre.travaux_realises or (ordre.travaux_prevus if ordre.accord_client else "Aucun travail : devis refusé par le client.")},
        ),
        "peut_facturer": utilisateur.gere_l_accueil and ordre.accord_client and not ordre.est_facture and ordre.statut in {S.TERMINE, S.PRET} and lignes,
        "peut_enregistrer_accord": utilisateur.gere_l_accueil and not ordre.accord_client and ordre.statut in {S.RECU, S.DIAGNOSTIC, S.DEVIS_ENVOYE},
        "peut_restituer": utilisateur.gere_l_accueil and ordre.statut == S.PRET,
        "restitution_bloquee": ordre.statut == S.PRET and not ordre.peut_etre_restitue,
        "taux_horaire": settings.GARAGE["taux_horaire_ht"],
    }
    return render(request, "garage/ordre_detail.html", contexte)


@accueil_requis
def ordre_modifier(request, pk):
    ordre = get_object_or_404(OrdreReparation.objects.select_related("vehicule"), pk=pk)
    form = EntreeForm(request.POST or None, instance=ordre, vehicule=None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Les informations d'entrée sont à jour.")
        return redirect(ordre)
    return render(request, "garage/ordre_form.html", {"ordre": ordre, "form": form})


def _ordre_modifiable(request, pk, *, lignes=False):
    ordre = get_object_or_404(OrdreReparation, pk=pk)
    if not peut_travailler_sur(request.user, ordre):
        raise PermissionDenied("Ce véhicule est confié à un autre mécanicien.")
    if lignes and (ordre.est_facture or not ordre.est_actif):
        raise PermissionDenied("Cet ordre de réparation est facturé : ses lignes ne changent plus.")
    return ordre


@login_required
@require_POST
def ordre_statut(request, pk):
    ordre = _ordre_modifiable(request, pk)
    nouveau = request.POST.get("statut", "")
    if nouveau not in S.values:
        messages.error(request, "Statut inconnu.")
    else:
        try:
            ordre.changer_statut(nouveau, request.user, request.POST.get("commentaire", "")[:200])
            messages.success(request, f"{ordre.vehicule.immatriculation} : {S(nouveau).label.lower()}.")
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
    return redirect(retour_securise(request, ordre.get_absolute_url()))


@login_required
@require_POST
def ordre_intervention(request, pk):
    ordre = _ordre_modifiable(request, pk)
    form = InterventionForm(request.POST, instance=ordre, utilisateur=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, "Intervention mise à jour.")
    else:
        messages.error(request, "L'intervention n'a pas été enregistrée : vérifiez les champs.")
    return redirect(f"{ordre.get_absolute_url()}#intervention")


@login_required
@require_POST
def ligne_ajouter(request, pk):
    ordre = _ordre_modifiable(request, pk, lignes=True)
    form = LigneForm(request.POST)
    if form.is_valid():
        ligne = form.save(commit=False)
        ligne.ordre = ordre
        ligne.save()
        messages.success(request, f"Ligne ajoutée : {ligne.designation}.")
    else:
        erreurs = "; ".join(f"{form.fields[c].label if c in form.fields else ''} {e[0]}".strip() for c, e in form.errors.items())
        messages.error(request, f"Ligne non ajoutée. {erreurs}")
    return redirect(f"{ordre.get_absolute_url()}#lignes")


@login_required
@require_POST
def ligne_supprimer(request, pk, ligne_pk):
    ordre = _ordre_modifiable(request, pk, lignes=True)
    ligne = get_object_or_404(LigneIntervention, pk=ligne_pk, ordre=ordre)
    ligne.delete()
    messages.success(request, f"Ligne retirée : {ligne.designation}.")
    return redirect(f"{ordre.get_absolute_url()}#lignes")


@accueil_requis
@require_POST
def ordre_accord(request, pk):
    ordre = get_object_or_404(OrdreReparation, pk=pk)
    form = AccordForm(request.POST)
    if form.is_valid():
        ordre.reemploi_propose = form.cleaned_data["reemploi_propose"]
        ordre.reemploi_choix = form.cleaned_data["reemploi_choix"]
        ordre.save(update_fields=["reemploi_propose", "reemploi_choix", "modifie_le"])
        try:
            ordre.enregistrer_accord(form.cleaned_data["accord_moyen"], request.user)
            messages.success(request, "Accord du client enregistré.")
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
    else:
        messages.error(request, "Indiquez comment le client a donné son accord.")
    return redirect(f"{ordre.get_absolute_url()}#accord")


@login_required
@require_POST
def ordre_documents(request, pk):
    ordre = _ordre_modifiable(request, pk)
    form = DocumentForm(request.POST, request.FILES)
    if form.is_valid():
        documents = enregistrer_documents(
            form.cleaned_data["fichiers"],
            vehicule=ordre.vehicule,
            ordre=ordre,
            type_document=form.cleaned_data["type_document"],
            utilisateur=request.user,
        )
        messages.success(request, f"{len(documents)} fichier(s) ajouté(s).")
    else:
        messages.error(request, " ".join(e for erreurs in form.errors.values() for e in erreurs))
    return redirect(f"{ordre.get_absolute_url()}#documents")


@accueil_requis
@require_POST
def ordre_facturer(request, pk):
    ordre = get_object_or_404(OrdreReparation.objects.select_related("client"), pk=pk)
    try:
        facture = Facture.emettre(ordre)
    except ValidationError as erreur:
        messages.error(request, erreur.messages[0])
        return redirect(ordre)
    messages.success(request, f"Facture {facture.numero} créée.")
    return redirect(facture)


@accueil_requis
@require_POST
def ordre_restitution(request, pk):
    ordre = get_object_or_404(OrdreReparation.objects.select_related("vehicule"), pk=pk)
    form = RestitutionForm(request.POST, instance=ordre)
    if not form.is_valid():
        messages.error(request, " ".join(e for erreurs in form.errors.values() for e in erreurs))
        return redirect(f"{ordre.get_absolute_url()}#restitution")
    raison = ordre.verifier_transition(S.RESTITUE, request.user)
    if raison:
        messages.error(request, raison)
        return redirect(ordre)
    with transaction.atomic():
        form.save()
        vehicule = ordre.vehicule
        if ordre.km_sortie and ordre.km_sortie > vehicule.kilometrage:
            vehicule.kilometrage = ordre.km_sortie
            vehicule.save(update_fields=["kilometrage", "modifie_le"])
        ordre.changer_statut(S.RESTITUE, request.user, "Véhicule rendu au client")
    messages.success(request, f"{vehicule.immatriculation} est rendu au client.")
    return redirect(ordre)
