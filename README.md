# Mission SIH — Industrial Fire & Thermal Source Detection

**Smart India Hackathon 2026 · SIH26162 · NTRO · Disaster Management · Software**

Mission SIH is a geospatial AI system for classifying satellite-detected thermal anomalies across India. It combines NASA FIRMS thermal detections with land-use data and OpenStreetMap infrastructure, applies type-specific neural-network classifiers, stores the results in PostgreSQL/PostGIS, and presents them on an interactive map.

The system is designed around two outputs of the SIH problem:

1. Separate industrial/persistent thermal sources from natural fires.
2. Store and visualize the classified detections as a GIS layer over India.

> **Important:** the website currently uses the configured NASA FIRMS **VIIRS NOAA-20 Standard Processing (`VIIRS_NOAA20_SP`)** source. This is not a true real-time/NRT feed. Standard Processing is used because the project depends on FIRMS' `type` field, including the `type = 1` volcano rule.

## Table of contents

- [System architecture](#system-architecture)
- [Classification pipeline](#classification-pipeline)
- [Training-data pipeline](#training-data-pipeline)
- [Models](#models)
- [Training/runtime parity](#trainingruntime-parity)
- [Repository layout](#repository-layout)
- [Running the website](#running-the-website)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Known limitations](#known-limitations)
- [Data and model notes](#data-and-model-notes)
- [License](#license)

---

## System architecture

```mermaid
graph TB
    subgraph frontend["Frontend — Plain HTML/JS/CSS"]
        map["Leaflet map\nclustering + base layers"]
        filters["Filters + statistics\nChart.js"]
        detail["Hotspot detail panel"]
    end

    subgraph backend["Backend — FastAPI"]
        main["main.py\nHTTP/API endpoints"]
        firms["firms.py\nFIRMS API client"]
        ingestion["ingestion.py\ningestion + scheduling"]
        pipeline["pipeline.py\nfeature engineering + classification"]
        database["database.py\nSQLAlchemy/PostGIS"]
    end

    subgraph storage["Local/DB storage"]
        postgres[("PostgreSQL + PostGIS\nhotspots + OSM + ingest runs")]
        landuse["Land-use BallTree indexes\nper year"]
        osm["OSM BallTree index"]
    end

    subgraph external["External services"]
        firmsapi["NASA FIRMS\nVIIRS NOAA-20 SP Area API"]
        hf["Hugging Face\n3 type-specific models"]
    end

    firmsapi --> firms
    firms --> ingestion
    ingestion --> pipeline
    pipeline --> landuse
    pipeline --> osm
    pipeline --> hf
    pipeline --> database
    database --> postgres
    main --> pipeline
    main --> database
    postgres --> map
    postgres --> filters
    postgres --> detail
    main -.serves.-> map
    main -.serves.-> filters
    main -.serves.-> detail
```

### Main components

**Backend:** FastAPI, SQLAlchemy, PostgreSQL/PostGIS, APScheduler, NumPy/Pandas/scikit-learn.

**Frontend:** plain HTML, CSS and JavaScript. Leaflet is used for mapping and Chart.js for statistics; there is no frontend build step.

**Spatial matching:** the website builds cached BallTree indexes from the land-use and OSM CSV files so request-time classification does not repeatedly scan the raw datasets.

**Models:** three existing scikit-learn `MLPClassifier` artifacts are loaded from Hugging Face when configured, with local `model/hf_model/type_{0,2,3}_model.joblib` files as the local fallback.

---

## Classification pipeline

Every FIRMS detection follows the same high-level decision order in `website/backend/app/pipeline.py`:

```text
FIRMS detection
      │
      ├── type == 1 ? ── yes ──> Volcano
      │                         (MLP not called)
      │
      └── otherwise
            │
            ▼
       Spatial lookup
       land-use + OSM
       within 2000 m
            │
            ├── no match ──> Unclassified
            │                (MLP not called)
            │
            └── match
                  │
                  ├── type 0 ──> Type-0 MLP
                  │              Forest / Agriculture
                  │
                  ├── type 2 ──> Type-2 MLP
                  │              industrial_facility / quarry /
                  │              power_plant / gas_flare / mine
                  │
                  ├── type 3 ──> Type-3 MLP
                  │              industrial_facility / quarry /
                  │              gas_flare / power_plant
                  │
                  └── unexpected type ──> Unclassified
```

### FIRMS type handling

The website currently expects NOAA-20 Standard Processing data containing the FIRMS `type` field.

- `type = 0`: presumed vegetation fire; classified by the Type-0 model.
- `type = 1`: active-volcano category; handled directly as `Volcano` without an MLP call.
- `type = 2`: other static land source; classified by the Type-2 model.
- `type = 3`: offshore source; classified by the Type-3 model.
- Any other type value: `Unclassified` with `decision_path = unexpected_type`.

### Spatial matching

The runtime pipeline uses a 2 km radius and great-circle distance with an Earth radius of **6,371,000 m**.

1. It searches the land-use index for the detection's calendar year.
2. If that exact year is unavailable at runtime, the current website falls back to the nearest available land-use year and records the year actually used in `landuse_year_used`.
3. It searches the OSM index globally.
4. An OSM match replaces the existing land-use match when the OSM point is within 2 km and is closer, or when there is no land-use match.
5. If neither source provides a point within 2 km, the detection is stored as `Unclassified` and no MLP prediction is made.

The distance to the selected point is stored as `match_dist_m`.

### Output groups

| Group | Labels |
|---|---|
| **Industrial** | `gas_flare`, `industrial_facility`, `mine`, `oil_gas`, `power_plant`, `quarry` |
| **Natural** | `Forest`, `Agriculture` |
| **Volcano** | `Volcano` |
| **Unclassified** | No spatial match or unexpected FIRMS type |

---

## Training-data pipeline

The training workflow is kept separately from the running website under `data/`, `data_processing/`, and `model/`.

### Source datasets

#### NASA FIRMS

The project training data uses **VIIRS NOAA-20** detections over the India bounding box:

```text
West:  68.0°E
East:  97.5°E
South:  6.0°N
North: 37.5°N
```

The training source uses the FIRMS fields:

```text
latitude, longitude, brightness, scan, track,
acq_date, acq_time, confidence, bright_t31,
frp, daynight, type
```

The project build notes record the historical training snapshot as covering **2018-04-01 through 2026-05-31**. The website is separate from that frozen snapshot and retrieves the latest data available through its configured FIRMS source/date limit.

#### OpenStreetMap

OSM infrastructure was fetched through Overpass for the India bounding box and cleaned into `data/osm_data_cleaned.csv`.

The cleaned categories are:

```text
industrial_facility
quarry
power_plant
mine
oil_gas
gas_flare
```

Refinery features were folded into `industrial_facility`. Volcano OSM features are not used for the classification file because volcano handling is performed directly from FIRMS `type = 1`.

The project build snapshot records **67,047 cleaned OSM points**.

#### Land-use data

`data/land_use_data.csv` contains year-tagged land-use points. The project build snapshot records **17,650,701 rows for 2018–2026**.

Large CSV datasets are stored using Git LFS. After cloning the repository, run `git lfs pull` before attempting to rebuild the lookup indexes.

### Preprocessing

FIRMS categorical fields are encoded during preprocessing and runtime as follows:

| Field | Mapping |
|---|---|
| `confidence` | `l = 300`, `n = 600`, `h = 900` |
| `daynight` | `D = 0`, `N = 1` |
| `acq_time` | raw FIRMS integer `HHMM`, in UTC |

Example: FIRMS `606` represents `06:06` UTC.

### Engineered values

The website computes these additional values from each FIRMS detection:

```text
track_scan  = scan × track
final_bright = brightness × bright_t31
radiation    = track_scan × frp
```

These values are stored and exposed by the backend. **They should not be confused with the actual MLP input contract used by the current deployed pipeline.**

---

## Models

The current website does **not** use the old single-model design described in the earlier `website/README.md`. It loads three type-specific MLPs:

| Model | FIRMS type | Output labels | Hidden layer | Activation | Test accuracy* |
|---|---:|---|---:|---|---:|
| Type 0 | 0 | Forest, Agriculture | 200 | ReLU | **73.95%** |
| Type 2 | 2 | industrial_facility, quarry, power_plant, gas_flare, mine | 300 | Logistic | **74.95%** |
| Type 3 | 3 | industrial_facility, quarry, gas_flare, power_plant | 200 | ReLU | **97.71%** |

\* Accuracy values are the values reported by the training notebooks on their respective held-out random test splits. They are **not** a guarantee of per-class field performance.

### Type-specific training configurations

All three models use the Adam optimizer, but they are not configured identically.

**Type 0:**

- Hidden layer: 200
- Activation: ReLU
- Batch size: 1000
- Learning rate: adaptive
- Initial learning rate: 0.001
- Early stopping: enabled
- Random state: 42

**Type 2:**

- Hidden layer: 300
- Activation: logistic
- Batch size: 5000
- Learning rate: adaptive
- Initial learning rate: 0.001
- Early stopping: disabled
- Random state: 23

**Type 3:**

- Hidden layer: 200
- Activation: ReLU
- Batch size: 100
- Learning rate: adaptive
- Initial learning rate: 0.0001
- Early stopping: enabled
- Random state: 42

The training notebooks do not use a feature-scaling step in the final `X = df.drop(columns="category")` model input.

### Actual model input contract

The current training datasets and deployment pipeline do **not** feed the same 15-column feature list that appeared in the earlier documentation/helper script.

The current backend explicitly selects:

**Type 0 — 13 inputs**

```text
latitude
longitude
brightness
scan
track
acq_time
confidence
bright_t31
frp
daynight
type
year
match_dist_m
```

**Type 2 — 12 inputs**

```text
latitude
longitude
brightness
scan
track
acq_time
confidence
bright_t31
frp
daynight
type
match_dist_m
```

**Type 3 — 12 inputs**

```text
latitude
longitude
brightness
scan
track
acq_time
confidence
bright_t31
frp
daynight
type
match_dist_m
```

The helper file `model/hf_model/model_predict.py` still contains an older 15-feature list. The running website should be treated as the authoritative inference path because it matches the currently loaded type-specific models and the backend's explicit feature selection.

### Class imbalance

The reported overall accuracies need strong qualification.

For Type 2, the training/test distribution is heavily dominated by `industrial_facility` and `quarry`, while `mine`, `gas_flare`, and `power_plant` have far fewer examples.

For Type 3, the test confusion matrix shows that the model correctly predicts the dominant `industrial_facility` class while making no correct predictions for several minority classes in that test run.

Therefore, an overall accuracy such as **97.71% for Type 3 must not be interpreted as 97.71% accuracy for every output class**.

---

## Training/runtime parity

The repository contains `website/backend/scripts/parity_check.py`, which checks the runtime feature engineering against rows in `data/final_dataset.csv`.

There is an important distinction to keep documented:

### Historical training notebook

`data_processing/produce_final_dataset.ipynb` contains the original training-data matching procedure. In that notebook, the OSM stage overwrites a land-use category whenever a valid OSM point exists within 2 km.

### Current website runtime

`website/backend/app/pipeline.py` uses the stricter rule:

```text
replace the land-use match only when
OSM is within 2 km AND is closer,
or when no land-use match exists
```

The runtime also has a nearest-available-year fallback for land-use indexes when an exact year is not present.

Because of these differences, the website should **not** be described as byte-for-byte identical to the original historical dataset-generation notebook. `parity_check.py` currently validates engineered feature calculations; it does not prove full spatial-label parity with every historical training row.

This distinction is intentional documentation of the current repository state.

---

## Repository layout

```text
mission_sih/
├── data/
│   ├── *.csv                     # Training/data artifacts; large files use Git LFS
│   └── osm_data_fetch.ipynb       # Overpass extraction notebook
│
├── data_processing/
│   ├── nasa_data_processing.ipynb
│   ├── osm_data_processing.ipynb
│   ├── landuse_data_processing.ipynb
│   └── produce_final_dataset.ipynb
│
├── model/
│   ├── hf_model/
│   │   ├── type_0_model.joblib
│   │   ├── type_2_model.joblib
│   │   ├── type_3_model.joblib
│   │   ├── model.joblib             # older artifact retained in repo
│   │   ├── model_predict.py         # older helper; see model-input note above
│   │   └── requirements.txt
│   ├── model_train_type_0.ipynb
│   ├── model_train_type_2.ipynb
│   └── model_train_type_3.ipynb
│
├── website/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── pipeline.py
│   │   │   ├── firms.py
│   │   │   ├── ingestion.py
│   │   │   ├── database.py
│   │   │   └── config.py
│   │   ├── scripts/
│   │   │   ├── probe_firms.py
│   │   │   ├── build_lookup.py
│   │   │   └── parity_check.py
│   │   └── db/init.sql
│   ├── frontend/
│   │   ├── index.html
│   │   ├── about.html
│   │   ├── css/
│   │   ├── js/
│   │   └── vendor/
│   ├── docker-compose.yml
│   ├── requirements.txt
│   ├── test_components.sh
│   ├── test_ingest.py
│   └── test_numpy_cast.py
│
├── process.md
├── MISSION_COMPLETE.md
├── .env.example
├── .gitignore
├── .gitattributes
└── LICENSE
```

---

## Running the website

The commands below are written for Arch Linux, but the Python/Docker steps are portable to other Linux distributions.

### 1. Clone the repository

```bash
git clone https://github.com/bazik-0/mission_sih.git
cd mission_sih
```

### 2. Pull Git LFS data

Large training/data CSVs are tracked with Git LFS.

```bash
git lfs install
git lfs pull
```

### 3. Create/activate the Python environment

The project dependencies are listed in `website/requirements.txt`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r website/requirements.txt
```

The repository notebooks were developed/tested with Python 3.14 in the checked-in notebook metadata. The code does not enforce a Python version in `requirements.txt`.

### 4. Configure environment variables

Create `.env` in the repository root from `.env.example`.

Minimum settings used by the current application are:

```env
NASA_FIRMS_MAP_KEY="your_firms_key"
HUGGING_FACE_API=""
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/mission_sih"
FIRMS_SOURCE="VIIRS_NOAA20_SP"
FIRMS_AREA="68,6,97.5,37.5"
INGEST_INTERVAL_MINUTES="1440"
INITIAL_BACKFILL_DAYS="30"
```

The current application configuration also contains:

```text
FIRMS_MAX_DATE = 2026-06-30
```

This is a configured application cap for the Standard Processing source. It is not a claim that NASA's upstream catalogue can never contain later observations.

### 5. Start PostgreSQL/PostGIS

```bash
cd website
docker compose up -d
```

Check the database if required:

```bash
docker compose logs -f db
```

Wait until PostgreSQL reports that it is ready to accept connections.

### 6. Build spatial lookup indexes

From the repository root:

```bash
python website/backend/scripts/build_lookup.py
```

The script reads the land-use CSV in chunks and builds one BallTree index per available year, plus one OSM index. The generated files are stored under:

```text
website/backend/.cache/
```

These cache files are local runtime artifacts and should not be committed.

### 7. Run the parity check

```bash
python website/backend/scripts/parity_check.py
```

The script compares selected engineered values such as `track_scan`, `final_bright`, `radiation`, confidence encoding and day/night encoding against matching rows from the historical training dataset.

It is a feature-engineering check, not a proof that every runtime spatial label exactly reproduces the historical training notebook.

### 8. Start the application

```bash
cd website/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open:

```text
http://localhost:8000
```

### Startup behavior

On startup the application can:

1. Load the three type-specific models from Hugging Face when a token is configured.
2. Fall back to local `type_0_model.joblib`, `type_2_model.joblib`, and `type_3_model.joblib` files.
3. Load OSM features into PostGIS if they are not already present.
4. Run the configured initial FIRMS backfill.
5. Start scheduled ingestion according to `INGEST_INTERVAL_MINUTES`.

---

## Configuration

| Variable | Default/current behavior | Purpose |
|---|---|---|
| `DATABASE_URL` | Local Postgres URL | PostgreSQL/PostGIS connection |
| `NASA_FIRMS_MAP_KEY` | Required | NASA FIRMS API key |
| `FIRMS_SOURCE` | `VIIRS_NOAA20_SP` | FIRMS source used by the website |
| `FIRMS_AREA` | `68,6,97.5,37.5` | India bounding box: west,south,east,north |
| `FIRMS_MAX_DATE` | `2026-06-30` in current config | Upper date cap used by the SP ingestion code |
| `HUGGING_FACE_API` | Empty | Optional Hugging Face token; enables HF model downloads |
| `INGEST_INTERVAL_MINUTES` | `1440` | Scheduled ingestion interval |
| `INITIAL_BACKFILL_DAYS` | `30` | Initial backfill length |

---

## API reference

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Model status/source, DB connectivity, FIRMS key presence, FIRMS usage information and latest acquisition information |
| `POST /api/ingest?days=N` | Trigger a manual ingestion run |
| `GET /api/hotspots` | Filter hotspots and return them as GeoJSON |
| `GET /api/hotspots/{id}` | Return full details for one hotspot, including probabilities and stored features |
| `GET /api/stats` | Return aggregate counts and daily statistics for the current filter |
| `GET /api/infrastructure` | Return OSM infrastructure features as GeoJSON |
| `GET /api/export?format=csv\|geojson` | Export the current filtered dataset |

The hotspot endpoint supports the filters implemented by the frontend/backend, including bounding box, date range, final label/group, decision path and minimum probability.

---

## Data flow into the database

For each ingested FIRMS detection, the backend stores the original observation fields together with:

- engineered values: `track_scan`, `final_bright`, `radiation`
- encoded values: `confidence_encoded`, `daynight_encoded`
- spatial attribution: `match_dist_m`, `matched_from`, `landuse_year_used`
- model output: `predicted_class`, class probability dictionary, `final_label`, `final_group`
- decision route: `decision_path`
- source metadata such as FIRMS source, satellite, instrument and version when provided

Ingestion is idempotent at the application level by checking the combination of latitude, longitude, acquisition date and acquisition time before inserting a new hotspot.

---

## Known limitations

### 1. Standard Processing is not real-time

The current source is `VIIRS_NOAA20_SP`, not the NRT feed. The site therefore represents the **latest available Standard Processing data within the configured date range**, not live satellite observations.

### 2. FIRMS type is an upstream dependency

The classification strategy depends on the FIRMS `type` field. In particular, the volcano shortcut requires `type = 1`, and the three MLPs are selected using `type = 0`, `2`, or `3`.

### 3. Spatial attribution is approximate

A FIRMS detection represents a satellite thermal observation, while the OSM and land-use datasets con
