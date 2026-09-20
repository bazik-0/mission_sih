"""
Ingestion service for fetching, classifying, and storing FIRMS data.
"""
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from .config import settings
from .database import IngestRun, Hotspot, SessionLocal
from .firms import firms_client
from .pipeline import pipeline

logger = logging.getLogger(__name__)

class IngestionService:
    """Service for ingesting FIRMS data."""

    def __init__(self):
        self.latest_acquisition_date: Optional[date] = None
        self.last_ingest_time: Optional[datetime] = None
        self.last_error: Optional[str] = None

    def ingest(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        days: Optional[int] = None
    ) -> Dict:
        """
        Ingest FIRMS data for a date range.

        Args:
            start_date: Start date (required if days not specified)
            end_date: End date (defaults to today)
            days: Number of days back from end_date (alternative to start_date)

        Returns:
            Ingestion summary
        """
        # FIRMS has ~1 day processing delay — cap to yesterday to avoid 400 errors
        yesterday = date.today() - timedelta(days=1)
        if end_date is None:
            end_date = yesterday
        else:
            end_date = min(end_date, yesterday)

        if days is not None:
            start_date = end_date - timedelta(days=days - 1)
        elif start_date is None:
            raise ValueError("Either start_date or days must be specified")

        logger.info(f"Starting ingestion: {start_date} to {end_date}")

        db = SessionLocal()
        run_id = None

        try:
            # Create ingest run record
            run = IngestRun(
                source=settings.FIRMS_SOURCE,
                area=settings.FIRMS_AREA,
                date_from=start_date,
                date_to=end_date,
                started_at=datetime.utcnow(),
                status='running'
            )
            db.add(run)
            db.commit()
            run_id = run.id

            # Fetch data
            detections = firms_client.fetch_date_range(start_date, end_date)

            # Filter to India bounds only (training region)
            # Model was trained on: 68°E-97.5°E, 6°N-37.5°N
            INDIA_BOUNDS = {
                'west': 68.0,
                'east': 97.5,
                'south': 6.0,
                'north': 37.5
            }

            detections_before_filter = len(detections)
            detections = [
                d for d in detections
                if (INDIA_BOUNDS['west'] <= d['longitude'] <= INDIA_BOUNDS['east'] and
                    INDIA_BOUNDS['south'] <= d['latitude'] <= INDIA_BOUNDS['north'])
            ]

            filtered_out = detections_before_filter - len(detections)
            if filtered_out > 0:
                logger.info(f"Filtered out {filtered_out} detections outside India bounds (Pakistan/China/etc.)")

            run.rows_fetched = len(detections)
            db.commit()

            if not detections:
                run.status = 'success'
                run.finished_at = datetime.utcnow()
                db.commit()
                logger.info("No detections to process")
                return self._build_summary(run, [])

            # Classify in batches
            batch_size = 1000
            all_results = []

            for i in range(0, len(detections), batch_size):
                batch = detections[i:i+batch_size]
                results = pipeline.classify_batch(batch)
                all_results.extend(results)

                logger.info(f"Classified batch {i//batch_size + 1}/{(len(detections)-1)//batch_size + 1}")

            # Store to database
            stored_count = self._store_hotspots(db, all_results)

            # Update run statistics
            run.rows_classified = len(all_results)
            run.rows_volcano = sum(1 for r in all_results if r['decision_path'] == 'volcano_rule')
            run.rows_mlp = sum(1 for r in all_results if r['decision_path'] == 'mlp')
            run.rows_no_match = sum(1 for r in all_results if r['decision_path'] == 'no_match')
            run.rows_unexpected_type = sum(1 for r in all_results if r['decision_path'] == 'unexpected_type')
            run.status = 'success'
            run.finished_at = datetime.utcnow()
            db.commit()

            # Update latest acquisition date
            if all_results:
                latest_acq = max(r['acq_date'] for r in all_results)
                self.latest_acquisition_date = datetime.strptime(latest_acq, '%Y-%m-%d').date()

            self.last_ingest_time = datetime.utcnow()
            self.last_error = None

            logger.info(f"Ingestion complete: {stored_count} hotspots stored")
            return self._build_summary(run, all_results)

        except Exception as e:
            logger.error(f"Ingestion failed: {e}", exc_info=True)
            self.last_error = str(e)

            if run_id:
                run = db.query(IngestRun).get(run_id)
                if run:
                    run.status = 'failed'
                    run.error_text = str(e)
                    run.finished_at = datetime.utcnow()
                    db.commit()

            raise

        finally:
            db.close()

    def _store_hotspots(self, db: Session, results: list) -> int:
        """Store classified hotspots to database (idempotent)."""
        stored = 0

        for result in results:
            try:
                # Parse datetime
                acq_date_str = result['acq_date']
                acq_time_int = int(result['acq_time'])
                acq_datetime = datetime.strptime(
                    f"{acq_date_str} {acq_time_int:04d}",
                    "%Y-%m-%d %H%M"
                )

                # Check if already exists
                existing = db.query(Hotspot).filter(
                    Hotspot.latitude == result['latitude'],
                    Hotspot.longitude == result['longitude'],
                    Hotspot.acq_date == acq_date_str,
                    Hotspot.acq_time == acq_time_int
                ).first()

                if existing:
                    continue  # Skip duplicate

                # Explicitly cast all numeric fields to native Python types
                # to avoid psycopg2 choking on np.float64 / np.int64 values
                hotspot = Hotspot(
                    geom=f"SRID=4326;POINT({float(result['longitude'])} {float(result['latitude'])})",
                    latitude=float(result['latitude']),
                    longitude=float(result['longitude']),
                    acq_datetime_utc=acq_datetime,
                    acq_date=acq_date_str,
                    acq_time=acq_time_int,
                    source=str(settings.FIRMS_SOURCE),

                    # Raw FIRMS fields
                    scan=float(result['scan']),
                    track=float(result['track']),
                    brightness=float(result['brightness']),
                    bright_t31=float(result['bright_t31']),
                    frp=float(result['frp']),
                    confidence=str(result['confidence_raw']),
                    daynight=str(result['daynight_raw']),
                    firms_type=int(result['type']) if result.get('type') is not None else None,
                    satellite=str(result['satellite']) if result.get('satellite') else None,
                    instrument=str(result['instrument']) if result.get('instrument') else None,
                    version=str(result['version']) if result.get('version') else None,

                    # Engineered features
                    track_scan=float(result['track_scan']),
                    final_bright=float(result['final_bright']),
                    radiation=float(result['radiation']),
                    confidence_encoded=int(result['confidence']),
                    daynight_encoded=int(result['daynight']),

                    # Matching
                    match_dist_m=float(result['match_dist_m']) if result.get('match_dist_m') is not None else None,
                    matched_from=str(result['matched_from']) if result.get('matched_from') else None,
                    landuse_year_used=int(result['landuse_year_used']) if result.get('landuse_year_used') is not None else None,

                    # Classification
                    predicted_class=result.get('predicted_class'),
                    probabilities=result.get('probabilities'),
                    final_label=str(result['final_label']),
                    final_group=str(result['final_group']),
                    decision_path=str(result['decision_path'])
                )

                db.add(hotspot)
                stored += 1

                # Commit in batches
                if stored % 500 == 0:
                    db.commit()

            except Exception as e:
                logger.warning(f"Failed to store hotspot: {e}")
                db.rollback()  # Reset session so next inserts can proceed
                continue

        db.commit()
        return stored

    def _build_summary(self, run: IngestRun, results: list) -> Dict:
        """Build ingestion summary."""
        return {
            'run_id': run.id,
            'source': run.source,
            'date_from': str(run.date_from),
            'date_to': str(run.date_to),
            'rows_fetched': run.rows_fetched,
            'rows_classified': run.rows_classified,
            'rows_volcano': run.rows_volcano,
            'rows_mlp': run.rows_mlp,
            'rows_no_match': run.rows_no_match,
            'rows_unexpected_type': run.rows_unexpected_type,
            'status': run.status,
            'started_at': run.started_at.isoformat() if run.started_at else None,
            'finished_at': run.finished_at.isoformat() if run.finished_at else None,
            'duration_seconds': (
                (run.finished_at - run.started_at).total_seconds()
                if run.finished_at and run.started_at else None
            )
        }

    def load_osm_features(self, db: Session) -> int:
        """Load OSM features into database."""
        from .database import OSMFeature
        import pandas as pd

        osm_file = settings.DATA_DIR / "osm_data_cleaned.csv"
        if not osm_file.exists():
            raise FileNotFoundError(f"OSM file not found: {osm_file}")

        # Check if already loaded
        count = db.query(OSMFeature).count()
        if count > 0:
            logger.info(f"OSM features already loaded: {count}")
            return count

        # Load from CSV
        df = pd.read_csv(osm_file)
        logger.info(f"Loading {len(df)} OSM features...")

        for _, row in df.iterrows():
            feature = OSMFeature(
                geom=f"SRID=4326;POINT({row['longitude']} {row['latitude']})",
                latitude=row['latitude'],
                longitude=row['longitude'],
                category=row['osm_category']
            )
            db.add(feature)

        db.commit()
        logger.info(f"Loaded {len(df)} OSM features")
        return len(df)

# Global instance
ingestion_service = IngestionService()
