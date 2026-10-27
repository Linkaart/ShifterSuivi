from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from garage.models import Client, Utilisateur
from garage.stockage import StockageVercelBlob


class StockageVercelBlobTests(TestCase):
    """Le stockage appelle le SDK Vercel Blob en accès privé."""

    def test_enregistrer_lire_supprimer(self):
        stockage = StockageVercelBlob()
        with mock.patch("vercel.blob.sync.put_blob", return_value=SimpleNamespace(pathname="documents/a.jpg")) as put:
            nom = stockage.save("documents/a.jpg", ContentFile(b"\xff\xd8\xff donnees", name="a.jpg"))
        self.assertEqual(nom, "documents/a.jpg")
        args, kwargs = put.call_args
        self.assertEqual((args[0], args[1]), ("documents/a.jpg", b"\xff\xd8\xff donnees"))
        self.assertEqual((kwargs["access"], kwargs["content_type"]), ("private", "image/jpeg"))

        with mock.patch("vercel.blob.sync.get_blob", return_value=SimpleNamespace(body=b"contenu")):
            self.assertEqual(stockage.open("documents/a.jpg").read(), b"contenu")

        with mock.patch("vercel.blob.sync.delete_blob") as supprimer:
            stockage.delete("documents/a.jpg")
        supprimer.assert_called_once_with("documents/a.jpg")

    def test_fichier_absent(self):
        from vercel.blob.sync import BlobNotFoundError

        with mock.patch("vercel.blob.sync.get_blob", side_effect=BlobNotFoundError()):
            with self.assertRaises(FileNotFoundError):
                StockageVercelBlob().open("documents/absent.jpg")


class PreparerDeploiementTests(TestCase):
    def test_migrations_sans_demo(self):
        sortie = StringIO()
        with mock.patch.dict("os.environ", {"SEED_DEMO": ""}):
            call_command("preparer_deploiement", stdout=sortie)
        self.assertIn("non demandée", sortie.getvalue())
        self.assertFalse(Client.objects.exists())

    def test_demo_chargee_une_seule_fois(self):
        with mock.patch.dict("os.environ", {"SEED_DEMO": "1", "DEMO_PASSWORD": "Demo-Garage-2026!"}):
            call_command("preparer_deploiement", stdout=StringIO())
            nb_clients = Client.objects.count()
            sortie = StringIO()
            call_command("preparer_deploiement", stdout=sortie)
        self.assertGreater(nb_clients, 0)
        self.assertEqual(Client.objects.count(), nb_clients)
        self.assertIn("déjà des données", sortie.getvalue())
        self.assertTrue(Utilisateur.objects.get(username="patron").check_password("Demo-Garage-2026!"))

    def test_demo_sans_mot_de_passe_refusee(self):
        with mock.patch.dict("os.environ", {"SEED_DEMO": "1", "DEMO_PASSWORD": ""}):
            with self.assertRaises(CommandError):
                call_command("preparer_deploiement", stdout=StringIO())
