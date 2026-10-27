import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from garage.models import Document, Facture, HistoriqueStatut, OrdreReparation, Utilisateur, Vehicule

from .outils import PNG_1PX, ajouter_ligne, creer_ordre, creer_utilisateur, creer_vehicule

S = OrdreReparation.Statut
MEDIA_TEST = tempfile.mkdtemp(prefix="shiftersuivi-tests-")


def tearDownModule():
    shutil.rmtree(MEDIA_TEST, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class PagesTests(TestCase):
    """Toutes les pages s'affichent avec les données de démonstration."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", mot_de_passe="atelier2026", stdout=open("/dev/null", "w"))

    def setUp(self):
        self.client.force_login(Utilisateur.objects.get(username="patron"))

    def test_connexion_obligatoire(self):
        self.client.logout()
        reponse = self.client.get(reverse("tableau_de_bord"))
        self.assertRedirects(reponse, f"{reverse('connexion')}?next=/")

    def test_pages_principales(self):
        ordre = OrdreReparation.objects.first()
        vehicule = Vehicule.objects.first()
        facture = Facture.objects.first()
        urls = [
            reverse("tableau_de_bord"),
            reverse("atelier"),
            reverse("atelier") + "?mecanicien=libre",
            reverse("ordre_list"),
            reverse("ordre_list") + "?statut=tous&q=OR",
            reverse("reception"),
            reverse("reception") + "?immat=ZZ-999-ZZ",
            reverse("reception") + f"?vehicule={vehicule.pk}",
            reverse("vehicule_list"),
            reverse("vehicule_detail", args=[vehicule.pk]),
            reverse("vehicule_modifier", args=[vehicule.pk]),
            reverse("vehicule_nouveau"),
            reverse("client_list"),
            reverse("client_detail", args=[vehicule.client.pk]),
            reverse("client_nouveau"),
            reverse("echeance_list"),
            reverse("echeance_list") + "?filtre=retard",
            reverse("echeance_nouveau"),
            reverse("facture_list"),
            reverse("facture_detail", args=[facture.pk]),
            reverse("recherche") + "?q=martin",
        ]
        urls += [reverse("ordre_detail", args=[o.pk]) for o in OrdreReparation.objects.all()]
        urls.append(reverse("ordre_modifier", args=[ordre.pk]))
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_recherche_plaque_exacte_ouvre_le_passage(self):
        ordre = OrdreReparation.objects.exclude(statut=S.RESTITUE).first()
        plaque = ordre.vehicule.immatriculation.replace("-", "").lower()
        reponse = self.client.get(reverse("recherche"), {"q": plaque})
        self.assertRedirects(reponse, ordre.get_absolute_url())


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class DroitsTests(TestCase):
    def setUp(self):
        self.meca = creer_utilisateur("meca", Utilisateur.Role.MECANICIEN)
        self.autre = creer_utilisateur("autre", Utilisateur.Role.MECANICIEN)
        self.client.force_login(self.meca)

    def test_mecanicien_sans_acces_clients_factures(self):
        for nom in ["client_list", "facture_list", "echeance_list", "reception"]:
            with self.subTest(page=nom):
                self.assertEqual(self.client.get(reverse(nom)).status_code, 403)

    def test_mecanicien_ne_change_pas_le_vehicule_d_un_autre(self):
        ordre = creer_ordre(mecanicien=self.autre)
        reponse = self.client.post(reverse("ordre_statut", args=[ordre.pk]), {"statut": S.DIAGNOSTIC})
        self.assertEqual(reponse.status_code, 403)

    def test_mecanicien_fait_avancer_son_vehicule(self):
        ordre = creer_ordre()
        self.client.post(reverse("ordre_statut", args=[ordre.pk]), {"statut": S.DIAGNOSTIC})
        ordre.refresh_from_db()
        self.assertEqual((ordre.statut, ordre.mecanicien), (S.DIAGNOSTIC, self.meca))


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class ParcoursAtelierTests(TestCase):
    def setUp(self):
        self.accueil = creer_utilisateur("accueil", Utilisateur.Role.ACCUEIL)
        self.client.force_login(self.accueil)

    def _donnees_reception(self, **extra):
        donnees = {
            "client_choix": "nouveau",
            "v-immatriculation": "gh404kl",
            "v-marque": "Peugeot",
            "v-modele": "208",
            "v-energie": "essence",
            "v-date_mise_circulation": "2022-11-15",
            "c-type_client": "particulier",
            "c-nom": "Martin",
            "c-prenom": "Julien",
            "c-telephone": "06 11 22 33 44",
            "c-adresse": "4 allée des Tilleuls",
            "c-code_postal": "57950",
            "c-ville": "Montigny-lès-Metz",
            "c-contact_prefere": "sms",
            "o-km_entree": "27400",
            "o-demande_client": "Révision des 30 000 km",
            "o-etat_entree": "Rayure pare-choc arrière",
            "o-urgence": "normale",
            "o-travaux_prevus": "Révision constructeur",
            "o-accord_immediat": "on",
            "o-accord_moyen": "signature",
        }
        donnees.update(extra)
        return donnees

    def test_reception_nouveau_client_nouveau_vehicule_avec_photo(self):
        photo = SimpleUploadedFile("pare-choc.png", PNG_1PX, content_type="image/png")
        reponse = self.client.post(reverse("reception"), {**self._donnees_reception(), "o-photos": [photo]})
        ordre = OrdreReparation.objects.get()
        self.assertRedirects(reponse, ordre.get_absolute_url())
        self.assertEqual(ordre.vehicule.immatriculation, "GH-404-KL")
        self.assertEqual(ordre.vehicule.kilometrage, 27400)
        self.assertTrue(ordre.accord_client)
        self.assertEqual(ordre.recu_par, self.accueil)
        self.assertEqual(ordre.documents.get().type_document, Document.Type.PHOTO_ENTREE)
        self.assertTrue(HistoriqueStatut.objects.filter(ordre=ordre, nouveau=S.RECU).exists())
        self.assertTrue(ordre.vehicule.echeances.filter(type="controle_technique").exists())
        # La photo est servie aux utilisateurs connectés seulement
        document = ordre.documents.get()
        self.assertEqual(self.client.get(reverse("document_voir", args=[document.pk])).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("document_voir", args=[document.pk])).status_code, 302)

    def test_faux_fichier_image_refuse(self):
        faux = SimpleUploadedFile("photo.jpg", b"<html><script>alert(1)</script></html>", content_type="image/jpeg")
        reponse = self.client.post(reverse("reception"), {**self._donnees_reception(), "o-photos": [faux]})
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "ne correspond pas à son format")
        self.assertFalse(OrdreReparation.objects.exists())

    def test_vehicule_deja_a_l_atelier(self):
        ordre = creer_ordre()
        reponse = self.client.post(
            reverse("reception"),
            {"vehicule_id": ordre.vehicule.pk, "o-km_entree": "40000", "o-demande_client": "x", "o-etat_entree": "x", "o-urgence": "normale"},
        )
        self.assertRedirects(reponse, ordre.get_absolute_url())
        self.assertEqual(OrdreReparation.objects.count(), 1)

    def test_kilometrage_inferieur_refuse(self):
        vehicule = creer_vehicule(kilometrage=50000)
        reponse = self.client.post(
            reverse("reception"),
            {"vehicule_id": vehicule.pk, "o-km_entree": "40000", "o-demande_client": "x", "o-etat_entree": "x", "o-urgence": "normale"},
        )
        self.assertContains(reponse, "Inférieur au dernier kilométrage connu")

    def test_parcours_complet_jusqu_a_la_restitution(self):
        ordre = creer_ordre()
        url = ordre.get_absolute_url()
        self.client.post(reverse("ligne_ajouter", args=[ordre.pk]), {"type_ligne": "main_oeuvre", "designation": "Vidange", "quantite": "1", "prix_unitaire_ht": "65", "taux_tva": "20"})
        self.client.post(reverse("ordre_accord", args=[ordre.pk]), {"accord_moyen": "telephone"})
        for statut in (S.EN_COURS, S.TERMINE, S.PRET):
            self.client.post(reverse("ordre_statut", args=[ordre.pk]), {"statut": statut})
        reponse = self.client.post(reverse("ordre_facturer", args=[ordre.pk]))
        facture = Facture.objects.get(ordre=ordre)
        self.assertRedirects(reponse, facture.get_absolute_url())
        self.assertEqual(str(facture.total_ttc), "78.00")
        # Facturé : les lignes ne bougent plus
        ligne = ordre.lignes.get()
        self.assertEqual(self.client.post(reverse("ligne_supprimer", args=[ordre.pk, ligne.pk])).status_code, 403)
        self.client.post(reverse("ordre_restitution", args=[ordre.pk]), {"km_sortie": str(ordre.km_entree + 5), "travaux_realises": "Vidange"})
        ordre.refresh_from_db()
        self.assertEqual(ordre.statut, S.RESTITUE)
        self.assertEqual(ordre.vehicule.kilometrage, ordre.km_entree + 5)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_paiement_facture(self):
        ordre = creer_ordre(accord_client=True, statut=S.TERMINE)
        ajouter_ligne(ordre, prix="100")
        facture = Facture.emettre(ordre)
        self.client.post(reverse("facture_paiement", args=[facture.pk]), {"montant": "120.00", "mode": "carte", "le": "2026-10-27"})
        facture.refresh_from_db()
        self.assertEqual(facture.statut_paiement, Facture.Paiement.PAYEE)
