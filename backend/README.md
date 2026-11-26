# FaktSure Backend

## Prérequis

- Python 3.12+
- venv

Pour les essais Docker : Docker Engine avec le plugin Docker Compose.

## Installation

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload
```

Pour une base neuve, initialisez le schéma par `.venv/bin/alembic upgrade head` avant le démarrage. En développement, le démarrage crée également les tables absentes.
Après une mise à jour du code, appliquez les nouvelles migrations avec `.venv/bin/alembic upgrade head` ; cela ajoute notamment le champ facultatif RCCM aux clients existants sans modifier leurs données.

API de santé: `GET /api/health`.
Voir [API.md](API.md) pour les identifiants UUID publics, l'authentification et le parcours document-vers-facture. La documentation interactive OpenAPI est accessible sur `/docs`.
Pour lancer l'extraction des documents natifs d'un lot (appels LLM facturables), utiliser `POST /api/batches/{id}/process`. L'import seul ne déclenche pas d'appel LLM. La progression se consulte avec `GET /api/batches/{id}`. Un lot en échec peut être relancé avec `retry_failed=true`.

Tests: `.venv/bin/python -m pytest`.

## Essai Docker avec PostgreSQL et Chromium

Cet environnement local est isolé de `backend/faktsure.db` : il démarre une base PostgreSQL neuve dans un volume Docker et n'importe ni ne modifie les données SQLite existantes.

```bash
cp backend/.env.example backend/.env
# Définir au minimum un JWT_SECRET unique d'au moins 32 caractères dans backend/.env.
docker compose up --build -d
docker compose ps
```

L'API est disponible sur `http://localhost:8000` et sa santé sur `http://localhost:8000/api/health`. Si ce port est déjà utilisé, définir `FAKTSURE_API_PORT=8081` avant `docker compose up`, puis ouvrir `http://localhost:8081`. Le premier démarrage applique automatiquement les migrations Alembic. Créez l'administrateur dans le conteneur avec `docker compose exec api python /app/scripts/create_admin.py`.

Les volumes `postgres_data` et `document_data` persistent lors d'un redémarrage. `docker compose down` les conserve ; `docker compose down -v` les supprime définitivement. Le mot de passe PostgreSQL défini dans `compose.yaml` est réservé à cet essai local : ne déployez pas le service `db` ni ces identifiants en production.

Pour arrêter l'essai sans supprimer les données : `docker compose down`.

## Déploiement d'une image Docker

Le fichier `backend/Dockerfile` installe Chromium, les dépendances système nécessaires et les dépendances Python, exécute en utilisateur non-root et applique `alembic upgrade head` avant de lancer Uvicorn. Un hébergeur qui détecte un Dockerfile à la racine peut utiliser `backend/Dockerfile` comme chemin Dockerfile et la racine du dépôt comme contexte de build.

Configurer les variables d'environnement depuis le gestionnaire de secrets de l'hébergeur, au minimum :

- `APP_ENV=production`
- `JWT_SECRET` : valeur unique et aléatoire d'au moins 32 caractères
- `DATABASE_URL` : URL PostgreSQL SQLAlchemy, au format `postgresql+psycopg://...`
- `R2_ENABLED=true`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`
- `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium`

Renseigner également la configuration LLM et `ISSUER_*` selon les fonctionnalités activées. Ne pas copier le fichier `.env` local dans l'image ni utiliser les identifiants locaux de Compose. Le port `PORT` fourni par la plateforme est pris en charge ; à défaut, le conteneur écoute sur `8000`.

Les migrations sont exécutées au démarrage du conteneur : commencer avec une seule instance API. Le disque local de la plateforme peut être éphémère ; R2 est nécessaire pour les fichiers métier persistants. Cette image ne réalise pas la migration des données SQLite vers PostgreSQL. Sauvegarder et migrer les données séparément après avoir choisi l'hébergeur et le fournisseur PostgreSQL.

### Essai gratuit Render + Neon

Le Blueprint [`render.yaml`](../render.yaml) configure l'API sur Render Free avec l'image Docker, Chromium et le health check. Créer d'abord une base PostgreSQL Neon Free, puis créer le service Render depuis le Blueprint et fournir `DATABASE_URL` lorsque Render le demande. Utiliser une URL PostgreSQL Neon avec le dialecte SQLAlchemy `postgresql+psycopg://` et TLS (`sslmode=require`); garder cette URL dans les variables secrètes Render, jamais dans Git ou le chat. Le Blueprint génère `JWT_SECRET` automatiquement.

Render Free fournit 512 Mo de RAM, met le service en veille après 15 minutes sans trafic et possède un système de fichiers éphémère. Le premier appel après la veille peut attendre environ une minute. `R2_ENABLED=false` est volontaire pour le test initial : les documents stockés localement pourront disparaître lors d'un redémarrage, d'une veille ou d'un redéploiement. Configurer R2 avant d'y conserver des documents ou PDF importants. Ne pas utiliser cette offre gratuite en production.

La limite mémoire a été vérifiée localement avec l'image Docker : l'API et un rendu PDF Chromium simple ont coexisté sous 512 Mo (pic mesuré d'environ 379 Mo). Le flux complet de génération de facture sur Render Free reste à vérifier; sa marge mémoire est limitée. CORS n'est pas encore configuré : l'origine exacte du frontend devra être ajoutée à l'application avant qu'un navigateur hébergé sur un autre domaine puisse appeler l'API.

Ne pas choisir le Postgres gratuit Render pour conserver les données du prototype : il est supprimé après 30 jours. Neon Free n'a pas cette expiration, mais suspend son calcul après cinq minutes d'inactivité et offre 1 Go de stockage par projet.

## LLM

Sélectionner `LLM_PROVIDER=gemini|groq|cloudflare` et renseigner les variables correspondantes dans `.env`. Aucun fournisseur fictif n'est utilisé en production.

## Stockage Cloudflare R2

Le stockage local reste actif comme copie de secours. Pour activer R2, créer un bucket et une clé API S3 R2 limitée à ce bucket, puis renseigner `R2_ENABLED=true`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID` et `R2_SECRET_ACCESS_KEY` dans `.env`. L'identifiant de compte et le nom du bucket seuls ne suffisent pas à s'authentifier. Les opérations R2 en échec basculent sur la copie locale et sont journalisées.

Les PDF de factures sont rendus depuis le template HTML/CSS `app/templates/invoices/facture.html` avec les styles et polices FaktSure sous `app/static/invoice/`. Le backend appelle Chromium en mode headless ; installez Chromium dans l'image de déploiement, ou définissez `CHROMIUM_EXECUTABLE_PATH` vers son exécutable. Les polices Inter, Space Grotesk et JetBrains Mono sont embarquées localement avec leurs licences : aucun accès réseau n'est requis lors du rendu.

Les PDF de factures sont des pièces métier persistantes : ils sont écrits dans R2 avant que l'émission soit validée en base. Si R2 n'est pas configuré ou indisponible, l'émission est refusée (`503`) plutôt que de conserver uniquement un PDF local. Une copie locale miroir est également gardée lorsque possible. `GET /api/invoices/{invoice_id}/pdf` télécharge le PDF stocké, vérifie son SHA-256 et permet de le retélécharger ; les PDF existants sont régénérés au premier téléchargement lorsqu'une nouvelle version du template est déployée. Les brouillons portent le statut ambre et le filigrane « BROUILLON — NON ÉMISE ».

## Configuration administrateur

Les administrateurs disposent de `GET /api/settings` et des mises à jour `PUT /api/settings/processing`, `/ai` et `/storage`. Les secrets restent dans l'environnement et ne sont jamais retournés par l'API. Les informations légales de l'émetteur peuvent être configurées avec les variables `ISSUER_*`.

## Règles financières

Les montants sont calculés en `Decimal` et arrondis au centième avec la règle HALF_UP. Une facture ne peut être créée que pour un document revu (`READY`) et ne peut être validée qu'en l’absence d’anomalie `BLOCKER`.

## Utilisateurs

Créez le premier administrateur par saisie interactive, sans identifiant par défaut:

```bash
.venv/bin/python ../scripts/create_admin.py
```

Les comptes et référentiels fictifs de démonstration peuvent être créés en développement avec un mot de passe fourni hors du dépôt:

```bash
export DEMO_PASSWORD='choose-a-unique-password-of-at-least-12-characters'
.venv/bin/python ../scripts/seed_demo.py
unset DEMO_PASSWORD
```

## Migrations existantes

Pour une base existante déjà créée par une version antérieure, effectuer et vérifier une sauvegarde avant toute opération. Si le schéma correspond exactement à la migration initiale, enregistrer uniquement cette révision comme déjà appliquée, puis appliquer les migrations restantes:

```bash
.venv/bin/alembic stamp bf4d2aa5e553
.venv/bin/alembic upgrade head
```

Ne pas utiliser `stamp head` pour une base sans UUID publics : cela marquerait aussi la migration UUID comme appliquée sans ajouter ses colonnes. Si le schéma ne correspond pas à la migration initiale, préparer une migration adaptée au lieu d'utiliser `stamp`. En production, l'application ne crée pas automatiquement le schéma.
