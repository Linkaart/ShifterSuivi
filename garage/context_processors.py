from django.conf import settings

from .models import STATUTS_ACTIFS, OrdreReparation


def garage(request):
    contexte = {"garage": settings.GARAGE}
    if request.user.is_authenticated:
        contexte["nb_atelier"] = OrdreReparation.objects.filter(statut__in=STATUTS_ACTIFS).count()
        url = request.resolver_match
        contexte["section"] = url.url_name.split("_")[0] if url and url.url_name else ""
    return contexte
