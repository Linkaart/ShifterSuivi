from django.contrib import messages
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render

from ..forms import ClientForm
from ..models import Client
from ..permissions import accueil_requis
from .outils import paginer


@accueil_requis
def client_list(request):
    clients = Client.objects.annotate(nb_vehicules=Count("vehicules", distinct=True), dernier_passage=Max("ordres__arrive_le")).order_by("nom", "prenom")
    q = request.GET.get("q", "").strip()
    if q:
        filtre = Q()
        for mot in q.split():
            filtre &= (
                Q(nom__icontains=mot)
                | Q(prenom__icontains=mot)
                | Q(raison_sociale__icontains=mot)
                | Q(telephone__icontains=mot)
                | Q(email__icontains=mot)
                | Q(ville__icontains=mot)
            )
        clients = clients.filter(filtre)
    type_client = request.GET.get("type", "")
    if type_client in Client.Type.values:
        clients = clients.filter(type_client=type_client)
    return render(
        request,
        "garage/client_list.html",
        {"page": paginer(request, clients), "q": q, "type": type_client, "types": Client.Type.choices},
    )


@accueil_requis
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    return render(
        request,
        "garage/client_detail.html",
        {
            "client": client,
            "vehicules": client.vehicules.all(),
            "ordres": client.ordres.select_related("vehicule")[:20],
            "factures": [o.facture for o in client.ordres.select_related("facture") if o.est_facture][:20],
        },
    )


@accueil_requis
def client_nouveau(request):
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        messages.success(request, f"Client {client.nom_affiche} ajouté.")
        return redirect(client)
    return render(request, "garage/client_form.html", {"form": form})


@accueil_requis
def client_modifier(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Fiche client mise à jour.")
        return redirect(client)
    return render(request, "garage/client_form.html", {"form": form, "client": client})
