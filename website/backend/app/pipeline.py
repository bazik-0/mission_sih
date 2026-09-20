"""
Feature pipeline and classification logic.
Matches the training pipeline exactly.
"""
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime

from .config import settings

EARTH_RADIUS_M = 6371000
RADIUS_LIMIT_M = 2000

FEATURE_ORDER = [
    "latitude", "longitude", "scan", "track", "track_scan",
    "frp", "radiation", "brightness", "bright_t31", "final_bright",
    "acq_time", "daynight", "confidence", "type", "match_dist_m"
]

# Industrial vs Natural grouping
INDUSTRIAL_CLASSES = {'gas_flare', 'industrial_facility', 'mine', 'oil_gas', 'power_plant', 'quarry'}
NATURAL_CLASSES = {'Forest', 'Agriculture'}

class FeaturePipeline:
    """Feature engineering and classification pipeline."""

    def __init__(self):
        self.model = None
        self.model_classes = None
        self.landuse_indexes = {}  # Cached by year
        self.osm_index = None
        self.model_source = None

    def load_model(self):
        """Load the model from Hugging Face or local fallback."""
        if self.model is not None:
            return

        import joblib

        # Try Hugging Face first
        if settings.HUGGING_FACE_API:
            try:
                from huggingface_hub import hf_hub_download
                model_path = hf_hub_download(
                    repo_id="bazik-0/mission-sih",
                    filename="model.joblib",
                    token=settings.HUGGING_FACE_API,
                    cache_dir=settings.CACHE_DIR / "hf_cache"
                )
                self.model = joblib.load(model_path)
                self.model_classes = self.model.classes_
                self.model_source = "huggingface"
                print(f"Model loaded from Hugging Face: {self.model_classes}")
                return
            except Exception as e:
                print(f"Failed to load from Hugging Face: {e}")

        # Fallback to local
        local_model = settings.MODEL_DIR / "model.joblib"
        if local_model.exists():
            self.model = joblib.load(local_model)
            self.model_classes = self.model.classes_
            self.model_source = "local"
            print(f"Model loaded from local: {self.model_classes}")
        else:
            raise RuntimeError(f"Model not found at {local_model}")

    def load_osm_index(self):
        """Load OSM index."""
        if self.osm_index is not None:
            return

        cache_file = settings.CACHE_DIR / "osm_index.pkl"
        if not cache_file.exists():
            raise RuntimeError(f"OSM index not found at {cache_file}. Run scripts/build_lookup.py first.")

        with open(cache_file, 'rb') as f:
            self.osm_index = pickle.load(f)

        print(f"OSM index loaded: {self.osm_index['count']} points")

    def load_landuse_index(self, year: int):
        """Load land use index for a specific year (cached)."""
        if year in self.landuse_indexes:
            return self.landuse_indexes[year]

        cache_dir = settings.CACHE_DIR / "landuse_indexes"
        index_file = cache_dir / f"landuse_{year}.pkl"

        if not index_file.exists():
            # Try to find nearest available year
            available_years = sorted([
                int(f.stem.split('_')[1])
                for f in cache_dir.glob("landuse_*.pkl")
            ])
            if not available_years:
                raise RuntimeError(f"No land use indexes found. Run scripts/build_lookup.py first.")

            # Find closest year
            year = min(available_years, key=lambda y: abs(y - year))
            index_file = cache_dir / f"landuse_{year}.pkl"

        with open(index_file, 'rb') as f:
            self.landuse_indexes[year] = pickle.load(f)

        return self.landuse_indexes[year]

    def lookup_nearest(self, rows: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Perform nearest-point lookup for a batch of rows.
        Returns: (categories, distances_m, landuse_years_used)
        """
        categories = np.full(len(rows), np.nan, dtype=object)
        distances = np.full(len(rows), np.inf)
        landuse_years = np.full(len(rows), -1, dtype=int)

        # Land use lookup (year-specific)
        for year, group_indices in rows.groupby('year').groups.items():
            try:
                landuse_idx = self.load_landuse_index(year)
            except RuntimeError:
                continue

            group_coords = rows.loc[group_indices, ['latitude', 'longitude']].values
            group_coords_rad = np.radians(group_coords)

            dist, idx = landuse_idx['nn'].kneighbors(group_coords_rad)
            dist_m = dist.flatten() * EARTH_RADIUS_M

            # Apply radius limit
            valid = dist_m <= RADIUS_LIMIT_M
            matched_types = landuse_idx['types'][idx.flatten()]

            categories[group_indices] = np.where(valid, matched_types, np.nan)
            distances[group_indices] = dist_m
            landuse_years[group_indices] = year

        # OSM lookup (global, replaces if closer or no match)
        if self.osm_index is not None:
            coords = rows[['latitude', 'longitude']].values
            coords_rad = np.radians(coords)

            dist_osm, idx_osm = self.osm_index['nn'].kneighbors(coords_rad)
            dist_osm_m = dist_osm.flatten() * EARTH_RADIUS_M

            valid_osm = dist_osm_m <= RADIUS_LIMIT_M
            matched_osm = self.osm_index['categories'][idx_osm.flatten()]

            # Replace if: valid AND (no previous match OR closer)
            no_prev_match = pd.isna(categories)
            closer = dist_osm_m < distances
            should_replace = valid_osm & (no_prev_match | closer)

            categories[should_replace] = matched_osm[should_replace]
            distances[should_replace] = dist_osm_m[should_replace]

        return categories, distances, landuse_years

    def engineer_features(self, row: Dict) -> Dict:
        """Engineer features from a FIRMS row."""
        # Normalize column names (bright_ti4 -> brightness, bright_ti5 -> bright_t31)
        brightness = row.get('brightness') or row.get('bright_ti4')
        bright_t31 = row.get('bright_t31') or row.get('bright_ti5')

        # Encode confidence: l=300, n=600, h=900
        confidence_map = {'l': 300, 'n': 600, 'h': 900}
        confidence_encoded = confidence_map.get(row['confidence'], 600)

        # Encode daynight: D=0, N=1
        daynight_encoded = 0 if row['daynight'] == 'D' else 1

        # Compute engineered features
        track_scan = row['scan'] * row['track']
        final_bright = brightness * bright_t31
        radiation = track_scan * row['frp']

        return {
            'latitude': row['latitude'],
            'longitude': row['longitude'],
            'scan': row['scan'],
            'track': row['track'],
            'track_scan': track_scan,
            'frp': row['frp'],
            'radiation': radiation,
            'brightness': brightness,
            'bright_t31': bright_t31,
            'final_bright': final_bright,
            'acq_time': row['acq_time'],
            'daynight': daynight_encoded,
            'confidence': confidence_encoded,
            'type': row.get('type'),
            'confidence_raw': row['confidence'],
            'daynight_raw': row['daynight']
        }

    def classify_batch(self, rows: List[Dict]) -> List[Dict]:
        """
        Classify a batch of FIRMS detections.
        Returns enriched rows with classification results.
        """
        if not rows:
            return []

        self.load_model()
        self.load_osm_index()

        # Convert to DataFrame
        df = pd.DataFrame(rows)

        # Engineer features
        features = [self.engineer_features(row) for row in rows]
        features_df = pd.DataFrame(features)

        # Extract year from acq_date
        df['year'] = pd.to_datetime(df['acq_date']).dt.year

        # Perform lookup
        categories, distances, landuse_years = self.lookup_nearest(df)

        results = []
        for i, row in enumerate(rows):
            result = {
                **row,
                **features[i],
                'match_dist_m': float(distances[i]) if not np.isinf(distances[i]) else None,
                'landuse_year_used': int(landuse_years[i]) if landuse_years[i] != -1 else None,
            }

            firms_type = row.get('type')

            # Decision path 1: Volcano rule (type == 1)
            if firms_type == 1:
                result['final_label'] = 'Volcano'
                result['final_group'] = 'volcano'
                result['decision_path'] = 'volcano_rule'
                result['predicted_class'] = None
                result['probabilities'] = None
                result['matched_from'] = None

            # Decision path 2: No match within 2000m
            elif pd.isna(categories[i]) or np.isinf(distances[i]):
                result['final_label'] = 'Unclassified'
                result['final_group'] = 'unclassified'
                result['decision_path'] = 'no_match'
                result['predicted_class'] = None
                result['probabilities'] = None
                result['matched_from'] = None

            # Decision path 3: Run MLP (types 0, 2, 3)
            elif firms_type in [0, 2, 3]:
                # Prepare features for model
                feature_dict = {
                    **features[i],
                    'match_dist_m': distances[i]
                }
                X = pd.DataFrame([feature_dict])[FEATURE_ORDER]

                # Predict
                probs = self.model.predict_proba(X)[0]
                predicted_idx = np.argmax(probs)
                predicted_class = self.model_classes[predicted_idx]

                # Build probabilities dict
                probs_dict = {cls: float(prob) for cls, prob in zip(self.model_classes, probs)}

                result['predicted_class'] = predicted_class
                result['probabilities'] = probs_dict
                result['final_label'] = predicted_class
                result['decision_path'] = 'mlp'

                # Determine matched_from
                if landuse_years[i] != -1:
                    result['matched_from'] = 'osm' if categories[i] in self.osm_index['categories'] else 'landuse'
                else:
                    result['matched_from'] = 'osm'

                # Group classification
                if predicted_class in INDUSTRIAL_CLASSES:
                    result['final_group'] = 'industrial'
                elif predicted_class in NATURAL_CLASSES:
                    result['final_group'] = 'natural'
                else:
                    result['final_group'] = 'unclassified'

            # Decision path 4: Unexpected type
            else:
                result['final_label'] = 'Unclassified'
                result['final_group'] = 'unclassified'
                result['decision_path'] = 'unexpected_type'
                result['predicted_class'] = None
                result['probabilities'] = None
                result['matched_from'] = None
                print(f"WARNING: Unexpected FIRMS type: {firms_type}")

            results.append(result)

        # Sanitize all numpy scalar types to native Python types before DB insertion
        return [_sanitize_result(r) for r in results]


def _sanitize_result(result: Dict) -> Dict:
    """Convert numpy scalar types to native Python types so psycopg2 can bind them."""
    sanitized = {}
    for k, v in result.items():
        if isinstance(v, np.floating):
            sanitized[k] = float(v)
        elif isinstance(v, np.integer):
            sanitized[k] = int(v)
        elif isinstance(v, np.bool_):
            sanitized[k] = bool(v)
        elif isinstance(v, np.ndarray):
            sanitized[k] = v.tolist()
        else:
            sanitized[k] = v
    return sanitized

# Global instance
pipeline = FeaturePipeline()
