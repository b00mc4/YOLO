import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base


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
        Index("ix_WhitelistTABLE_license_plate_trgm", "license_plate", postgresql_using="gin", postgresql_ops={"license_plate": "gin_trgm_ops"}),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    village_id = Column(UUID(as_uuid=True), ForeignKey("GroupTABLE.id"), nullable=False)
    name = Column(String(255), nullable=False)
    house_no = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    license_plate = Column(String(255), nullable=False)
    province = Column(String(255), nullable=False)
    color = Column(String(255), nullable=True)
    note = Column(String(255), nullable=True)
    added_by = Column(UUID(as_uuid=True), ForeignKey("UserTABLE.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    village = relationship("Group", back_populates="whitelist_entries")
    added_by_user = relationship("User", back_populates="whitelist_entries_added")