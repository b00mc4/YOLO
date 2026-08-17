from fastapi import APIRouter
from app.api.endpoints import auth, detection, camera, villages, blacklist, whitelist, contacts, audit_logs, users, sse, reports

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(detection.router)
api_router.include_router(camera.router)
api_router.include_router(villages.router)
api_router.include_router(blacklist.router)
api_router.include_router(whitelist.router)
api_router.include_router(contacts.router)
api_router.include_router(audit_logs.router)
api_router.include_router(reports.router)
api_router.include_router(sse.router)
