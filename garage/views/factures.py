from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..forms import PaiementForm
from ..models import Facture
from ..permissions import accueil_requis
from .outils import paginer


@accueil_requis
def facture_list(request):
    factures = Facture.objects.select_related("ordre", "ordre__vehicule")
    paiement = request.GET.get("paiement", "")
    if paiement == "a_regler":
        factures = factures.exclude(statut_paiement=Facture.Paiement.PAYEE)
    elif paiement in Facture.Paiement.values:
        factures = factures.filter(statut_paiement=paiement)
    q = request.GET.get("q", "").strip()
    if q:
        factures = factures.filter(Q(numero__icontains=q) | Q(client_nom__icontains=q) | Q(ordre__vehicule__immat_cle__icontains=q.replace("-", "").replace(" ", "")))
    totaux = factures.aggregate(ttc=Sum("total_ttc"), reste=Sum(F("total_ttc") - F("montant_regle")))
    return render(
        request,
        "garage/facture_list.html",
        {
            "page": paginer(request, factures),
            "paiement": paiement,
            "q": q,
            "total_ttc": totaux["ttc"] or Decimal("0"),
            "total_reste": totaux["reste"] or Decimal("0"),
        },
    )


@accueil_requis
def facture_detail(request, pk):
    facture = get_object_or_404(Facture.objects.select_related("ordre", "ordre__vehicule"), pk=pk)
    ordre = facture.ordre
    return render(
        request,
        "garage/facture_detail.html",
        {
            "facture": facture,
            "ordre": ordre,
            "vehicule": ordre.vehicule,
            "lignes": ordre.lignes.all(),
            "ventilation": ordre.ventilation_tva(),
            "form_paiement": PaiementForm(initial={"montant": facture.reste_a_payer}),
        },
    )


@accueil_requis
@require_POST
def facture_paiement(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    form = PaiementForm(request.POST)
    if form.is_valid():
        try:
            facture.enregistrer_paiement(form.cleaned_data["montant"], form.cleaned_data["mode"], form.cleaned_data["le"])
            messages.success(request, f"Paiement enregistré. {facture.get_statut_paiement_display()}.")
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
    else:
        messages.error(request, "Paiement non enregistré : vérifiez le montant et la date.")
    return redirect(facture)
