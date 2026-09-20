"""
Probe FIRMS API to determine which data source (NRT or SP) to use.
Tests for presence of 'type' column and available date ranges.
"""
import os
import sys
from pathlib import Path

# Add parent directory to path to import from app
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: python -m pip install requests")
    sys.exit(1)

# Load environment variables manually
env_path = Path(__file__).parent.parent.parent.parent / ".env"
MAP_KEY = None

if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("NASA_FIRMS_MAP_KEY="):
                MAP_KEY = line.split("=", 1)[1].strip('"\'')
                break

if not MAP_KEY:
    # Try environment variable
    MAP_KEY = os.getenv("NASA_FIRMS_MAP_KEY")
if not MAP_KEY:
    print("ERROR: NASA_FIRMS_MAP_KEY not found in .env")
    sys.exit(1)

# India bounding box: west, south, east, north
INDIA_BBOX = "68,6,97.5,37.5"

def redact_key(url):
    """Redact MAP_KEY from URL for safe logging"""
    return url.replace(MAP_KEY, "***REDACTED***")

def probe_availability(source):
    """Check data availability for a source"""
    url = f"https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/{MAP_KEY}/{source}"
    print(f"\n{'='*60}")
    print(f"Checking availability: {source}")
    print(f"URL: {redact_key(url)}")

    response = requests.get(url, timeout=30)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        lines = response.text.strip().split('\n')
        if len(lines) > 1:
            dates = [line.strip() for line in lines if line.strip()]
            print(f"Available dates: {dates[0]} to {dates[-1]}")
            print(f"Total days: {len(dates)}")
            return dates
    else:
        print(f"ERROR: {response.text[:200]}")
    return []

def probe_data(source, date=None):
    """Fetch sample data from a source"""
    # Use 1 day range
    date_param = f"/{date}" if date else ""
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{source}/{INDIA_BBOX}/1{date_param}"

    print(f"\n{'='*60}")
    print(f"Fetching sample data: {source}")
    print(f"URL: {redact_key(url)}")

    response = requests.get(url, timeout=30)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        lines = response.text.strip().split('\n')
        if len(lines) >= 1:
            print(f"\nHeader:")
            print(lines[0])

            # Check for 'type' column
            header = lines[0].split(',')
            has_type = 'type' in header
            print(f"\nHas 'type' column: {has_type}")

            # Check for brightness columns
            has_brightness = 'brightness' in header
            has_bright_ti4 = 'bright_ti4' in header
            has_bright_t31 = 'bright_t31' in header
            has_bright_ti5 = 'bright_ti5' in header

            print(f"Has 'brightness': {has_brightness}")
            print(f"Has 'bright_ti4': {has_bright_ti4}")
            print(f"Has 'bright_t31': {has_bright_t31}")
            print(f"Has 'bright_ti5': {has_bright_ti5}")

            # Print sample data rows
            print(f"\nSample data ({min(2, len(lines)-1)} rows):")
            for i in range(1, min(3, len(lines))):
                print(lines[i])

            print(f"\nTotal rows: {len(lines) - 1}")

            return {
                'header': header,
                'has_type': has_type,
                'has_brightness': has_brightness,
                'has_bright_ti4': has_bright_ti4,
                'has_bright_t31': has_bright_t31,
                'has_bright_ti5': has_bright_ti5,
                'row_count': len(lines) - 1
            }
        else:
            print("No data rows (only header or empty)")
    else:
        print(f"ERROR: {response.text[:200]}")

    return None

def check_usage():
    """Check API key usage"""
    url = f"https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/?MAP_KEY={MAP_KEY}"
    print(f"\n{'='*60}")
    print(f"Checking API usage")
    print(f"URL: {redact_key(url)}")

    response = requests.get(url, timeout=30)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        print(f"Usage info:\n{response.text}")
    else:
        print(f"ERROR: {response.text[:200]}")

if __name__ == "__main__":
    print("FIRMS API Probe")
    print("="*60)

    # Check usage first
    check_usage()

    # Check availability for both sources
    nrt_dates = probe_availability("VIIRS_NOAA20_NRT")
    sp_dates = probe_availability("VIIRS_NOAA20_SP")

    # Probe NRT data (most recent)
    nrt_info = probe_data("VIIRS_NOAA20_NRT")

    # Probe SP data - parse the actual dates from CSV format
    sp_info = None
    if sp_dates and len(sp_dates) > 1:
        # The response is CSV format: data_id,min_date,max_date
        # Second line has: VIIRS_NOAA20_SP,2018-04-01,2026-06-30
        parts = sp_dates[1].split(',')
        if len(parts) >= 3:
            max_date = parts[2]  # Use the max available date
            print(f"\nTesting SP with date: {max_date}")
            sp_info = probe_data("VIIRS_NOAA20_SP", max_date)

    # Decision
    print("\n" + "="*60)
    print("DECISION")
    print("="*60)

    if nrt_info and nrt_info['has_type']:
        print("✓ Use VIIRS_NOAA20_NRT (has 'type' column)")
        print(f"  Latest available: {nrt_dates[-1] if nrt_dates else 'unknown'}")
    elif sp_info and sp_info['has_type']:
        print("✓ Use VIIRS_NOAA20_SP (has 'type' column)")
        print(f"  Latest available: {sp_dates[-1] if sp_dates else 'unknown'}")
        print("  WARNING: This is standard processing data with several months lag")
        print("  The interface MUST show 'Data through YYYY-MM-DD, standard processing'")
    else:
        print("✗ NEITHER source has 'type' column - CANNOT PROCEED")
        print("  Contact the mission owner for guidance")
        sys.exit(1)
