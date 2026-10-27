from django.core.paginator import Paginator
from django.utils.http import url_has_allowed_host_and_scheme


def paginer(request, queryset, par_page: int = 25):
    return Paginator(queryset, par_page).get_page(request.GET.get("page"))


def retour_securise(request, defaut: str) -> str:
    """Adresse de retour fournie par le formulaire, si elle reste sur le site."""
    suivant = request.POST.get("suivant") or request.GET.get("suivant")
    if suivant and url_has_allowed_host_and_scheme(
        suivant, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return suivant
    return defaut


def enregistrer_documents(fichiers, *, vehicule, ordre, type_document, utilisateur):
    from ..models import Document

    return [
        Document.objects.create(
            vehicule=vehicule,
            ordre=ordre,
            type_document=type_document,
            fichier=fichier,
            nom_original=fichier.name[:200],
            ajoute_par=utilisateur,
        )
        for fichier in fichiers
    ]
