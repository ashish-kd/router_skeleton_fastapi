import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/routerdb")

engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    pool_size=20,          # Increase connection pool
    max_overflow=0,        # No overflow connections (predictable performance)
    pool_recycle=3600,     # Recycle connections every hour
    echo=False             # Disable SQL logging for performance
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
