from typing import Any

from pydantic import BaseModel


class UploadResponse(BaseModel):
    source_id: str
    rows: int


class SetupFieldsResponse(BaseModel):
    entity_type: str
    mappings: list[dict[str, Any]]


class PopulateResponse(BaseModel):
    vendor_ids: list[str]


class VendorResponse(BaseModel):
    id: str
    tenant_id: str
    name: str | None
    gstin: str | None
    vendor_code: str | None
    extra: dict[str, Any]
    identifiers: dict[str, str]


class HistoryResponse(BaseModel):
    history: list[dict[str, Any]]
