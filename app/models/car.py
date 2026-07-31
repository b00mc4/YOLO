import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, false
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

class Car(Base):
    __tablename__ = "CarTABLE"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    camera_id = Column(UUID(as_uuid=True), ForeignKey("CameraTABLE.id"),unique=True ,nullable=False, index=True)
    license_plate = Column(String(255), nullable=False, index=True)
    province = Column(String(255), nullable=False)
    color = Column(String(255), nullable=False)
    image_crop = Column(String(255), nullable=False)
    image_full = Column(String(255), nullable=False)
    time_detect = Column(DateTime(timezone=True), nullable=False, index=True)
    is_blacklist = Column(Boolean, nullable=False, server_default=false())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    camera = relationship("Camera", back_populates="detections")