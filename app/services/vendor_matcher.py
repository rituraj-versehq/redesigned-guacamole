from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EntityIdentifier, Vendor


def find_vendor_by_gstin(db: Session, tenant_id: str, gstin: str | None) -> Vendor | None:
    if not gstin:
        return None

    return db.scalar(
        select(Vendor).where(Vendor.tenant_id == tenant_id, Vendor.gstin == gstin)
    )


def find_vendor_by_identifier(
    db: Session, tenant_id: str, identifier_type: str, identifier_value: str | None
) -> Vendor | None:
    if not identifier_value:
        return None

    identifier = db.scalar(
        select(EntityIdentifier).where(
            EntityIdentifier.identifier_type == identifier_type,
            EntityIdentifier.identifier_value == identifier_value,
        )
    )
    if not identifier:
        return None

    return db.scalar(
        select(Vendor).where(
            Vendor.id == identifier.entity_id,
            Vendor.tenant_id == tenant_id,
        )
    )
