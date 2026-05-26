from typing import Any

from sqlalchemy.orm import Session

from ..ai.field_mapper import run_source_mapping_agent


def setup_fields(db: Session, source_id: str) -> dict[str, Any]:
    output = run_source_mapping_agent(db, source_id)
    validate_output(output)
    return output


def validate_output(output: dict[str, Any]) -> None:
    if output["entity_type"] != "vendor":
        raise ValueError("entity_type must be vendor")

    for mapping in output["mappings"]:
        for key in ["source_field", "target_field", "field_role", "storage"]:
            mapping[key]
