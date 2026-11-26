# Livrable 3 : README d'installation et de reproduction

> **FaktSure** : plateforme d'automatisation de la facturation (Hackathon BWAI 2026).
> Ce guide est décrit : installation, configuration, comptes de démonstration, parcours de reproduction, réinitialisation et reprise après interruption. Il décrit donc l'état réel du dépôt : **backend FastAPI complet et testé**, frontend React + Vite.

## 1. État et version de référence

- Le dépôt contient le **backend** (API REST, extraction IA, contrôles métier, facturation, PDF, audit) et sa suite de tests automatisés, et le **frontend** (React + Vite).
- Périmètre d'extraction : **PDF natifs qui contiennent du texte**. Les PDF scannés, PDF mixtes et images sont identifiés à l'import et conservés, mais leur extraction (OCR/vision) n'est pas implémentée.
- Empreinte de commit : `2e8d481a0cf2efea21037ba66421f863fba0706e`

## 2. Prérequis

| Prérequis | Usage | Obligatoire ? |
|---|---|---|
| Python 3.12+ | Backend | Oui |
| Chromium | Rendu des factures PDF (HTML/CSS → PDF headless) | Oui pour générer un PDF de facture |
| Clé API Groq (ou autre fournisseur LLM) | Extraction structurée des documents | Oui pour extraire ; l'API démarre sans clé |
| Bucket Cloudflare R2 + credentials S3 | Archivage des PDF de facture émis | Oui pour **valider/émettre une facture et télécharger son PDF** |
| Docker + Compose | Environnement PostgreSQL conteneurisé | Non (SQLite suffit en local) |

Points importants :
- Les **documents sources** sont toujours conservés en stockage local (complété par R2 si configuré).
- Les **PDF de facture** sont des artefacts essentiels : ils doivent être écrits dans R2 **avant** la finalisation de l'émission. Sans R2 configuré, la validation d'une facture et le téléchargement de son PDF échouent (HTTP 503) ; c'est voulu, car aucune facture n'est émise sans archive persistée.
- Les tests automatisés n'ont **ni** clé LLM, ni bucket R2 : fournisseurs et stockages y sont simulés.

## 3. Installation locale

Depuis la racine du dépôt :

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Installer Chromium et indiquer son chemin dans `.env` (variable `CHROMIUM_EXECUTABLE_PATH`). Sous Debian/Ubuntu : `sudo apt-get install chromium` puis `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium`. À défaut de paquet système, un binaire Playwright convient également :

```bash
pip install playwright && playwright install chromium
# puis dans .env :
# CHROMIUM_EXECUTABLE_PATH=<chemin>/ms-playwright/chromium-XXXX/chrome-linux64/chrome
```

Appliquer le schéma puis démarrer l'API :

```bash
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

Adresses locales : API `http://127.0.0.1:8000` · Swagger `http://127.0.0.1:8000/docs` · OpenAPI `http://127.0.0.1:8000/openapi.json` · Santé `http://127.0.0.1:8000/api/health`.

En mode `APP_ENV=development`, les tables manquantes sont créées au démarrage ; Alembic reste la référence des migrations (obligatoire en production).

## 4. Configuration (.env)

Toutes les variables sont externalisées dans `.env` (jamais committées ; une variable d'environnement exportée prévaut sur le fichier).

| Variable | Rôle / valeur pour la démo |
|---|---|
| `APP_ENV` | `development` en local. En `production`, `JWT_SECRET` doit être unique et ≥ 32 caractères. |
| `DATABASE_URL` | Défaut `sqlite:///./faktsure.db` ; PostgreSQL supporté (voir Compose). |
| `JWT_SECRET` | Secret de signature des JWT. Valeur aléatoire unique requise hors démonstration locale. |
| `LLM_PROVIDER` | `groq` (démo de l'équipe), `gemini` ou `cloudflare`. Défaut du code : `groq`. |
| `GROQ_API_KEY` | Clé du fournisseur Groq. |
| `GROQ_MODEL` | **`openai/gpt-oss-120b`**, le modèle réellement utilisé par l'équipe pour la démo. Défaut du code : `openai/gpt-oss-120b`. |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Alternative Gemini (`gemini-3.5-flash-lite` par défaut). |
| `CLOUDFLARE_ACCOUNT_ID/API_TOKEN/MODEL` | Alternative Cloudflare Workers AI (`@cf/openai/gpt-oss-120b` par défaut). |
| `R2_ENABLED` + `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Active l'archivage R2 des PDF de facture. **Requis pour émettre/valider une facture et télécharger son PDF.** |
| `DOCUMENT_BATCH_SIZE` | Taille des groupes de traitement (défaut 3). |
| `MAX_DOCUMENT_CONCURRENCY` | Traitements de lots simultanés dans le processus (défaut 1, séquentiel). |
| `MAX_UPLOAD_SIZE_MB` | Taille maximale par fichier (défaut 20 Mo). |
| `CORS_ALLOWED_ORIGINS` | Origines explicites du frontend, séparées par des virgules (ex. `http://localhost:5173` pour un dev Vite). Jamais de `*`. |
| `ISSUER_*` (name, address, tax_identifier, rccm, phone, email, payment_terms) | Informations de l'entreprise émettrice sur les factures ; modifiables ensuite via `PUT /api/settings/issuer` par un ADMIN. |
| `STORAGE_ROOT` | Répertoire local des fichiers (défaut `storage/documents`). |
| `CHROMIUM_EXECUTABLE_PATH` | Chemin du binaire Chromium. |

Le fournisseur et le modèle LLM peuvent aussi être changés **à chaud** par un administrateur via `PUT /api/settings/ai` (persisté en base, audité).

## 5. Comptes de démonstration

Le dépôt ne contient **aucun mot de passe en clair** ; les comptes sont créés par les scripts :

1. **Comptes fictifs de démonstration** (`scripts/seed_demo.py`, uniquement si `APP_ENV=development`) : crée trois comptes `admin@demo.faktsure.com` (ADMIN), `accountant@demo.faktsure.com` (ACCOUNTANT), `validator@demo.faktsure.com` (VALIDATOR) avec le mot de passe fourni via la variable `DEMO_PASSWORD` (≥ 12 caractères), ainsi qu'un référentiel fictif (client « Client Démo Fictif », produit `DEMO-SKU-001` à 1 000 XOF, règle de TVA `DEMO-TAX-18` à 18 %) :

   ```bash
   cd backend
   read -s DEMO_PASSWORD && export DEMO_PASSWORD
   .venv/bin/python ../scripts/seed_demo.py
   unset DEMO_PASSWORD
   ```

   Le seed est idempotent mais **n'est pas un outil de remise à zéro** (il n'efface ni documents, ni factures, ni audit) et ne remplace pas le mot de passe d'un compte existant.

2. **Administrateur nominatif** (`scripts/create_admin.py`, interactif) ou **API** (`POST /api/users`, réservé ADMIN ; mot de passe ≥ 12 caractères).

3. **Compte de test de l'équipe** utilisé sur l'instance de démonstration du hackathon :

   | Rôle | Identifiant | Mot de passe |
   |---|---|---|
   | Administrateur | `admin@test.com` | `password1234` |

   Ces identifiants n'existent que sur l'instance de démonstration de l'équipe (ou sur toute base où ce compte a été créé) ; sur une installation fraîche, créer vos propres comptes comme ci-dessus. À ne pas réutiliser ailleurs.

## 6. Reproduire le parcours de démonstration

L'extraction n'est **pas** déclenchée à l'import : elle se lance par document ou par lot. Depuis Swagger (`/docs`), cliquer **Authorize** et fournir `Bearer <access_token>`.

1. **Connexion** : `POST /api/auth/login` avec `{"email": "admin@test.com", "password": "password1234"}` (ou un compte seedé) → récupérer `access_token`.
2. **Créer un lot** : `POST /api/batches` avec `{"name": "Démo jury"}` → noter le `batch_id` (UUID public).
3. **Importer les documents** : `POST /api/batches/{batch_id}/documents`, formulaire multipart, champ `files` (plusieurs fichiers PDF natifs). Chaque fichier est contrôlé (signature réelle, taille, format), doublonné par empreinte SHA-256, stocké et audité. Un document identique déjà présent est renvoyé avec le statut `duplicate`.
4. **Lancer le traitement** : `POST /api/batches/{batch_id}/process` (HTTP 202) : les PDF natifs sont mis en file et extraits par groupes de 3, séquentiellement, en arrière-plan. Alternative document par document : `POST /api/documents/{document_id}/extract`.
5. **Consulter les résultats** : `GET /api/documents/{document_id}/fields` (valeurs, confiance, page et texte source) et `GET /api/documents/{document_id}/anomalies` (type, gravité, valeurs attendue/observée). L'appel au LLM externe peut être facturable selon votre quota.
6. **Corriger si nécessaire** : `PUT /api/documents/{document_id}/fields` (corrections champ par champ, tracées) et `POST /api/documents/{document_id}/anomalies/{anomaly_id}/resolve` pour résoudre un bloqueur avec une correction.
7. **Revue humaine obligatoire** : `POST /api/documents/{document_id}/review` avec `{"confirmed": true}`. Un bloqueur ouvert interdit la revue ; chaque avertissement ouvert exige une décision (`warning_decision`). Le document passe alors en `READY`.
8. **Créer le brouillon de facture** : `POST /api/invoices` avec `{"document_id": "..."}`. Le client est rapproché automatiquement du référentiel (RCCM/IFU, sinon nom exact) ; les lignes sont reprises des champs revus ; la TVA est appliquée par ligne ou par règle globale (les deux modes sont exclusifs) ; les montants sont recalculés côté serveur en `Decimal` et rapprochés des totaux extraits.
9. **Valider et émettre** : `POST /api/invoices/{invoice_id}/validate` (rôles ADMIN ou VALIDATOR). Le numéro définitif `FS-AAAA-NNNNNN` est attribué de façon atomique, le PDF est rendu par Chromium puis écrit dans R2 **avant** la finalisation (sans R2 → 503, émission annulée), et l'émission est auditée.
10. **Télécharger le PDF** : `GET /api/invoices/{invoice_id}/pdf`.
11. **Vérifier l'audit** : `GET /api/audit` (ADMIN) : importations, extractions, corrections, revues, brouillons, émissions.

Rôles : `ADMIN` (tout), `ACCOUNTANT` (imports, extractions, corrections, revue, brouillons), `VALIDATOR` (consultation, revue/rejet, validation/émission). La création de compte est réservée à l'ADMIN ; il n'existe pas d'inscription publique.

## 7. Réinitialiser les données de démonstration

La méthode la plus sûre est une base **jetable** déclarée dès le départ :

```bash
cd backend
export DATABASE_URL=sqlite:////tmp/faktsure-hackathon-demo.db
export STORAGE_ROOT=/tmp/faktsure-hackathon-demo-files
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

Pour repartir de zéro : arrêter l'API, vérifier que `DATABASE_URL` et `STORAGE_ROOT` pointent bien vers ces chemins temporaires, supprimer **uniquement** `/tmp/faktsure-hackathon-demo.db` et `/tmp/faktsure-hackathon-demo-files`, puis rejouer `alembic upgrade head` et les créations de comptes. Cette opération détruit les données de démonstration correspondantes ; ne jamais l'appliquer à une base utile.

## 8. Reprise après interruption

- À chaque démarrage, l'application exécute une routine de récupération : les documents restés en `EXTRACTING` (état possible après un arrêt brutal) sont remis en `QUEUED`, et les lots `PROCESSING` sont ré-enfileés s'ils contiennent encore des documents à traiter, sinon clôturés en `COMPLETED` / `PARTIALLY_COMPLETED`.
- Pour réessayer les documents en échec d'un lot : `POST /api/batches/{batch_id}/process?retry_failed=true`.
- Un test automatisé démontre cette reprise :

```bash
backend/.venv/bin/python -m pytest backend/tests/unit/test_batch_processing.py::test_recovery_requeues_interrupted_extraction -q
```

Limites assumées : la file de traitement est en mémoire dans le processus (pas de broker externe) ; si un appel fournisseur s'était terminé avant l'arrêt sans transaction persistée, le traitement peut être rejoué, et il n'y a pas de garantie « exactement une fois » côté fournisseur. Une instance API unique est recommandée pour la démonstration.

## 9. Tests automatisés

Depuis la racine du dépôt :

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

Résultat vérifié le **26 novembre 2026** (Python 3.12, Chromium présent, base SQLite jetable créée par les tests) : **48 tests passent**, en ~10 s. La suite couvre notamment : le parcours intégral document → extraction (fournisseur simulé) → revue → brouillon → émission → PDF ; les calculs financiers (`Decimal`, remises, TVA par ligne et globale) ; la détection d'anomalies ; la numérotation atomique et la validation unique ; la reprise après interruption ; le stockage local/R2 et ses replis ; les importations CSV/XLSX ; les rôles et CORS ; la documentation OpenAPI française complète.

Les tests n'appellent aucun fournisseur LLM ni bucket R2 réel (fournisseurs et stockage simulés) et n'ont besoin d'aucune clé.

## 10. Essai Docker (PostgreSQL + Chromium)

```bash
cp backend/.env.example backend/.env
# renseigner les secrets de développement dans backend/.env (jamais commités)
docker compose up --build -d
docker compose ps
curl http://127.0.0.1:8000/api/health
```

Compose démarre PostgreSQL 17 et l'API (migrations appliquées à l'entrée du conteneur, Chromium inclus dans l'image, utilisateur non root). Le conteneur ne copie volontairement que `create_admin.py` : exécuter `seed_demo.py` depuis un environnement Python local qui pointe sur la même base si besoin. `docker compose down -v` supprime irréversiblement les volumes (à réserver à un environnement local jetable).

## 11. Dépendances, modèles et licences

Dépendances Python de premier niveau (`backend/requirements.txt`, versions en plages) :

| Dépendance | Usage | Licence amont usuelle |
|---|---|---|
| FastAPI, Uvicorn | API HTTP et serveur ASGI | MIT / BSD-3-Clause |
| SQLAlchemy, Alembic, psycopg | ORM, migrations, accès PostgreSQL | MIT / LGPL-3.0 (psycopg 3) |
| Pydantic, pydantic-settings, email-validator | Validation et configuration | MIT / CC0-1.0 |
| python-jose, bcrypt, passlib | JWT et hachage des mots de passe | MIT / Apache-2.0 / BSD-3-Clause |
| PyMuPDF | Extraction des PDF | **AGPL-3.0 ou licence commerciale** |
| Jinja2, openpyxl | Template de facture et import XLSX | BSD-3-Clause / MIT |
| boto3 | Accès S3/R2 | Apache-2.0 |
| httpx, python-multipart | Appels LLM et upload HTTP | BSD-3-Clause / Apache-2.0 |
| pytest | Tests | MIT |

Points de conformité à traiter avant une exploitation au-delà du hackathon :
- **PyMuPDF** est sous AGPL-3.0 : vérifier la compatibilité de l'usage ou acquérir la licence commerciale.
- Le fichier racine `LICENSE` est **vide** : la licence du code FaktSure n'est pas encore déclarée.
- Aucun poids de modèle n'est livré dans le dépôt ; le LLM (`openai/gpt-oss-120b` via Groq pour la démo) est un service distant régi par les conditions de Groq. Les polices embarquées du modèle de facture (Inter, Space Grotesk, JetBrains Mono) sont sous SIL Open Font License 1.1 (textes inclus dans `backend/app/static/invoice/fonts/`).

## 12. Données et secrets

Un balayage du dépôt (clés API, tokens, mots de passe) n'a révélé **aucun secret** : `.env.example` ne contient que des variables vides ou des espaces réservés, et les identifiants PostgreSQL de `compose.yaml` sont des valeurs locales triviales. Les clés API LLM et R2, ainsi que `JWT_SECRET`, se fournissent uniquement par variables d'environnement ou gestionnaire de secrets. Les données seedées et les documents de test sont entièrement fictifs : ne jamais importer de données client réelles dans une instance de démonstration.
