from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms import EcheanceForm, RappelForm
from ..models import Echeance, Vehicule
from ..permissions import accueil_requis
from .outils import paginer, retour_securise

FILTRES = [
    ("proches", "30 prochains jours"),
    ("retard", "En retard"),
    ("a_venir", "Toutes à venir"),
    ("faites", "Faites"),
]


@accueil_requis
def echeance_list(request):
    aujourd_hui = timezone.localdate()
    echeances = Echeance.objects.select_related("vehicule", "vehicule__client")
    filtre = request.GET.get("filtre", "proches")
    if filtre == "retard":
        echeances = echeances.exclude(statut=Echeance.Statut.FAITE).filter(prevue_le__lt=aujourd_hui)
    elif filtre == "a_venir":
        echeances = echeances.exclude(statut=Echeance.Statut.FAITE)
    elif filtre == "faites":
        echeances = echeances.filter(statut=Echeance.Statut.FAITE).order_by("-faite_le")
    else:
        filtre = "proches"
        echeances = echeances.exclude(statut=Echeance.Statut.FAITE).filter(prevue_le__lte=aujourd_hui + timedelta(days=30))
    type_echeance = request.GET.get("type", "")
    if type_echeance in Echeance.Type.values:
        echeances = echeances.filter(type=type_echeance)
    return render(
        request,
        "garage/echeance_list.html",
        {
            "page": paginer(request, echeances),
            "filtre": filtre,
            "filtres": FILTRES,
            "type": type_echeance,
            "types": Echeance.Type.choices,
            "canaux": Echeance.Canal.choices,
        },
    )


@accueil_requis
def echeance_nouveau(request):
    vehicule = None
    vehicule_id = request.GET.get("vehicule")
    if vehicule_id and vehicule_id.isdigit():
        vehicule = get_object_or_404(Vehicule, pk=vehicule_id)
    form = EcheanceForm(request.POST or None, vehicule=vehicule)
    if request.method == "POST" and form.is_valid():
        echeance = form.save()
        messages.success(request, f"Échéance ajoutée : {echeance.get_type_display().lower()}.")
        return redirect(echeance.vehicule.get_absolute_url() if vehicule else "echeance_list")
    return render(request, "garage/echeance_form.html", {"form": form, "vehicule": vehicule})


@accueil_requis
def echeance_modifier(request, pk):
    echeance = get_object_or_404(Echeance.objects.select_related("vehicule"), pk=pk)
    form = EcheanceForm(request.POST or None, instance=echeance, vehicule=echeance.vehicule)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Échéance mise à jour.")
        return redirect(echeance.vehicule)
    return render(request, "garage/echeance_form.html", {"form": form, "vehicule": echeance.vehicule, "echeance": echeance})


@accueil_requis
@require_POST
def echeance_rappel(request, pk):
    echeance = get_object_or_404(Echeance.objects.select_related("vehicule__client"), pk=pk)
    form = RappelForm(request.POST)
    if form.is_valid():
        echeance.marquer_rappel(form.cleaned_data["canal"])
        messages.success(request, f"Rappel noté pour {echeance.vehicule.immatriculation}.")
        if not echeance.vehicule.client.accord_rappels:
            messages.warning(request, "Ce client n'a pas donné son accord pour recevoir des rappels.")
    return redirect(retour_securise(request, "echeance_list"))


@accueil_requis
@require_POST
def echeance_faite(request, pk):
    echeance = get_object_or_404(Echeance.objects.select_related("vehicule"), pk=pk)
    echeance.marquer_faite()
    message = f"{echeance.get_type_display()} faite pour {echeance.vehicule.immatriculation}."
    if echeance.type == Echeance.Type.CONTROLE_TECHNIQUE:
        message += " Prochain contrôle planifié."
    messages.success(request, message)
    return redirect(retour_securise(request, "echeance_list"))
