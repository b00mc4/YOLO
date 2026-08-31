import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings
from app.db.base import Base # This imports all models
from app.services.audit_service import list_audit_logs
from app.models.user import User, UserRole
import uuid

async def test():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        admin = User(id=uuid.uuid4(), role=UserRole.ADMIN, village_id=uuid.uuid4())
        try:
            res = await list_audit_logs(db, admin, None, None, None, None, None, 1, 10)
            print("Admin OK, total:", res.total)
        except Exception as e:
            print("Admin ERROR:", type(e), e)
            
        superadmin = User(id=uuid.uuid4(), role=UserRole.SUPERADMIN, village_id=None)
        try:
            res = await list_audit_logs(db, superadmin, None, None, None, None, None, 1, 10)
            print("SuperAdmin OK, total:", res.total)
        except Exception as e:
            print("SuperAdmin ERROR:", type(e), e)

asyncio.run(test())
