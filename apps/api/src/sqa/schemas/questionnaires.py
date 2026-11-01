import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from sqa.models import QuestionnaireKind, QuestionnaireStatus


class QuestionnaireOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    kind: QuestionnaireKind
    size_bytes: int
    status: QuestionnaireStatus
    error_code: str | None
    extractor: str | None
    question_count: int
    uploaded_by: str | None
    created_at: datetime
    processed_at: datetime | None


class QuestionnaireDetailOut(QuestionnaireOut):
    # Column mapping for spreadsheets/tables ("source": "detected" or "user").
    mapping: dict[str, Any] | None
    # First rows of each sheet, for choosing the mapping.
    preview: dict[str, Any] | None


class QuestionnaireUploadOut(BaseModel):
    questionnaire: QuestionnaireOut
    duplicate: bool


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ordinal: int
    ref: str | None
    section: str | None
    text: str
    locator: dict[str, Any]
    excluded: bool
    edited: bool


class QuestionPage(BaseModel):
    items: list[QuestionOut]
    total: int


class SheetMappingIn(BaseModel):
    sheet: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    # None: the sheet has no header row; questions start on the first row.
    header_row: int | None = Field(default=None, ge=0, le=1000)
    question_col: int = Field(ge=0, le=500)
    answer_col: int | None = Field(default=None, ge=0, le=500)
    ref_col: int | None = Field(default=None, ge=0, le=500)
    comment_col: int | None = Field(default=None, ge=0, le=500)


class MappingIn(BaseModel):
    sheets: list[SheetMappingIn] = Field(min_length=1, max_length=50)


class QuestionPatch(BaseModel):
    text: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=4000)]
        | None
    ) = None
    excluded: bool | None = None
