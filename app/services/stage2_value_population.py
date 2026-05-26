from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    EntityFieldValue,
    EntityIdentifier,
    SourceFieldMapping,
    SourceRecord,
    Vendor,
)
from .history_service import save_history
from .source_loader import TENANT_ID, next_vendor_id
from .vendor_matcher import find_vendor_by_gstin, find_vendor_by_identifier


def populate_vendors(db: Session, source_id: str) -> list[Vendor]:
    records = db.scalars(
        select(SourceRecord).where(SourceRecord.source_id == source_id)
    ).all()
    mappings = db.scalars(
        select(SourceFieldMapping).where(SourceFieldMapping.source_id == source_id)
    ).all()

    vendors = [
        process_vendor_row(db, record.data, mappings, TENANT_ID, record.source_type)
        for record in records
    ]
    db.commit()
    return vendors


def process_vendor_row(
    db: Session,
    row: dict[str, Any],
    mappings: list[SourceFieldMapping],
    tenant_id: str,
    source_type: str,
) -> Vendor:
    gstin = read_mapped_value(row, mappings, "gstin")
    vendor = find_vendor_by_gstin(db, tenant_id, gstin)

    if vendor is None:
        identifier_mapping = next(
            (mapping for mapping in mappings if mapping.field_role == "identifier"),
            None,
        )
        if identifier_mapping:
            vendor = find_vendor_by_identifier(
                db,
                tenant_id,
                identifier_mapping.target_field,
                row.get(identifier_mapping.source_field),
            )

    if vendor is None:
        vendor = Vendor(
            id=next_vendor_id(db),
            tenant_id=tenant_id,
            name=read_mapped_value(row, mappings, "name"),
            gstin=gstin,
        )
        db.add(vendor)
        db.flush()

    update_main_fields(db, vendor, row, mappings, source_type)
    upsert_identifiers(db, vendor, row, mappings, source_type)
    upsert_extra_field_values(db, vendor, row, mappings, source_type)
    return vendor


def read_mapped_value(
    row: dict[str, Any], mappings: list[SourceFieldMapping], target_field: str
) -> Any:
    mapping = next(
        (mapping for mapping in mappings if mapping.target_field == target_field),
        None,
    )
    if not mapping:
        return None
    return row.get(mapping.source_field)


def update_main_fields(
    db: Session,
    vendor: Vendor,
    row: dict[str, Any],
    mappings: list[SourceFieldMapping],
    source_type: str,
) -> None:
    for mapping in mappings:
        if mapping.storage != "main_column":
            continue
        value = row.get(mapping.source_field)
        old_value = getattr(vendor, mapping.target_field)
        setattr(vendor, mapping.target_field, value)
        save_history(db, vendor.id, mapping.target_field, old_value, value, source_type)


def upsert_extra_field_values(
    db: Session,
    vendor: Vendor,
    row: dict[str, Any],
    mappings: list[SourceFieldMapping],
    source_type: str,
) -> None:
    for mapping in mappings:
        if mapping.storage != "extra_field":
            continue

        value = row.get(mapping.source_field)
        existing = db.scalar(
            select(EntityFieldValue).where(
                EntityFieldValue.entity_id == vendor.id,
                EntityFieldValue.field_name == mapping.target_field,
            )
        )
        if existing:
            old_value = existing.value
            existing.value = value
            existing.source_type = source_type
        else:
            old_value = None
            db.add(
                EntityFieldValue(
                    entity_id=vendor.id,
                    field_name=mapping.target_field,
                    value=value,
                    source_type=source_type,
                )
            )

        save_history(db, vendor.id, mapping.target_field, old_value, value, source_type)


def upsert_identifiers(
    db: Session,
    vendor: Vendor,
    row: dict[str, Any],
    mappings: list[SourceFieldMapping],
    source_type: str,
) -> None:
    for mapping in mappings:
        if mapping.storage != "identifier":
            continue

        value = row.get(mapping.source_field)
        existing = db.scalar(
            select(EntityIdentifier).where(
                EntityIdentifier.entity_id == vendor.id,
                EntityIdentifier.identifier_type == mapping.target_field,
            )
        )
        if existing:
            old_value = existing.identifier_value
            existing.identifier_value = value
            existing.source_type = source_type
        else:
            old_value = None
            db.add(
                EntityIdentifier(
                    entity_id=vendor.id,
                    identifier_type=mapping.target_field,
                    identifier_value=value,
                    source_type=source_type,
                )
            )

        save_history(db, vendor.id, mapping.target_field, old_value, value, source_type)
