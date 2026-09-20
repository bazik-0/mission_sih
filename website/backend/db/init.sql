-- Create PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Hotspots table
CREATE TABLE IF NOT EXISTS hotspots (
    id SERIAL PRIMARY KEY,
    geom GEOMETRY(Point, 4326) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    acq_datetime_utc TIMESTAMP NOT NULL,
    acq_date DATE NOT NULL,
    acq_time INTEGER NOT NULL,
    source VARCHAR(30) NOT NULL, -- e.g. 'VIIRS_NOAA20_SP'

    -- Raw FIRMS fields
    scan DOUBLE PRECISION NOT NULL,
    track DOUBLE PRECISION NOT NULL,
    brightness DOUBLE PRECISION NOT NULL,
    bright_t31 DOUBLE PRECISION NOT NULL,
    frp DOUBLE PRECISION NOT NULL,
    confidence VARCHAR(10) NOT NULL, -- 'l', 'n', 'h' for VIIRS or numeric for MODIS
    daynight VARCHAR(1) NOT NULL, -- 'D' or 'N'
    firms_type INTEGER, -- 0, 1, 2, 3
    satellite VARCHAR(30),
    instrument VARCHAR(30),
    version VARCHAR(30),

    -- Engineered features
    track_scan DOUBLE PRECISION NOT NULL,
    final_bright DOUBLE PRECISION NOT NULL,
    radiation DOUBLE PRECISION NOT NULL,
    confidence_encoded INTEGER NOT NULL, -- 300, 600, 900
    daynight_encoded INTEGER NOT NULL, -- 0 or 1

    -- Matching results
    match_dist_m DOUBLE PRECISION,
    matched_from VARCHAR(20), -- 'landuse' or 'osm'
    landuse_year_used INTEGER,

    -- Classification results
    predicted_class VARCHAR(50),
    probabilities JSONB, -- {class: probability}
    final_label VARCHAR(50) NOT NULL,
    final_group VARCHAR(20) NOT NULL, -- 'industrial', 'natural', 'volcano', 'unclassified'
    decision_path VARCHAR(20) NOT NULL, -- 'volcano_rule', 'mlp', 'no_match', 'unexpected_type'

    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint to prevent duplicates
    UNIQUE(latitude, longitude, acq_date, acq_time)
);

-- Spatial index
CREATE INDEX IF NOT EXISTS idx_hotspots_geom ON hotspots USING GIST(geom);

-- Other indexes for filtering
CREATE INDEX IF NOT EXISTS idx_hotspots_acq_date ON hotspots(acq_date);
CREATE INDEX IF NOT EXISTS idx_hotspots_final_label ON hotspots(final_label);
CREATE INDEX IF NOT EXISTS idx_hotspots_final_group ON hotspots(final_group);
CREATE INDEX IF NOT EXISTS idx_hotspots_decision_path ON hotspots(decision_path);

-- OSM features table
CREATE TABLE IF NOT EXISTS osm_features (
    id SERIAL PRIMARY KEY,
    geom GEOMETRY(Point, 4326) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    category VARCHAR(50) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_osm_features_geom ON osm_features USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_osm_features_category ON osm_features(category);

-- Ingest runs table
CREATE TABLE IF NOT EXISTS ingest_runs (
    id SERIAL PRIMARY KEY,
    source VARCHAR(30) NOT NULL,
    area VARCHAR(50) NOT NULL,
    date_from DATE NOT NULL,
    date_to DATE NOT NULL,
    rows_fetched INTEGER NOT NULL DEFAULT 0,
    rows_classified INTEGER NOT NULL DEFAULT 0,
    rows_volcano INTEGER NOT NULL DEFAULT 0,
    rows_mlp INTEGER NOT NULL DEFAULT 0,
    rows_no_match INTEGER NOT NULL DEFAULT 0,
    rows_unexpected_type INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status VARCHAR(20) NOT NULL, -- 'running', 'success', 'failed'
    error_text TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingest_runs_started_at ON ingest_runs(started_at DESC);
