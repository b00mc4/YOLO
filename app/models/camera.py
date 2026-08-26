import enum
import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Boolean, UniqueConstraint, true
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class CameraVerificationStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class CameraDirection(str, enum.Enum):
    ENTRY = "entry"
    EXIT = "exit"


class Camera(Base):
    __tablename__ = "CameraTABLE"
    __table_args__ = (
        UniqueConstraint("stream_ai", name="uq_CameraTABLE_stream_ai"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    village_id = Column(UUID(as_uuid=True), ForeignKey("GroupTABLE.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    lat = Column(Float(53), nullable=False)
    long = Column(Float(53), nullable=False)
    stream_ai = Column(String(1000), nullable=False)
    direction = Column(
        SAEnum(
            CameraDirection,
            name="camera_direction",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )
    verification_status = Column(
        SAEnum(
            CameraVerificationStatus,
            name="camera_verification_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=CameraVerificationStatus.PENDING.value,
    )
    ai_vision_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=true())

    village = relationship("Group", back_populates="cameras")
    detections = relationship("Car", back_populates="camera")