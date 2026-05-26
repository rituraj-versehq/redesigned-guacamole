import csv
import io

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import PopulateResponse, SetupFieldsResponse, UploadResponse
from ..services.source_loader import load_source
from ..services.stage1_field_setup import setup_fields
from ..services.stage2_value_population import populate_vendors

router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("/upload", response_model=UploadResponse)
async def upload_source(
    source_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = (await file.read()).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(content)))
    source_id = load_source(db, source_type, rows)
    return UploadResponse(source_id=source_id, rows=len(rows))


@router.post("/{source_id}/setup-fields", response_model=SetupFieldsResponse)
def run_setup_fields(source_id: str, db: Session = Depends(get_db)):
    return setup_fields(db, source_id)


@router.post("/{source_id}/populate", response_model=PopulateResponse)
def run_population(source_id: str, db: Session = Depends(get_db)):
    vendors = populate_vendors(db, source_id)
    return PopulateResponse(vendor_ids=[vendor.id for vendor in vendors])
