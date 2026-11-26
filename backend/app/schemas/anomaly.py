from pydantic import BaseModel, ConfigDict, Field


class FieldCorrection(BaseModel):
    field_name: str = Field(min_length=1, max_length=100)
    corrected_value: str = Field(min_length=1, max_length=10000)


class CorrectFieldsRequest(BaseModel):
    corrections: list[FieldCorrection] = Field(min_length=1)


class DocumentReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = Field(
        description="Explicitly confirm that the extracted document was reviewed."
    )
    warning_decision: str | None = Field(
        default=None,
        min_length=3,
        max_length=1000,
        description="Required when open warning anomalies exist; records the reviewer's decision.",
    )


class DocumentRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(
        default=None,
        min_length=3,
        max_length=1000,
        description="Optional reason for rejecting the document.",
    )


class ResolveAnomalyRequest(FieldCorrection):
    resolution_note: str = Field(min_length=3, max_length=1000)