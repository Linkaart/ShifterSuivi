from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from garage.models import (
    Echeance,
    Facture,
    HistoriqueStatut,
    OrdreReparation,
    Utilisateur,
    Vehicule,
    normaliser_immatriculation,
)

from .outils import ajouter_ligne, creer_client, creer_ordre, creer_utilisateur, creer_vehicule

S = OrdreReparation.Statut


class ImmatriculationTests(TestCase):
    def test_plaque_siv_mise_au_format(self):
        self.assertEqual(normaliser_immatriculation("ab123cd"), "AB-123-CD")
        self.assertEqual(normaliser_immatriculation(" ab 123-cd "), "AB-123-CD")

    def test_ancienne_plaque_conservee(self):
        self.assertEqual(normaliser_immatriculation("1234 ab 57"), "1234 AB 57")

    def test_doublon_refuse_meme_ecrit_autrement(self):
        vehicule = creer_vehicule(immatriculation="AB-123-CD")
        autre = Vehicule(client=vehicule.client, immatriculation="ab 123 cd", marque="Peugeot", modele="208", energie="diesel")
        with self.assertRaises(ValidationError) as erreur:
            autre.full_clean(exclude=["immat_cle"])
        self.assertIn("immatriculation", erreur.exception.message_dict)


class NumerotationTests(TestCase):
    def test_numeros_or_continus(self):
        vehicule = creer_vehicule()
        annee = timezone.localdate().year
        numeros = [creer_ordre(vehicule).numero for _ in range(3)]
        self.assertEqual(numeros, [f"OR-{annee}-0001", f"OR-{annee}-0002", f"OR-{annee}-0003"])


class MontantsTests(TestCase):
    def test_totaux_et_tva_par_taux(self):
        ordre = creer_ordre()
        ajouter_ligne(ordre, prix="79.00", quantite="2")
        ajouter_ligne(ordre, prix="10.00", taux="5.50")
        self.assertEqual(ordre.total_ht, Decimal("168.00"))
        ventilation = {v["taux"]: v["tva"] for v in ordre.ventilation_tva()}
        self.assertEqual(ventilation[Decimal("20.00")], Decimal("31.60"))
        self.assertEqual(ventilation[Decimal("5.50")], Decimal("0.55"))
        self.assertEqual(ordre.total_ttc, Decimal("200.15"))


class StatutsTests(TestCase):
    def setUp(self):
        self.accueil = creer_utilisateur("accueil", Utilisateur.Role.ACCUEIL)
        self.meca = creer_utilisateur("meca", Utilisateur.Role.MECANICIEN)
        self.autre_meca = creer_utilisateur("autre", Utilisateur.Role.MECANICIEN)
        self.ordre = creer_ordre()

    def test_saut_d_etape_refuse(self):
        with self.assertRaises(ValidationError):
            self.ordre.changer_statut(S.TERMINE, self.accueil)

    def test_reparation_exige_l_accord(self):
        self.ordre.changer_statut(S.DIAGNOSTIC, self.accueil)
        self.assertIn("accord", self.ordre.verifier_transition(S.EN_COURS, self.accueil))
        self.ordre.enregistrer_accord(OrdreReparation.MoyenAccord.TELEPHONE, self.accueil)
        self.ordre.changer_statut(S.EN_COURS, self.accueil)
        self.assertEqual(self.ordre.statut, S.EN_COURS)

    def test_accord_sur_devis_envoye_passe_a_devis_accepte(self):
        self.ordre.changer_statut(S.DEVIS_ENVOYE, self.accueil)
        self.ordre.enregistrer_accord(OrdreReparation.MoyenAccord.EMAIL, self.accueil)
        self.ordre.refresh_from_db()
        self.assertEqual(self.ordre.statut, S.DEVIS_ACCEPTE)

    def test_historique_enregistre_chaque_changement(self):
        self.ordre.changer_statut(S.DIAGNOSTIC, self.meca)
        entree = HistoriqueStatut.objects.get(ordre=self.ordre)
        self.assertEqual((entree.ancien, entree.nouveau, entree.par), (S.RECU, S.DIAGNOSTIC, self.meca))

    def test_mecanicien_prend_le_vehicule_non_attribue(self):
        self.ordre.changer_statut(S.DIAGNOSTIC, self.meca)
        self.assertEqual(self.ordre.mecanicien, self.meca)

    def test_mecanicien_limite_aux_etapes_techniques(self):
        self.assertIsNotNone(self.ordre.verifier_transition(S.DEVIS_ENVOYE, self.meca))
        self.assertNotIn(S.DEVIS_ENVOYE, self.ordre.transitions_possibles(self.meca))

    def test_mecanicien_ne_touche_pas_au_vehicule_d_un_autre(self):
        self.ordre.mecanicien = self.autre_meca
        self.ordre.save()
        self.assertIn("autre mécanicien", self.ordre.verifier_transition(S.DIAGNOSTIC, self.meca))

    def test_etape_conseillee_en_premier(self):
        self.ordre.accord_client = True
        self.assertEqual(self.ordre.etape_conseillee(), S.EN_COURS)
        self.assertEqual(self.ordre.transitions_possibles()[0], S.EN_COURS)

    def test_retard(self):
        self.ordre.fin_prevue_le = timezone.localdate() - timedelta(days=1)
        self.assertTrue(self.ordre.en_retard)
        self.ordre.statut = S.PRET
        self.assertFalse(self.ordre.en_retard)


class FactureTests(TestCase):
    def setUp(self):
        self.accueil = creer_utilisateur("accueil", Utilisateur.Role.ACCUEIL)
        self.ordre = creer_ordre(accord_client=True)
        ajouter_ligne(self.ordre, prix="100.00")

    def _terminer(self):
        for statut in (S.EN_COURS, S.TERMINE):
            self.ordre.changer_statut(statut, self.accueil)

    def test_facture_refusee_avant_la_fin_des_travaux(self):
        with self.assertRaises(ValidationError):
            Facture.emettre(self.ordre)

    def test_facture_fige_les_montants_et_se_numerote(self):
        self._terminer()
        facture = Facture.emettre(self.ordre)
        self.assertEqual(facture.numero, f"FA-{timezone.localdate().year}-0001")
        self.assertEqual((facture.total_ht, facture.total_ttc), (Decimal("100.00"), Decimal("120.00")))
        self.assertEqual(facture.client_nom, "DURAND Claire")
        with self.assertRaises(ValidationError):
            Facture.emettre(self.ordre)

    def test_paiements(self):
        self._terminer()
        facture = Facture.emettre(self.ordre)
        facture.enregistrer_paiement(Decimal("50.00"), Facture.Mode.CARTE)
        self.assertEqual(facture.statut_paiement, Facture.Paiement.PARTIELLE)
        with self.assertRaises(ValidationError):
            facture.enregistrer_paiement(Decimal("80.00"), Facture.Mode.CARTE)
        facture.enregistrer_paiement(Decimal("70.00"), Facture.Mode.ESPECES)
        self.assertEqual(facture.statut_paiement, Facture.Paiement.PAYEE)
        self.assertEqual(facture.reste_a_payer, Decimal("0"))

    def test_restitution_exige_la_facture_si_travaux(self):
        self._terminer()
        self.ordre.changer_statut(S.PRET, self.accueil)
        self.assertIsNotNone(self.ordre.verifier_transition(S.RESTITUE, self.accueil))
        Facture.emettre(self.ordre)
        self.ordre.changer_statut(S.RESTITUE, self.accueil)
        self.assertIsNotNone(self.ordre.restitue_le)

    def test_devis_refuse_rendu_sans_facture(self):
        ordre = creer_ordre(creer_vehicule(creer_client(), immatriculation="CD-456-EF"))
        ajouter_ligne(ordre)
        ordre.changer_statut(S.DEVIS_ENVOYE, self.accueil)
        ordre.changer_statut(S.PRET, self.accueil)
        with self.assertRaises(ValidationError):
            Facture.emettre(ordre)
        ordre.changer_statut(S.RESTITUE, self.accueil)
        self.assertEqual(ordre.statut, S.RESTITUE)


class ControleTechniqueTests(TestCase):
    def test_premier_ct_quatre_ans_apres_la_mise_en_circulation(self):
        vehicule = creer_vehicule(date_mise_circulation=date(2022, 6, 10))
        self.assertEqual(vehicule.prochain_ct, date(2026, 6, 10))

    def test_ct_suivant_deux_ans_apres(self):
        vehicule = creer_vehicule(date_dernier_ct=date(2025, 2, 28))
        self.assertEqual(vehicule.prochain_ct, date(2027, 2, 28))

    def test_ct_fait_planifie_le_suivant(self):
        vehicule = creer_vehicule(date_mise_circulation=date(2022, 6, 10))
        echeance = vehicule.planifier_ct()
        echeance.marquer_faite(date(2026, 6, 1))
        vehicule.refresh_from_db()
        self.assertEqual(vehicule.date_dernier_ct, date(2026, 6, 1))
        suivante = vehicule.echeances.exclude(statut=Echeance.Statut.FAITE).get()
        self.assertEqual(suivante.prevue_le, date(2028, 6, 1))
