from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# For local docker-compose setup, defaulting to postgres:password@localhost:5432/customer_support
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:password@localhost:5432/customer_support")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
