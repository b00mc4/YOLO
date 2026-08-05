import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Boolean, true
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

class Camera(Base):
    __tablename__ = "CameraTABLE"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    village_id = Column(UUID(as_uuid=True), ForeignKey("GroupTABLE.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    lat = Column(Float(53), nullable=False)
    long = Column(Float(53), nullable=False)
    stream_ai = Column(String(255), nullable=False)
    ai_vision_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=true())

    village = relationship("Group", back_populates="cameras")
    detections = relationship("Car", back_populates="camera")