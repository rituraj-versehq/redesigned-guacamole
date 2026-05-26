from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import EntityFieldValue, EntityHistory, EntityIdentifier, Vendor
from ..schemas import HistoryResponse, VendorResponse

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("/{vendor_id}", response_model=VendorResponse)
def get_vendor(vendor_id: str, db: Session = Depends(get_db)):
    vendor = db.get(Vendor, vendor_id)
    values = db.scalars(
        select(EntityFieldValue).where(EntityFieldValue.entity_id == vendor_id)
    ).all()
    identifiers = db.scalars(
        select(EntityIdentifier).where(EntityIdentifier.entity_id == vendor_id)
    ).all()
    return VendorResponse(
        id=vendor.id,
        tenant_id=vendor.tenant_id,
        name=vendor.name,
        gstin=vendor.gstin,
        vendor_code=vendor.vendor_code,
        extra={value.field_name: value.value for value in values},
        identifiers={
            identifier.identifier_type: identifier.identifier_value
            for identifier in identifiers
        },
    )


@router.get("/{vendor_id}/history", response_model=HistoryResponse)
def get_vendor_history(vendor_id: str, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(EntityHistory)
        .where(EntityHistory.entity_id == vendor_id)
        .order_by(EntityHistory.id)
    ).all()
    return HistoryResponse(
        history=[
            {
                "field_name": row.field_name,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "source_type": row.source_type,
            }
            for row in rows
        ]
    )
