import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, String, false, Index

from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.models.camera import CameraDirection

class Car(Base):
    __tablename__ = "CarTABLE"
    __table_args__ = (
        Index("ix_CarTABLE_village_time", "village_id", "time_detect"),
        Index("ix_CarTABLE_license_plate_trgm", "license_plate", postgresql_using="gin", postgresql_ops={"license_plate": "gin_trgm_ops"}),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), nullable=False,unique=True, index=True)
    camera_id = Column(UUID(as_uuid=True), ForeignKey("CameraTABLE.id", ondelete="SET NULL"), nullable=True, index=True)
    village_id = Column(UUID(as_uuid=True), ForeignKey("GroupTABLE.id", ondelete="SET NULL"), nullable=True, index=True)
    camera_name = Column(String(255), nullable=True)
    camera_lat = Column(Float(53), nullable=True)
    camera_long = Column(Float(53), nullable=True)
    license_plate = Column(String(255), nullable=False, index=True)
    province = Column(String(255), nullable=False)
    color = Column(String(255), nullable=False)
    image_crop = Column(String(255), nullable=False)
    image_full = Column(String(255), nullable=False)
    time_detect = Column(DateTime(timezone=True), nullable=False, index=True)
    is_blacklist = Column(Boolean, nullable=False, server_default=false())
    is_whitelist = Column(Boolean, nullable=False, server_default=false())
    direction = Column(
        SAEnum(
            CameraDirection,
            name="camera_direction",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    camera = relationship("Camera", back_populates="detections")