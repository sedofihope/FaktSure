# Livrable 3 — README d'installation et de reproduction

Ce guide est destiné au jury. Il décrit l'installation, la configuration, le lancement, les comptes de démonstration et la reproduction des scénarios avec le code actuellement présent dans le dépôt. Il ne contient aucun secret ni mot de passe de démonstration par défaut.

## 1. État et version de référence

- Projet : FaktSure, backend d'automatisation de la facturation.
- Version applicative vérifiée lors de la préparation de ce guide : commit `aba680b` (`feat: add issuer settings and VAT modes`).
- Pour identifier l'exemplaire exact remis au jury, relever le SHA complet après gel du dépôt :

```bash
git rev-parse HEAD
git status --short
```

Le dossier de livraison devrait être gelé sur un commit propre, avec la sortie de ces commandes consignée dans le procès-verbal ou le rapport. Le dépôt contient actuellement le backend; `frontend/` est vide hormis `.gitkeep`. Swagger constitue l'interface d'exploration disponible, pas une interface de démonstration métier complète.

## 2. Prérequis

- Linux, macOS ou Windows avec WSL2.
- Python 3.12 ou ultérieur.
- Chromium pour rendre les factures PDF.
- Accès réseau et une clé valide pour le fournisseur LLM activé si l'on souhaite exécuter une extraction réelle.
- Pour le mode R2 : un compte Cloudflare, un bucket et des credentials S3 limités à ce bucket.
- Docker Engine + Compose uniquement pour l'environnement PostgreSQL conteneurisé.

L'API peut démarrer sans clé LLM, mais l'extraction échouera tant qu'aucun fournisseur ne sera configuré. Les tests utilisent des fournisseurs et stockages simulés; ils ne nécessitent ni clé externe ni compte R2 réel.

## 3. Installation et configuration locale

Depuis la racine du dépôt :

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Installer Chromium avec le gestionnaire de paquets de l'OS, puis régler `CHROMIUM_EXECUTABLE_PATH` vers son exécutable. Exemple courant sous Linux : `/usr/bin/chromium`.

La configuration de développement utilise SQLite (`sqlite:///./faktsure.db`) et `APP_ENV=development`. Les paramètres sont chargés depuis les variables d'environnement et `.env`; une variable d'environnement exportée prévaut sur le fichier. Les réglages sensibles doivent rester hors Git.

Paramètres selon le scénario :

| Variable | Quand la renseigner |
|---|---|
| `JWT_SECRET` | Toujours définir une valeur aléatoire unique en production (minimum 32 caractères). Ne jamais réutiliser un secret de démonstration. |
| `LLM_PROVIDER` | `gemini`, `groq` ou `cloudflare`; le défaut de code est `gemini`. |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Requis pour Gemini; modèle par défaut dans le code : `gemini-2.0-flash`. |
| `GROQ_API_KEY`, `GROQ_MODEL` | Requis pour Groq; modèle par défaut dans le code : `llama-3.3-70b-versatile`. |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_MODEL` | Requis pour Cloudflare Workers AI; aucun modèle Cloudflare n'est présélectionné. |
| `R2_ENABLED`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Requis pour R2. L'émission d'une facture est refusée si son PDF essentiel ne peut pas être écrit dans R2. |
| `CORS_ALLOWED_ORIGINS` | Origines exactes du frontend, séparées par des virgules; vide par défaut. Ne pas mettre de wildcard, chemin ou slash final. |
| `ISSUER_*` | Valeurs initiales de la société émettrice; un ADMIN peut ensuite mettre à jour ces informations dans l'API. |
| `STORAGE_ROOT` | Répertoire de fichiers local; défaut `storage/documents`. |
| `MAX_UPLOAD_SIZE_MB` | Taille limite d'un fichier; défaut 20 Mo. |

Appliquer le schéma et démarrer :

```bash
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

Adresses locales : API `http://127.0.0.1:8000`, Swagger `http://127.0.0.1:8000/docs`, OpenAPI `http://127.0.0.1:8000/openapi.json`, santé `http://127.0.0.1:8000/api/health`.

## 4. Comptes de démonstration

Le dépôt ne fournit **aucun mot de passe prédéfini**. Pour une base locale de développement uniquement, le script `scripts/seed_demo.py` crée les trois comptes et des données explicitement fictives :

| Rôle | Adresse |
|---|---|
| Administrateur | `admin@demo.faktsure.com` |
| Comptable | `accountant@demo.faktsure.com` |
| Validateur | `validator@demo.faktsure.com` |

Les trois comptes partagent le mot de passe choisi au moment du seed via `DEMO_PASSWORD`; le script exige au moins 12 caractères. Ne pas utiliser ces identités ou données pour de vraies factures.

Exécuter le seed depuis `backend/` après avoir lancé le schéma. Saisir le mot de passe sans l'inscrire dans le dépôt ou l'historique :

```bash
read -s -p "Mot de passe fictif pour les comptes de démonstration : " DEMO_PASSWORD
printf '\n'
export DEMO_PASSWORD
python ../scripts/seed_demo.py
unset DEMO_PASSWORD
```

Ce seed est idempotent pour ses données connues, mais **ce n'est pas un outil de remise à zéro** : il n'efface ni documents, ni factures, ni événements d'audit. Le mot de passe des comptes déjà créés n'est pas remplacé par le seed.

Pour créer un administrateur nominatif plutôt que les comptes fictifs, utiliser `.venv/bin/python ../scripts/create_admin.py`; nom, adresse et mot de passe sont saisis interactivement.

## 5. Reproduire le parcours de démonstration

1. Se connecter avec l'un des comptes seedés sur `POST /api/auth/login` dans Swagger; cliquer ensuite sur **Authorize** et fournir `Bearer <access_token>`.
2. Créer un lot avec `POST /api/batches`.
3. Importer un PDF natif contenant du texte avec `POST /api/batches/{batch_id}/documents` (formulaire multipart, champ `files`). Le fichier de test d'équipe est généré dans les tests; aucun échantillon de facture réelle n'est livré.
4. Lancer `POST /api/documents/{document_id}/extract`, ou `POST /api/batches/{batch_id}/process`. L'appel d'extraction utilise un service LLM externe et peut être facturable.
5. Examiner les champs et anomalies; corriger si nécessaire avec `PUT /api/documents/{document_id}/fields`; confirmer la revue avec `POST /api/documents/{document_id}/review`.
6. Créer le brouillon avec `POST /api/invoices`. Choisir la TVA par ligne ou une règle de TVA globale à la racine; ne pas mélanger les deux.
7. Avec `ADMIN` ou `VALIDATOR`, appeler `POST /api/invoices/{invoice_id}/validate`. R2 doit être configuré et disponible pour que l'émission réussisse.
8. Télécharger le résultat avec `GET /api/invoices/{invoice_id}/pdf`.

Seuls les PDF natifs textuels sont actuellement extraits. Les images et PDF scannés/mixés sont détectés et importables, mais l'OCR n'est pas implémenté et leur extraction métier n'est pas disponible.

## 6. Tests automatisés et scénario de reprise

Depuis la racine du dépôt :

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

Résultat vérifié le 26 novembre 2026 pour le commit applicatif `aba680b` : **48 tests passent**. La suite comprend le parcours document→facture avec LLM et stockage simulés, les calculs, les rôles, les réglages, les imports, la documentation et les cas de reprise.

Pour reproduire spécifiquement une interruption :

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/unit/test_batch_processing.py::test_recovery_requeues_interrupted_extraction -q
```

Ce test crée une base SQLite isolée, place un document dans l'état `EXTRACTING` (état pouvant rester après arrêt du processus), appelle la routine de récupération et vérifie que le document revient dans la file `QUEUED`. Au démarrage, l'application réexécute les lots restés en file. Ce test vérifie la logique applicative; il ne constitue pas un essai de panne forcée du service Railway ni une garantie de reprise d'un appel fournisseur en cours.

Pour observer un redémarrage réel, utiliser une instance **locale de test et une base jetable**, jamais la base du service ou des factures réelles. Préparer un lot non sensible et un fournisseur de test contrôlé, arrêter le processus pendant une extraction, puis redémarrer l'API avec la même base. Vérifier les logs, l'état du lot et celui du document. Si l'appel LLM s'était terminé avant l'arrêt mais que la transaction n'avait pas persisté, le traitement peut être rejoué; aucun mécanisme d'idempotence fournisseur ou de file externe ne garantit une exécution exactement une fois.

### Réinitialisation de la démonstration locale

La manière la plus sûre de recommencer est de choisir dès le départ une base explicitement jetable, distincte de toute base personnelle ou déployée :

```bash
cd backend
export DATABASE_URL=sqlite:////tmp/faktsure-hackathon-demo.db
export STORAGE_ROOT=/tmp/faktsure-hackathon-demo-files
.venv/bin/alembic upgrade head
```

Après avoir arrêté l'API et vérifié que `DATABASE_URL` et `STORAGE_ROOT` pointent bien vers ces chemins temporaires, supprimer **uniquement** `/tmp/faktsure-hackathon-demo.db` et `/tmp/faktsure-hackathon-demo-files`, puis rejouer les commandes d'initialisation et de seed. Cette opération détruit les données de démonstration correspondantes. Ne jamais appliquer cette procédure à une base ou un stockage contenant des données utiles. Pour Compose, `docker compose down -v` supprime irréversiblement les volumes PostgreSQL et documents : à réserver à un environnement local jetable après sauvegarde ou renoncement explicite aux données.

## 7. Essai Docker local

Depuis la racine :

```bash
cp backend/.env.example backend/.env
# Définir les secrets de développement dans backend/.env, sans les committer.
docker compose up --build -d
docker compose ps
curl http://127.0.0.1:8000/api/health
```

Compose crée une base PostgreSQL 17 et les volumes locaux. Les migrations sont appliquées au démarrage. Pour le seed de développement, il faut exécuter le script depuis un environnement Python local configuré sur la même base ou ajouter explicitement le script au conteneur de développement; l'image de démonstration de production ne copie volontairement que `create_admin.py`.

## 8. Dépendances, modèles et composants préexistants

Les dépendances Python de premier niveau sont déclarées dans `backend/requirements.txt`; leurs versions sont des plages, pas un verrouillage complet. Les licences indiquées ci-dessous sont celles des projets amont, à confirmer sur les distributions exactes retenues avant diffusion :

| Dépendances principales | Usage | Licence amont usuelle |
|---|---|---|
| FastAPI, Uvicorn | API HTTP et serveur ASGI | MIT / BSD-3-Clause |
| SQLAlchemy, Alembic, psycopg | ORM, migrations, accès PostgreSQL | MIT / LGPL-3.0 pour Psycopg 3 |
| Pydantic, pydantic-settings, email-validator | Validation et configuration | MIT / CC0-1.0 |
| python-jose, bcrypt, passlib | JWT et hash de mots de passe | MIT / Apache-2.0 / BSD-3-Clause |
| PyMuPDF | Lecture et extraction des PDF | **AGPL-3.0-or-later ou licence commerciale** |
| Jinja2, openpyxl | Template PDF et import XLSX | BSD-3-Clause / MIT |
| boto3 | Accès S3/R2 | Apache-2.0 |
| httpx, python-multipart | Appels LLM et upload HTTP | BSD-3-Clause / Apache-2.0 |
| pytest | Tests | MIT |

PyMuPDF est un point de conformité majeur : avant une remise publique ou une exploitation propriétaire, vérifier si l'usage respecte l'AGPL ou obtenir la licence commerciale appropriée. Les dépendances transitives ne sont pas toutes listées dans le tableau; produire un SBOM et figer les versions exactes avant la remise finale.

Les modèles distants disponibles sont configurés par environnement : Gemini (`gemini-2.0-flash` par défaut), Groq (`llama-3.3-70b-versatile` par défaut) ou un identifiant Workers AI configuré par `CLOUDFLARE_MODEL`. Aucun poids de modèle n'est livré dans le dépôt. Les conditions d'utilisation, licences et disponibilités dépendent de l'API et du modèle précis choisis; consigner l'identifiant effectif au gel.

Les polices embarquées dans le PDF — Inter, Space Grotesk et JetBrains Mono — incluent chacune leur texte SIL Open Font License 1.1 dans `backend/app/static/invoice/fonts/`. Les bibliothèques et modèles préexistants ne sont pas les auteurs du code métier FaktSure.

Le fichier racine `LICENSE` est vide au moment de ce guide : la licence du code original FaktSure n'est donc **pas encore déclarée**. Il faut choisir et ajouter une licence avant de présenter la licence du dépôt comme déterminée.

## 9. Données et secrets

Les données seedées sont synthétiques. N'utiliser aucun document client, identifiant fiscal, coordonnées personnelles ou secret réel dans les tests, captures vidéo ou documents remis au jury. Les clés API et `JWT_SECRET` se fournissent par variables d'environnement ou gestionnaire de secrets et ne figurent jamais dans le dépôt.
