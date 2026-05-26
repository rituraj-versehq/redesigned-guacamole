import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    EntityFieldDefinition,
    EntityFieldValue,
    EntityIdentifier,
    SourceRecord,
    Vendor,
)

TENANT_ID = "T1"


def load_source(db: Session, source_type: str, rows: list[dict[str, Any]]) -> str:
    source_id = f"SRC-{uuid.uuid4().hex[:8]}"
    parsed_rows = [{key: parse_value(value) for key, value in row.items()} for row in rows]
    
    for row in parsed_rows:
        db.add(
            SourceRecord(
                source_id=source_id,
                tenant_id=TENANT_ID,
                source_type=source_type,
                data=row,
            )
        )

    if source_type == "SAP":
        load_sap_vendors(db, parsed_rows)

    db.commit()
    return source_id


def load_sap_vendors(db: Session, rows: list[dict[str, Any]]) -> None:
    ensure_field(db, "payment_blocked", "boolean")

    for row in rows:
        vendor = Vendor(
            id=next_vendor_id(db),
            tenant_id=TENANT_ID,
            name=row.get("SupplierName"),
            gstin=row.get("GSTNumber"),
            vendor_code=row.get("SupplierId"),
        )
        db.add(vendor)
        db.flush()

        db.add(
            EntityFieldValue(
                entity_id=vendor.id,
                field_name="payment_blocked",
                value=row.get("PaymentBlockStatus"),
                source_type="SAP",
            )
        )
        db.add(
            EntityIdentifier(
                entity_id=vendor.id,
                identifier_type="gstin",
                identifier_value=row.get("GSTNumber"),
                source_type="SAP",
            )
        )
        db.add(
            EntityIdentifier(
                entity_id=vendor.id,
                identifier_type="sap_vendor_id",
                identifier_value=row.get("SupplierId"),
                source_type="SAP",
            )
        )


def ensure_field(db: Session, field_name: str, field_type: str) -> None:
    existing = db.scalar(
        select(EntityFieldDefinition).where(
            EntityFieldDefinition.tenant_id == TENANT_ID,
            EntityFieldDefinition.entity_type == "vendor",
            EntityFieldDefinition.field_name == field_name,
        )
    )
    if existing:
        return

    db.add(
        EntityFieldDefinition(
            id=next_field_id(db),
            tenant_id=TENANT_ID,
            entity_type="vendor",
            field_name=field_name,
            field_type=field_type,
        )
    )


def next_vendor_id(db: Session) -> str:
    ids = db.scalars(select(Vendor.id)).all()
    numbers = [int(value.split("-")[1]) for value in ids if value.startswith("VEN-")]
    return f"VEN-{max(numbers, default=100) + 1}"


def next_field_id(db: Session) -> str:
    ids = db.scalars(select(EntityFieldDefinition.id)).all()
    numbers = [int(value.split("-")[1]) for value in ids if value.startswith("FIELD-")]
    return f"FIELD-{max(numbers, default=0) + 1}"


def parse_value(value: Any) -> Any:
    if isinstance(value, str) and value.lower() == "true":
        return True
    if isinstance(value, str) and value.lower() == "false":
        return False
    return value
