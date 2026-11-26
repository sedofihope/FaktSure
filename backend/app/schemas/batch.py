from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class BatchCreate(BaseModel):
    name: str = Field(description="Nom lisible du lot.")


class BatchResponse(BaseModel):
    public_id: UUID = Field(description="UUID public à utiliser dans les routes.")
    name: str = Field(description="Nom du lot.")
    total_documents: int = Field(description="Nombre total de documents importés.")
    processed_documents: int = Field(description="Nombre de documents traités.")
    failed_documents: int = Field(description="Nombre de documents en échec.")
    status: str = Field(description="État du lot : CREATED, PROCESSING, COMPLETED ou PARTIALLY_COMPLETED.")
    created_at: datetime = Field(description="Date de création UTC.")
    updated_at: datetime = Field(description="Date de dernière mise à jour UTC.")

    model_config = {"from_attributes": True}
