# FaktSure

FaktSure est un backend d'automatisation de la facturation. Il transforme des documents commerciaux en données structurées, détecte les incohérences, permet une revue humaine, puis prépare et émet des factures PDF.

> **Principe de contrôle :** le LLM extrait les informations; le backend applique les règles métier et recalcule les montants; un utilisateur autorisé vérifie et décide avant l'émission. FaktSure ne transmet pas les factures à une administration fiscale et n'effectue pas de paiement.

## État du projet

Le dépôt contient actuellement une API FastAPI fonctionnelle et testée. Elle comprend l'authentification par JWT, les rôles `ADMIN`, `ACCOUNTANT` et `VALIDATOR`, l'import et l'extraction de documents, leur revue, la préparation des factures, les PDF, les référentiels, les réglages administratifs et le journal d'audit.

Le répertoire `frontend/` est encore un emplacement réservé : aucun frontend React n'est livré dans ce dépôt. Le navigateur Swagger (`/docs`) sert à explorer et tester l'API.

Le MVP extrait les PDF natifs contenant du texte. Les PDF scannés et les images peuvent être identifiés et importés, mais leur extraction est actuellement marquée comme indisponible; l'OCR et l'extraction d'images restent à développer. Voir [Architecture et limites](docs/architecture/README.md#limites-actuelles-et-décisions-métier-à-confirmer).

## Démarrage local

Prérequis : Python 3.12 ou ultérieur; Chromium est requis pour rendre les PDF de facture.

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Renseigner au minimum `JWT_SECRET` avec une valeur unique et aléatoire d'au moins 32 caractères si `APP_ENV=production`. En développement, configurer au besoin les identifiants du fournisseur LLM, le stockage R2 et les informations de l'émetteur. Les clés secrètes ne doivent jamais être ajoutées au dépôt.

Initialiser la base puis démarrer l'API :

```bash
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

L'API est disponible sur <http://127.0.0.1:8000>, Swagger sur <http://127.0.0.1:8000/docs>, le schéma OpenAPI sur <http://127.0.0.1:8000/openapi.json> et l'état de santé sur <http://127.0.0.1:8000/api/health>.

Créer le premier administrateur par saisie interactive, depuis `backend/` :

```bash
.venv/bin/python ../scripts/create_admin.py
```

Pour remplir une base de développement avec des données explicitement fictives, définir d'abord `DEMO_PASSWORD` (12 caractères minimum), puis lancer `../scripts/seed_demo.py`. Ce script refuse de s'exécuter hors de `APP_ENV=development`.

## Parcours fonctionnel principal

1. Un comptable crée un lot et importe des documents.
2. Le backend vérifie le type et l'empreinte, puis extrait les champs des PDF natifs avec le fournisseur LLM configuré.
3. Le système compare les données extraites aux référentiels et signale les anomalies.
4. Un utilisateur examine le document, corrige les données et confirme sa revue.
5. Un comptable crée un brouillon; le backend recalcule les lignes, les remises et la TVA, puis vérifie la cohérence des totaux.
6. Un administrateur ou un validateur autorisé émet la facture; le PDF définitif est conservé dans R2.

Les appels LLM peuvent être facturés par le fournisseur. L'import d'un fichier ne lance pas l'extraction automatiquement.

## Déploiement et configuration

Le backend est conteneurisé dans `backend/Dockerfile`. L'entrypoint exécute `alembic upgrade head` avant Uvicorn. Un déploiement Railway de démonstration a été préparé avec SQLite sur volume persistant; les PDF émis exigent cependant R2 configuré.

Variables importantes :

| Variable | Utilité |
|---|---|
| `APP_ENV` | Environnement (`development` ou `production`). |
| `DATABASE_URL` | URL SQLAlchemy de SQLite ou PostgreSQL. |
| `JWT_SECRET` | Secret de signature JWT; unique et d'au moins 32 caractères en production. |
| `CORS_ALLOWED_ORIGINS` | Liste séparée par virgules d'origines frontend explicites; vide par défaut. |
| `STORAGE_ROOT` | Répertoire du stockage local. |
| `R2_ENABLED`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Stockage Cloudflare R2. |
| `LLM_PROVIDER` | Fournisseur sélectionné : `gemini`, `groq` ou `cloudflare`. |
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | Identifiants des fournisseurs LLM, selon le fournisseur sélectionné. |
| `DOCUMENT_BATCH_SIZE`, `MAX_DOCUMENT_CONCURRENCY`, `MAX_UPLOAD_SIZE_MB` | Réglages de traitement et d'import. |
| `ISSUER_*` | Valeurs initiales de l'émetteur; les réglages modifiés par l'admin sont persistés en base. |
| `CHROMIUM_EXECUTABLE_PATH` | Chemin Chromium; défini sur `/usr/bin/chromium` dans l'image Docker. |

Ne pas copier un `.env` local dans une image ni publier ses valeurs. Dans Railway, placer les variables dans le gestionnaire de variables. Pour un frontend séparé, ajouter son origine exacte dans `CORS_ALLOWED_ORIGINS`, par exemple `https://app.example.com`; ne pas utiliser `*`, ni ajouter de chemin ou de slash final. L'authentification est par Bearer JWT, pas par cookie.

Pour les détails d'installation, Docker, SQLite/Railway, PostgreSQL, R2 et les opérations sur les migrations, consulter [backend/README.md](backend/README.md).

## Documentation

- [Guide complet de l'API](docs/api/README.md) — routes, rôles, formats, règles métier et exemples.
- [Architecture](docs/architecture/README.md) — composants, données, flux, stockage et limites.
- [Spécifications fonctionnelles et techniques](docs/specifications/README.md) — objectifs, périmètre et exigences du projet.
- [Guide du backend](backend/README.md) — environnement local, conteneur, déploiement et migrations.
- [Dossier des livrables hackathon](docs/livrables/README.md) — guide jury/reproduction, rapport technique et fiche IA.

## Tests

Depuis `backend/`, après installation des dépendances :

```bash
.venv/bin/python -m pytest
```

La suite couvre les routes, les permissions, les réglages, les calculs, les workflows de facture et la documentation OpenAPI.

## Structure du dépôt

```text
backend/                 API FastAPI, modèles, services, tests et migrations
docs/
  api/                   Guide d'intégration frontend
  architecture/          Vue technique et limites connues
  livrables/             Documents destinés au jury du hackathon
  specifications/        Spécifications fonctionnelles et techniques
frontend/                Emplacement réservé au frontend, pas encore implémenté
scripts/                 Création de l'admin et données de démonstration
compose.yaml             Essai local Docker avec PostgreSQL et l'API
```

## Sécurité et données

- Les mots de passe sont stockés sous forme de hash; les routes ne renvoient jamais ces hashes.
- Les routes privées exigent un jeton Bearer et vérifient le rôle.
- Les clés LLM et R2 restent dans l'environnement; l'API de réglages ne les accepte ni ne les renvoie.
- Les fichiers sont vérifiés par SHA-256 lors de leur lecture.
- La validation humaine et le journal d'audit font partie du workflow.
- L'émission est bloquée si R2 ne peut pas conserver le PDF essentiel.
- SQLite sur un volume Railway et un seul processus conviennent à la démonstration, pas à une exploitation multi-instance.

## Statut de fiscalité et conformité

Le backend accepte une TVA soit par ligne (taux différents possibles), soit avec une règle unique au niveau de la facture; les deux modes sont exclusifs. Dans les deux cas, la TVA est calculée après remise. Les taux, exonérations et périodes d'application doivent être confirmés et configurés par l'administrateur en fonction des règles applicables à l'entreprise. La présence d'un calcul correct ne constitue pas une validation de conformité fiscale.