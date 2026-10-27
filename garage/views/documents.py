import mimetypes
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from ..models import Document


@login_required
def document_voir(request, pk):
    """Les documents ne sont jamais publics : ils passent par cette vue protégée."""
    document = get_object_or_404(Document, pk=pk)
    try:
        fichier = document.fichier.open("rb")
    except FileNotFoundError as erreur:
        raise Http404("Fichier introuvable.") from erreur
    extension = Path(document.fichier.name).suffix.lower()
    type_mime = mimetypes.types_map.get(extension, "application/octet-stream")
    nom = Path(document.nom_original or document.fichier.name).name
    reponse = FileResponse(fichier, content_type=type_mime, as_attachment=False, filename=nom)
    reponse["Cache-Control"] = "private, max-age=3600"
    return reponse
