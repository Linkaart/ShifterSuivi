from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..forms import DocumentForm, VehiculeForm
from ..models import Client, Document, OrdreReparation, Vehicule, cle_immatriculation
from ..permissions import accueil_requis
from .outils import enregistrer_documents, paginer


@login_required
def vehicule_list(request):
    en_cours = OrdreReparation.objects.filter(vehicule=OuterRef("pk")).exclude(statut=OrdreReparation.Statut.RESTITUE)
    vehicules = Vehicule.objects.select_related("client").annotate(
        statut_atelier=Subquery(en_cours.values("statut")[:1]),
        ordre_atelier=Subquery(en_cours.values("pk")[:1]),
    )
    q = request.GET.get("q", "").strip()
    if q:
        cle = cle_immatriculation(q)
        filtre = Q(marque__icontains=q) | Q(modele__icontains=q) | Q(client__nom__icontains=q) | Q(vin__icontains=q)
        if cle:
            filtre |= Q(immat_cle__contains=cle)
        vehicules = vehicules.filter(filtre)
    if request.GET.get("atelier") == "1":
        vehicules = vehicules.filter(statut_atelier__isnull=False)
    return render(
        request,
        "garage/vehicule_list.html",
        {"page": paginer(request, vehicules), "q": q, "atelier": request.GET.get("atelier", "")},
    )


@login_required
def vehicule_detail(request, pk):
    vehicule = get_object_or_404(Vehicule.objects.select_related("client"), pk=pk)
    documents = list(vehicule.documents.select_related("ordre"))
    return render(
        request,
        "garage/vehicule_detail.html",
        {
            "vehicule": vehicule,
            "client": vehicule.client,
            "ordres": vehicule.ordres.select_related("mecanicien").prefetch_related("lignes"),
            "passage": vehicule.passage_en_cours,
            "echeances": vehicule.echeances.exclude(statut="faite"),
            "photos": [d for d in documents if d.est_image][:12],
            "fichiers": [d for d in documents if not d.est_image],
            "form_document": DocumentForm(initial={"type_document": Document.Type.CARTE_GRISE}),
        },
    )


@accueil_requis
def vehicule_nouveau(request):
    initial = {}
    client_id = request.GET.get("client")
    if client_id and client_id.isdigit():
        initial["client"] = get_object_or_404(Client, pk=client_id)
    form = VehiculeForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        vehicule = form.save()
        vehicule.planifier_ct()
        messages.success(request, f"Véhicule {vehicule.immatriculation} ajouté.")
        return redirect(vehicule)
    return render(request, "garage/vehicule_form.html", {"form": form})


@accueil_requis
def vehicule_modifier(request, pk):
    vehicule = get_object_or_404(Vehicule, pk=pk)
    form = VehiculeForm(request.POST or None, instance=vehicule)
    if request.method == "POST" and form.is_valid():
        vehicule = form.save()
        vehicule.planifier_ct()
        messages.success(request, "Fiche véhicule mise à jour.")
        return redirect(vehicule)
    return render(request, "garage/vehicule_form.html", {"form": form, "vehicule": vehicule})


@accueil_requis
@require_POST
def vehicule_documents(request, pk):
    vehicule = get_object_or_404(Vehicule, pk=pk)
    form = DocumentForm(request.POST, request.FILES)
    if form.is_valid():
        documents = enregistrer_documents(
            form.cleaned_data["fichiers"],
            vehicule=vehicule,
            ordre=None,
            type_document=form.cleaned_data["type_document"],
            utilisateur=request.user,
        )
        messages.success(request, f"{len(documents)} fichier(s) ajouté(s).")
    else:
        messages.error(request, " ".join(e for erreurs in form.errors.values() for e in erreurs))
    return redirect(f"{vehicule.get_absolute_url()}#documents")
