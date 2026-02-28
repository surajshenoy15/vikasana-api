from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from app.core.database import Base


class EventActivityType(Base):
    __tablename__ = "event_activity_types"
    __table_args__ = (UniqueConstraint("event_id", "activity_type_id", name="uq_event_activity_type"),)

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type_id = Column(Integer, ForeignKey("activity_types.id", ondelete="RESTRICT"), nullable=False, index=True)