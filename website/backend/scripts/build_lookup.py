"""
Build lookup indexes from land use and OSM data.
Reproduces the logic from produce_final_dataset.ipynb.
"""
import sys
from pathlib import Path
import pickle
import time
import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings

EARTH_RADIUS_M = 6371000
CHUNK_SIZE = 1000000  # Process land use data in chunks

def build_landuse_indexes():
    """Build year-specific KD-tree indexes for land use data."""
    print("Building land use indexes...")
    start_time = time.time()

    landuse_file = settings.DATA_DIR / "land_use_data.csv"
    if not landuse_file.exists():
        print(f"ERROR: {landuse_file} not found")
        return

    cache_dir = settings.CACHE_DIR / "landuse_indexes"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Read in chunks and group by year
    year_data = {}
    total_rows = 0

    print(f"Reading {landuse_file} in chunks...")
    for chunk in pd.read_csv(landuse_file, chunksize=CHUNK_SIZE):
        total_rows += len(chunk)
        print(f"  Processed {total_rows:,} rows...", end='\r')

        for year, group in chunk.groupby('year'):
            if year not in year_data:
                year_data[year] = {'coords': [], 'types': []}

            coords = group[['latitude', 'longitude']].values
            types = group['land_type'].values

            year_data[year]['coords'].append(coords)
            year_data[year]['types'].append(types)

    print(f"\nTotal rows: {total_rows:,}")
    print(f"Years: {sorted(year_data.keys())}")

    # Build and save indexes for each year
    for year in sorted(year_data.keys()):
        print(f"Building index for year {year}...", end=' ')

        # Concatenate all chunks for this year
        coords = np.vstack(year_data[year]['coords'])
        types = np.concatenate(year_data[year]['types'])

        # Convert to radians for haversine
        coords_rad = np.radians(coords)

        # Build KD-tree with haversine metric
        nn = NearestNeighbors(n_neighbors=1, metric='haversine', algorithm='ball_tree')
        nn.fit(coords_rad)

        # Save to cache
        index_file = cache_dir / f"landuse_{year}.pkl"
        with open(index_file, 'wb') as f:
            pickle.dump({
                'nn': nn,
                'types': types,
                'coords': coords,
                'count': len(coords)
            }, f)

        print(f"{len(coords):,} points")

    elapsed = time.time() - start_time
    print(f"\nLand use indexes built in {elapsed:.2f} seconds")
    print(f"Cached to {cache_dir}")

    # Report memory estimate for one year
    sample_year = sorted(year_data.keys())[0]
    sample_file = cache_dir / f"landuse_{sample_year}.pkl"
    size_mb = sample_file.stat().st_size / 1024 / 1024
    print(f"Sample index size (year {sample_year}): {size_mb:.2f} MB")

def build_osm_index():
    """Build KD-tree index for OSM data."""
    print("\nBuilding OSM index...")
    start_time = time.time()

    osm_file = settings.DATA_DIR / "osm_data_cleaned.csv"
    if not osm_file.exists():
        print(f"ERROR: {osm_file} not found")
        return

    df = pd.read_csv(osm_file)
    print(f"OSM points: {len(df):,}")

    coords = df[['latitude', 'longitude']].values
    categories = df['osm_category'].values

    # Convert to radians for haversine
    coords_rad = np.radians(coords)

    # Build KD-tree
    nn = NearestNeighbors(n_neighbors=1, metric='haversine', algorithm='ball_tree')
    nn.fit(coords_rad)

    # Save to cache
    cache_file = settings.CACHE_DIR / "osm_index.pkl"
    with open(cache_file, 'wb') as f:
        pickle.dump({
            'nn': nn,
            'categories': categories,
            'coords': coords,
            'count': len(coords)
        }, f)

    elapsed = time.time() - start_time
    size_mb = cache_file.stat().st_size / 1024 / 1024
    print(f"OSM index built in {elapsed:.2f} seconds")
    print(f"Index size: {size_mb:.2f} MB")
    print(f"Cached to {cache_file}")

if __name__ == "__main__":
    print("="*60)
    print("Building lookup indexes")
    print("="*60)

    build_landuse_indexes()
    build_osm_index()

    print("\n" + "="*60)
    print("Done!")
    print("="*60)
