"""
FastAPI application for Mission SIH industrial fire detection.
"""
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, text
from apscheduler.schedulers.background import BackgroundScheduler
import json
import io

from .config import settings
from .database import get_db, Hotspot, OSMFeature, engine, run_migrations
from .pipeline import pipeline
from .firms import firms_client
from .ingestion import ingestion_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create app
app = FastAPI(title="Mission SIH - Industrial Fire Detection")

# Scheduler for automatic ingestion
scheduler = BackgroundScheduler()

@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    logger.info("Starting Mission SIH application")

    # Apply any pending DB schema migrations
    try:
        run_migrations()
        logger.info("DB migrations applied")
    except Exception as e:
        logger.error(f"DB migrations failed: {e}")

    # Test database connection
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection OK")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")

    # Load model
    try:
        pipeline.load_model()
        logger.info(f"Model loaded from {pipeline.model_source}")
    except Exception as e:
        logger.error(f"Model loading failed: {e}")

    # Load OSM index
    try:
        pipeline.load_osm_index()
        logger.info("OSM index loaded")
    except Exception as e:
        logger.error(f"OSM index loading failed: {e}")

    # Load OSM features into database
    try:
        db = next(get_db())
        ingestion_service.load_osm_features(db)
    except Exception as e:
        logger.warning(f"OSM features loading: {e}")

    # Schedule automatic ingestion
    def scheduled_ingest():
        try:
            logger.info("Running scheduled ingestion")
            ingestion_service.ingest(days=1)
        except Exception as e:
            logger.error(f"Scheduled ingestion failed: {e}")

    scheduler.add_job(
        scheduled_ingest,
        'interval',
        minutes=settings.INGEST_INTERVAL_MINUTES,
        id='auto_ingest'
    )
    scheduler.start()
    logger.info(f"Scheduled ingestion every {settings.INGEST_INTERVAL_MINUTES} minutes")

    # Run initial backfill
    try:
        logger.info(f"Running initial backfill ({settings.INITIAL_BACKFILL_DAYS} days)")
        ingestion_service.ingest(days=settings.INITIAL_BACKFILL_DAYS)
    except Exception as e:
        logger.error(f"Initial backfill failed: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    scheduler.shutdown()
    logger.info("Application shutdown")

# API Endpoints

@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    health = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Model status
    if hasattr(pipeline, 'models') and len(pipeline.models) > 0:
        health["model_loaded"] = True
        health["model_source"] = getattr(pipeline, 'model_source', 'unknown')
        if pipeline.model_classes is not None:
            health["model_classes"] = [str(c) for c in pipeline.model_classes]
        else:
            first_key = list(pipeline.models.keys())[0]
            health["model_classes"] = [str(c) for c in pipeline.models[first_key].classes_]
        health["model_types_loaded"] = list(pipeline.models.keys())
    else:
        health["model_loaded"] = False

    # Database status
    try:
        db.execute(text("SELECT 1"))
        health["database"] = "connected"
    except Exception as e:
        health["database"] = f"error: {str(e)}"

    # Lookup indexes
    health["osm_index_loaded"] = pipeline.osm_index is not None
    health["landuse_indexes_cached"] = len(pipeline.landuse_indexes)

    # FIRMS key present (don't show the actual key)
    health["firms_key_present"] = bool(settings.NASA_FIRMS_MAP_KEY)

    # FIRMS usage
    try:
        usage = firms_client.check_usage()
        health["firms_usage"] = usage
    except Exception as e:
        health["firms_usage"] = {"error": str(e)}

    # Data source and latest acquisition
    health["data_source"] = settings.FIRMS_SOURCE
    if ingestion_service.latest_acquisition_date:
        health["latest_acquisition_date"] = str(ingestion_service.latest_acquisition_date)

    if ingestion_service.last_ingest_time:
        health["last_ingest_time"] = ingestion_service.last_ingest_time.isoformat()

    if ingestion_service.last_error:
        health["last_error"] = ingestion_service.last_error

    return health

@app.post("/api/ingest")
def trigger_ingest(
    days: int = Query(1, ge=1, le=30),
    db: Session = Depends(get_db)
):
    """Manually trigger ingestion."""
    try:
        result = ingestion_service.ingest(days=days)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hotspots")
def get_hotspots(
    bbox: Optional[str] = Query(None, description="Bounding box: west,south,east,north"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    final_label: Optional[str] = Query(None),
    final_group: Optional[str] = Query(None),
    decision_path: Optional[str] = Query(None),
    min_probability: Optional[float] = Query(None, ge=0.0, le=1.0),
    limit: int = Query(10000, le=50000),
    db: Session = Depends(get_db)
):
    """Get hotspots as GeoJSON."""
    query = db.query(Hotspot)

    # Apply filters
    if bbox:
        try:
            west, south, east, north = map(float, bbox.split(','))
            query = query.filter(
                and_(
                    Hotspot.longitude >= west,
                    Hotspot.longitude <= east,
                    Hotspot.latitude >= south,
                    Hotspot.latitude <= north
                )
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid bbox format")

    if date_from:
        query = query.filter(Hotspot.acq_date >= date_from)

    if date_to:
        query = query.filter(Hotspot.acq_date <= date_to)

    if final_label:
        query = query.filter(Hotspot.final_label == final_label)

    if final_group:
        query = query.filter(Hotspot.final_group == final_group)

    if decision_path:
        query = query.filter(Hotspot.decision_path == decision_path)

    # Min probability filter (on predicted class only)
    if min_probability is not None:
        query = query.filter(
            Hotspot.predicted_class.isnot(None)
        )

    # Limit results
    total_count = query.count()
    truncated = total_count > limit
    hotspots = query.limit(limit).all()

    # Filter by probability if needed (in Python since it requires JSONB query)
    if min_probability is not None:
        filtered = []
        for h in hotspots:
            if h.probabilities and h.predicted_class:
                prob = h.probabilities.get(h.predicted_class, 0)
                if prob >= min_probability:
                    filtered.append(h)
        hotspots = filtered

    # Build GeoJSON
    features = []
    for h in hotspots:
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [h.longitude, h.latitude]
            },
            "properties": {
                "id": h.id,
                "acq_date": str(h.acq_date),
                "acq_time": h.acq_time,
                "final_label": h.final_label,
                "final_group": h.final_group,
                "decision_path": h.decision_path,
                "frp": h.frp,
                "brightness": h.brightness,
                "confidence": h.confidence,
            }
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "count": len(features),
            "total_count": total_count,
            "truncated": truncated,
            "limit": limit
        }
    }

    return geojson

@app.get("/api/hotspots/{hotspot_id}")
def get_hotspot_detail(hotspot_id: int, db: Session = Depends(get_db)):
    """Get detailed information for a single hotspot."""
    hotspot = db.query(Hotspot).filter(Hotspot.id == hotspot_id).first()

    if not hotspot:
        raise HTTPException(status_code=404, detail="Hotspot not found")

    # Build detailed response
    detail = {
        "id": hotspot.id,
        "latitude": hotspot.latitude,
        "longitude": hotspot.longitude,
        "acq_datetime_utc": hotspot.acq_datetime_utc.isoformat(),
        "acq_date": str(hotspot.acq_date),
        "acq_time": hotspot.acq_time,
        "source": hotspot.source,

        # Raw FIRMS fields
        "firms": {
            "scan": hotspot.scan,
            "track": hotspot.track,
            "brightness": hotspot.brightness,
            "bright_t31": hotspot.bright_t31,
            "frp": hotspot.frp,
            "confidence": hotspot.confidence,
            "daynight": hotspot.daynight,
            "type": hotspot.firms_type,
            "satellite": hotspot.satellite,
            "instrument": hotspot.instrument,
        },

        # Engineered features
        "features": {
            "track_scan": hotspot.track_scan,
            "final_bright": hotspot.final_bright,
            "radiation": hotspot.radiation,
        },

        # Matching
        "matching": {
            "distance_m": hotspot.match_dist_m,
            "matched_from": hotspot.matched_from,
            "landuse_year_used": hotspot.landuse_year_used,
        },

        # Classification
        "classification": {
            "predicted_class": hotspot.predicted_class,
            "probabilities": hotspot.probabilities,
            "final_label": hotspot.final_label,
            "final_group": hotspot.final_group,
            "decision_path": hotspot.decision_path,
        },

        "ingested_at": hotspot.ingested_at.isoformat(),
    }

    return detail

@app.get("/api/stats")
def get_stats(
    bbox: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db)
):
    """Get statistics for the current filter."""
    query = db.query(Hotspot)

    # Apply same filters as hotspots endpoint
    if bbox:
        try:
            west, south, east, north = map(float, bbox.split(','))
            query = query.filter(
                and_(
                    Hotspot.longitude >= west,
                    Hotspot.longitude <= east,
                    Hotspot.latitude >= south,
                    Hotspot.latitude <= north
                )
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid bbox format")

    if date_from:
        query = query.filter(Hotspot.acq_date >= date_from)

    if date_to:
        query = query.filter(Hotspot.acq_date <= date_to)

    # Counts by group
    group_counts = db.query(
        Hotspot.final_group,
        func.count(Hotspot.id)
    ).filter(
        Hotspot.id.in_(query.with_entities(Hotspot.id))
    ).group_by(Hotspot.final_group).all()

    # Counts by label
    label_counts = db.query(
        Hotspot.final_label,
        func.count(Hotspot.id)
    ).filter(
        Hotspot.id.in_(query.with_entities(Hotspot.id))
    ).group_by(Hotspot.final_label).all()

    # Counts by day
    day_counts = db.query(
        Hotspot.acq_date,
        func.count(Hotspot.id)
    ).filter(
        Hotspot.id.in_(query.with_entities(Hotspot.id))
    ).group_by(Hotspot.acq_date).order_by(Hotspot.acq_date).all()

    return {
        "total": query.count(),
        "by_group": {group: count for group, count in group_counts},
        "by_label": {label: count for label, count in label_counts},
        "by_day": [{"date": str(d), "count": c} for d, c in day_counts],
    }

@app.get("/api/infrastructure")
def get_infrastructure(
    bbox: str = Query(..., description="Bounding box: west,south,east,north"),
    db: Session = Depends(get_db)
):
    """Get OSM infrastructure points as GeoJSON."""
    try:
        west, south, east, north = map(float, bbox.split(','))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid bbox format")

    features_query = db.query(OSMFeature).filter(
        and_(
            OSMFeature.longitude >= west,
            OSMFeature.longitude <= east,
            OSMFeature.latitude >= south,
            OSMFeature.latitude <= north
        )
    ).limit(10000)

    features = []
    for f in features_query:
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [f.longitude, f.latitude]
            },
            "properties": {
                "category": f.category
            }
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features
    }

@app.get("/api/export")
def export_data(
    format: str = Query("csv", regex="^(csv|geojson)$"),
    bbox: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    final_label: Optional[str] = Query(None),
    final_group: Optional[str] = Query(None),
    limit: int = Query(10000, le=50000),
    db: Session = Depends(get_db)
):
    """Export hotspots as CSV or GeoJSON."""
    query = db.query(Hotspot)

    # Apply filters (same as get_hotspots)
    if bbox:
        try:
            west, south, east, north = map(float, bbox.split(','))
            query = query.filter(
                and_(
                    Hotspot.longitude >= west,
                    Hotspot.longitude <= east,
                    Hotspot.latitude >= south,
                    Hotspot.latitude <= north
                )
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid bbox format")

    if date_from:
        query = query.filter(Hotspot.acq_date >= date_from)

    if date_to:
        query = query.filter(Hotspot.acq_date <= date_to)

    if final_label:
        query = query.filter(Hotspot.final_label == final_label)

    if final_group:
        query = query.filter(Hotspot.final_group == final_group)

    hotspots = query.limit(limit).all()

    if format == "csv":
        # Generate CSV
        output = io.StringIO()
        import csv
        writer = csv.writer(output)

        # Header
        writer.writerow([
            'id', 'latitude', 'longitude', 'acq_date', 'acq_time',
            'brightness', 'frp', 'confidence', 'final_label', 'final_group',
            'decision_path', 'predicted_class', 'match_dist_m'
        ])

        # Rows
        for h in hotspots:
            writer.writerow([
                h.id, h.latitude, h.longitude, h.acq_date, h.acq_time,
                h.brightness, h.frp, h.confidence, h.final_label, h.final_group,
                h.decision_path, h.predicted_class, h.match_dist_m
            ])

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=hotspots.csv"}
        )

    else:  # geojson
        features = []
        for h in hotspots:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [h.longitude, h.latitude]
                },
                "properties": {
                    "id": h.id,
                    "acq_date": str(h.acq_date),
                    "acq_time": h.acq_time,
                    "brightness": h.brightness,
                    "frp": h.frp,
                    "confidence": h.confidence,
                    "final_label": h.final_label,
                    "final_group": h.final_group,
                    "decision_path": h.decision_path,
                    "predicted_class": h.predicted_class,
                }
            }
            features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        return StreamingResponse(
            iter([json.dumps(geojson)]),
            media_type="application/geo+json",
            headers={"Content-Disposition": "attachment; filename=hotspots.geojson"}
        )

# Serve frontend — use absolute path so it works regardless of working directory
_FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
