from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from ..models import (
    STATUTS_ACTIFS,
    Client,
    Echeance,
    Facture,
    OrdreReparation,
    Utilisateur,
    Vehicule,
    cle_immatriculation,
)

S = OrdreReparation.Statut

# Le tableau de l'atelier regroupe les 8 statuts actifs en 4 colonnes.
COLONNES_ATELIER = [
    ("Arrivées", [S.RECU, S.DIAGNOSTIC]),
    ("Devis", [S.DEVIS_ENVOYE, S.DEVIS_ACCEPTE]),
    ("Sur le pont", [S.ATTENTE_PIECES, S.EN_COURS]),
    ("Sortie", [S.TERMINE, S.PRET]),
]


def _ordres_actifs():
    return OrdreReparation.objects.filter(statut__in=STATUTS_ACTIFS).select_related("vehicule", "client", "mecanicien")


def _action_suivante(ordre, utilisateur):
    """L'étape conseillée, si cet utilisateur peut la faire maintenant."""
    statut = ordre.etape_conseillee()
    if statut and statut in ordre.transitions_possibles(utilisateur) and ordre.verifier_transition(statut, utilisateur) is None:
        return statut, ordre.libelle_action(statut)
    return None


@login_required
def tableau_de_bord(request):
    aujourd_hui = timezone.localdate()
    utilisateur = request.user
    actifs = _ordres_actifs()
    if utilisateur.est_mecanicien:
        actifs = actifs.filter(Q(mecanicien=utilisateur) | Q(mecanicien__isnull=True))

    comptes = dict(actifs.order_by().values("statut").annotate(n=Count("pk")).values_list("statut", "n"))
    total_actifs = sum(comptes.values())
    charge = [
        {"statut": s, "libelle": S(s).label, "nombre": comptes.get(s, 0)}
        for s in STATUTS_ACTIFS
    ]

    en_retard = actifs.filter(fin_prevue_le__lt=aujourd_hui).exclude(statut=S.PRET).order_by("fin_prevue_le")
    prets = actifs.filter(statut=S.PRET).order_by("statut_depuis")
    en_attente = actifs.filter(statut__in=[S.DEVIS_ENVOYE, S.ATTENTE_PIECES]).order_by("statut_depuis")

    contexte = {
        "aujourd_hui": aujourd_hui,
        "total_actifs": total_actifs,
        "arrives_aujourd_hui": actifs.filter(arrive_le__date=aujourd_hui).count(),
        "charge": charge,
        "en_retard": en_retard[:6],
        "nb_en_retard": en_retard.count(),
        "prets": prets[:6],
        "nb_prets": prets.count(),
        "en_attente": en_attente[:6],
        "nb_en_attente": en_attente.count(),
    }

    if utilisateur.est_mecanicien:
        contexte["mes_ordres"] = actifs.filter(mecanicien=utilisateur).order_by("fin_prevue_le", "arrive_le")

    if utilisateur.gere_l_accueil:
        limite = aujourd_hui + timedelta(days=30)
        contexte["echeances"] = (
            Echeance.objects.exclude(statut=Echeance.Statut.FAITE)
            .filter(prevue_le__lte=limite)
            .select_related("vehicule", "vehicule__client")
            .order_by("prevue_le")[:7]
        )

    if utilisateur.est_patron:
        debut_mois = aujourd_hui.replace(day=1)
        factures_mois = Facture.objects.filter(emise_le__gte=debut_mois)
        impayees = Facture.objects.exclude(statut_paiement=Facture.Paiement.PAYEE)
        contexte["mois"] = {
            "facture_ht": factures_mois.aggregate(t=Sum("total_ht"))["t"] or Decimal("0"),
            "encaisse": factures_mois.aggregate(t=Sum("montant_regle"))["t"] or Decimal("0"),
            "nb_factures": factures_mois.count(),
            "rendus": OrdreReparation.objects.filter(restitue_le__date__gte=debut_mois).count(),
            "impayes": impayees.aggregate(t=Sum(F("total_ttc") - F("montant_regle")))["t"] or Decimal("0"),
            "nb_impayees": impayees.count(),
        }
    return render(request, "garage/tableau_de_bord.html", contexte)


@login_required
def atelier(request):
    utilisateur = request.user
    ordres = _ordres_actifs()
    filtre = request.GET.get("mecanicien", "")
    if filtre == "moi":
        ordres = ordres.filter(mecanicien=utilisateur)
    elif filtre == "libre":
        ordres = ordres.filter(mecanicien__isnull=True)
    elif filtre.isdigit():
        ordres = ordres.filter(mecanicien_id=int(filtre))

    ordres = sorted(
        ordres,
        key=lambda o: (o.urgence != OrdreReparation.Urgence.URGENTE, not o.en_retard, o.statut_depuis),
    )
    colonnes = []
    for titre, statuts in COLONNES_ATELIER:
        cartes = []
        for ordre in ordres:
            if ordre.statut in statuts:
                ordre.action = _action_suivante(ordre, utilisateur)
                cartes.append(ordre)
        colonnes.append({"titre": titre, "statuts": [(s, S(s).label) for s in statuts], "cartes": cartes})

    return render(
        request,
        "garage/atelier.html",
        {
            "colonnes": colonnes,
            "filtre": filtre,
            "mecaniciens": Utilisateur.objects.filter(role=Utilisateur.Role.MECANICIEN, is_active=True),
            "nb_cartes": len(ordres),
        },
    )


@login_required
def recherche(request):
    q = request.GET.get("q", "").strip()
    cle = cle_immatriculation(q)
    vehicules, clients, ordres = [], [], []
    if len(q) >= 2:
        vehicules = list(Vehicule.objects.filter(immat_cle__contains=cle).select_related("client")[:20]) if cle else []
        if len(vehicules) == 1 and vehicules[0].immat_cle == cle:
            vehicule = vehicules[0]
            passage = vehicule.passage_en_cours
            return redirect(passage.get_absolute_url() if passage else vehicule.get_absolute_url())
        ordres = list(OrdreReparation.objects.filter(numero__icontains=q).select_related("vehicule", "client")[:20])
        if request.user.gere_l_accueil:
            mots = Q()
            for mot in q.split():
                mots &= Q(nom__icontains=mot) | Q(prenom__icontains=mot) | Q(raison_sociale__icontains=mot) | Q(telephone__icontains=mot)
            clients = list(Client.objects.filter(mots).annotate(nb_vehicules=Count("vehicules")).order_by("nom", "prenom")[:20])
    return render(
        request,
        "garage/recherche.html",
        {"q": q, "vehicules": vehicules, "clients": clients, "ordres": ordres},
    )
