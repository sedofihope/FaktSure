from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class BatchCreate(BaseModel):
    name: str


class BatchResponse(BaseModel):
    public_id: UUID
    name: str
    total_documents: int
    processed_documents: int
    failed_documents: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
