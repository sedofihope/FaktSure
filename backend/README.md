# FaktSure Backend

## Prérequis

- Python 3.12 ou ultérieur, avec `venv`
- Chromium, pour le rendu des PDF de facture
- Pour les essais Docker : Docker Engine avec le plugin Docker Compose

## Installation

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload
```

Pour une base neuve, initialiser le schéma avec `.venv/bin/alembic upgrade head` avant le démarrage. En développement, le démarrage crée aussi les tables absentes. Après une mise à jour du code, appliquer les nouvelles migrations avec `.venv/bin/alembic upgrade head`.

Santé de l'API : `GET /api/health`. Voir [API.md](API.md) pour les identifiants UUID publics, l'authentification et le parcours document vers facture. La documentation interactive OpenAPI est accessible sur `/docs`.

Pour lancer l'extraction des documents natifs d'un lot (appels LLM facturables), utiliser `POST /api/batches/{id}/process`. L'import seul ne déclenche aucun appel LLM. La progression se consulte avec `GET /api/batches/{id}`. Un lot en échec peut être relancé avec `retry_failed=true`.

Tests : `.venv/bin/python -m pytest`. La suite compte 48 tests, vérifiés le 26 novembre 2026 ; elle crée des bases SQLite jetables et simule le fournisseur LLM et le stockage, sans clé ni service externe.

## Essai Docker avec PostgreSQL et Chromium

Cet environnement local est isolé de `backend/faktsure.db` : il démarre une base PostgreSQL neuve dans un volume Docker et n'importe ni ne modifie les données SQLite existantes.

```bash
cp backend/.env.example backend/.env
# Définir au minimum un JWT_SECRET unique d'au moins 32 caractères dans backend/.env.
docker compose up --build -d
docker compose ps
```

L'API répond sur `http://localhost:8000` et sa santé sur `http://localhost:8000/api/health`. Si ce port est déjà occupé, définir `FAKTSURE_API_PORT=8081` avant `docker compose up`, puis ouvrir `http://localhost:8081`. Le premier démarrage applique automatiquement les migrations Alembic. Créer l'administrateur dans le conteneur avec `docker compose exec api python /app/scripts/create_admin.py`.

Les volumes `postgres_data` et `document_data` persistent lors d'un redémarrage. `docker compose down` les conserve ; `docker compose down -v` les supprime définitivement. Le mot de passe PostgreSQL défini dans `compose.yaml` est réservé à cet essai local : ne pas déployer le service `db` ni ces identifiants en production.

Pour arrêter l'essai sans supprimer les données : `docker compose down`.

## Déploiement d'une image Docker

Le fichier `backend/Dockerfile` installe Chromium, les dépendances système et les dépendances Python, s'exécute en utilisateur non-root et applique `alembic upgrade head` avant de lancer Uvicorn. Un hébergeur qui détecte un Dockerfile à la racine peut utiliser `backend/Dockerfile` comme chemin Dockerfile et la racine du dépôt comme contexte de build.

Configurer les variables d'environnement depuis le gestionnaire de secrets de l'hébergeur, au minimum :

- `APP_ENV=production`
- `JWT_SECRET` : valeur unique et aléatoire d'au moins 32 caractères
- `DATABASE_URL` : URL PostgreSQL SQLAlchemy, au format `postgresql+psycopg://...`
- `R2_ENABLED=true`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`
- `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium`

Renseigner aussi la configuration LLM et les variables `ISSUER_*` selon les fonctionnalités activées. Ne pas copier le fichier `.env` local dans l'image ni utiliser les identifiants locaux de Compose. Le port `PORT` fourni par la plateforme est pris en charge ; à défaut, le conteneur écoute sur `8000`.

Pour autoriser un frontend hébergé sur un autre domaine, définir `CORS_ALLOWED_ORIGINS` avec les origines exactes, séparées par virgules (par exemple `https://app.example.com`). Le réglage est fermé par défaut ; ni chemin, ni barre oblique finale. L'authentification utilise un jeton Bearer, pas des cookies.

Les migrations s'exécutent au démarrage du conteneur : commencer avec une seule instance API. Le disque local de la plateforme peut être éphémère ; R2 est nécessaire pour les fichiers métier persistants. Cette image ne réalise pas la migration des données SQLite vers PostgreSQL : sauvegarder et migrer les données séparément, après le choix de l'hébergeur et du fournisseur PostgreSQL.

### Démo temporaire sur Railway avec SQLite

Pour la démonstration, Railway exécute l'image Docker ci-dessus avec SQLite sur un volume persistant. Monter un volume sur `/data` et configurer `APP_ENV=production`, `DATABASE_URL=sqlite:////data/faktsure.db`, `STORAGE_ROOT=/data/documents`, `JWT_SECRET` (unique, aléatoire, d'au moins 32 caractères) et `MAX_DOCUMENT_CONCURRENCY=1`. Le Dockerfile définit déjà `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium`. Définir `RAILWAY_DOCKERFILE_PATH=backend/Dockerfile` et garder la racine du dépôt comme contexte de build.

Le volume Railway est monté avec des permissions root ; l'image utilise par défaut un utilisateur non-root. Pour cette démonstration seulement, `RAILWAY_RUN_UID=0` permet au conteneur d'écrire sur le volume, au prix d'une isolation réduite. Garder une seule instance : les tâches de traitement vivent en mémoire et SQLite n'est pas configuré pour plusieurs instances. Le plan Railway Free limite chaque service à 512 Mo de RAM et le volume à 0,5 Go ; vérifier la consommation avant une démonstration réelle et ne pas traiter de données importantes sans sauvegardes.

Le fichier SQLite et les documents conservés sous `/data` persistent sur le volume. Les pièces PDF des factures émises doivent néanmoins être stockées dans R2 : activer `R2_ENABLED=true` et configurer les identifiants R2 dans les variables Railway. Les variables sensibles restent dans le gestionnaire de variables Railway ; ne pas copier un `.env` local complet ni le committer.

## LLM

Sélectionner `LLM_PROVIDER=gemini|groq|cloudflare` et renseigner les variables correspondantes dans `.env` : `GEMINI_API_KEY` avec `GEMINI_MODEL` (`gemini-3.5-flash-lite` par défaut), `GROQ_API_KEY` avec `GROQ_MODEL` (`openai/gpt-oss-120b` par défaut), ou `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` avec `CLOUDFLARE_MODEL` (`@cf/openai/gpt-oss-120b` par défaut). Pour la démonstration du hackathon, l'équipe a utilisé `GROQ_MODEL=openai/gpt-oss-120b`. Le fournisseur et le modèle peuvent aussi être changés à chaud par un administrateur via `PUT /api/settings/ai`, sans redémarrage. Aucun fournisseur fictif n'est utilisé en production.

## Stockage Cloudflare R2

Le stockage local reste actif comme copie de secours. Pour activer R2, créer un bucket et une clé API S3 R2 limitée à ce bucket, puis renseigner `R2_ENABLED=true`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID` et `R2_SECRET_ACCESS_KEY` dans `.env`. L'identifiant de compte et le nom du bucket seuls ne suffisent pas à s'authentifier. Les opérations R2 en échec basculent sur la copie locale et sont journalisées.

## Rendu des PDF

Les PDF de factures sont rendus depuis le modèle HTML/CSS `app/templates/invoices/facture.html` avec les styles et polices FaktSure sous `app/static/invoice/`. Le backend appelle Chromium en mode headless ; installer Chromium dans l'image de déploiement, ou définir `CHROMIUM_EXECUTABLE_PATH` vers son exécutable. Les polices Inter, Space Grotesk et JetBrains Mono sont embarquées localement avec leurs licences SIL Open Font License : aucun accès réseau n'est requis lors du rendu.

Les PDF de factures sont des pièces métier persistantes : ils sont écrits dans R2 avant que l'émission soit validée en base. Si R2 n'est pas configuré ou indisponible, l'émission est refusée (`503`) plutôt que de conserver uniquement un PDF local. Une copie locale miroir est également gardée lorsque possible. `GET /api/invoices/{invoice_id}/pdf` télécharge le PDF stocké, vérifie son SHA-256 et permet de le retélécharger ; les PDF existants sont régénérés au premier téléchargement lorsqu'une nouvelle version du modèle est déployée. Un brouillon porte une étiquette dédiée et un filigrane de brouillon sur chaque page ; la facture émise porte le numéro définitif.

## Configuration administrateur

Les administrateurs disposent de `GET /api/settings` et des mises à jour `PUT /api/settings/processing`, `/ai`, `/storage` et `/issuer`. Les secrets restent dans l'environnement et ne sont jamais retournés par l'API. Les informations légales de l'émetteur sont initialisées par les variables `ISSUER_*`, puis modifiables par l'administration ; ces valeurs sont persistées en base et auditées.

## Règles financières

Les montants sont calculés en `Decimal` et arrondis au centième avec la règle HALF_UP. Une facture ne peut être créée que pour un document revu (`READY`) et ne peut être validée qu'en l'absence d'anomalie `BLOCKER`. La formule vérifiée est `grand_total = subtotal - discount_total + tax_total`.

## Utilisateurs

Créer le premier administrateur par saisie interactive, sans identifiant par défaut :

```bash
.venv/bin/python ../scripts/create_admin.py
```

Les comptes et référentiels fictifs de démonstration peuvent être créés en développement avec un mot de passe fourni hors du dépôt :

```bash
export DEMO_PASSWORD='choose-a-unique-password-of-at-least-12-characters'
.venv/bin/python ../scripts/seed_demo.py
unset DEMO_PASSWORD
```

## Migrations existantes

Le dépôt contient sept migrations Alembic, dans l'ordre : schéma initial (`bf4d2aa5e553`), UUID publics (`a19c7d2ef431`), RCCM client (`c72e4a91d630`), modalités de paiement et réglages runtime (`f0a73c91be42`), stockage PDF des factures (`d4b6a8c219ef`), version de format des PDF (`e29c6f4a1b73`) et TVA globale au niveau de la facture (`8b7c1d9a42e6`).

Pour une base existante déjà créée par une version antérieure, effectuer et vérifier une sauvegarde avant toute opération. Si le schéma correspond exactement à la migration initiale, enregistrer uniquement cette révision comme déjà appliquée, puis appliquer les migrations restantes :

```bash
.venv/bin/alembic stamp bf4d2aa5e553
.venv/bin/alembic upgrade head
```

Ne pas utiliser `stamp head` sur une base sans UUID publics : cela marquerait aussi la migration UUID comme appliquée, sans ajouter ses colonnes. Si le schéma ne correspond pas à la migration initiale, préparer une migration adaptée au lieu de `stamp`. En production, l'application ne crée pas automatiquement le schéma.
