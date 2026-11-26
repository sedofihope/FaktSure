# Livrable 5 — Fiche IA FaktSure

## Système et tâche

FaktSure utilise un LLM distant pour extraire des faits commerciaux d'un document en JSON structuré : type et numéro, dates, devise, client, lignes, quantités, prix, remises, sous-total, taxes/TVA et total. Le prompt (`backend/app/ai/prompts.py`) demande de ne pas inventer les champs absents et de ne pas recalculer les montants. Le backend valide ensuite le schéma, rapproche les valeurs avec le texte source et applique ses propres contrôles métier. Aucun entraînement ni fine-tuning FaktSure n'est réalisé.

| Élément | Déclaration |
|---|---|
| Entrée | Texte extrait d'un PDF natif par PyMuPDF, limité à 30 000 caractères transmis au fournisseur. |
| Sortie | Champs structurés et lignes; les valeurs absentes doivent rester nulles. |
| Fournisseurs configurables | Gemini, Groq ou Cloudflare Workers AI. |
| Valeurs par défaut du code | Gemini `gemini-2.0-flash`; Groq `llama-3.3-70b-versatile`; modèle Cloudflare à configurer via `CLOUDFLARE_MODEL`. |

Le modèle effectivement utilisé dépend des variables du déploiement. Son identifiant/version n'est pas persisté par extraction dans la base ni dans l'audit; on ne peut donc pas déclarer quel modèle a traité une facture réelle. Avant la démonstration évaluée, consigner le fournisseur, l'identifiant exact et la date. Les alias et conditions d'accès peuvent évoluer.

## Données et séparation des jeux

Aucun poids de modèle ni corpus réel annoté n'est livré. Les tests utilisent surtout des documents synthétiques et des réponses de fournisseurs simulées. Il n'existe pas de jeux train/validation/test enregistrés; les échantillons de test ne représentent pas statistiquement les langues, fournisseurs, mises en page ou qualités de documents rencontrés en pratique.

Les textes d'extraction sont envoyés au fournisseur configuré. Pour toute expérimentation réelle, documenter la provenance et l'autorisation des données, anonymiser les documents et vérifier les politiques de conservation et de traitement du fournisseur. Construire un corpus annoté, séparer les jeux par document/client/source pour éviter les doublons, et réserver un jeu final qui n'est pas utilisé pour régler le prompt.

## Évaluation et résultats

Au 26 novembre 2026, 48 tests automatisés passent sur la référence applicative `aba680b`. Ils vérifient notamment le parsing et la validation de sortie, les contrôles métier et un workflow de facture avec fournisseur simulé. **Ils ne mesurent pas la précision d'un modèle réel.** Aucun résultat de justesse, rappel, taux d'hallucination ou benchmark sur factures réelles n'est disponible; ces métriques sont inconnues, pas supposées parfaites.

Protocole à appliquer avant toute affirmation de performance : faire annoter chaque document par deux personnes puis arbitrer les désaccords; geler modèle et prompt; comparer les sorties non corrigées à la vérité terrain. Rapporter l'exactitude des champs, précision/rappel/F1 des lignes, exactitude des montants et TVA, taux de champs manquants et non étayés, erreurs JSON/fournisseur, escalades humaines, latence médiane/p95, tokens et coût. Ventiler les résultats selon la qualité, le format et la complexité, avec taille d'échantillon et incertitude. Les scans et images doivent être considérés non pris en charge, pas mélangés à l'évaluation des PDF natifs.

## Erreurs et limites connues

- PDF scannés, images et PDF mixtes : import/classification possibles, mais l'extraction métier n'est disponible que pour les PDF natifs textuels; l'OCR n'est pas implémenté.
- L'ordre des colonnes/tableaux, le bruit et la limite de 30 000 caractères peuvent faire perdre ou mal interpréter des valeurs.
- JSON invalide, absence de réponse exploitable ou erreur réseau : extraction en échec; pas de stratégie générique d'essais multiples.
- Dates, remises, plusieurs taux de TVA et informations client similaires peuvent être ambigus. Le prompt de non-invention réduit le risque sans le supprimer. Les documents sont des entrées non fiables; une résistance absolue aux instructions malveillantes n'est pas démontrée.
- La version de modèle active n'étant pas conservée par extraction, la reproductibilité historique est limitée.

## Seuils et revue humaine

La confiance est heuristique, non calibrée statistiquement. Pour un champ ordinaire, le service attribue environ `0.85` si la valeur est retrouvée dans le texte source, `0.35` si elle ne l'est pas, et `0` si elle est absente. Pour une ligne, la confiance déclarée par le modèle est plafonnée à `0.85` si sa description est retrouvée et à `0.35` sinon. Une valeur sous `0.5` produit une anomalie `LOW_CONFIDENCE` de niveau `WARNING`.

Ce seuil sert au triage, pas à l'acceptation automatique : **chaque document doit être explicitement revu par un utilisateur habilité avant création de facture**. Les anomalies `BLOCKER` ouvertes empêchent la progression; les avertissements ouverts exigent une décision consignée. L'émission est séparée et requiert `ADMIN` ou `VALIDATOR`. Ces seuils n'ont pas été optimisés sur un corpus annoté.

## Coût et conclusion

L'application ne mesure pas les tokens par requête; le coût réel n'est pas disponible. Une estimation illustrative Cloudflare Workers AI, ses hypothèses et sa source officielle figurent dans le [rapport technique](rapport-technique.md#6-coûts-estimatifs-dusage); elle ne représente pas nécessairement le modèle actif.

FaktSure démontre un pipeline d'intégration contrôlé — extraction, validation, provenance partielle, contrôles déterministes et revue humaine — mais pas encore la performance générale d'un modèle sur des factures réelles ni un gain statistique par rapport au processus manuel. Ces résultats nécessitent un corpus représentatif et une évaluation indépendante.
