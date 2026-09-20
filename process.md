# Build the SIH26162 website

You are building a complete, working website for Smart India Hackathon 2026 problem statement SIH26162 (NTRO, Disaster Management, Software): AI-based detection and classification of industrial fires and persistent thermal sources using NASA FIRMS, OSM and satellite data. The owner is Bazik. The code lives in the GitHub repo bazik-0/mission_sih, which is checked out locally. Work inside it.

## How to work

- Read the repo first and check every fact in this prompt against the real files. If a file, column name or number differs from what is written here, stop and tell me instead of guessing.
- Never invent data. Do not make up a feature value, a label, a coordinate, a test result or a benchmark. If something you need is missing, say exactly what is missing and ask.
- Do not touch the trained model, the training notebooks, or anything under data/, data_processing/ and model/. Elsewhere in the repo, change existing files minimally (for example, append lines to .env.example and .gitignore). Leave website/aca.ipynb alone.
- Finish the job. No TODOs, no placeholders, no mock data in the running app, no "left as an exercise". Run the app against the real FIRMS API and confirm it works end to end before you say it is done. Report plainly what you verified and what you could not verify.
- Keep the interface plain and functional, a map-first tool and not a landing page. No emojis, no decorative gradients, no filler text.
- Do not add features that are not listed here (no login, no chatbot, no persistence or time-series analysis, no retraining).

## 1. The problem, in short

NASA FIRMS reports thermal anomalies seen by satellites but does not say what caused them: an industrial fire, a persistent industrial heat source such as a gas flare, agricultural burning, a forest fire, mining, a volcano. The task is a geospatial AI system that combines thermal detections with land-cover data, industrial infrastructure data and satellite imagery to identify, classify and monitor industrial fires and persistent thermal sources.

Two deliverables are listed: (i) classify and separate industrial fires from forest fires and other natural fires; (ii) a GIS-based solution that stores the data and shows the output as overlays on a map. This website is that solution, for India.

## 2. What already exists in the repo (verify each item)

Repo layout: data/, data_processing/, model/, website/ (contains only an empty notebook), .env.example, .gitignore (contains .env), .gitattributes (CSV files are Git LFS), LICENSE (Apache-2.0).

Training data pipeline, as written in data_processing/ and data/osm_data_fetch.ipynb:
- NASA FIRMS VIIRS detections from NOAA-20 only (satellite value N20), India, 2018-04-01 to 2026-05-31, 5,089,539 rows. Columns kept: latitude, longitude, brightness, scan, track, acq_date, acq_time, confidence, bright_t31, frp, daynight, type.
- Encodings: daynight D=0, N=1. confidence l/n/h was mapped to 0/1/2, then to 1/2/3, then multiplied by 300, so l=300, n=600, h=900. acq_time is the raw integer HHMM in UTC (606 means 06:06).
- OSM points fetched with Overpass for the box south 6.0, west 68.0, north 37.5, east 97.5. After cleaning (volcano category removed) there are 67,047 points in data/osm_data_cleaned.csv with columns latitude, longitude, osm_category. Categories: industrial_facility, quarry, power_plant, mine, oil_gas, gas_flare. Refineries were merged into industrial_facility.
- Land-use points in data/land_use_data.csv: 17,650,701 rows, columns year, land_type, latitude, longitude. This file is Git LFS (about 899 MB). Check that it is a real CSV and not a small LFS pointer text file. If it is a pointer, tell me to run git lfs pull; do not work around it.
- Labelling: each detection got a category from the nearest land-use point of the same year (radius 2000 m, haversine, earth radius 6371000 m), then the nearest OSM point (radius 2000 m) replaced it if the OSM point was within 2000 m and either no land-use match existed or it was closer. Detections with no match were dropped. Years with no land-use rows were skipped for the land-use step. Read data_processing/produce_final_dataset.ipynb and reproduce this logic exactly.
- Engineered features: track_scan = scan * track; final_bright = brightness * bright_t31; radiation = track_scan * frp; match_dist_m = distance in metres to the matched point (always 2000 or less for kept rows).

The model, model/hf_model/model.joblib (also uploaded to Hugging Face as bazik-0/mission-sih, note the hyphen):
- scikit-learn MLPClassifier, one hidden layer of 200 units, relu, adam, early stopping, no feature scaling.
- 15 input features in exactly this order: latitude, longitude, scan, track, track_scan, frp, radiation, brightness, bright_t31, final_bright, acq_time, daynight, confidence, type, match_dist_m.
- 8 output classes, in classes_ order: Agriculture, Forest, gas_flare, industrial_facility, mine, oil_gas, power_plant, quarry. There is no volcano class.
- Test accuracy 0.6786 on a random 20% split (random_state 42). No per-class metrics were computed.
- model/hf_model/model_predict.py shows the intended feature order. For the site, load the model once and call predict_proba on whole batches; take the class with argmax over model.classes_. If loading the model raises an InconsistentVersionWarning, report it and pin scikit-learn to the version used for training.

## 3. Decisions already made by the owner (do not revisit)

- Data comes from the live NASA FIRMS Area API, India only, NOAA-20 VIIRS only (the model was trained on N20 detections only; do not mix in S-NPP, NOAA-21 or MODIS).
- Classification uses the existing MLP exactly as trained. No retraining and no replacement model.
- Decision order for every hotspot:
  1. FIRMS type equals 1 (active volcano): label Volcano directly. The MLP is never called. The model was trained without type 1.
  2. Otherwise run the nearest-point lookup (section 5). If there is no land-use or OSM point within 2000 m, label Unclassified. The MLP is not called.
  3. Otherwise run the MLP (types 0, 2 and 3) and store the predicted class and all eight probabilities.
  If type is anything other than 0, 1, 2 or 3, label Unclassified with reason unexpected_type and log it.
- Grouping for the industrial versus natural separation: Industrial = gas_flare, industrial_facility, mine, oil_gas, power_plant, quarry. Natural = Forest, Agriculture. Volcano and Unclassified are their own groups.
- Stack: FastAPI backend, PostgreSQL with PostGIS, plain HTML, JavaScript and CSS with Leaflet, no front-end build step. It runs locally now and may be hosted later using Supabase (Postgres with PostGIS) and similar services, so keep all configuration in environment variables and use only standard Postgres and PostGIS features.
- The owner uses Arch Linux. Write the run instructions for it.

## 4. The FIRMS feed: probe first, then build

The FIRMS documentation says near-real-time (NRT) VIIRS data does not carry the type field and uses the column names bright_ti4 and bright_ti5 instead of brightness and bright_t31. The standard-processing (SP) product has the type field but lags by several months. The owner's training file used brightness, bright_t31 and type. Do not trust this paragraph or the owner's memory; test it.

Step 0, before writing application code, using the FIRMS key from .env (section 6), write scripts/probe_firms.py and run it:
- GET https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/{MAP_KEY}/VIIRS_NOAA20_SP and the same for VIIRS_NOAA20_NRT. Record the min and max dates.
- GET the Area API for VIIRS_NOAA20_NRT (1 day) and for VIIRS_NOAA20_SP (1 day, a date inside its available range), using the India box 68,6,97.5,37.5 (order is west,south,east,north). URL shape: https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{AREA}/{DAY_RANGE}/{DATE}. The DATE part is optional. Check https://firms.modaps.eosdis.nasa.gov/api/area/ for the maximum DAY_RANGE and chunk requests accordingly.
- Print only the CSV header and two data rows, never the key. Report the findings to me in your final message.

Then apply this rule:
- If the NRT response has a type column, use NRT as the source.
- Otherwise, if the SP response has a type column, use SP as the source. In that case the interface must show the source name and the latest acquisition date in a banner ("Data through YYYY-MM-DD, standard processing") so nobody mistakes it for live data.
- If neither has type, stop and tell me. Never fill in type with a guess, a constant or a value from a rule.

Column normalisation (accept both schemas): brightness or bright_ti4 becomes brightness; bright_t31 or bright_ti5 becomes bright_t31. Ignore version, satellite and instrument for the model. confidence arrives as the letters l, n, h and is encoded as in section 2. Times are UTC. An empty response with only a header means no detections. A body saying the key is invalid is an error, not "no data".

Rate limit: 5000 transactions per 10 minutes per key, and larger requests count as several transactions. Check usage with GET https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/?MAP_KEY={MAP_KEY} (returns JSON) and show it on the health endpoint. Cache responses, make ingestion idempotent, and never poll faster than the source updates. Interval and initial backfill length are config values (default backfill 30 days of available data).

## 5. Feature pipeline and lookup (must match training)

Build the same 15 features as training, in the same order, from a FIRMS row:
- latitude, longitude, scan, track, frp as given; acq_time as the integer HHMM.
- track_scan, final_bright, radiation from the formulas in section 2. daynight and confidence encoded as in section 2. type as the integer from FIRMS.
- match_dist_m from the lookup below.

Lookup, reproducing produce_final_dataset.ipynb:
- Land-use: nearest point among land-use rows of the same calendar year as acq_date, within 2000 m. If the file has no rows for that year, use the nearest available year and record which year was used (landuse_year_used). Skip the land-use step only if the file has no rows at all.
- OSM: nearest point in osm_data_cleaned.csv within 2000 m. It replaces the land-use match if it is within 2000 m and there is no land-use match, or it is closer.
- Distances are great-circle metres with earth radius 6371000. A KD-tree on 3D unit vectors with chord-to-arc conversion, or a haversine BallTree, are both fine as long as results match.
- Write scripts/build_lookup.py that reads land_use_data.csv in chunks and stores one coordinate array per year plus land_type codes on disk (gitignored). At runtime load a year's index only when a batch needs it, and cache it. Measure and report build time, load time and memory. Do not load all 17.6 million points at once unless you have measured that it is fine.
- Write scripts/parity_check.py: take a random sample from data/nasa_data_cleaned.csv, run it through your pipeline, and compare the engineered features and match_dist_m with the matching rows of data/final_dataset.csv (join on latitude, longitude, acq_time and brightness). Report the match rate and any differences. Note that final_dataset.csv has no date, so the year-specific step can only be checked through the joined rows.

## 6. Secrets

- The real .env is not committed. It holds the Hugging Face token and the FIRMS MAP_KEY. It may be a file or a directory: inspect it. .env.example currently has only HUGGING_FACE_API.
- List the variable names only. Never print, log or return values. If the FIRMS variable name is not obvious, ask me.
- The FIRMS key is part of the request URL. Turn off or redact URL logging in your HTTP client and web server so the key never reaches logs, tracebacks or the browser. Keys stay on the server.
- Add new variable names (with empty values) to .env.example, for example DATABASE_URL. Do not overwrite .env. Add generated indexes, Docker volumes and caches to .gitignore. Never commit large generated files.
- Load the model from the Hugging Face repo bazik-0/mission-sih using the token, cache it locally, and fall back to model/hf_model/model.joblib if Hugging Face is unreachable. Report which one was used at startup.

## 7. Storage (deliverable ii)

PostgreSQL with PostGIS, started with docker compose for local use. Tables:
- hotspots: id, geom (Point, SRID 4326, GiST index), latitude, longitude, acq_datetime_utc, acq_date, acq_time, source (NRT or SP), the raw FIRMS fields, the engineered features, fired_type, match_dist_m, matched_from (landuse or osm), landuse_year_used, predicted_class, probabilities (jsonb, all eight classes), final_label, final_group (industrial, natural, volcano, unclassified), decision_path (volcano_rule, mlp, no_match, unexpected_type), ingested_at. Unique on latitude, longitude, acq_date, acq_time so re-ingesting never duplicates.
- osm_features: the 67,047 OSM points (geom, category) for the infrastructure overlay.
- ingest_runs: source, area, date range, rows fetched, rows classified, rows per decision path, started and finished times, status, error text.
Use migrations or one SQL init script, and document which.

## 8. Backend (FastAPI)

- GET /api/health: model loaded and from where, database reachable, lookup indexes state, FIRMS key present (true or false only), FIRMS transaction usage, data source and latest acquisition date.
- POST /api/ingest for a manual run, plus a scheduled ingestion using an in-process scheduler with the interval from config.
- GET /api/hotspots with filters: bbox, date range, final_label, final_group, minimum probability, decision_path. Returns GeoJSON. Limit result size sensibly and say in the response when it was truncated.
- GET /api/hotspots/{id}: full detail including probabilities, features, matched feature and distance.
- GET /api/stats: counts by label, group and day for the current filter.
- GET /api/infrastructure: OSM points in a bbox, GeoJSON.
- GET /api/export: the current filter as CSV or GeoJSON.
- Classify in batches with vectorised lookups. Validate input, return useful errors, and log without secrets.

## 9. Front end

Plain HTML, JavaScript modules and CSS, served by FastAPI. Vendor Leaflet and any chart library locally under a vendor folder so the app has no runtime CDN dependency other than map tiles.
- Layout: filter panel on the left, map in the centre, detail panel on the right, a status bar showing the data source, latest acquisition date, last ingest time and any ingestion error.
- Map centred on India, limited to the India area. Base layers: OpenStreetMap, and one openly licensed satellite imagery basemap with correct attribution. Overlay toggles: hotspots, OSM infrastructure.
- Hotspot markers coloured by final label, with a legend. Industrial labels in warm colours, Natural in greens, Volcano and Unclassified clearly different. Use a colour-blind-safe palette. Use canvas rendering and clustering so tens of thousands of points stay responsive.
- Filters: date range, group, label, minimum probability, decision path. Time shown in UTC with IST alongside.
- Detail panel per hotspot: acquisition time, coordinates, FRP, brightness (ti4), bright_t31 (ti5), confidence, day or night, FIRMS type with its meaning (0 presumed vegetation fire, 1 active volcano, 2 other static land source, 3 offshore), decision path, predicted class with the top three probabilities, matched feature source, category, distance in metres, land-use year used.
- Stats panel: counts by group and label, and a per-day chart. Export button for the current filter.
- An About page that states plainly: what the model is, how the training labels were produced (nearest land-use or OSM point within 2000 m), that lat/lon and match_dist_m are model inputs, that test accuracy was 67.86% on a random split with no per-class metrics, that the gas_flare class rests on very few OSM points, that FIRMS pixels are 375 m so attribution to a single facility is uncertain, and the data source and its freshness.
- Responsive enough to use on a laptop and a tablet; keyboard reachable controls; readable contrast.

## 9a. Suggested layout

website/backend (app package, scripts, tests), website/frontend (index.html, about.html, js, css, vendor), website/docker-compose.yml, website/README.md. Adjust if the repo suggests better, but keep everything under website/.

## 10. Testing and acceptance

Write automated tests for: feature engineering against hand-computed rows; both FIRMS column schemas; the confidence and daynight encodings; the decision order (type 1 never reaches the MLP, no match never reaches the MLP); idempotent ingestion; API filters; health output containing no secrets. Run scripts/parity_check.py and report its result.

The work is done only when all of this is true and you have run it:
1. Fresh clone plus the README steps gets the app running locally on Arch Linux.
2. A real ingestion with the real key stores real hotspots, and the map shows them classified with the colours and legend.
3. Volcano, Unclassified and MLP paths are each exercised, with at least one real or test-fixture example of each. Say which.
4. The status bar shows the true source and latest acquisition date.
5. No secret appears in logs, responses, the repo or the front-end code.
6. You looked at the running interface in a browser (for example with Playwright screenshots) and fixed what was broken.

## 11. Things to ask me instead of deciding

- The FIRMS variable name in .env, if not obvious.
- What to do if neither FIRMS product returns type.
- Whether to clip results to India's boundary. Bounding-box only is the default. If clipping is wanted I will supply the boundary file; do not pick a boundary source yourself.
- Any dependency that does not support the Python version in the owner's environment (the notebooks show Python 3.14).

## 12. Final message

Give: what you built and how to run it; the probe findings (which FIRMS source was used, whether type was present, latest available dates); the parity check result; measured build time and memory for the lookup; what you tested and how; anything you could not verify; and anything that differed from this prompt.