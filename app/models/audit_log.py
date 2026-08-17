import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

class AuditLog(Base):
    __tablename__ = "AuditLogTABLE"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    village_id = Column(UUID(as_uuid=True), ForeignKey("GroupTABLE.id"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("UserTABLE.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(255), nullable=False)
    detail = Column(String(1000), nullable=False)
    ip_address = Column(String(255), nullable=False)
    user_agent = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    village = relationship("Group", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")