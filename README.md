# Entity Resolution POC

## Pipeline

1. Upload source CSV.
2. Store raw rows in `source_records`.
3. Stage 1 looks at:
   - source columns
   - sample source rows
   - existing Vendor fields
   - sample Vendor rows
4. Stage 1 saves mappings:
   - source column -> internal Vendor field
5. Stage 2 uses saved mappings to fill data.
6. Stage 2 matches Vendors by strong IDs like GSTIN.

AI is used for mapping only.

Data filling is normal code.

## Example

SAP has existing Vendors:

```text
VEN-101 | ABC LOGISTICS      | 29ABCDE1234F1Z5 | SUP-991
VEN-102 | FastRoad Transport | 27PQRSX8821T1Z8 | SUP-442
```

MegaERP has a large Vendor-like source table:

```text
EXT_VENDOR_ID
SUPPLIER_LEGAL_NAME
TAX_REG_NUM
SUPPLIER_SEGMENT
PAY_TERMS_CODE
RISK_TIER
...
ERP_NOISE_001
ERP_NOISE_002
...
ERP_NOISE_180
```

Internal Vendor also has many existing extra fields.

The test checks whether the mapper can pick useful columns and ignore junk.

## Run Example

### 1. Start Clean

Start clean:

```bash
docker compose down -v
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload
```

What this means:

- DB is empty.
- Tables exist.
- No Vendors are loaded yet.

Check:

```bash
docker compose exec postgres psql -U postgres -d entity_resolution_poc \
  -c "select count(*) from vendors;"
```

Expected:

```text
0
```

PM read:

```text
We are starting from a blank system.
```

### 2. Load Existing SAP Vendors

Upload SAP:

```bash
curl -s -X POST http://127.0.0.1:8000/sources/upload \
  -F source_type=SAP \
  -F file=@data/sap_vendors.csv | jq
```

Observed:

```json
{
  "source_id": "SRC-0d297bd1",
  "rows": 2
}
```

DB effect:

- Raw SAP rows are stored in `source_records`.
- Existing Vendors are created in `vendors`.
- SAP IDs and GSTINs are stored in `entity_identifiers`.
- SAP payment block is stored as an extra field value.

Check Vendors:

```bash
docker compose exec postgres psql -U postgres -d entity_resolution_poc \
  -c "select id,name,gstin,vendor_code from vendors order by id;"
```

Expected:

```text
VEN-101 | ABC LOGISTICS      | 29ABCDE1234F1Z5 | SUP-991
VEN-102 | FastRoad Transport | 27PQRSX8821T1Z8 | SUP-442
```

PM read:

```text
SAP is our existing truth for Vendors.
We now have two Vendors in our system.
```

### 3. Make Internal Vendor Model Large

Seed many internal Vendor fields:

```bash
docker compose exec -T postgres psql -U postgres -d entity_resolution_poc \
  < data/stress/seed_many_vendor_fields.sql
```

Observed:

```text
INSERT 0 125
```

Check field count:

```bash
docker compose exec postgres psql -U postgres -d entity_resolution_poc \
  -c "select count(*) from entity_field_definitions;"
```

Observed:

```text
 count
-------
   126
```

DB effect:

- Internal Vendor now has many possible extra fields.
- Examples: `payment_terms`, `risk_rating`, `tax_country`, `pan_number`.

PM read:

```text
We are testing a realistic case where our system already knows many Vendor fields.
The mapper must choose the right field, not create duplicates.
```

### 4. Upload A Large New Source

Upload wide MegaERP source:

```bash
SRC=$(curl -s -X POST http://127.0.0.1:8000/sources/upload \
  -F source_type=MegaERP \
  -F file=@data/stress/wide_internal_and_source_vendor.csv | jq -r .source_id)
```

DB effect:

- MegaERP rows are stored in `source_records`.
- No Vendor data is changed yet.
- No mappings are created yet.

Check raw rows:

```bash
docker compose exec postgres psql -U postgres -d entity_resolution_poc \
  -c "select source_type, count(*) from source_records group by source_type;"
```

PM read:

```text
We have connected a new source.
At this point, the system has only stored raw source data.
It has not trusted or applied anything yet.
```

### 5. Run Field Mapping

Run mapping:

```bash
curl -s -X POST http://127.0.0.1:8000/sources/$SRC/setup-fields | jq
```

What this step does:

- Looks at MegaERP columns.
- Looks at sample MegaERP rows.
- Looks at internal Vendor fields.
- Decides which source columns mean which Vendor fields.
- Saves those decisions as mappings.

Observed mappings:

```text
TAX_REG_NUM         -> gstin
EXT_VENDOR_ID       -> vendor_code
SUPPLIER_SEGMENT    -> vendor_category
SUPPLIER_LEGAL_NAME -> name
PAYMENT_BLOCK_FLAG  -> payment_blocked
TRANSPORT_PREF      -> preferred_transport_mode
PAY_TERMS_CODE      -> payment_terms
RISK_TIER           -> risk_rating
COMPLIANCE_STATE    -> compliance_status
ONBOARDING_STATE    -> onboarding_status
PROC_REGION         -> procurement_region
PREFERRED_CCY       -> preferred_currency
PAYMENT_METHOD_CODE -> payment_method
TAX_COUNTRY_CODE    -> tax_country
PAN_VALUE           -> pan_number
MSME_ID             -> msme_registration
```

How to read one mapping:

```json
{
  "source_field": "TAX_REG_NUM",
  "target_field": "gstin",
  "field_role": "match_key",
  "storage": "main_column"
}
```

PM read:

```text
MegaERP calls the tax ID TAX_REG_NUM.
Our system calls it gstin.
Use this field to match existing Vendors.
Store it directly on the Vendor row.
```

Another mapping:

```json
{
  "source_field": "RISK_TIER",
  "target_field": "risk_rating",
  "field_role": "value",
  "storage": "extra_field"
}
```

PM read:

```text
MegaERP calls this RISK_TIER.
Our system already has risk_rating.
Copy the value into the Vendor's extra fields.
```

Bad mapping found:

```json
{
  "source_field": "EXT_VENDOR_ID",
  "target_field": "vendor_code",
  "field_role": "identifier",
  "storage": "identifier"
}
```

PM read:

```text
This is close but not ideal.
EXT_VENDOR_ID is MegaERP's Vendor ID.
It should be stored as megaerp_vendor_id, not vendor_code.
This tells us we need a stronger rule for source-specific IDs.
```

Check saved mappings:

```bash
docker compose exec postgres psql -U postgres -d entity_resolution_poc \
  -c "select source_field,target_field,field_role,storage from source_field_mappings order by id;"
```

Observed:

```text
    source_field     |       target_field       | field_role |   storage
---------------------+--------------------------+------------+-------------
 TAX_REG_NUM         | gstin                    | match_key  | main_column
 EXT_VENDOR_ID       | vendor_code              | identifier | identifier
 SUPPLIER_SEGMENT    | vendor_category          | value      | extra_field
 SUPPLIER_LEGAL_NAME | name                     | value      | main_column
 PAYMENT_BLOCK_FLAG  | payment_blocked          | value      | extra_field
 TRANSPORT_PREF      | preferred_transport_mode | value      | extra_field
 PAY_TERMS_CODE      | payment_terms            | value      | extra_field
 RISK_TIER           | risk_rating              | value      | extra_field
 COMPLIANCE_STATE    | compliance_status        | value      | extra_field
 ONBOARDING_STATE    | onboarding_status        | value      | extra_field
 PROC_REGION         | procurement_region       | value      | extra_field
 PREFERRED_CCY       | preferred_currency       | value      | extra_field
 PAYMENT_METHOD_CODE | payment_method           | value      | extra_field
 TAX_COUNTRY_CODE    | tax_country              | value      | extra_field
 PAN_VALUE           | pan_number               | value      | extra_field
 MSME_ID             | msme_registration        | value      | extra_field
```

DB effect:

- `source_field_mappings` now has 16 rows.
- These rows are the saved translation rules.
- No Vendor data has been filled yet.

PM read:

```text
The system learned how to translate MegaERP columns into our Vendor model.
This mapping can be reused for later MegaERP uploads.
```

### 6. Check If Junk Was Ignored

Run:

```bash
docker compose exec postgres psql -U postgres -d entity_resolution_poc \
  -c "select source_field,target_field from source_field_mappings where source_field like 'ERP_NOISE%' or source_field in ('CREATED_BY','CREATED_AT','UPDATED_AT');"
```

Expected:

```text
0 rows
```

PM read:

```text
The source had many junk columns.
The mapper did not blindly import everything.
That is important because real customer tables are messy.
```

### 7. Fill Vendor Data

Only run this after checking mappings.

```bash
curl -s -X POST http://127.0.0.1:8000/sources/$SRC/populate | jq
```

What this step does:

- Reads saved mappings.
- Uses GSTIN to find existing Vendors.
- Updates existing Vendors.
- Creates new Vendors when no match exists.
- Stores extra values.
- Stores identifiers.
- Stores history.

Check Vendors:

```bash
docker compose exec postgres psql -U postgres -d entity_resolution_poc \
  -c "select id,name,gstin,vendor_code from vendors order by id;"
```

PM read:

```text
This is the actual data fill step.
AI is not deciding row by row.
Normal code is applying saved mappings.
```

Check extra values:

```bash
docker compose exec postgres psql -U postgres -d entity_resolution_poc \
  -c "select entity_id,field_name,value,source_type from entity_field_values order by entity_id,field_name;"
```

PM read:

```text
This shows flexible Vendor facts like risk_rating and payment_terms.
They are queryable and source-aware.
```

Check history:

```bash
docker compose exec postgres psql -U postgres -d entity_resolution_poc \
  -c "select entity_id,field_name,old_value,new_value,source_type from entity_history order by id;"
```

PM read:

```text
This shows what changed and which source changed it.
```

## Findings

Good:

- It found the GSTIN field.
- It found the Vendor name field.
- It reused many existing internal fields.
- It ignored the `ERP_NOISE_*` columns.
- It ignored `CREATED_BY`, `CREATED_AT`, and `UPDATED_AT`.

Needs fixing:

- `EXT_VENDOR_ID` should not become `vendor_code`.
- Better mapping:

```text
EXT_VENDOR_ID -> megaerp_vendor_id
field_role    -> identifier
storage       -> identifier
```

## Why Not Just JSON

JSON is flexible but becomes messy.

Example:

```json
{
  "name": "ABC Logistics",
  "Vendor_Name__c": "ABC Logistics Pvt Ltd",
  "supplierName": "ABC LOGISTICS"
}
```

Now it is unclear which name is correct.

It is also harder to query cleanly:

```text
Show all vendors with risk_rating = Low
```

## Why Not One Huge Vendor Table

A 350-column Vendor table guesses the future.

Most columns stay empty.

New sources still bring new fields.

Every new field needs a schema decision.

## Our Approach

Keep core Vendor clean:

```text
vendors:
id, name, gstin, vendor_code
```

Store flexible facts separately:

```text
entity_field_values:
VEN-101, risk_rating, Low, MegaERP
VEN-101, payment_terms, NET30, MegaERP
```

Store mappings clearly:

```text
TAX_REG_NUM -> gstin
RISK_TIER   -> risk_rating
```

This gives us:

- flexibility like JSON
- cleaner querying than JSON
- less schema bloat than a 350-column table
- source-aware values
- reusable mappings
- deterministic data filling

## Why This Scales Better

Real example:

```text
SAP calls the field SupplierName.
Salesforce calls it Vendor_Name__c.
MegaERP calls it SUPPLIER_LEGAL_NAME.
```

All three can map to:

```text
Vendor.name
```

So our system stores one clean Vendor name field and three reusable mappings:

```text
SupplierName         -> name
Vendor_Name__c       -> name
SUPPLIER_LEGAL_NAME  -> name
```

With JSON, this becomes messy:

```json
{
  "SupplierName": "ABC LOGISTICS",
  "Vendor_Name__c": "ABC Logistics Pvt Ltd",
  "SUPPLIER_LEGAL_NAME": "ABC Logistics Pvt Ltd"
}
```

Problem:

```text
Which one should the product show?
Which one should search use?
Which one changed last?
```

With a 350-column table, we keep adding columns:

```text
supplier_name
vendor_name
supplier_legal_name
account_name
display_name
name_1
name_2
```

Problem:

```text
The table grows forever.
Most columns are empty.
Every new source creates another schema debate.
```

Our approach scales because new source systems mostly add mappings, not new database columns.

Example:

```text
New source field: RISK_TIER
Existing internal field: risk_rating
Action: save mapping RISK_TIER -> risk_rating
```

No schema change needed.

If the source has a truly new useful fact:

```text
New source field: CARBON_REPORTING_TIER
No internal field exists.
Action: create one extra field, then map to it.
```

So growth is controlled:

```text
Known concept -> reuse existing field
New useful concept -> add one extra field
Junk column -> ignore
```

That is why this approach works better when:

- there are many source systems
- each source has different names
- each source has hundreds of columns
- most columns are irrelevant
- new customer schemas keep appearing
