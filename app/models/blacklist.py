import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

class Blacklist(Base):
    __tablename__ = "BlacklistTABLE"
    __table_args__ = (
        Index(
            "ix_blacklisttable_village_plate_province",
            "village_id",
            "license_plate",
            "province",
            unique=True,
        ),
        Index("ix_BlacklistTABLE_license_plate_trgm", "license_plate", postgresql_using="gin", postgresql_ops={"license_plate": "gin_trgm_ops"}),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    village_id = Column(UUID(as_uuid=True), ForeignKey("GroupTABLE.id", ondelete="CASCADE"), nullable=False)
    license_plate = Column(String(255), nullable=False)
    province = Column(String(255), nullable=False)
    reason = Column(String(255), nullable=False)
    added_by = Column(UUID(as_uuid=True), ForeignKey("UserTABLE.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    village = relationship("Group", back_populates="blacklist_entries")
    added_by_user = relationship("User", back_populates="blacklist_entries_added")