import json
import os
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EntityFieldDefinition, SourceFieldMapping, SourceRecord, Vendor
from ..services.source_loader import TENANT_ID, ensure_field

load_dotenv()


def run_pipeline_field_mapper(db: Session, source_id: str) -> dict[str, Any]:
    for source_object in discover_source_objects(db, source_id):
        source_shape = inspect_source_object(db, source_object["source_id"])

        for entity in internal_entities(db):
            decision = classify_source_table_for_entity(
                source_object, source_shape, entity
            )
            if decision.get("matches_entity"):
                save_decision(db, source_id, decision)

    db.commit()
    return saved_mapping_output(db, source_id)


def discover_source_objects(db: Session, source_id: str) -> list[dict[str, Any]]:
    records = source_records(db, source_id)
    return [
        {
            "name": source_object_name(records[0].source_type),
            "source_id": source_id,
            "source_type": records[0].source_type,
            "rows": len(records),
        }
    ]


def inspect_source_object(db: Session, source_id: str) -> dict[str, Any]:
    records = source_records(db, source_id)
    return {
        "columns": list(records[0].data.keys()),
        "sample_rows": [record.data for record in records[:5]],
    }


def internal_entities(db: Session) -> list[dict[str, Any]]:
    return [vendor_entity(db)]


def vendor_entity(db: Session) -> dict[str, Any]:
    extra_fields = db.scalars(
        select(EntityFieldDefinition).where(
            EntityFieldDefinition.tenant_id == TENANT_ID,
            EntityFieldDefinition.entity_type == "vendor",
        )
    ).all()
    vendors = db.scalars(select(Vendor).limit(5)).all()

    return {
        "entity_type": "vendor",
        "main_fields": [
            {"name": "name", "type": "text"},
            {"name": "gstin", "type": "text", "role": "strong_identifier"},
            {"name": "vendor_code", "type": "text", "role": "strong_identifier"},
        ],
        "extra_fields": [
            {"name": field.field_name, "type": field.field_type}
            for field in extra_fields
        ],
        "sample_rows": [
            {
                "id": vendor.id,
                "name": vendor.name,
                "gstin": vendor.gstin,
                "vendor_code": vendor.vendor_code,
            }
            for vendor in vendors
        ],
    }


def classify_source_table_for_entity(
    source_object: dict[str, Any],
    source_shape: dict[str, Any],
    entity: dict[str, Any],
) -> dict[str, Any]:
    model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), temperature=0)
    response = model.invoke(
        [
            (
                "system",
                (
                    "Return JSON only. "
                    "Only map a source table to Vendor if it has at least one "
                    "strong Vendor identifier: "
                    "- GSTIN / tax registration "
                    "- supplier id / vendor id / vendor code "
                    "- explicit vendor role/type flag. "
                    "If not, return matches_entity=false and empty mappings. "
                    "Generic Id must not map to vendor_code. "
                    "Output shape: "
                    '{"matches_entity": true, "entity_type": "vendor", '
                    '"new_fields": [{"field_name": "vendor_category", '
                    '"field_type": "text"}], "mappings": [{"source_field": '
                    '"GSTIN__c", "target_field": "gstin", "field_role": '
                    '"match_key", "storage": "main_column"}]}. '
                    "Use field_role match_key, value, or identifier. Use storage "
                    "main_column, extra_field, or identifier."
                ),
            ),
            (
                "user",
                json.dumps(
                    {
                        "source_object": source_object,
                        "source_shape": source_shape,
                        "internal_entity": entity,
                    }
                ),
            ),
        ]
    )
    return parse_json_response(response.content)


def save_decision(db: Session, source_id: str, decision: dict[str, Any]) -> None:
    for field in decision.get("new_fields", []):
        ensure_field(db, field["field_name"], field["field_type"])

    for mapping in decision["mappings"]:
        db.add(
            SourceFieldMapping(
                source_id=source_id,
                source_field=mapping["source_field"],
                target_field=mapping["target_field"],
                field_role=mapping["field_role"],
                storage=mapping["storage"],
            )
        )


def saved_mapping_output(db: Session, source_id: str) -> dict[str, Any]:
    return {
        "entity_type": "vendor",
        "mappings": [
            {
                "source_field": mapping.source_field,
                "target_field": mapping.target_field,
                "field_role": mapping.field_role,
                "storage": mapping.storage,
            }
            for mapping in db.scalars(
                select(SourceFieldMapping)
                .where(SourceFieldMapping.source_id == source_id)
                .order_by(SourceFieldMapping.id)
            ).all()
        ],
    }


def source_records(db: Session, source_id: str) -> list[SourceRecord]:
    return db.scalars(
        select(SourceRecord)
        .where(SourceRecord.source_id == source_id)
        .order_by(SourceRecord.id)
    ).all()


def source_object_name(source_type: str) -> str:
    if source_type == "Salesforce":
        return "salesforce.Supplier_Account__c"
    return source_type


def parse_json_response(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```", 2)[1]
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content)
