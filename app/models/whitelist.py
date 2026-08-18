import enum
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class WhitelistCategory(str, enum.Enum):
    RESIDENT = "resident"
    REGULAR = "regular"
    GUEST = "guest"


class Whitelist(Base):
    __tablename__ = "WhitelistTABLE"
    __table_args__ = (
        Index(
            "ix_whitelisttable_village_plate_province",
            "village_id",
            "license_plate",
            "province",
            unique=True,
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    village_id = Column(UUID(as_uuid=True), ForeignKey("GroupTABLE.id"), nullable=False)
    category = Column(
        SAEnum(
            WhitelistCategory,
            name="whitelist_category",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    license_plate = Column(String(255), nullable=False)
    province = Column(String(255), nullable=False)
    note = Column(String(255), nullable=True)
    added_by = Column(UUID(as_uuid=True), ForeignKey("UserTABLE.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    village = relationship("Group", back_populates="whitelist_entries")
    added_by_user = relationship("User", back_populates="whitelist_entries_added")