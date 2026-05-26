import csv
import io

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import (
    EntityFieldDefinition,
    EntityFieldValue,
    EntityIdentifier,
    SourceFieldMapping,
    Vendor,
)


def test_salesforce_updates_existing_sap_vendor(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    tool_names = []
    monkeypatch.setattr(
        "app.ai.field_mapper.invoke_langchain_agent",
        lambda model, tools, source_id, system_prompt: run_scripted_tools(
            tools, tool_names
        ),
    )

    try:
        with TestClient(app) as client:
            seed_sap_vendor(
                TestingSessionLocal,
                tenant_id="T1",
                name="ABC LOGISTICS",
                gstin="29ABCDE1234F1Z5",
                vendor_code="SUP-991",
            )

            source_id = upload_salesforce_row(
                client,
                {
                    "Id": "SF-V-900",
                    "Vendor_Name__c": "ABC Logistics Pvt Ltd",
                    "GSTIN__c": "29ABCDE1234F1Z5",
                    "Vendor_Category__c": "Strategic",
                    "Preferred_Transport_Mode__c": "Road",
                    "Credit_Hold__c": False,
                },
            )

            client.post(f"/sources/{source_id}/setup-fields")
            client.post(f"/sources/{source_id}/populate")

            db = TestingSessionLocal()
            vendor = get_vendor_by_gstin(db, "29ABCDE1234F1Z5")

            assert vendor.name == "ABC Logistics Pvt Ltd"
            assert get_extra(db, vendor.id)["vendor_category"] == "Strategic"
            assert get_extra(db, vendor.id)["preferred_transport_mode"] == "Road"
            assert get_identifiers(db, vendor.id)["salesforce_vendor_id"] == "SF-V-900"
            assert len(db.scalars(select(SourceFieldMapping)).all()) == 6
            assert tool_names[:5] == [
                "list_source_objects",
                "describe_source_object",
                "sample_source_rows",
                "describe_internal_entity",
                "list_existing_vendors",
            ]
            assert client.get(f"/vendors/{vendor.id}/history").json()["history"]
            db.close()
    finally:
        app.dependency_overrides.clear()


def seed_sap_vendor(session_factory, tenant_id, name, gstin, vendor_code):
    db = session_factory()
    db.add(
        EntityFieldDefinition(
            id="FIELD-1",
            tenant_id=tenant_id,
            entity_type="vendor",
            field_name="payment_blocked",
            field_type="boolean",
        )
    )
    db.add(
        Vendor(
            id="VEN-101",
            tenant_id=tenant_id,
            name=name,
            gstin=gstin,
            vendor_code=vendor_code,
        )
    )
    db.add(
        EntityIdentifier(
            entity_id="VEN-101",
            identifier_type="gstin",
            identifier_value=gstin,
            source_type="SAP",
        )
    )
    db.add(
        EntityIdentifier(
            entity_id="VEN-101",
            identifier_type="sap_vendor_id",
            identifier_value=vendor_code,
            source_type="SAP",
        )
    )
    db.commit()
    db.close()


def upload_salesforce_row(client, row):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(row.keys()))
    writer.writeheader()
    writer.writerow(row)
    response = client.post(
        "/sources/upload",
        data={"source_type": "Salesforce"},
        files={"file": ("salesforce_vendors.csv", output.getvalue(), "text/csv")},
    )
    return response.json()["source_id"]


def run_scripted_tools(tools, tool_names):
    tools_by_name = {tool.name: tool for tool in tools}
    calls = [
        ("list_source_objects", {}),
        ("describe_source_object", {"object_name": "salesforce.Supplier_Account__c"}),
        (
            "sample_source_rows",
            {"object_name": "salesforce.Supplier_Account__c", "limit": 5},
        ),
        ("describe_internal_entity", {"entity_type": "vendor"}),
        ("list_existing_vendors", {"limit": 5}),
        (
            "create_extra_field",
            {
                "entity_type": "vendor",
                "field_name": "vendor_category",
                "field_type": "text",
            },
        ),
        (
            "create_extra_field",
            {
                "entity_type": "vendor",
                "field_name": "preferred_transport_mode",
                "field_type": "text",
            },
        ),
        (
            "save_mapping",
            {
                "source_field": "GSTIN__c",
                "target_field": "gstin",
                "field_role": "match_key",
                "storage": "main_column",
            },
        ),
        (
            "save_mapping",
            {
                "source_field": "Vendor_Name__c",
                "target_field": "name",
                "field_role": "value",
                "storage": "main_column",
            },
        ),
        (
            "save_mapping",
            {
                "source_field": "Credit_Hold__c",
                "target_field": "payment_blocked",
                "field_role": "value",
                "storage": "extra_field",
            },
        ),
        (
            "save_mapping",
            {
                "source_field": "Vendor_Category__c",
                "target_field": "vendor_category",
                "field_role": "value",
                "storage": "extra_field",
            },
        ),
        (
            "save_mapping",
            {
                "source_field": "Preferred_Transport_Mode__c",
                "target_field": "preferred_transport_mode",
                "field_role": "value",
                "storage": "extra_field",
            },
        ),
        (
            "save_mapping",
            {
                "source_field": "Id",
                "target_field": "salesforce_vendor_id",
                "field_role": "identifier",
                "storage": "identifier",
            },
        ),
        ("finish", {"entity_type": "vendor"}),
    ]

    for name, arguments in calls:
        tool_names.append(name)
        tools_by_name[name].invoke(arguments)

    return {"messages": []}


def get_vendor_by_gstin(db, gstin):
    return db.scalar(select(Vendor).where(Vendor.gstin == gstin))


def get_extra(db, vendor_id):
    values = db.scalars(
        select(EntityFieldValue).where(EntityFieldValue.entity_id == vendor_id)
    ).all()
    return {value.field_name: value.value for value in values}


def get_identifiers(db, vendor_id):
    identifiers = db.scalars(
        select(EntityIdentifier).where(EntityIdentifier.entity_id == vendor_id)
    ).all()
    return {
        identifier.identifier_type: identifier.identifier_value
        for identifier in identifiers
    }
