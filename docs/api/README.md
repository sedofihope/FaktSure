# Guide d'intégration API FaktSure

Ce guide s'adresse au développeur frontend et décrit le contrat de l'API actuellement implémenté. Les détails OpenAPI propres à chaque opération sont également disponibles dans Swagger : démarrer l'API et ouvrir `/docs`. Le schéma machine est exposé sur `/openapi.json`.

Toutes les routes métier utilisent le préfixe `/api`. Une route de santé séparée est disponible sur `GET /api/health`.

## Base URL et formats

En local, la base URL est `http://127.0.0.1:8000`. En production, utiliser le domaine HTTPS de l'API. Les corps de requête et réponses sont JSON, sauf import de fichiers (`multipart/form-data`) et téléchargement de documents/PDF (binaire).

Les identifiants transmis à l'API sont des UUID publics (`public_id`), jamais les clés numériques internes. Les montants financiers sont sérialisés en chaînes décimales pour ne pas dépendre de la précision des nombres flottants JavaScript.

## Authentification et rôles

L'authentification s'effectue avec `POST /api/auth/login`. Envoyer le jeton reçu avec chaque requête protégée :

```http
Authorization: Bearer <access_token>
```

`GET /api/auth/me` retourne le profil associé au jeton. Les comptes inactifs ne peuvent pas accéder à l'API. Il n'y a pas d'inscription publique; les utilisateurs sont créés par un administrateur.

Rôles :

- `ADMIN` : paramètres, utilisateurs, audit et écriture sur les référentiels; peut aussi travailler sur les documents et factures.
- `ACCOUNTANT` : lots, extraction, correction/revue des documents et création/modification des brouillons; accès en lecture aux référentiels, sans droit de les créer/importer/modifier.
- `VALIDATOR` : consultation des documents et factures, revue/rejet, et émission des factures; aucun accès au journal d'audit ni à la modification des référentiels.

`401` signifie qu'une authentification valide manque; `403` signifie que le rôle ne permet pas l'opération.

### Connexion

```http
POST /api/auth/login
Content-Type: application/json

{"email":"admin@example.com","password":"<mot-de-passe>"}
```

Réponse : `access_token`, `token_type` (`bearer`). Les erreurs d'identifiants renvoient `401`; un compte désactivé renvoie `403`.

## Matrice des routes

| Méthode et route | Accès | Rôle et fonction |
|---|---|---|
| `GET /api/health` | Public | Santé de l'application et environnement. |
| `POST /api/auth/login` | Public | Connexion et émission d'un JWT. |
| `GET /api/auth/me` | Authentifié | Profil de l'utilisateur courant. |
| `GET /api/batches` | Authentifié | Lister les lots. |
| `POST /api/batches` | `ADMIN`, `ACCOUNTANT` | Créer un lot. |
| `GET /api/batches/{batch_id}` | Authentifié | État et progression d'un lot. |
| `POST /api/batches/{batch_id}/documents` | `ADMIN`, `ACCOUNTANT` | Importer plusieurs PDF/images dans un lot. |
| `POST /api/batches/{batch_id}/process` | `ADMIN`, `ACCOUNTANT` | Mettre en traitement les PDF natifs admissibles; répond `202`. |
| `GET /api/documents/{document_id}` | Authentifié | Détails et état du document. |
| `GET /api/documents/{document_id}/preview` | Authentifié | Lire le fichier original en binaire. |
| `POST /api/documents/{document_id}/extract` | `ADMIN`, `ACCOUNTANT` | Extraire un PDF natif via le fournisseur LLM configuré. |
| `GET /api/documents/{document_id}/fields` | Authentifié | Champs extraits/corrigés, confiance et éléments source disponibles. |
| `PUT /api/documents/{document_id}/fields` | `ADMIN`, `ACCOUNTANT` | Corriger les champs et recalculer les anomalies. |
| `GET /api/documents/{document_id}/anomalies` | Authentifié | Consulter les anomalies et leur gravité. |
| `POST /api/documents/{document_id}/anomalies/{anomaly_id}/resolve` | `ADMIN`, `ACCOUNTANT` | Corriger le champ lié à une anomalie bloquante et vérifier qu'elle est levée. |
| `POST /api/documents/{document_id}/review` | Authentifié | Confirmer la revue humaine après résolution des blocages. |
| `POST /api/documents/{document_id}/reject` | Authentifié | Rejeter le document avec un motif facultatif. |
| `GET /api/clients` | Authentifié | Lister les clients. |
| `POST /api/clients` | `ADMIN` | Créer une fiche client. |
| `GET /api/clients/{client_id}` | Authentifié | Consulter une fiche client. |
| `PUT /api/clients/{client_id}` | `ADMIN` | Modifier un client. |
| `DELETE /api/clients/{client_id}` | `ADMIN` | Désactiver un client sans supprimer son historique. |
| `GET /api/products` | Authentifié | Lister les produits. |
| `POST /api/products` | `ADMIN` | Créer un produit ou service. |
| `GET /api/products/{product_id}` | Authentifié | Consulter un produit. |
| `PUT /api/products/{product_id}` | `ADMIN` | Modifier un produit. |
| `DELETE /api/products/{product_id}` | `ADMIN` | Désactiver un produit sans supprimer son historique. |
| `GET /api/tax-rules` | Authentifié | Consulter les règles de TVA. |
| `POST /api/tax-rules` | `ADMIN` | Créer une règle de TVA avec taux et validité. |
| `GET /api/products/{product_id}/prices` | Authentifié | Consulter les prix historiques d'un produit. |
| `POST /api/products/{product_id}/prices` | `ADMIN` | Ajouter un prix daté. |
| `POST /api/references/import` | `ADMIN` | Importer clients, produits ou règles de TVA en CSV/XLSX. |
| `POST /api/invoices` | `ADMIN`, `ACCOUNTANT` | Créer un brouillon à partir d'un document revu. |
| `GET /api/invoices` | Authentifié | Lister les factures et brouillons. |
| `GET /api/invoices/{invoice_id}` | Authentifié | Consulter une facture. |
| `PUT /api/invoices/{invoice_id}` | `ADMIN`, `ACCOUNTANT` | Modifier l'échéance d'un brouillon. |
| `POST /api/invoices/{invoice_id}/validate` | `ADMIN`, `VALIDATOR` | Valider et émettre une facture. |
| `GET /api/invoices/{invoice_id}/pdf` | Authentifié | Télécharger le PDF. |
| `GET /api/audit` | `ADMIN` | Consulter les 500 événements les plus récents. |
| `GET /api/users` | `ADMIN` | Lister les comptes sans données de mot de passe. |
| `POST /api/users` | `ADMIN` | Créer un utilisateur. |
| `GET /api/users/{user_id}` | `ADMIN` | Consulter un utilisateur. |
| `PUT /api/users/{user_id}` | `ADMIN` | Modifier profil, rôle ou statut actif. |
| `GET /api/settings` | `ADMIN` | Lire les réglages non secrets. |
| `PUT /api/settings/processing` | `ADMIN` | Régler lots, concurrence et taille maximale d'import. |
| `PUT /api/settings/ai` | `ADMIN` | Choisir le fournisseur et le modèle parmi les credentials d'environnement disponibles. |
| `PUT /api/settings/storage` | `ADMIN` | Sélectionner le stockage local ou R2. |
| `PUT /api/settings/issuer` | `ADMIN` | Modifier partiellement les coordonnées et modalités de paiement de l'émetteur. |

## Parcours document vers facture

1. `POST /api/batches` avec `{"name":"Lot à traiter"}`; conserver le `public_id`.
2. `POST /api/batches/{batch_id}/documents` en multipart avec un ou plusieurs champs `files`.
3. Import réussi retourne un résultat par fichier : `uploaded`, `duplicate` ou `error`. Les doublons sont identifiés par SHA-256. L'import seul n'exécute pas de LLM.
4. Lancer `POST /api/documents/{document_id}/extract` pour un document, ou `POST /api/batches/{batch_id}/process` pour la file des PDF natifs. Pour réessayer les documents en échec, ajouter `?retry_failed=true`. Le traitement de lot répond `202`; consulter `GET /api/batches/{batch_id}`.
5. Lire `/fields` et `/anomalies`. Corriger par `PUT /fields`, ou résoudre un blocage avec `/anomalies/{anomaly_id}/resolve`.
6. Confirmer `POST /review` avec `{"confirmed":true}`. Si des avertissements restent ouverts, renseigner également `warning_decision`. Un document prêt passe à l'état `READY`.
7. Créer le brouillon : `POST /api/invoices` avec le document et, si nécessaire, les remplacements décrits ci-dessous.
8. Émettre via `POST /api/invoices/{invoice_id}/validate`, puis télécharger le PDF avec `GET /api/invoices/{invoice_id}/pdf`.

Le workflow exige une revue humaine. Une anomalie `BLOCKER` ouverte empêche la revue prête et la création de facture. Les appels LLM sont externes et potentiellement facturables.

### Formats et état des documents

L'import prend en charge les PDF, PNG, JPEG, TIFF et WebP, jusqu'à `MAX_UPLOAD_SIZE_MB` par fichier. Le backend détecte le format à partir de la signature plutôt que de faire confiance au seul MIME annoncé.

À ce jour, l'extraction métier fonctionne sur les PDF natifs contenant du texte. Les images et PDF scannés/mixés sont classés mais l'extracteur renvoie un état d'échec indisponible; ils ne sont pas convertis par OCR. Les imports de lots traitent les PDF natifs séquentiellement dans le processus API.

Les valeurs de statut de document et de lot sont renvoyées dans leurs réponses; le frontend doit utiliser ces valeurs plutôt que simuler un traitement automatique à l'upload.

## Brouillon, montants et TVA

Le corps minimal de création est :

```json
{
  "document_id": "8c4a4b9e-4e51-46c1-8c4a-9b9f1d45a4c2"
}
```

Le document doit être en état `READY`. Le backend reprend par défaut les champs examinés, associe un client actif sans ambiguïté et recalcule les montants. Il refuse les données manquantes ou incohérentes plutôt que de les inventer. Les paramètres facultatifs incluent `client_id`, `issue_date`, `due_date`, `payment_terms`, `currency` et `items`.

Si une taxe totale a été extraite sans règle explicitement fournie, le backend tente de l'associer à une règle active unique qui réconcilie le montant sur toutes les lignes. Si aucun taux unique ne correspond, ou si plusieurs taux conviennent, la création est refusée : corriger les champs ou fournir explicitement la TVA par ligne ou la règle globale.

Fournir `items` remplace toutes les lignes extraites. Chaque ligne comprend `description`, `quantity`, `unit`, `unit_price`, et éventuellement `discount`, `product_id`, `tax_rule_id`. Une remise est un montant monétaire, elle ne peut dépasser le montant brut de la ligne.

La TVA peut être appliquée selon un seul de deux modes pour une facture :

**TVA par ligne** — configure `tax_rule_id` sur les lignes auxquelles la règle s'applique. Cela permet des taux différents et des lignes sans règle de TVA.

**TVA globale** — indique `tax_rule_id` à la racine du corps JSON. Une seule règle s'applique alors à la base nette totale `subtotal - discount_total`.

Ne pas envoyer simultanément une règle racine et des règles sur les lignes. Les règles doivent être actives et valides à la date de facture. Le backend calcule la TVA après remise et vérifie :

```text
grand_total = subtotal - discount_total + tax_total
```

Exemple de facture globale à 18 % :

```json
{
  "document_id": "8c4a4b9e-4e51-46c1-8c4a-9b9f1d45a4c2",
  "tax_rule_id": "d44e8db7-1255-47be-9d65-a6947b888d71",
  "items": [
    {
      "description": "Prestation",
      "quantity": "1",
      "unit": "service",
      "unit_price": "100000",
      "discount": "10000"
    }
  ]
}
```

Il appartient à l'administrateur de vérifier les taux et périodes configurés. Le logiciel applique les règles saisies; il ne détermine pas de lui-même le régime fiscal légal.

## Réglages et secrets

`GET /api/settings` expose les réglages non secrets de traitement, IA, stockage et émetteur. Il indique si les credentials sont configurés sans retourner leur valeur.

`PUT /api/settings/issuer` met à jour partiellement les champs `name`, `address`, `tax_identifier`, `rccm`, `phone`, `email` et `payment_terms`. Les champs omis restent inchangés; envoyer `null` ou une chaîne vide efface une valeur. Une requête vide est rejetée. Les changements sont persistés dans `app_settings` et inscrits à l'audit. Ils prennent le pas sur les variables initiales `ISSUER_*`.

Les mises à jour IA et stockage ne configurent pas les credentials. Les clés API, JWT et R2 restent dans l'environnement du déploiement.

Pour une application web hébergée sur une autre origine, configurer `CORS_ALLOWED_ORIGINS` côté serveur avec des origines complètes et exactes, séparées par des virgules : `https://app.example.com,http://localhost:5173`. N'inclure ni wildcard, chemin, query string ni slash final. Laisser vide si aucun appel navigateur cross-origin n'est nécessaire.

## Upload d'un référentiel

`POST /api/references/import` attend un seul fichier multipart nommé `file` au format CSV UTF-8 ou XLSX. Une colonne `name` est obligatoire. `type` (ou `kind`) choisit la nature : `client`, `product` (défaut) ou `tax` (règle de TVA). Les erreurs sont retournées par ligne; les lignes valides sont importées.

Seul `ADMIN` peut importer ou écrire les référentiels; les trois rôles peuvent les lire. Les détails des colonnes et formats sont décrits dans le schéma OpenAPI de cette route.

## Erreurs et réponses binaires

Les erreurs JSON utilisent généralement `{"detail":"..."}` :

| Code | Signification |
|---|---|
| `400` | Prérequête CORS refusée ou requête invalide selon le middleware. |
| `401` | Identifiants/jeton invalides, manquants ou expirés. |
| `403` | Rôle insuffisant ou compte désactivé. |
| `404` | Ressource introuvable. |
| `409` | État ou règle métier incompatible (ex. blocage non résolu, R2 non configuré). |
| `413` | Fichier trop volumineux. |
| `415` | Type de fichier non accepté. |
| `422` | Corps, UUID, paramètres ou contenu de fichier invalide. |
| `503` | Dépendance ou stockage essentiel indisponible. |

`GET /api/documents/{document_id}/preview` renvoie le document original avec son MIME. `GET /api/invoices/{invoice_id}/pdf` renvoie `application/pdf` en pièce jointe. Les deux peuvent répondre `404`; le téléchargement peut répondre `503` si une dépendance nécessaire est indisponible. L'API vérifie les empreintes des fichiers stockés.

L'émission exige la persistance du PDF essentiel dans R2. Si R2 manque ou échoue, l'émission est refusée; l'API ne présente pas un PDF local seul comme facture émise et durable.

## Contrat exhaustif et évolution

Les schémas détaillés, exemples, descriptions françaises et réponses d'erreur par opération sont maintenus avec le code et exposés par `/docs` et `/openapi.json`. En cas de divergence, le schéma OpenAPI déployé correspondant à la version du backend fait foi.
