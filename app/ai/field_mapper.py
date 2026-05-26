import os
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    EntityFieldDefinition,
    SourceFieldMapping,
    SourceRecord,
    Vendor,
)
from ..services.source_loader import TENANT_ID, ensure_field

load_dotenv()


def run_source_mapping_agent(db: Session, source_id: str) -> dict[str, Any]:
    state = {"done": False}
    tools = build_tools(db, source_id, state)
    model = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), temperature=0)

    invoke_langchain_agent(
        model=model,
        tools=tools,
        source_id=source_id,
        system_prompt=(
            "You are an entity-resolution setup agent. Explore the connected source "
            "with tools, inspect our internal DB with tools, then create only the "
            "Vendor extra fields and mappings needed for value population. Do not "
            "guess when a tool can inspect it. Call finish after saving mappings."
        ),
    )

    db.commit()
    return saved_mapping_output(db, source_id)


def invoke_langchain_agent(
    model: ChatOpenAI,
    tools: list[Any],
    source_id: str,
    system_prompt: str,
):
    agent = create_agent(model=model, tools=tools, system_prompt=system_prompt)
    return agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"A source was connected with source_id={source_id}. "
                        "Investigate it incrementally and create the Vendor mappings."
                    ),
                }
            ]
        },
        config={"recursion_limit": 20},
    )


def build_tools(db: Session, source_id: str, state: dict[str, Any]) -> list[Any]:
    @tool
    def list_source_objects() -> dict[str, Any]:
        """List objects available in the connected source."""
        records = source_records(db, source_id)
        return {
            "objects": [
                {
                    "name": source_object_name(records[0].source_type),
                    "source_id": source_id,
                    "rows": len(records),
                }
            ]
        }

    @tool
    def describe_source_object(object_name: str) -> dict[str, Any]:
        """Read columns for a connected source object."""
        records = source_records(db, source_id)
        return {
            "object": source_object_name(records[0].source_type),
            "columns": list(records[0].data.keys()),
        }

    @tool
    def sample_source_rows(object_name: str, limit: int = 5) -> dict[str, Any]:
        """Read sample rows from a connected source object."""
        return {"rows": [record.data for record in source_records(db, source_id)[:limit]]}

    @tool
    def describe_internal_entity(entity_type: str) -> dict[str, Any]:
        """Inspect the current internal Vendor entity shape."""
        extra_fields = db.scalars(
            select(EntityFieldDefinition).where(
                EntityFieldDefinition.tenant_id == TENANT_ID,
                EntityFieldDefinition.entity_type == "vendor",
            )
        ).all()
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
        }

    @tool
    def list_existing_vendors(limit: int = 5) -> dict[str, Any]:
        """Inspect current Vendor rows for matching context."""
        vendors = db.scalars(select(Vendor).limit(limit)).all()
        return {
            "vendors": [
                {
                    "id": vendor.id,
                    "name": vendor.name,
                    "gstin": vendor.gstin,
                    "vendor_code": vendor.vendor_code,
                }
                for vendor in vendors
            ]
        }

    @tool
    def create_extra_field(
        entity_type: str, field_name: str, field_type: str
    ) -> dict[str, str]:
        """Create a Vendor extra field."""
        ensure_field(db, field_name, field_type)
        return {"created": field_name}

    @tool
    def save_mapping(
        source_field: str,
        target_field: str,
        field_role: str,
        storage: str,
    ) -> dict[str, str]:
        """Save one source-to-Vendor field mapping."""
        db.add(
            SourceFieldMapping(
                source_id=source_id,
                source_field=source_field,
                target_field=target_field,
                field_role=field_role,
                storage=storage,
            )
        )
        return {"saved": target_field}

    @tool
    def finish(entity_type: str) -> dict[str, bool]:
        """Finish once the Vendor mappings have been saved."""
        state["done"] = True
        return {"done": True}

    return [
        list_source_objects,
        describe_source_object,
        sample_source_rows,
        describe_internal_entity,
        list_existing_vendors,
        create_extra_field,
        save_mapping,
        finish,
    ]


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
