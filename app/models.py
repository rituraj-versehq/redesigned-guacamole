from typing import Any

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    gstin: Mapped[str | None] = mapped_column(String, nullable=True)
    vendor_code: Mapped[str | None] = mapped_column(String, nullable=True)


class EntityFieldDefinition(Base):
    __tablename__ = "entity_field_definitions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String)
    entity_type: Mapped[str] = mapped_column(String)
    field_name: Mapped[str] = mapped_column(String)
    field_type: Mapped[str] = mapped_column(String)


class SourceRecord(Base):
    __tablename__ = "source_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String)
    tenant_id: Mapped[str] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class SourceFieldMapping(Base):
    __tablename__ = "source_field_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String)
    source_field: Mapped[str] = mapped_column(String)
    target_field: Mapped[str] = mapped_column(String)
    field_role: Mapped[str] = mapped_column(String)
    storage: Mapped[str] = mapped_column(String)


class EntityFieldValue(Base):
    __tablename__ = "entity_field_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String)
    field_name: Mapped[str] = mapped_column(String)
    value: Mapped[Any] = mapped_column(JSON)
    source_type: Mapped[str] = mapped_column(String)


class EntityIdentifier(Base):
    __tablename__ = "entity_identifiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String)
    identifier_type: Mapped[str] = mapped_column(String)
    identifier_value: Mapped[str] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String)


class EntityHistory(Base):
    __tablename__ = "entity_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String)
    field_name: Mapped[str] = mapped_column(String)
    old_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    source_type: Mapped[str] = mapped_column(String)
