from sqlalchemy import Column, Text, Integer, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Log(Base):
    __tablename__ = "logs"
    log_id = Column(Text, primary_key=True)
    ts = Column(TIMESTAMP(timezone=True), nullable=False)
    sender_id = Column(Text, nullable=False)
    kind = Column(Text, nullable=False)
    routed_agents = Column(JSONB, nullable=False)
    response = Column(JSONB, nullable=True)
    log_metadata = Column("metadata", JSONB, nullable=False)

class DLQ(Base):
    __tablename__ = "dlq"
    id = Column(Integer, primary_key=True)
    ts = Column(TIMESTAMP(timezone=True), nullable=False)
    log_id = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=False)
    attempts = Column(Integer, nullable=False)
