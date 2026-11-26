# API FaktSure

L'API est préfixée par `/api`. La spécification OpenAPI générée par FastAPI est disponible à `/docs` (et le schéma JSON à `/openapi.json`) lorsque le serveur est démarré.

La documentation Swagger est rédigée en français pour l'intégration frontend : chaque opération décrit son rôle, ses paramètres, les règles métier, les effets de bord, les erreurs possibles et le parcours recommandé. Les schémas de requête et de réponse documentent les champs; les fichiers uploadés et téléchargés sont exposés comme binaires.

## Identifiants publics

Les ressources exposées par l'API sont identifiées par leur `public_id`, un UUID au format canonique, par exemple `8c4a4b9e-4e51-46c1-8c4a-9b9f1d45a4c2`. Utilisez cet UUID dans les chemins et les références entre ressources. Les clés numériques restent internes à la base et ne doivent pas être utilisées par les clients API.

Les réponses d'authentification, utilisateurs, clients, produits, règles de taxe, tarifs, lots, documents, champs extraits, anomalies et factures fournissent un `public_id`. Les références telles que `document_id`, `batch_id`, `client_id`, `product_id`, `tax_rule_id` et `anomaly_id` sont également des UUID lorsqu'elles sont acceptées ou renvoyées par l'API. Les clients acceptent et retournent notamment `tax_identifier` et `rccm`; le RCCM est facultatif.

## Authentification et rôles

Connectez-vous avec un compte actif via `POST /api/auth/login`. Le jeton retourné doit être envoyé dans l'en-tête `Authorization: Bearer <access_token>` pour les routes protégées. `GET /api/auth/me` retourne le compte authentifié.

Les rôles disponibles sont `ADMIN`, `ACCOUNTANT` et `VALIDATOR`. Les routes de lecture métier acceptent généralement les trois rôles ; la création et les modifications sont réservées à `ADMIN` et `ACCOUNTANT`, tandis que l'émission d'une facture est réservée à `ADMIN` et `VALIDATOR`. Les routes de gestion des utilisateurs sont réservées à `ADMIN`. La documentation OpenAPI décrit les exigences par opération.

```http
POST /api/auth/login
Content-Type: application/json

{"email":"admin@example.com","password":"<mot-de-passe>"}
```

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

## Parcours document vers facture

1. Créer un lot avec `POST /api/batches`.
2. Importer un ou plusieurs PDF/images via `POST /api/batches/{batch_id}/documents` avec un champ multipart `files`. L'import conserve le document mais ne lance pas l'extraction LLM.
3. Extraire un document natif avec `POST /api/documents/{document_id}/extract`, ou lancer séquentiellement le traitement d'un lot avec `POST /api/batches/{batch_id}/process`. Ces opérations peuvent entraîner des appels LLM facturables. Le traitement par lot répond `202 Accepted`; suivre son état avec `GET /api/batches/{batch_id}`.
4. Consulter les champs via `GET /api/documents/{document_id}/fields` et les anomalies via `GET /api/documents/{document_id}/anomalies`. Corriger les champs avec `PUT /api/documents/{document_id}/fields`. Les anomalies bloquantes doivent être résolues avant la revue.
5. Confirmer la revue avec `POST /api/documents/{document_id}/review`, avec `confirmed` (booléen) obligatoire. `warning_decision` (texte, facultatif sauf si des avertissements restent ouverts) consigne la décision du réviseur. Le document doit être en état `EXTRACTED` ou `REVIEW_REQUIRED`, sans anomalie bloquante ouverte.
6. Créer un brouillon avec `POST /api/invoices` en transmettant l'UUID du document. Par défaut, le backend réutilise les champs extraits et corrigés : client identifié par RCCM/IFU ou nom exact, devise, lignes, remise et taxes. La date de facture est la date du jour ; l'échéance reste vide sauf si elle est fournie explicitement. Les dates du bon de commande/devis ne sont pas assimilées à celles de la facture. Le document doit avoir été revu et les montants extraits doivent être cohérents.
7. Émettre le brouillon avec `POST /api/invoices/{invoice_id}/validate`. Une facture émise reçoit son numéro définitif et son PDF est persisté dans R2. Le télécharger ou le retélécharger via `GET /api/invoices/{invoice_id}/pdf`.

L'émission requiert un R2 opérationnel pour garantir la persistance du PDF ; si R2 est indisponible, l'API renvoie `503` et n'émet pas la facture. Une copie locale miroir est conservée lorsque possible. Les factures émises avant l'activation du stockage PDF sont générées et enregistrées à la demande lors de leur premier téléchargement.

Dans Swagger (`/docs`), ouvre `POST /api/batches/{batch_id}/documents`, clique sur **Try it out**, puis utilise le sélecteur de fichiers du champ `files`. Il accepte plusieurs fichiers ; pour sélectionner plusieurs documents dans le navigateur, utilise `Ctrl` (ou `Cmd` sur macOS) pendant la sélection. Le champ `batch_id` attend l'UUID renvoyé à la création du lot.

Exemple de demande de revue :

```json
{
  "confirmed": true,
  "warning_decision": "Avertissements vérifiés et acceptés"
}
```

Sans avertissement ouvert, `{"confirmed": true}` suffit. La route `POST /api/documents/{document_id}/reject` accepte un corps `{"reason":"Motif du rejet"}` ; `reason` est facultatif.

Exemple minimal : le document doit être en état `READY`, les lignes et totaux doivent avoir été extraits et corrigés, et le client correspondant doit exister comme client actif.

```http
POST /api/invoices
Authorization: Bearer <jwt>
Content-Type: application/json
```

```json
{
  "document_id": "8c4a4b9e-4e51-46c1-8c4a-9b9f1d45a4c2"
}
```

Les lignes et la devise extraites sont utilisées par défaut. Si un client ne peut pas être associé sans ambiguïté par son RCCM/IFU (ou par son nom exact lorsqu'aucun identifiant n'est extrait), ajoute `client_id` avec l'UUID d'un client actif déjà créé. Tu peux fournir `issue_date` et `due_date`; sinon la date de facture prend la date du jour et l'échéance reste vide. Tu peux aussi remplacer la devise extraite avec `currency`.

N'envoie `items` que pour remplacer manuellement les lignes extraites. Dans ce cas, chaque ligne contient `description`, `quantity`, `unit`, `unit_price`, et éventuellement `discount`, `product_id` et `tax_rule_id`. La remise globale extraite est répartie proportionnellement entre les lignes ; la taxe et les totaux extraits sont conservés et vérifiés. Les montants doivent se réconcilier selon `subtotal - discount_total + tax_total = grand_total`. Le backend recalcule les totaux du brouillon et refuse les données extraites incomplètes ou incohérentes plutôt que de les deviner.

Pour la validation de cohérence des montants extraits, le total attendu est `subtotal - discount_total + tax_total`; la remise est retranchée du sous-total avant d'ajouter la taxe calculée sur la base taxable remisée.

## Opérations principales

| Domaine | Routes |
|---|---|
| Santé et session | `GET /api/health`, `POST /api/auth/login`, `GET /api/auth/me` |
| Lots et documents | `GET/POST /api/batches`, `GET /api/batches/{batch_id}`, `POST /api/batches/{batch_id}/documents`, `POST /api/batches/{batch_id}/process` |
| Documents | `GET /api/documents/{document_id}`, `GET /api/documents/{document_id}/preview`, `POST /api/documents/{document_id}/extract`, routes `/fields`, `/anomalies`, `/review` et `/reject` sous le document |
| Clients et produits | CRUD sous `/api/clients` et `/api/products` |
| Référentiels | `/api/tax-rules`, `/api/products/{product_id}/prices`, `POST /api/references/import` (CSV/XLSX, clients avec colonne facultative `rccm`) |
| Factures | `GET/POST /api/invoices`, `GET/PUT /api/invoices/{invoice_id}`, `POST /api/invoices/{invoice_id}/validate`, `GET /api/invoices/{invoice_id}/pdf` |
| Administration et audit | `/api/users`, `GET /api/audit` |

## Configuration administrateur

`GET /api/settings` affiche la configuration de traitement, du fournisseur LLM, du stockage et des informations de l'émetteur, sans exposer les secrets. Un administrateur peut modifier :

- `PUT /api/settings/processing` : taille des lots, concurrence et taille maximale d'import.
- `PUT /api/settings/ai` : fournisseur LLM et modèle. Les identifiants restent gérés dans l'environnement.
- `PUT /api/settings/storage` : sélection de `local` ou `r2`. R2 doit être entièrement configuré dans l'environnement avant sa sélection.

Les PDF sont générés depuis le template HTML/CSS FaktSure avec Chromium. Un PDF de brouillon porte le marquage ambre « BROUILLON — NON ÉMISE » et une référence provisoire ; après validation, le PDF affiche le numéro définitif et le statut vert. Les coordonnées manquantes de la fiche client sont complétées à partir des champs extraits et de leurs éléments sources. Les montants utilisent des espaces comme séparateurs de milliers ; les lignes affichent le montant et le pourcentage de remise, puis le récapitulatif montre le total net après remises et les bases et montants de taxe. Une taxe est nommée (TVA, etc.) uniquement si une règle fiscale liée à la ligne le permet ; sinon elle est explicitement indiquée comme non catégorisée, sans lui attribuer une nature fiscale inventée. Les polices de la charte sont embarquées localement et le rendu n'a pas besoin d'accéder à Internet.

## Erreurs courantes

Les erreurs métier renvoient un objet JSON avec un champ `detail`, par exemple `{"detail":"Document not found"}`.

| HTTP | Signification habituelle |
|---|---|
| `401` | Jeton absent/invalide ou identifiants incorrects |
| `403` | Rôle insuffisant ou compte inactif |
| `404` | Ressource inexistante |
| `409` | Conflit d'état métier, par exemple document non revu ou anomalie bloquante |
| `413` | Fichier trop volumineux |
| `415` | Type de fichier non pris en charge |
| `422` | UUID, paramètres, corps JSON ou fichier invalide |
