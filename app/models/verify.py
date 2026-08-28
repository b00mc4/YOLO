import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, false
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

class VerifyType(str, enum.Enum):
    INITIAL_SETUP = "initial_setup"
    PASSWORD_RESET = "password_reset"
    EMAIL_CHANGE = "email_change"


class Verify(Base):
    __tablename__ = "VerifyTABLE"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("UserTABLE.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(SAEnum(VerifyType, name="verify_type", values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    new_email = Column(String(255), nullable=True)
    token_hash = Column(String(255), nullable=False, index=True)
    expire_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, nullable=False, server_default=false())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="verifications")