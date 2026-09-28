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
    """Feature engineering and classification pipeline with type-specific models."""

    def __init__(self):
        self.models = {}  # Dictionary to hold models by type: {0: model, 2: model, 3: model}
        self.model_classes = None  # All models share the same classes
        self.landuse_indexes = {}  # Cached by year
        self.osm_index = None
        self.model_source = None

    def load_model(self):
        """Load type-specific models from Hugging Face or local fallback."""
        if len(self.models) > 0:
            return

        import joblib

        # Load models for each type: 0, 2, 3
        model_types = [0, 2, 3]

        # Try Hugging Face first
        if settings.HUGGING_FACE_API:
            try:
                from huggingface_hub import hf_hub_download

                # Create Hugging Face repo connection string
                for model_type in model_types:
                    try:
                        # For Type 0, 2, 3 models
                        repo_id = f"bazik-0/mission-sih-type-{model_type}"
                        model_filename = f"type_{model_type}_model.joblib"
                        model_path = hf_hub_download(
                            repo_id=repo_id,
                            filename=model_filename,
                            token=settings.HUGGING_FACE_API,
                            cache_dir=settings.CACHE_DIR / f"hf_cache_type_{model_type}"
                        )
                        self.models[model_type] = joblib.load(model_path)
                        print(f"Model for type {model_type} loaded from Hugging Face: {repo_id}/{model_filename}")
                    except Exception as e:
                        print(f"Failed to load model for type {model_type} from Hugging Face: {e}")
                        # Continue to try other types

                # If we loaded at least one model, set the classes from the first one
                if len(self.models) > 0:
                    # Get classes from the first loaded model
                    first_model_key = list(self.models.keys())[0]
                    self.model_classes = self.models[first_model_key].classes_
                    self.model_source = "huggingface"
                    print(f"Loaded {len(self.models)} type-specific models from Hugging Face")
                    return

            except Exception as e:
                print(f"Hugging Face loading failed: {e}")

        # Fallback to local models
        for model_type in model_types:
            try:
                # Look for type-specific models in local directory
                local_model = settings.MODEL_DIR / f"type_{model_type}_model.joblib"
                if local_model.exists():
                    self.models[model_type] = joblib.load(local_model)
                    print(f"Model for type {model_type} loaded from local: {local_model}")
                else:
                    print(f"Local model not found for type {model_type}: {local_model}")
            except Exception as e:
                print(f"Failed to load local model for type {model_type}: {e}")

        # If we loaded at least one model, set the classes
        if len(self.models) > 0:
            # Get classes from the first loaded model
            first_model_key = list(self.models.keys())[0]
            self.model_classes = self.models[first_model_key].classes_
            self.model_source = "local"
            print(f"Loaded {len(self.models)} type-specific models from local")
            return

        # If no models loaded at all
        raise RuntimeError(f"No type-specific models found for types {model_types}")

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
            elif pd.isna(categories[i]):
                result['final_label'] = 'Unclassified'
                result['final_group'] = 'unclassified'
                result['decision_path'] = 'no_match'
                result['predicted_class'] = None
                result['probabilities'] = None
                result['matched_from'] = None

            # Decision path 3: Run type-specific MLP (types 0, 2, 3)
            elif firms_type in [0, 2, 3]:
                # Check if we have a model for this type
                if firms_type not in self.models:
                    # Fallback to any available model or skip classification
                    if len(self.models) > 0:
                        # Use the first available model as fallback
                        model_type = list(self.models.keys())[0]
                        model = self.models[model_type]
                        print(f"WARNING: No model for type {firms_type}, using fallback model for type {model_type}")
                    else:
                        # No models available at all
                        result['final_label'] = 'Unclassified'
                        result['final_group'] = 'unclassified'
                        result['decision_path'] = 'no_model'
                        result['predicted_class'] = None
                        result['probabilities'] = None
                        result['matched_from'] = None
                        results.append(result)
                        continue
                else:
                    model = self.models[firms_type]

                # Prepare features for model based on type
                # Note: type 0 uses 'year', while types 2 and 3 do not.
                feature_dict = {
                    **features[i],
                    'match_dist_m': distances[i]
                }

                # Setup specific features for current model
                if firms_type == 0:
                    feature_dict['year'] = landuse_years[i] if landuse_years[i] != -1 else int(str(row.get('acq_date', '2018'))[:4])
                    features_to_use = [
                        "latitude", "longitude", "brightness", "scan", "track",
                        "acq_time", "confidence", "bright_t31", "frp", "daynight",
                        "type", "year", "match_dist_m"
                    ]
                else:
                    features_to_use = [
                        "latitude", "longitude", "brightness", "scan", "track",
                        "acq_time", "confidence", "bright_t31", "frp", "daynight",
                        "type", "match_dist_m"
                    ]

                X = pd.DataFrame([feature_dict])[features_to_use]

                # Predict
                probs = model.predict_proba(X)[0]
                predicted_idx = np.argmax(probs)
                predicted_class = model.classes_[predicted_idx]

                # Map generic class IDs back to original labels if necessary
                # based on our knowledge of the model.classes_
                if firms_type == 0:
                    class_mapping = {1: 'Forest', 2: 'Agriculture'}
                elif firms_type == 2:
                    class_mapping = {1: 'industrial_facility', 2: 'quarry', 3: 'power_plant', 4: 'gas_flare', 5: 'mine'}
                else:  # type 3
                    class_mapping = {1: 'industrial_facility', 2: 'quarry', 3: 'gas_flare', 4: 'power_plant'}

                # Ensure predicted_class is a string representation of the mapped class label
                if isinstance(predicted_class, (int, np.integer)) or (isinstance(predicted_class, str) and predicted_class.isdigit()):
                    predicted_class = class_mapping.get(int(predicted_class), str(predicted_class))

                # Also update probabilities keys
                mapped_probs_dict = {}
                for cls, prob in zip(model.classes_, probs):
                    mapped_cls = class_mapping.get(int(cls), str(cls)) if isinstance(cls, (int, np.integer)) or (isinstance(cls, str) and cls.isdigit()) else str(cls)
                    mapped_probs_dict[mapped_cls] = float(prob)

                result['predicted_class'] = predicted_class
                result['probabilities'] = mapped_probs_dict
                result['final_label'] = predicted_class
                result['decision_path'] = f'mlp_type_{firms_type}'

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
