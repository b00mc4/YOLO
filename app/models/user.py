import enum
import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"

class User(Base):
    __tablename__ = "UserTABLE"
    __table_args__ = (
        CheckConstraint(
            "(role = 'superadmin' AND village_id IS NULL) OR "
            "(role != 'superadmin' AND village_id IS NOT NULL)",
            name="user_village_id_matches_role",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(255), unique=True, nullable=False)
    fullname = Column(String(255), nullable=False)
    avatar_path = Column(String(255), nullable=True)
    hashpassword = Column(String(255), nullable=True)
    email = Column(String(255), unique=True, nullable=False)
    role = Column(SAEnum(UserRole, name="user_role", values_callable=lambda enum_cls: [member.value for member in enum_cls]),nullable=False,)
    village_id = Column(UUID(as_uuid=True), ForeignKey("GroupTABLE.id"), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False)
    is_verify = Column(Boolean, nullable=False)
    password_changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    village = relationship("Group", back_populates="users")
    verifications = relationship("Verify", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    contacts = relationship("Contact", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    blacklist_entries_added = relationship("Blacklist", back_populates="added_by_user")
    whitelist_entries_added = relationship("Whitelist", back_populates="added_by_user")
    audit_logs = relationship("AuditLog", back_populates="user")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)