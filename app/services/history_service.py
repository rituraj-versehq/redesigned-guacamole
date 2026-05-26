from typing import Any

from sqlalchemy.orm import Session

from ..models import EntityHistory


def save_history(
    db: Session,
    entity_id: str,
    field_name: str,
    old_value: Any,
    new_value: Any,
    source_type: str,
) -> None:
    if old_value == new_value:
        return

    db.add(
        EntityHistory(
            entity_id=entity_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            source_type=source_type,
        )
    )
