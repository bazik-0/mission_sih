# Mission SIH - Industrial Fire Detection System

AI-based detection and classification of industrial fires and persistent thermal sources using NASA FIRMS, OSM, and satellite data.

**Problem Statement:** SIH26162 (NTRO, Disaster Management, Software)

## Overview

This system classifies NASA FIRMS thermal detections in India to distinguish industrial fires and persistent thermal sources from natural fires. It combines satellite thermal data with land-cover and industrial infrastructure datasets using a trained neural network.

## Features

- **Real-time Classification:** Classifies VIIRS thermal detections using a trained MLP model
- **Interactive Map:** View hotspots on an interactive map with filtering by group, label, date, and confidence
- **Decision Logic:** Volcano rule → No match rule → MLP classification
- **Statistics Dashboard:** View counts by group, label, and day
- **Export:** Export filtered data as CSV or GeoJSON
- **Automated Ingestion:** Scheduled fetching and classification of new FIRMS data

## Architecture

- **Backend:** FastAPI with PostgreSQL/PostGIS
- **Frontend:** Plain HTML/JS/CSS with Leaflet for mapping
- **Model:** scikit-learn MLPClassifier (67.86% test accuracy)
- **Data Sources:** NASA FIRMS VIIRS NOAA-20 (Standard Processing), OpenStreetMap, Land-use dataset

## Prerequisites

- Python 3.14+
- PostgreSQL with PostGIS extension
- Docker and Docker Compose (for database)
- Arch Linux (or adapt package manager commands)

## Setup Instructions

### 1. Clone and Navigate

```bash
cd ~/mission_sih/mission_sih/website
```

### 2. Install System Dependencies

```bash
sudo pacman -S docker docker-compose curl unzip
sudo systemctl start docker
sudo systemctl enable docker
```

### 3. Set Up Python Environment

```bash
# Activate your virtual environment
source ~/.venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 4. Configure Environment Variables

The `.env` file already exists in the project root. Verify it contains:

```bash
HUGGING_FACE_API="your_token_here"
NASA_FIRMS_MAP_KEY="your_key_here"
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/mission_sih"
FIRMS_SOURCE="VIIRS_NOAA20_SP"
FIRMS_AREA="68,6,97.5,37.5"
INGEST_INTERVAL_MINUTES="1440"
INITIAL_BACKFILL_DAYS="30"
```

The NASA_FIRMS_MAP_KEY is already set in your `.env`.

### 5. Start PostgreSQL Database

```bash
docker-compose up -d
```

Wait for the database to be ready:

```bash
docker-compose logs -f db
# Wait until you see "database system is ready to accept connections"
# Press Ctrl+C to exit logs
```

### 6. Build Lookup Indexes

This step creates spatial indexes for land-use and OSM data (takes ~5-10 minutes):

```bash
python backend/scripts/build_lookup.py
```

Expected output:
- Land use indexes built for years 2018-2026
- OSM index built with 67,047 points
- Cached to `backend/.cache/`

### 7. Verify Feature Engineering (Parity Check)

```bash
python backend/scripts/parity_check.py
```

This compares your feature pipeline with the training data. Should show >99% match rate.

### 8. Start the Application

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The application will:
1. Load the model from Hugging Face (or local fallback)
2. Load OSM features into the database
3. Run initial backfill (30 days of FIRMS data)
4. Start scheduled ingestion (every 24 hours by default)

### 9. Access the Application

Open your browser and navigate to:

```
http://localhost:8000
```

## Usage

### Main Interface

- **Map:** Click on hotspots to view details
- **Filters:** Filter by date range, group (industrial/natural/volcano/unclassified), label, decision path, and minimum probability
- **Statistics:** View counts by group and daily trends
- **Export:** Download filtered data as CSV or GeoJSON
- **Manual Ingest:** Trigger a manual data fetch from FIRMS

### About Page

Navigate to `/about.html` for detailed information about:
- Classification model and training
- Labeling method
- Decision logic
- Limitations and uncertainties

## Data Sources

### NASA FIRMS

- **Source:** VIIRS NOAA-20 Standard Processing (SP)
- **Coverage:** India (68°E to 97.5°E, 6°N to 37.5°N)
- **Lag:** ~3 months (latest data: 2026-06-30)
- **Type field:** Present in SP, used for volcano detection

### OpenStreetMap

- **Points:** 67,047 industrial infrastructure features
- **Categories:** power_plant, mine, oil_gas, gas_flare, industrial_facility, quarry

### Land Use

- **Points:** 17.6 million land-use points (2018-2026)
- **Types:** Agriculture, Forest, and others

## Classification

### Model

- **Type:** scikit-learn MLPClassifier
- **Architecture:** 1 hidden layer, 200 units, ReLU activation
- **Input features:** 15 (lat, lon, scan, track, FRP, brightness, etc.)
- **Output classes:** 8 (Agriculture, Forest, gas_flare, industrial_facility, mine, oil_gas, power_plant, quarry)
- **Test accuracy:** 67.86% on 20% random split

### Decision Logic

1. **Volcano rule:** If FIRMS type = 1, label as Volcano (model not called)
2. **No match:** If no land-use or OSM point within 2000m, label as Unclassified (model not called)
3. **MLP:** For types 0, 2, 3 with a match, run model and use prediction
4. **Unexpected type:** For other types, label as Unclassified

### Groups

- **Industrial:** gas_flare, industrial_facility, mine, oil_gas, power_plant, quarry
- **Natural:** Forest, Agriculture
- **Volcano:** Active volcanic sources
- **Unclassified:** No match or unexpected type

## API Endpoints

- `GET /api/health` - System health and status
- `POST /api/ingest?days=N` - Trigger manual ingestion
- `GET /api/hotspots?bbox=...&date_from=...&date_to=...&final_group=...` - Get hotspots (GeoJSON)
- `GET /api/hotspots/{id}` - Get detailed hotspot information
- `GET /api/stats?bbox=...` - Get statistics for current filter
- `GET /api/infrastructure?bbox=...` - Get OSM infrastructure points (GeoJSON)
- `GET /api/export?format=csv&bbox=...` - Export data (CSV or GeoJSON)

## Configuration

Edit `.env` to adjust:

- `INGEST_INTERVAL_MINUTES` - How often to fetch new data (default: 1440 = 24 hours)
- `INITIAL_BACKFILL_DAYS` - How many days to backfill on startup (default: 30)
- `FIRMS_SOURCE` - FIRMS data source (default: VIIRS_NOAA20_SP)

## Troubleshooting

### Database Connection Failed

```bash
# Check if database is running
docker-compose ps

# Restart database
docker-compose restart db

# Check logs
docker-compose logs db
```

### Model Not Loading

The application tries Hugging Face first, then falls back to `model/hf_model/model.joblib`. Ensure the local model file exists.

### No Detections Displayed

1. Check if ingestion completed successfully (see logs or `/api/health`)
2. Verify date filters match available data
3. Check that the map bounds cover India

### Lookup Indexes Not Found

Run `python backend/scripts/build_lookup.py` to build the indexes.

## Testing

### Run Parity Check

```bash
python backend/scripts/parity_check.py
```

### Test Individual Components

```bash
# Test FIRMS API
python backend/scripts/probe_firms.py

# Test database connection
python -c "from app.database import engine; from sqlalchemy import text; engine.connect().execute(text('SELECT 1'))"
```

## Project Structure

```
website/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI application
│   │   ├── config.py        # Configuration
│   │   ├── database.py      # Database models
│   │   ├── pipeline.py      # Feature engineering & classification
│   │   ├── firms.py         # FIRMS API client
│   │   └── ingestion.py     # Ingestion service
│   ├── scripts/
│   │   ├── probe_firms.py   # FIRMS API probe
│   │   ├── build_lookup.py  # Build spatial indexes
│   │   └── parity_check.py  # Verify feature pipeline
│   └── db/
│       └── init.sql         # Database schema
├── frontend/
│   ├── index.html           # Main page
│   ├── about.html           # About page
│   ├── css/
│   │   └── style.css        # Styles
│   ├── js/
│   │   ├── app.js          # Main application logic
│   │   ├── map.js          # Map manager
│   │   ├── api.js          # API client
│   │   └── ui.js           # UI manager
│   └── vendor/              # Third-party libraries (Leaflet, Chart.js)
├── docker-compose.yml       # PostgreSQL with PostGIS
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## License

Apache-2.0

## Credits

- **Owner:** Bazik
- **Repository:** github.com/bazik-0/mission_sih
- **Model:** Hugging Face bazik-0/mission-sih
