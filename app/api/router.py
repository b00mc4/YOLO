from fastapi import APIRouter
from app.api.endpoints import auth, detection

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(detection.router)