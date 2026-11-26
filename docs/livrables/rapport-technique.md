# Livrable 4 — Rapport technique FaktSure

**Projet :** FaktSure — automatisation de la préparation de factures à partir de documents commerciaux

**Cadre :** Hackathon BWAI 2026

**État décrit :** backend implémenté, sans frontend de démonstration livré

**Référence applicative vérifiée :** commit `aba680b`
**Date de vérification des tests :** 26 novembre 2026

> **Périmètre de preuve.** Ce rapport sépare les fonctions présentes, les résultats des tests logiciels et les performances IA. La suite automatisée passe, mais aucun jeu de factures annotées ni essai comparatif chronométré avec des utilisateurs n'est conservé dans le dépôt. Nous ne présentons donc pas de taux d'exactitude IA ni de gain de temps comme résultats mesurés.

## 1. Besoin et réponse proposée

La préparation manuelle d'une facture à partir d'un bon de commande, d'un devis ou d'un autre document commercial demande de recopier l'identité client, les lignes, les quantités, les prix, les remises et les montants. Il faut ensuite contrôler les incohérences, calculer les taxes, préparer le document final et conserver une trace des décisions. Les erreurs de saisie ou d'interprétation sont particulièrement coûteuses lorsque les montants ou les règles fiscales sont mal appliqués.

FaktSure vise à réduire la ressaisie en extrayant des données structurées au moyen d'un LLM, tout en conservant une validation métier déterministe et une revue humaine obligatoire. Le système est une aide à la préparation : il ne décide pas seul de la conformité fiscale, n'émet pas auprès d'une administration et ne réalise pas de paiement.

Le périmètre implémenté comprend l'authentification JWT et les rôles, l'import de lots, l'extraction des PDF natifs, le rapprochement avec des référentiels, la détection d'anomalies, les corrections, la revue, les brouillons de facture, le calcul des remises et de la TVA, la génération PDF, R2 pour les PDF émis, les réglages d'émetteur, l'audit et la documentation OpenAPI. Il n'existe pas encore de frontend applicatif dans le dépôt; la démonstration fonctionnelle peut s'appuyer sur Swagger.

## 2. Parcours utilisateur livré

1. Un `ACCOUNTANT` crée un lot et importe un ou plusieurs documents. Les signatures de fichiers et tailles sont contrôlées; SHA-256 permet d'identifier les doublons. L'import n'appelle pas automatiquement le LLM.
2. L'utilisateur déclenche l'extraction d'un PDF natif ou le traitement du lot. PyMuPDF extrait le texte et les blocs; le fournisseur configuré retourne un objet JSON avec les champs et lignes demandés.
3. Les données sont persistées comme champs extraits, avec valeur originale, éventuelle correction, confiance et éléments source quand une correspondance est retrouvée. Des contrôles recherchent les champs manquants, valeurs peu étayées, doublons, écarts de prix et incohérences de totaux.
4. Un utilisateur habilité consulte l'original, corrige les valeurs et résout les anomalies bloquantes. La revue nécessite une confirmation; les avertissements ouverts exigent une décision consignée.
5. Un `ACCOUNTANT` ou `ADMIN` crée un brouillon à partir d'un document en état `READY`. Le backend recalcule les montants avec `Decimal` et refuse les données non cohérentes.
6. Un `VALIDATOR` ou `ADMIN` émet le brouillon. Le numéro définitif est attribué, puis le PDF est écrit dans R2 avant que l'émission soit finalisée. Une défaillance R2 bloque l'émission.

Les rôles et limites sont appliqués par route : `ADMIN` gère les utilisateurs, réglages, audit et référentiels; `ACCOUNTANT` traite les documents et brouillons, avec lecture seule des référentiels; `VALIDATOR` consulte, révise/rejette et émet, sans accès à l'audit ni écriture de référentiel.

## 3. Architecture et contrôles

Le projet est un monolithe FastAPI utilisant Pydantic, SQLAlchemy et Alembic. SQLite convient à la démonstration sur volume persistant; PostgreSQL est pris en charge et utilisé par Compose local. Les documents utilisent un stockage local et, lorsque activé, une copie R2. Les PDF émis nécessitent R2. Chromium headless rend les factures à partir d'un template HTML/CSS Jinja et de polices embarquées.

Les interfaces LLM sont interchangeables entre Gemini, Groq et Cloudflare Workers AI. La base relationnelle contient utilisateurs, lots, documents, champs extraits, anomalies, clients, produits, tarifs, règles de TVA, factures, lignes, séquence de numérotation, paramètres non secrets et événements d'audit.

Contrôles importants :

- JWT signé et vérification du compte actif; hash de mot de passe et absence de route d'inscription.
- Autorisations RBAC et tests d'accès interdit.
- Limitation de taille, contrôle de type/signature et déduplication par empreinte pour les fichiers.
- Vérification SHA-256 à la lecture des artefacts.
- Aucune création de facture si le document n'a pas été revu ou si un blocage subsiste.
- Calcul côté serveur avec décimaux; relation vérifiée : `grand_total = subtotal - discount_total + tax_total`.
- TVA soit par ligne, soit par règle unique globale; les deux modes sont exclusifs. Les remises sont déduites avant le calcul.
- Journalisation des opérations sensibles sans journaliser les credentials.
- PDF d'émission persisté dans R2 avant validation de l'émission.
- CORS fermé par défaut et origines explicites uniquement.

Limites d'architecture : l'extraction réellement disponible porte sur les PDF natifs textuels; l'OCR d'image/scans n'est pas fourni. Les tâches de traitement de lots sont séquentielles et en mémoire dans le processus; la reprise au redémarrage est codée, mais il n'y a pas de broker ni de garantie « exactly once ». Une instance API est recommandée pour la démo. La configuration de l'émetteur est globale à une instance, sans multi-entreprise.

## 4. Protocole et résultats des tests

### Protocole reproductible

Les tests sont exécutés avec Python 3.12+ et les dépendances de `backend/requirements.txt` :

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

Les tests automatisés emploient des bases SQLite isolées, des documents synthétiques, des fournisseurs LLM simulés et des stockages simulés lorsque nécessaire. Cela rend la suite reproductible sans divulguer de credentials ni appeler un modèle facturable. Le test d'intégration principal fabrique un PDF synthétique, simule la réponse structurée, réalise le parcours de revue et facture, génère un PDF et vérifie les totaux et états.

### Résultats logiciel

Au 26 novembre 2026, sur la référence applicative `aba680b` :

- **48 tests passent** dans `backend/tests`.
- Le parcours d'intégration document → extraction simulée → revue → brouillon → émission → téléchargement PDF est couvert.
- Les tests unitaires couvrent calculs, remises, TVA par ligne et globale, validation des règles, lecture/écriture des réglages, CORS, import de références, droits des rôles et génération/documentation OpenAPI.
- Le test `test_recovery_requeues_interrupted_extraction` confirme qu'un document laissé `EXTRACTING` redevient `QUEUED` lors de la routine de récupération.
- `alembic upgrade head` a été exécuté avec succès sur une base SQLite temporaire vierge, jusqu'à la migration `8b7c1d9a42e6`.
- Aucune clé de fournisseur ni bucket R2 réels n'a été nécessaire à cette suite.

Ces résultats démontrent la cohérence du code testé, pas la précision d'extraction de modèles en production. La suite de workflow simule le fournisseur, le stockage et le rendu selon les tests; elle n'est pas un essai de charge, un test de restauration Railway ni une mesure de disponibilité externe.

### Tests encore nécessaires avant une expérimentation terrain

1. Constituer un corpus autorisé et anonymisé de documents représentatifs, avec vérité terrain revue par deux personnes.
2. Geler fournisseur et identifiant modèle; faire une évaluation réelle, journaliser usages/erreurs/coûts et conserver les résultats.
3. Mesurer précision/rappel des champs et lignes, exactitude exacte/normalisée des montants, taux de champs manquants et taux de revue manuelle.
4. Comparer les temps d'exécution et de correction sur le même corpus avec le processus manuel de référence.
5. Tester une coupure réelle en environnement de staging, restauration de sauvegarde, limites mémoire, R2 et comportement en cas de timeout fournisseur.

## 5. Comparaison au processus de référence

La référence fonctionnelle est une préparation manuelle : lecture du document, ressaisie des données, contrôle, calcul, production du PDF et validation par un responsable. Aucun temps de référence observé, échantillon de factures ni coût salarial n'est fourni dans le dépôt; toute différence chiffrée serait spéculative.

| Étape | Référence manuelle | FaktSure actuellement | Effet attendu, non mesuré |
|---|---|---|---|
| Lecture et ressaisie | Opérateur lit puis recopie | Texte PDF natif transmis au LLM | Réduire la ressaisie sur les documents pris en charge. |
| Contrôle | Vérifications manuelles | Contrôles déterministes et anomalies affichables | Rendre certaines incohérences plus systématiques. |
| Correction | Correction dans le support de travail | Champ corrigé et auteur/événement persistés | Améliorer la traçabilité. |
| Calcul | Feuille/calculateur ou logiciel | Decimal et formule serveur après remise | Réduire les erreurs de calcul; taux métier toujours à configurer. |
| Validation | Approbation responsable | Route réservée au validateur/admin | Garder une séparation de fonctions. |
| Archivage | Classement selon procédure interne | Fichier original et PDF émis stockables, intégrité SHA-256 | Faciliter le retéléchargement si les services persistants sont opérationnels. |

La comparaison doit être quantifiée lors du pilote avec le même lot de documents, en mesurant temps actif, nombre de corrections, erreurs résiduelles et coût LLM. Jusqu'à cette mesure, la proposition est une hypothèse de gain et non un résultat démontré.

## 6. Coûts estimatifs d'usage

L'API n'enregistre pas actuellement le nombre de tokens par extraction. Les valeurs ci-dessous sont donc une **projection de scénario**, pas une facture réelle ni le coût observé dans le hackathon.

Pour donner un ordre de grandeur reproductible, on prend le modèle Cloudflare Workers AI `@cf/meta/llama-3.3-70b-instruct-fp8-fast` publié à **0,293 USD / million de tokens d'entrée** et **2,253 USD / million de tokens de sortie** sur la page officielle consultée le 26 novembre 2026. Le code autorise ce modèle via `CLOUDFLARE_MODEL`, mais il n'est pas défini par défaut. Hypothèses par document natif : 2 000–10 000 tokens d'entrée (texte + prompt) et 300–1 200 tokens de sortie JSON.

```text
coût/document = tokens entrée / 1 000 000 × 0,293
             + tokens sortie / 1 000 000 × 2,253
```

| Volume de documents | Estimation variable LLM USD |
|---:|---:|
| 1 | environ 0,0013–0,0057 USD |
| 100 | environ 0,13–0,56 USD |
| 1 000 | environ 1,26–5,63 USD |

La fourchette dépend fortement du texte, du nombre de lignes, du JSON généré, des reprises et des tokens réellement facturés. Vérifier les tarifs, modèles, limites gratuites et conditions de données au moment du gel; les prix peuvent évoluer. Les offres Gemini/Groq ont des règles et prix distincts et ne sont pas incluses dans cette estimation.

Sont exclus : hébergement Railway, stockage/transactions/egress R2, base, trafic, supervision, sauvegardes, temps de revue humaine et coûts d'intégration. Leur estimation requiert une durée de pilote, un volume d'archives, la taille moyenne des fichiers et le plan de service exact. Le quota gratuit Cloudflare Workers AI est limité en Neurons/jour et ne doit pas être interprété comme une capacité garantie sans connaître la consommation réelle.

Source tarifaire : [Cloudflare Workers AI — Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/), consultée le 26 novembre 2026.

## 7. Limites, risques et étapes d'expérimentation

Les risques principaux sont une extraction erronée ou incomplète, une ambiguïté de client ou de taxe, une variation de disponibilité/qualité des modèles, l'envoi de données commerciales à un fournisseur tiers, l'absence d'OCR, une interruption du traitement en mémoire et la persistance du PDF dépendante de R2. La confiance affichée est un indicateur heuristique fondé sur la présence d'une correspondance avec le texte source et/ou la valeur de confiance d'une ligne; elle n'est pas une probabilité statistiquement calibrée.

Avant le pilote :

1. Décider du modèle et du fournisseur, vérifier conditions et politiques de conservation, puis consigner la version effective.
2. Vérifier les licences de toutes les dépendances et résoudre le point PyMuPDF AGPL/commercial; le fichier `LICENSE` du dépôt est vide.
3. Faire valider les taux de TVA, exonérations et mentions du PDF par une personne compétente.
4. Ajouter un vrai frontend ou préparer une démonstration Swagger guidée; le présent dépôt n'a pas de UI utilisateur.
5. Préparer sauvegarde/restauration, base PostgreSQL, monitoring et file de tâches durable si l'usage dépasse une démonstration mono-instance.
6. Évaluer un corpus autorisé et comparer au processus manuel sans présenter l'extraction comme décision finale.
