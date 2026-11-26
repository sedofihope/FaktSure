from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(description="État de disponibilité de l'API.")
    environment: str = Field(description="Environnement d'exécution configuré.")


class UploadFileResult(BaseModel):
    filename: str | None = Field(description="Nom du fichier fourni par le client.")
    status: str = Field(description="Résultat : uploaded, duplicate ou error.")
    document_id: UUID | None = Field(
        default=None,
        description="UUID public du document importé ou déjà existant.",
    )
    sha256: str | None = Field(default=None, description="Empreinte SHA-256 du contenu.")
    error: str | None = Field(default=None, description="Cause lisible si status vaut error.")


class BatchUploadResponse(BaseModel):
    batch_id: UUID = Field(description="UUID public du lot cible.")
    results: list[UploadFileResult] = Field(description="Un résultat indépendant par fichier envoyé.")


class BatchProcessResponse(BaseModel):
    batch_id: UUID = Field(description="UUID public du lot mis en traitement.")
    status: str = Field(description="État du lot après mise en file, normalement PROCESSING.")
    queued_documents: int = Field(description="Nombre de documents placés en file.")


class ExtractedFieldResponse(BaseModel):
    public_id: UUID = Field(description="UUID public du champ extrait.")
    field_name: str = Field(description="Nom stable du champ métier.")
    value: str | None = Field(description="Valeur originale produite par l'extraction.")
    corrected_value: str | None = Field(description="Valeur corrigée retenue si renseignée.")
    confidence: float = Field(ge=0, le=1, description="Confiance estimée entre 0 et 1.")
    status: str = Field(description="État du champ : RELIABLE, UNCERTAIN, MISSING ou CORRECTED.")
    source_page: int | None = Field(description="Numéro de page source, à partir de 1.")
    source_text: str | None = Field(description="Extrait textuel du document justifiant la valeur.")
    source_bbox: str | None = Field(description="Coordonnées source sérialisées si disponibles.")


class CorrectFieldsResponse(BaseModel):
    status: str = Field(description="Résultat de la correction.")
    count: int = Field(description="Nombre de champs corrigés.")


class AnomalyResponse(BaseModel):
    public_id: UUID = Field(description="UUID public de l'anomalie.")
    field_name: str | None = Field(description="Champ métier concerné, si applicable.")
    anomaly_type: str = Field(description="Code stable du type d'anomalie.")
    severity: str = Field(description="Sévérité : BLOCKER ou WARNING.")
    description: str = Field(description="Explication lisible de l'anomalie.")
    expected_value: str | None = Field(description="Valeur ou règle attendue.")
    actual_value: str | None = Field(description="Valeur constatée.")
    status: str = Field(description="État : OPEN ou résolue.")


class ResolveAnomalyResponse(BaseModel):
    status: str = Field(description="Vaut resolved si la correction a levé le blocage.")
    anomaly_id: UUID = Field(description="UUID public de l'anomalie traitée.")


class DocumentReviewResponse(BaseModel):
    status: str = Field(description="État du document après revue, READY.")
    reviewed_by: int = Field(description="Identifiant interne de l'utilisateur réviseur.")


class DocumentRejectResponse(BaseModel):
    status: str = Field(description="État final du document, REJECTED.")
    rejected_by: int = Field(description="Identifiant interne de l'utilisateur ayant rejeté.")


class ReferenceImportError(BaseModel):
    line: int = Field(description="Numéro de ligne dans le fichier, en comptant l'en-tête.")
    error: str = Field(description="Motif de rejet de la ligne.")


class ReferenceImportResponse(BaseModel):
    imported: int = Field(description="Nombre de lignes importées avec succès.")
    errors: list[ReferenceImportError] = Field(description="Lignes invalides ou en doublon.")


class AuditEntryResponse(BaseModel):
    public_id: UUID = Field(description="UUID public de l'événement d'audit.")
    user_public_id: UUID | None = Field(description="UUID public de l'auteur, si encore disponible.")
    action: str = Field(description="Code de l'action enregistrée.")
    entity_type: str = Field(description="Type de ressource concernée.")
    entity_id: str = Field(description="Identifiant de ressource tel qu'enregistré.")
    previous_value: str | None = Field(description="Valeur précédente, si applicable.")
    new_value: str | None = Field(description="Nouvelle valeur ou décision, si applicable.")
    created_at: datetime = Field(description="Date et heure UTC de l'événement.")


class ProcessingSettingsResponse(BaseModel):
    document_batch_size: int = Field(description="Nombre de documents traités par lot interne.")
    max_document_concurrency: int = Field(description="Nombre maximal de traitements simultanés.")
    max_upload_size_mb: int = Field(description="Taille maximale autorisée par fichier, en Mo.")


class AISettingsResponse(BaseModel):
    provider: str = Field(description="Fournisseur IA actuellement sélectionné.")
    model: str = Field(description="Nom du modèle utilisé.")
    configured: bool = Field(description="Indique si les identifiants du fournisseur sont présents.")
    available_providers: dict[str, bool] = Field(description="Disponibilité configurée par fournisseur.")


class StorageSettingsResponse(BaseModel):
    backend: str = Field(description="Stockage actuellement sélectionné : local ou r2.")
    r2_configured: bool = Field(description="Indique si tous les paramètres R2 sont présents.")


class IssuerSettingsResponse(BaseModel):
    name: str = Field(description="Nom légal de l'émetteur.")
    address: str = Field(description="Adresse de l'émetteur.")
    tax_identifier: str = Field(description="Identifiant fiscal (IFU) de l'émetteur.")
    rccm: str = Field(description="Numéro RCCM de l'émetteur.")
    phone: str = Field(description="Téléphone de l'émetteur.")
    email: str = Field(description="Adresse e-mail de l'émetteur.")
    payment_terms: str = Field(description="Modalités de paiement par défaut.")


class SettingsResponse(BaseModel):
    processing: ProcessingSettingsResponse
    ai: AISettingsResponse
    storage: StorageSettingsResponse
    issuer: IssuerSettingsResponse


class SettingsUpdateResponse(BaseModel):
    status: str = Field(description="Résultat de la mise à jour.")
    processing: ProcessingSettingsResponse | None = None
    provider: str | None = None
    model: str | None = None
    backend: str | None = None
