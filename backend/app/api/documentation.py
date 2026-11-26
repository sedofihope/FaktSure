"""Documentation française injectée dans le schéma OpenAPI FastAPI."""

API_DESCRIPTION = """
## Bien démarrer

Toutes les routes sont préfixées par `/api`. Swagger est disponible sur `/docs`
et le schéma OpenAPI brut sur `/openapi.json`. Les identifiants transmis dans
les URL et les relations entre ressources sont des UUID `public_id`, jamais les
clés numériques internes.

Pour les routes protégées, cliquer sur **Authorize** et saisir le jeton obtenu
avec `POST /api/auth/login` sous la forme `Bearer <jeton>`. Les rôles sont
`ADMIN`, `ACCOUNTANT` et `VALIDATOR`. Chaque opération indique les rôles admis.
Un `401` signifie que le jeton est absent ou invalide ; un `403` indique que le
rôle ne permet pas l'opération.

## Parcours conseillé : document vers facture

1. Créer un lot (`POST /api/batches`), puis importer un ou plusieurs fichiers
   avec `POST /api/batches/{batch_id}/documents` en multipart et le champ
   `files`. L'import conserve le document mais ne lance pas l'extraction IA.
2. Extraire un PDF natif avec `POST /api/documents/{document_id}/extract`, ou
   mettre en traitement les PDF natifs d'un lot avec
   `POST /api/batches/{batch_id}/process`. Le traitement de lot répond `202` :
   consulter son avancement avec `GET /api/batches/{batch_id}`. L'extraction
   appelle le fournisseur IA configuré et peut entraîner une consommation
   facturée par ce fournisseur.
3. Lire les données extraites (`/fields`) et leurs anomalies (`/anomalies`).
   Corriger les champs ou lever les anomalies bloquantes, puis examiner
   l'original avec `/preview`. Une revue explicite est requise avant la facture.
4. Créer le brouillon avec `POST /api/invoices`. Le backend reprend par défaut
   les champs relus, associe le client actif, recalcule et vérifie les montants.
   Une ambiguïté ou une incohérence doit être corrigée, pas devinée.
5. Émettre le brouillon avec `POST /api/invoices/{invoice_id}/validate`, puis
   télécharger son PDF avec `GET /api/invoices/{invoice_id}/pdf`. L'émission
   exige un stockage R2 configuré et disponible.

## États et erreurs

Les réponses métier de succès sont décrites par opération. Les erreurs JSON
utilisent généralement `{"detail":"..."}`. `404` indique une ressource absente,
`409` un conflit d'état ou de règle métier, `413` un fichier trop volumineux,
`415` un format non pris en charge, `422` une requête invalide et `503` une
dépendance nécessaire indisponible. Les listes sont retournées sous forme de
tableaux JSON ; les PDF et aperçus sont des réponses binaires.

Les traitements par lot et les appels IA sont déclenchés explicitement : le
téléversement ne lance pas de traitement en arrière-plan. Les tâches en cours
vivent dans le processus API ; conserver une seule instance pour cette
configuration de démonstration.
"""

TAGS_METADATA = [
    {
        "name": "health",
        "description": "Disponibilité de l'API et environnement d'exécution.",
    },
    {
        "name": "authentication",
        "description": "Connexion par identifiants et lecture du compte connecté.",
    },
    {
        "name": "batches",
        "description": "Création et suivi des lots, import de fichiers et traitement IA séquentiel.",
    },
    {
        "name": "documents",
        "description": "Consultation, extraction, correction, anomalies, revue et rejet des documents.",
    },
    {
        "name": "clients",
        "description": "Répertoire des clients utilisés pour rapprocher les factures.",
    },
    {
        "name": "products",
        "description": "Catalogue des produits et services facturables.",
    },
    {
        "name": "references",
        "description": "Règles de TVA, historique de prix et import CSV/XLSX des référentiels (réservés à l'administrateur en écriture).",
    },
    {
        "name": "invoices",
        "description": "Brouillons, émission contrôlée et téléchargement des PDF de facture.",
    },
    {
        "name": "users",
        "description": "Gestion des comptes et des rôles, réservée aux administrateurs.",
    },
    {
        "name": "settings",
        "description": "Lecture de configuration et mise à jour des réglages non secrets.",
    },
    {
        "name": "audit",
        "description": "Historique chronologique des actions métier et administratives.",
    },
]

# Chaque clé correspond à la méthode HTTP et au chemin OpenAPI complet.
OPERATIONS = {
    ("get", "/api/health"): (
        "Vérifier la disponibilité de l'API",
        "Retourne un statut léger pour le contrôle de santé de l'hébergeur. "
        "Cette route ne vérifie pas la disponibilité du fournisseur IA ou du stockage documentaire.",
        (),
    ),
    ("post", "/api/auth/login"): (
        "Ouvrir une session",
        "Authentifie un compte actif avec son adresse e-mail et son mot de passe. "
        "La réponse contient un jeton JWT Bearer à envoyer dans `Authorization` "
        "pour les routes protégées. Identifiants erronés : `401`; compte désactivé : `403`.",
        (401, 403),
    ),
    ("get", "/api/auth/me"): (
        "Lire le compte connecté",
        "Retourne le profil de l'utilisateur associé au jeton Bearer : UUID public, "
        "nom, e-mail, rôle et état actif. N'expose jamais le hash du mot de passe. "
        "Rôles admis : `ADMIN`, `ACCOUNTANT`, `VALIDATOR`.",
        (401,),
    ),
    ("post", "/api/batches"): (
        "Créer un lot de documents",
        "Crée un lot vide qui servira à regrouper les imports et suivre leur traitement. "
        "Retourne son UUID public, son nom, ses compteurs et son état initial. "
        "Rôles admis : `ADMIN`, `ACCOUNTANT`.",
        (401, 403, 422),
    ),
    ("get", "/api/batches"): (
        "Lister les lots",
        "Retourne les lots du plus récent au plus ancien avec leurs compteurs "
        "(documents importés, traités et en échec) et leur état. "
        "Rôles admis : `ADMIN`, `ACCOUNTANT`, `VALIDATOR`.",
        (401, 403),
    ),
    ("get", "/api/batches/{batch_id}"): (
        "Consulter un lot",
        "Retourne les détails et la progression d'un lot identifié par son UUID public. "
        "Après un traitement accepté, interroger cette route pour suivre les compteurs "
        "et attendre `COMPLETED` ou `PARTIALLY_COMPLETED`. "
        "Rôles admis : `ADMIN`, `ACCOUNTANT`, `VALIDATOR`.",
        (401, 403, 404),
    ),
    ("post", "/api/batches/{batch_id}/documents"): (
        "Importer des documents dans un lot",
        "Téléverse un ou plusieurs PDF ou images via `multipart/form-data`; sélectionner "
        "le ou les fichiers dans le champ `files`. Chaque élément de `results` indique "
        "`uploaded`, `duplicate` ou `error`, son UUID, son SHA-256 et un message éventuel. "
        "Les fichiers vides, trop volumineux, les MIME non autorisés et les signatures "
        "de contenu invalides sont refusés individuellement; une erreur sur un fichier "
        "n'annule pas les autres. Un doublon SHA-256 n'est pas réimporté. L'import "
        "ne déclenche pas l'extraction IA. Rôles admis : `ADMIN`, `ACCOUNTANT`.",
        (401, 403, 404, 413, 415, 422),
    ),
    ("post", "/api/batches/{batch_id}/process"): (
        "Mettre en traitement les PDF du lot",
        "Place en file les documents PDF natifs éligibles et déclenche leur extraction "
        "et leur validation d'anomalies en tâche de fond, de façon séquentielle. "
        "Répond `202` avec l'identifiant du lot et le nombre de documents en file; "
        "suivre ensuite `GET /api/batches/{batch_id}`. `retry_failed=true` inclut les "
        "documents précédemment en échec. Les appels IA peuvent être facturés. "
        "Un lot déjà en traitement ou sans document éligible renvoie `409`. "
        "Rôles admis : `ADMIN`, `ACCOUNTANT`.",
        (401, 403, 404, 409),
    ),
    ("get", "/api/documents/{document_id}"): (
        "Consulter un document",
        "Retourne les métadonnées du document, son lot, son type détecté, son empreinte "
        "SHA-256 et son état de traitement. Le contenu original se consulte via `/preview`. "
        "Rôles admis : `ADMIN`, `ACCOUNTANT`, `VALIDATOR`.",
        (401, 403, 404),
    ),
    ("get", "/api/documents/{document_id}/preview"): (
        "Afficher le fichier original",
        "Retourne le contenu binaire original avec son type MIME et une disposition "
        "d'affichage inline, pour prévisualisation dans le navigateur. Le frontend peut "
        "ouvrir l'URL dans un nouvel onglet ou lire la réponse comme un Blob. "
        "Rôles admis : `ADMIN`, `ACCOUNTANT`, `VALIDATOR`.",
        (401, 403, 404),
    ),
    ("post", "/api/documents/{document_id}/extract"): (
        "Extraire un PDF natif",
        "Extrait le texte du PDF natif, appelle le fournisseur IA configuré, enregistre "
        "les champs et lignes extraits, puis détecte les anomalies. La réponse contient "
        "les données structurées extraites; consulter `/fields` pour les valeurs "
        "enregistrées avec confiance et provenance. L'opération peut coûter des crédits "
        "au fournisseur IA. Formats non pris en charge ou état incompatible : `409`. "
        "Rôles admis : `ADMIN`, `ACCOUNTANT`.",
        (401, 403, 404, 409),
    ),
    ("get", "/api/documents/{document_id}/fields"): (
        "Lister les champs extraits",
        "Retourne pour chaque champ son nom, sa valeur d'origine, la valeur corrigée "
        "(si présente), son niveau de confiance, son état et sa provenance "
        "(page, texte source, coordonnées). Utiliser `corrected_value` lorsqu'il n'est "
        "pas nul pour afficher la valeur retenue. Rôles admis : tous les rôles métier.",
        (401, 403, 404),
    ),
    ("put", "/api/documents/{document_id}/fields"): (
        "Corriger les champs extraits",
        "Applique une ou plusieurs corrections ciblées, sans remplacer les champs absents "
        "de `corrections`; chaque entrée désigne `field_name` et sa nouvelle "
        "`corrected_value`. Les corrections sont auditées et les anomalies sont "
        "recalculées. La réponse donne le nombre de champs corrigés. Si le document "
        "a déjà un brouillon associé, les champs ne peuvent plus être corrigés. "
        "Rôles admis : `ADMIN`, `ACCOUNTANT`.",
        (401, 403, 404, 409, 422),
    ),
    ("get", "/api/documents/{document_id}/anomalies"): (
        "Lister les anomalies",
        "Retourne les anomalies détectées pour le document : champ concerné, type, "
        "sévérité (`BLOCKER` ou `WARNING`), valeurs comparées et état (`OPEN` ou résolue). "
        "Les anomalies `BLOCKER` ouvertes doivent être corrigées avant la revue. "
        "Rôles admis : tous les rôles métier.",
        (401, 403, 404),
    ),
    ("post", "/api/documents/{document_id}/anomalies/{anomaly_id}/resolve"): (
        "Corriger une anomalie bloquante",
        "Corrige le champ indiqué et relance les contrôles. L'anomalie n'est résolue "
        "que si la correction élimine effectivement le blocage; sinon toute l'opération "
        "est annulée avec `409`. `resolution_note` explique la décision et est conservée "
        "dans l'audit. Rôles admis : `ADMIN`, `ACCOUNTANT`.",
        (401, 403, 404, 409, 422),
    ),
    ("post", "/api/documents/{document_id}/review"): (
        "Confirmer la revue humaine",
        "Fait passer le document à `READY` après revue. `confirmed` doit être vrai; "
        "aucun blocage ouvert ne doit subsister. Si des avertissements restent ouverts, "
        "`warning_decision` est obligatoire et sera consignée; les avertissements sont "
        "alors marqués comme traités. Cette étape est nécessaire avant la création du "
        "brouillon. Rôles admis : tous les rôles métier.",
        (401, 403, 404, 409, 422),
    ),
    ("post", "/api/documents/{document_id}/reject"): (
        "Rejeter un document",
        "Marque le document `REJECTED` et enregistre le motif facultatif `reason` "
        "dans l'historique. Cette action est destinée à clore la revue d'un document "
        "qui ne doit pas produire de facture. Rôles admis : tous les rôles métier.",
        (401, 403, 404, 422),
    ),
    ("get", "/api/clients"): (
        "Lister les clients",
        "Retourne les clients, y compris les fiches inactives, avec leurs identifiants "
        "légaux (IFU, RCCM), coordonnées et état. Les fiches inactives ne sont pas "
        "proposées pour une nouvelle facture. Rôles admis : tous les rôles métier.",
        (401, 403),
    ),
    ("post", "/api/clients"): (
        "Créer un client",
        "Crée une fiche client. Le RCCM, l'IFU et les coordonnées sont facultatifs. "
        "L'UUID public retourné sert aux références dans les autres routes. "
        "Réservé au rôle `ADMIN`; les comptables peuvent consulter les fiches mais pas "
        "modifier les référentiels.",
        (401, 403, 422),
    ),
    ("get", "/api/clients/{client_id}"): (
        "Consulter un client",
        "Retourne la fiche client identifiée par son UUID public, y compris si elle est "
        "inactive. Rôles admis : tous les rôles métier.",
        (401, 403, 404),
    ),
    ("put", "/api/clients/{client_id}"): (
        "Modifier un client",
        "Met à jour uniquement les propriétés présentes dans le corps; omettre un champ "
        "le conserve inchangé. Pour effacer une valeur facultative, envoyer `null`. "
        "Réservé au rôle `ADMIN`.",
        (401, 403, 404, 422),
    ),
    ("delete", "/api/clients/{client_id}"): (
        "Désactiver un client",
        "Désactive la fiche sans supprimer son historique ni ses références aux factures. "
        "Réponse `204` sans corps. Seul `ADMIN` peut effectuer cette opération.",
        (401, 403, 404),
    ),
    ("get", "/api/products"): (
        "Lister les produits",
        "Retourne le catalogue, y compris les produits inactifs, avec SKU, libellé et unité. "
        "Les prix datés sont consultables sur `/products/{product_id}/prices`. "
        "Rôles admis : tous les rôles métier.",
        (401, 403),
    ),
    ("post", "/api/products"): (
        "Créer un produit",
        "Ajoute un produit ou service au catalogue. Le SKU est facultatif mais, s'il est "
        "fourni, il doit être unique. Un doublon renvoie `409`. "
        "Réservé au rôle `ADMIN`.",
        (401, 403, 409, 422),
    ),
    ("get", "/api/products/{product_id}"): (
        "Consulter un produit",
        "Retourne une fiche produit par UUID public, y compris si elle est inactive. "
        "Rôles admis : tous les rôles métier.",
        (401, 403, 404),
    ),
    ("put", "/api/products/{product_id}"): (
        "Modifier un produit",
        "Met à jour uniquement les champs envoyés; les autres restent inchangés. "
        "Envoyer `null` pour effacer une valeur facultative. Un SKU déjà utilisé "
        "par un autre produit renvoie `409`. Réservé au rôle `ADMIN`.",
        (401, 403, 404, 409, 422),
    ),
    ("delete", "/api/products/{product_id}"): (
        "Désactiver un produit",
        "Désactive le produit sans supprimer son historique de prix ni les lignes "
        "de facture déjà créées. Réponse `204` sans corps. Seul `ADMIN` peut agir.",
        (401, 403, 404),
    ),
    ("get", "/api/tax-rules"): (
        "Lister les règles de TVA",
        "Retourne les règles de TVA configurées, leur taux, leur période de validité "
        "et leur état. Dans le parcours actuel, chaque ligne de facture référence au "
        "plus une règle de TVA; la date de facture doit être couverte par sa période "
        "de validité. Tous les rôles métier peuvent consulter les règles.",
        (401, 403),
    ),
    ("post", "/api/tax-rules"): (
        "Créer une règle de TVA",
        "Crée une règle avec un taux compris entre 0 et 100 et des dates de validité "
        "cohérentes. `valid_until` peut être omis pour une validité sans date de fin. "
        "Les montants de TVA sont calculés sur la base de chaque ligne après remise. "
        "Réservé au rôle `ADMIN`.",
        (401, 403, 422),
    ),
    ("get", "/api/products/{product_id}/prices"): (
        "Lister l'historique des prix",
        "Retourne les tarifs du produit, du plus récent au plus ancien, avec devise et "
        "période de validité. `product_id` est l'UUID public du produit. "
        "Rôles admis : tous les rôles métier.",
        (401, 403, 404),
    ),
    ("post", "/api/products/{product_id}/prices"): (
        "Ajouter un prix daté",
        "Ajoute un tarif historique au produit; le prix ne modifie pas les factures "
        "existantes. La devise par défaut est `XOF`; `valid_until` doit être égale "
        "ou postérieure à `valid_from`. Réservé au rôle `ADMIN`.",
        (401, 403, 404, 422),
    ),
    ("post", "/api/references/import"): (
        "Importer des référentiels CSV ou XLSX",
        "Importe des clients, produits ou règles de TVA depuis un fichier `.csv` "
        "UTF-8 ou `.xlsx`. Le nom de fichier détermine le format; une colonne `name` "
        "est obligatoire. La colonne `type` (ou `kind`) vaut `client`, `product` "
        "(défaut) ou `tax`. Colonnes clients : `name`, `tax_identifier`, `rccm`, "
        "`address`, `phone`, `email`. Produits : `name`, `sku`, `description`, `unit`. "
        "TVA (`type=tax`) : `name`, `rate`, `valid_from`, `valid_until`, `calculation_type`. "
        "Les erreurs sont rapportées par ligne dans `errors`; les lignes valides sont "
        "importées. Réservé au rôle `ADMIN`.",
        (401, 403, 413, 415, 422),
    ),
    ("post", "/api/invoices"): (
        "Créer un brouillon de facture",
        "Le document source doit être en état `READY`, sans anomalie bloquante ouverte. "
        "Le corps minimal est `{document_id}`. Sans `items`, le backend reprend les "
        "lignes et montants corrigés après revue; il associe un client actif par IFU/RCCM "
        "ou nom exact, sinon fournir `client_id`. `issue_date` vaut aujourd'hui par "
        "défaut; `due_date` reste vide si absente. La TVA extraite doit correspondre "
        "sans ambiguïté à une règle active pour cette date. Pour appliquer une règle à "
        "toute la facture, fournir le `tax_rule_id` au niveau supérieur : la TVA porte "
        "alors sur `subtotal - discount_total`. Sinon, définir les `tax_rule_id` sur "
        "les lignes pour gérer des taux différents. Les deux modes ne peuvent pas être "
        "mélangés dans une même facture. Avec `items`, les lignes sont remplacées et "
        "tous les montants sont recalculés. La relation vérifiée est "
        "`grand_total = subtotal - discount_total + tax_total`. "
        "Rôles admis : `ADMIN`, `ACCOUNTANT`.",
        (401, 403, 404, 409, 422),
    ),
    ("get", "/api/invoices"): (
        "Lister les factures",
        "Retourne les factures et brouillons du plus récent au plus ancien, avec leur "
        "client, leurs montants et leur état (`DRAFT`, `PENDING_VALIDATION` ou `ISSUED`). "
        "Rôles admis : tous les rôles métier.",
        (401, 403),
    ),
    ("get", "/api/invoices/{invoice_id}"): (
        "Consulter une facture",
        "Retourne les détails d'un brouillon ou d'une facture par UUID public. "
        "Les montants sont sérialisés en chaînes décimales pour éviter les pertes "
        "de précision côté navigateur. Rôles admis : tous les rôles métier.",
        (401, 403, 404),
    ),
    ("put", "/api/invoices/{invoice_id}"): (
        "Modifier l'échéance du brouillon",
        "Seule la date d'échéance (`due_date`) est modifiable par cette route et "
        "uniquement avant émission. Les autres champs sont ignorés par le schéma. "
        "Une facture émise ne peut pas être modifiée (`409`). "
        "Rôles admis : `ADMIN`, `ACCOUNTANT`.",
        (401, 403, 404, 409, 422),
    ),
    ("post", "/api/invoices/{invoice_id}/validate"): (
        "Émettre et valider la facture",
        "Émet un brouillon après contrôles métier, attribue le numéro définitif, "
        "enregistre l'approbation et génère le PDF. Le document doit avoir été revu "
        "et aucun blocage ne doit subsister. R2 doit être configuré et disponible pour "
        "garantir la conservation du PDF; une indisponibilité renvoie `503` sans émission. "
        "Rôles admis : `ADMIN`, `VALIDATOR`.",
        (401, 403, 404, 409, 503),
    ),
    ("get", "/api/invoices/{invoice_id}/pdf"): (
        "Télécharger le PDF de facture",
        "Retourne le PDF en binaire (`application/pdf`) en téléchargement. Le PDF est "
        "créé ou régénéré si nécessaire, puis vérifié à l'aide de son empreinte. "
        "Les brouillons portent le filigrane « BROUILLON — NON ÉMISE ». "
        "Rôles admis : tous les rôles métier.",
        (401, 403, 404, 503),
    ),
    ("get", "/api/audit"): (
        "Consulter le journal d'audit",
        "Retourne les 500 événements les plus récents : auteur, action, ressource, "
        "valeur précédente et nouvelle valeur. Les mots de passe et secrets ne sont "
        "pas journalisés. Réservé au rôle `ADMIN`.",
        (401, 403),
    ),
    ("get", "/api/users"): (
        "Lister les utilisateurs",
        "Retourne les comptes avec UUID public, rôle et état actif. Les hashes de "
        "mot de passe ne sont jamais exposés. Réservé au rôle `ADMIN`.",
        (401, 403),
    ),
    ("post", "/api/users"): (
        "Créer un utilisateur",
        "Crée un compte sans inscription publique. Le mot de passe doit comporter "
        "au moins 12 caractères; les rôles autorisés sont `ADMIN`, `ACCOUNTANT` et "
        "`VALIDATOR`. L'e-mail est normalisé en minuscules et doit être unique. "
        "Réservé au rôle `ADMIN`.",
        (401, 403, 409, 422),
    ),
    ("get", "/api/users/{user_id}"): (
        "Consulter un utilisateur",
        "Retourne le profil public d'un utilisateur par UUID, sans donnée de "
        "mot de passe. Réservé au rôle `ADMIN`.",
        (401, 403, 404),
    ),
    ("put", "/api/users/{user_id}"): (
        "Modifier un utilisateur",
        "Met à jour uniquement les champs envoyés (`full_name`, `role`, `is_active`). "
        "Un administrateur ne peut pas désactiver son propre compte ni supprimer le "
        "dernier administrateur actif. Toute modification est auditée. "
        "Réservé au rôle `ADMIN`.",
        (401, 403, 404, 409, 422),
    ),
    ("get", "/api/settings"): (
        "Lire les réglages effectifs",
        "Retourne les réglages non secrets de traitement, IA, stockage et émetteur. "
        "Les secrets d'API ne sont jamais renvoyés; les indicateurs `configured` "
        "signalent seulement si les identifiants nécessaires sont présents. "
        "Réservé au rôle `ADMIN`.",
        (401, 403),
    ),
    ("put", "/api/settings/processing"): (
        "Modifier les réglages de traitement",
        "Met à jour la taille des lots, le nombre maximal de documents traités en "
        "parallèle et la taille maximale d'import en Mo. Limites respectives : "
        "1–100, 1–32 et 1–500. Les valeurs sont persistées en base. "
        "Réservé au rôle `ADMIN`.",
        (401, 403, 422),
    ),
    ("put", "/api/settings/ai"): (
        "Choisir le fournisseur et le modèle IA",
        "Sélectionne `gemini`, `groq` ou `cloudflare` et le nom du modèle. Les "
        "identifiants du fournisseur doivent déjà être configurés comme variables "
        "d'environnement Railway; cette route ne reçoit ni ne stocke de clé secrète. "
        "Réservé au rôle `ADMIN`.",
        (401, 403, 409, 422),
    ),
    ("put", "/api/settings/storage"): (
        "Choisir le stockage documentaire",
        "Sélectionne `local` ou `r2`. Pour `r2`, les quatre variables "
        "`R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID` et `R2_SECRET_ACCESS_KEY` "
        "doivent être configurées dans l'environnement avant l'appel. "
        "Réservé au rôle `ADMIN`.",
        (401, 403, 409, 422),
    ),
    ("put", "/api/settings/issuer"): (
        "Modifier les coordonnées de l'émetteur",
        "Met à jour partiellement le nom légal, l'adresse, l'identifiant fiscal, "
        "le RCCM, les coordonnées et les modalités de paiement utilisés dans les factures. "
        "Les champs absents restent inchangés; une valeur `null` ou vide efface le champ. "
        "Les modifications sont persistées en base et inscrites au journal d'audit. "
        "Les clés API et autres secrets ne sont pas modifiables par cette route. "
        "Réservé au rôle `ADMIN`.",
        (401, 403, 422),
    ),
}

ERROR_RESPONSE = {
    "description": "La requête a échoué.",
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {
                    "detail": {
                        "type": "string",
                        "description": "Explication lisible de l'erreur.",
                    }
                },
                "required": ["detail"],
            },
            "example": {"detail": "La ressource demandée est introuvable."},
        }
    },
}
