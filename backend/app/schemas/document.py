from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    public_id: UUID
    batch_id: UUID = Field(validation_alias="batch_public_id")
    original_filename: str
    mime_type: str
    file_size: int
    document_type: str
    classification_confidence: float
    processing_engine: str | None
    storage_backend: str
    sha256: str
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImportFileResult(BaseModel):
    filename: str
    status: str
    document_id: UUID | None = None
    sha256: str | None = None
    error: str | None = None
