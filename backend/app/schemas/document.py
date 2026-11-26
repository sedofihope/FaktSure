from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    public_id: UUID = Field(description="UUID public à utiliser dans les routes.")
    batch_id: UUID = Field(validation_alias="batch_public_id", description="UUID public du lot parent.")
    original_filename: str = Field(description="Nom original du fichier importé.")
    mime_type: str = Field(description="Type MIME détecté à partir du contenu.")
    file_size: int = Field(description="Taille originale du fichier en octets.")
    document_type: str = Field(description="Type détecté, par exemple NATIVE_PDF.")
    classification_confidence: float = Field(description="Confiance de la classification entre 0 et 1.")
    processing_engine: str | None = Field(description="Moteur ayant extrait le document, si traité.")
    storage_backend: str = Field(description="Backend interne contenant l'original.")
    sha256: str = Field(description="Empreinte SHA-256 servant à détecter les doublons.")
    status: str = Field(description="État du document dans le parcours d'extraction et de revue.")
    error_message: str | None = Field(description="Détail du dernier échec, le cas échéant.")
    created_at: datetime = Field(description="Date de création UTC.")
    updated_at: datetime = Field(description="Date de dernière mise à jour UTC.")

    model_config = {"from_attributes": True}


class ImportFileResult(BaseModel):
    filename: str = Field(description="Nom du fichier fourni par le client.")
    status: str = Field(description="Résultat de l'import.")
    document_id: UUID | None = Field(default=None, description="UUID public du document.")
    sha256: str | None = Field(default=None, description="Empreinte SHA-256 du fichier.")
    error: str | None = Field(default=None, description="Cause de l'échec, le cas échéant.")
