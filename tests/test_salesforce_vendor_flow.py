from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    EntityFieldDefinition,
    EntityFieldValue,
    EntityHistory,
    EntityIdentifier,
    SourceFieldMapping,
    Vendor,
)
from app.services.source_loader import load_source
from app.services.stage1_field_setup import setup_fields
from app.services.stage2_value_population import populate_vendors

CLASSIFIER_OUTPUT = {
    "matches_entity": True,
    "entity_type": "vendor",
    "new_fields": [
        {"field_name": "vendor_category", "field_type": "text"},
        {"field_name": "preferred_transport_mode", "field_type": "text"},
    ],
    "mappings": [
        {
            "source_field": "GSTIN__c",
            "target_field": "gstin",
            "field_role": "match_key",
            "storage": "main_column",
        },
        {
            "source_field": "Vendor_Name__c",
            "target_field": "name",
            "field_role": "value",
            "storage": "main_column",
        },
        {
            "source_field": "Credit_Hold__c",
            "target_field": "payment_blocked",
            "field_role": "value",
            "storage": "extra_field",
        },
        {
            "source_field": "Vendor_Category__c",
            "target_field": "vendor_category",
            "field_role": "value",
            "storage": "extra_field",
        },
        {
            "source_field": "Preferred_Transport_Mode__c",
            "target_field": "preferred_transport_mode",
            "field_role": "value",
            "storage": "extra_field",
        },
        {
            "source_field": "Id",
            "target_field": "salesforce_vendor_id",
            "field_role": "identifier",
            "storage": "identifier",
        },
    ],
}


def test_salesforce_updates_existing_sap_vendor(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    classifier_calls = []
    monkeypatch.setattr(
        "app.ai.pipeline_field_mapper.classify_source_table_for_entity",
        lambda source_object, source_shape, entity: fake_classifier(
            classifier_calls, source_object, source_shape, entity
        ),
    )

    seed_sap_vendor(
        TestingSessionLocal,
        tenant_id="T1",
        name="ABC LOGISTICS",
        gstin="29ABCDE1234F1Z5",
        vendor_code="SUP-991",
    )

    db = TestingSessionLocal()
    source_id = load_source(
        db,
        "Salesforce",
        [
            {
                "Id": "SF-V-900",
                "Vendor_Name__c": "ABC Logistics Pvt Ltd",
                "GSTIN__c": "29ABCDE1234F1Z5",
                "Vendor_Category__c": "Strategic",
                "Preferred_Transport_Mode__c": "Road",
                "Credit_Hold__c": False,
            }
        ],
    )

    setup_fields(db, source_id)
    populate_vendors(db, source_id)

    vendor = get_vendor_by_gstin(db, "29ABCDE1234F1Z5")

    assert vendor.name == "ABC Logistics Pvt Ltd"
    assert get_extra(db, vendor.id)["vendor_category"] == "Strategic"
    assert get_extra(db, vendor.id)["preferred_transport_mode"] == "Road"
    assert get_identifiers(db, vendor.id)["salesforce_vendor_id"] == "SF-V-900"
    assert len(db.scalars(select(SourceFieldMapping)).all()) == 6
    assert classifier_calls[0]["source_object"]["name"] == (
        "salesforce.Supplier_Account__c"
    )
    assert classifier_calls[0]["entity"]["entity_type"] == "vendor"
    assert db.scalars(
        select(EntityHistory).where(EntityHistory.entity_id == vendor.id)
    ).all()
    db.close()


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


def fake_classifier(classifier_calls, source_object, source_shape, entity):
    classifier_calls.append(
        {
            "source_object": source_object,
            "source_shape": source_shape,
            "entity": entity,
        }
    )
    return CLASSIFIER_OUTPUT


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
