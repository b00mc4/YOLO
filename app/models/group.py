import uuid

from sqlalchemy import Boolean, Column, DateTime, String, false
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

class Group(Base):
    __tablename__ = "GroupTABLE"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    address = Column(String(255), nullable=False, server_default="-")
    is_active = Column(Boolean, nullable=False, server_default=false())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    users = relationship("User", back_populates="village")
    cameras = relationship("Camera", back_populates="village")
    blacklist_entries = relationship("Blacklist", back_populates="village")
    whitelist_entries = relationship("Whitelist", back_populates="village")
    audit_logs = relationship("AuditLog", back_populates="village")
    notifications = relationship("Notification", back_populates="village")