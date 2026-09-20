"""
Database models and connection.
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, Text, UniqueConstraint, Index, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

from .config import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Hotspot(Base):
    __tablename__ = "hotspots"

    id = Column(Integer, primary_key=True, index=True)
    geom = Column(Geometry('POINT', srid=4326), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    acq_datetime_utc = Column(DateTime, nullable=False)
    acq_date = Column(Date, nullable=False)
    acq_time = Column(Integer, nullable=False)
    source = Column(String(30), nullable=False)

    # Raw FIRMS fields
    scan = Column(Float, nullable=False)
    track = Column(Float, nullable=False)
    brightness = Column(Float, nullable=False)
    bright_t31 = Column(Float, nullable=False)
    frp = Column(Float, nullable=False)
    confidence = Column(String(10), nullable=False)
    daynight = Column(String(1), nullable=False)
    firms_type = Column(Integer)
    satellite = Column(String(30))
    instrument = Column(String(30))
    version = Column(String(30))

    # Engineered features
    track_scan = Column(Float, nullable=False)
    final_bright = Column(Float, nullable=False)
    radiation = Column(Float, nullable=False)
    confidence_encoded = Column(Integer, nullable=False)
    daynight_encoded = Column(Integer, nullable=False)

    # Matching results
    match_dist_m = Column(Float)
    matched_from = Column(String(20))
    landuse_year_used = Column(Integer)

    # Classification results
    predicted_class = Column(String(50))
    probabilities = Column(JSONB)
    final_label = Column(String(50), nullable=False)
    final_group = Column(String(20), nullable=False)
    decision_path = Column(String(20), nullable=False)

    ingested_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('latitude', 'longitude', 'acq_date', 'acq_time', name='uq_hotspot'),
        Index('idx_hotspots_geom', 'geom', postgresql_using='gist'),
    )

class OSMFeature(Base):
    __tablename__ = "osm_features"

    id = Column(Integer, primary_key=True, index=True)
    geom = Column(Geometry('POINT', srid=4326), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    category = Column(String(50), nullable=False)

    __table_args__ = (
        Index('idx_osm_features_geom', 'geom', postgresql_using='gist'),
    )

class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(30), nullable=False)
    area = Column(String(50), nullable=False)
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)
    rows_fetched = Column(Integer, default=0)
    rows_classified = Column(Integer, default=0)
    rows_volcano = Column(Integer, default=0)
    rows_mlp = Column(Integer, default=0)
    rows_no_match = Column(Integer, default=0)
    rows_unexpected_type = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime)
    status = Column(String(20), nullable=False)
    error_text = Column(Text)

def run_migrations():
    """Apply any schema migrations needed on the live database.
    Safe to run on every startup — ALTER TYPE only widens columns.
    """
    migrations = [
        "ALTER TABLE hotspots ALTER COLUMN source TYPE VARCHAR(30)",
        "ALTER TABLE hotspots ALTER COLUMN satellite TYPE VARCHAR(30)",
        "ALTER TABLE hotspots ALTER COLUMN instrument TYPE VARCHAR(30)",
        "ALTER TABLE hotspots ALTER COLUMN version TYPE VARCHAR(30)",
        "ALTER TABLE hotspots ALTER COLUMN matched_from TYPE VARCHAR(20)",
        "ALTER TABLE ingest_runs ALTER COLUMN source TYPE VARCHAR(30)",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            conn.execute(text(stmt))
        conn.commit()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
