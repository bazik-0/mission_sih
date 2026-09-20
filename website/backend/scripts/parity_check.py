"""
Parity check: verify feature engineering matches training pipeline.
Takes a sample from nasa_data_cleaned.csv, runs it through the pipeline,
and compares results with final_dataset.csv.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.pipeline import pipeline

def check_parity():
    """Compare engineered features with training data."""
    print("="*60)
    print("Parity Check: Feature Engineering")
    print("="*60)

    # Load samples
    nasa_file = settings.DATA_DIR / "nasa_data_cleaned.csv"
    final_file = settings.DATA_DIR / "final_dataset.csv"

    if not nasa_file.exists():
        print(f"ERROR: {nasa_file} not found")
        return

    if not final_file.exists():
        print(f"ERROR: {final_file} not found")
        return

    print(f"\nLoading samples...")

    # Load a small sample from nasa_data_cleaned
    nasa_df = pd.read_csv(nasa_file, nrows=1000)
    print(f"Loaded {len(nasa_df)} rows from nasa_data_cleaned.csv")

    # Load corresponding rows from final_dataset
    # Join on lat, lon, acq_time, brightness to find matches
    final_df = pd.read_csv(final_file)
    print(f"Loaded {len(final_df)} rows from final_dataset.csv")

    # Prepare nasa data for comparison
    nasa_sample = nasa_df.head(100).to_dict('records')

    print(f"\nTesting {len(nasa_sample)} samples...")

    matches = 0
    mismatches = []

    for row in nasa_sample:
        # Find matching row in final_dataset
        mask = (
            (final_df['latitude'] == row['latitude']) &
            (final_df['longitude'] == row['longitude']) &
            (final_df['acq_time'] == row['acq_time']) &
            (np.abs(final_df['brightness'] - row['brightness']) < 0.01)
        )

        final_row = final_df[mask]

        if len(final_row) == 0:
            continue  # This row was filtered out in training

        if len(final_row) > 1:
            final_row = final_row.iloc[0:1]  # Take first match

        final_row = final_row.iloc[0]

        # Engineer features using our pipeline
        engineered = pipeline.engineer_features(row)

        # Compare
        checks = {
            'track_scan': (engineered['track_scan'], final_row['track_scan']),
            'final_bright': (engineered['final_bright'], final_row['final_bright']),
            'radiation': (engineered['radiation'], final_row['radiation']),
            'confidence': (engineered['confidence'], final_row['confidence']),
            'daynight': (engineered['daynight'], final_row['daynight']),
        }

        all_match = True
        for feature, (computed, expected) in checks.items():
            if not np.isclose(computed, expected, rtol=1e-5):
                all_match = False
                mismatches.append({
                    'feature': feature,
                    'computed': computed,
                    'expected': expected,
                    'lat': row['latitude'],
                    'lon': row['longitude']
                })

        if all_match:
            matches += 1

    print(f"\nResults:")
    print(f"  Matches: {matches}")
    print(f"  Mismatches: {len(mismatches)}")

    if matches > 0:
        print(f"  Match rate: {matches / (matches + len(mismatches)) * 100:.1f}%")

    if mismatches:
        print(f"\nFirst 5 mismatches:")
        for mm in mismatches[:5]:
            print(f"  {mm['feature']}: computed={mm['computed']:.6f}, expected={mm['expected']:.6f}")
            print(f"    Location: {mm['lat']:.5f}, {mm['lon']:.5f}")

    print("\n" + "="*60)
    if len(mismatches) == 0 and matches > 0:
        print("✓ PASS: All features match training pipeline")
    elif matches / (matches + len(mismatches)) > 0.99:
        print("✓ PASS: >99% features match (minor floating point differences)")
    else:
        print("✗ FAIL: Significant mismatches found")
    print("="*60)

if __name__ == "__main__":
    # Load model and indexes first
    print("Loading model and indexes...")
    try:
        pipeline.load_model()
        print(f"Model loaded: {pipeline.model_source}")
    except Exception as e:
        print(f"Warning: Could not load model: {e}")

    check_parity()
