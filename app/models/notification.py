import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, false
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class Notification(Base):
    __tablename__ = "NotificationTABLE"
    __table_args__ = (
        Index(
            "ix_notificationtable_user_unread_created",
            "user_id",
            "is_read",
            "created_at",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("UserTABLE.id", ondelete="CASCADE"), nullable=False, index=True)
    village_id = Column(UUID(as_uuid=True), ForeignKey("GroupTABLE.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(255), nullable=False)
    detail = Column(String(1000), nullable=False)
    payload = Column(JSONB, nullable=True)
    is_read = Column(Boolean, nullable=False, server_default=false())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    user = relationship("User", back_populates="notifications")
    village = relationship("Group", back_populates="notifications")