from __future__ import annotations
from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import verify_api_key
from app.db.session import get_db
from app.schemas.car import CarRead, DetectionCreate
from app.services import detection_service

router = APIRouter(prefix="/detections", tags=["detections"])

@router.post(
    "",
    response_model=CarRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
)
async def create_detection(
    request: Request,
    payload: DetectionCreate = Depends(DetectionCreate.as_form),
    image_crop: UploadFile = File(...),
    image_full: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    return await detection_service.create_detection(db, request, payload, image_crop, image_full)