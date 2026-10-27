"""Stockage des documents dans Vercel Blob (store privé).

Les fichiers n'ont jamais d'URL publique : l'appli les lit côté serveur et les
sert par la vue protégée `document_voir`. Le jeton vient de la variable
BLOB_READ_WRITE_TOKEN, ajoutée par Vercel quand le store est relié au projet.
"""

import mimetypes

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class StockageVercelBlob(Storage):
    acces = "private"

    def _save(self, name, content):
        from vercel.blob.sync import put_blob

        if hasattr(content, "seek"):
            content.seek(0)
        donnees = content.read()
        type_mime = getattr(content, "content_type", None) or mimetypes.guess_type(name)[0] or "application/octet-stream"
        resultat = put_blob(name, donnees, access=self.acces, content_type=type_mime)
        return resultat.pathname

    def _open(self, name, mode="rb"):
        from vercel.blob.sync import BlobNotFoundError, get_blob

        try:
            resultat = get_blob(name, access=self.acces)
        except BlobNotFoundError as erreur:
            raise FileNotFoundError(name) from erreur
        return ContentFile(resultat.body, name=name)

    def delete(self, name):
        from vercel.blob.sync import delete_blob

        delete_blob(name)

    def exists(self, name):
        from vercel.blob.sync import BlobNotFoundError, head_blob

        try:
            head_blob(name)
        except BlobNotFoundError:
            return False
        return True

    def get_available_name(self, name, max_length=None):
        # Les noms contiennent déjà un identifiant unique (uuid4) : pas de requête de vérification.
        return name

    def size(self, name):
        from vercel.blob.sync import head_blob

        return head_blob(name).size

    def url(self, name):
        # Pas d'URL publique : passer par la vue `document_voir`.
        return ""
