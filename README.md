# ShifterSuivi

Application web de suivi des véhicules pour un garage : chaque voiture est suivie de la réception à la remise des clés, avec l'ordre de réparation, le devis, l'accord du client, les photos, la facture et les rappels d'entretien.

Django 5.2, rendu serveur, aucune dépendance front (CSS et JS maison, polices Barlow auto-hébergées).

## Ce que fait l'application

| Écran | Rôle |
| --- | --- |
| Tableau de bord | Charge de l'atelier par étape, véhicules en retard, prêts à rendre, en attente, échéances à 30 jours, chiffres du mois (patron) |
| Atelier | Tableau en 4 colonnes (Arrivées, Devis, Sur le pont, Sortie), un bouton pour passer chaque voiture à l'étape suivante |
| Nouvelle réception | Recherche par plaque ; si la voiture est inconnue, création du véhicule et du client sur le même écran, état d'entrée et photos |
| Ordre de réparation | 9 étapes, demande et état d'entrée, diagnostic, lignes pièces et main-d'œuvre (devis), accord du client, photos et documents, facture, restitution, historique |
| Véhicules / Clients | Fiches avec carte grise, passages, factures, prochain contrôle technique |
| Échéances | Contrôles techniques (planifiés automatiquement : 4 ans puis tous les 2 ans) et entretiens, rappels envoyés |
| Factures | Numérotation continue FA-AAAA-NNNN, montants figés, paiements partiels, impression ou PDF depuis le navigateur |

### Rôles

- **Patron** : tout, y compris le chiffre d'affaires et la gestion des comptes (`/admin/`).
- **Accueil** : réception, clients, devis, accords, factures, échéances.
- **Mécanicien** : atelier, diagnostic, lignes, photos et étapes techniques de ses véhicules (ou des véhicules non attribués).

### Règles métier intégrées

- Les étapes suivent un chemin défini : impossible de sauter de « Reçu » à « Terminé ».
- Réparation, attente de pièces et fin de travaux exigent l'accord du client enregistré (date et moyen).
- Une voiture déjà à l'atelier ne peut pas être réceptionnée une deuxième fois.
- Le kilométrage d'entrée ne peut pas être inférieur au dernier connu.
- Une facture fige les montants : les lignes de l'OR ne sont plus modifiables et une facture ne se supprime pas.
- Un véhicule réparé ne sort qu'une fois facturé ; un devis refusé se rend sans facture.
- Les photos et documents ne sont jamais publics : ils passent par une vue réservée aux utilisateurs connectés, et leur contenu réel est vérifié (pas seulement l'extension).

## Installation

Prérequis : Python 3.11 ou plus récent.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # puis compléter les infos du garage
python manage.py migrate
```

### Avec des données de démonstration

```bash
pip install Pillow                 # facultatif : photos de démonstration
python manage.py seed_demo
python manage.py runserver
```

Ouvrez http://127.0.0.1:8000 et connectez-vous avec `patron`, `accueil`, `yanis`, `thomas` ou `lucas`, mot de passe `atelier2026`.

`python manage.py seed_demo --reinitialiser` efface les données du garage et recrée la démonstration.

### Sans démonstration (vrai garage)

```bash
python manage.py createsuperuser   # le compte du patron
python manage.py runserver
```

Dans `/admin/`, donnez le rôle « Patron » à ce compte, puis créez les comptes de l'accueil et des mécaniciens.

## Tests

```bash
DJANGO_DEBUG=1 python manage.py test garage
```

34 tests : immatriculations, numérotation, TVA par taux, étapes et droits par rôle, factures et paiements, contrôle technique, parcours complet de la réception à la restitution, refus d'un faux fichier image, accès protégé aux documents.

## Mise en production

1. `.env` : `DJANGO_DEBUG=0`, une `DJANGO_SECRET_KEY` générée, `DJANGO_ALLOWED_HOSTS` et `DJANGO_CSRF_TRUSTED_ORIGINS` avec le domaine, et les informations du garage (`GARAGE_*`, affichées sur les factures).
2. PostgreSQL conseillé : `pip install "psycopg[binary]"` et `DB_ENGINE=postgresql` + `DB_*`.
3. `python manage.py collectstatic` (fichiers servis par WhiteNoise), `python manage.py migrate`.
4. Lancer avec `gunicorn config.wsgi --bind 0.0.0.0:8000` derrière un proxy HTTPS (`DJANGO_BEHIND_PROXY=1`, et selon l'hébergement `DJANGO_SSL_REDIRECT=1`, `DJANGO_HSTS_SECONDS`).
5. Sauvegarder la base **et** le dossier `media/` (photos, cartes grises, OR signés).

Les factures et ordres de réparation sont des pièces commerciales à conserver au moins 10 ans.

## Structure

```
config/                 réglages, URL racine, WSGI
garage/models.py        clients, véhicules, OR, lignes, historique, documents, factures, échéances
garage/views/           une vue par écran (tableau, ordres, véhicules, clients, échéances, factures)
garage/forms.py         formulaires et contrôle des fichiers envoyés
garage/permissions.py   droits par rôle
garage/management/commands/seed_demo.py
garage/tests/           tests automatisés
templates/              gabarits HTML
static/                 CSS, JS, polices, icône
```

## Limites connues

- Pas d'envoi automatique de SMS ou d'e-mails : le rappel est noté comme envoyé, l'envoi se fait à la main.
- Le PDF de facture passe par l'impression du navigateur (« Enregistrer en PDF »).
- Pas de signature électronique de l'OR : on photographie l'OR signé et on l'ajoute aux documents.
- Les mentions de facture (SIRET, TVA, pénalités de retard pour les professionnels) sont à faire valider par le comptable du garage.
