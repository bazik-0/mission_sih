#!/bin/bash
# Simple test script to verify components without database

echo "Mission SIH - Component Tests"
echo "=============================="

# Test 1: Python dependencies
echo -e "\n[1/5] Testing Python dependencies..."
python -c "import fastapi, sqlalchemy, pandas, numpy, sklearn, requests" 2>&1
if [ $? -eq 0 ]; then
    echo "✓ All Python dependencies installed"
else
    echo "✗ Missing Python dependencies"
fi

# Test 2: Data files exist
echo -e "\n[2/5] Checking data files..."
if [ -f "../data/nasa_data_cleaned.csv" ]; then
    echo "✓ nasa_data_cleaned.csv exists"
else
    echo "✗ nasa_data_cleaned.csv missing"
fi

if [ -f "../data/land_use_data.csv" ]; then
    echo "✓ land_use_data.csv exists"
else
    echo "✗ land_use_data.csv missing"
fi

if [ -f "../data/osm_data_cleaned.csv" ]; then
    echo "✓ osm_data_cleaned.csv exists"
else
    echo "✗ osm_data_cleaned.csv missing"
fi

if [ -f "../model/hf_model/model.joblib" ]; then
    echo "✓ model.joblib exists"
else
    echo "✗ model.joblib missing"
fi

# Test 3: Frontend files
echo -e "\n[3/5] Checking frontend files..."
if [ -f "frontend/index.html" ]; then
    echo "✓ index.html exists"
else
    echo "✗ index.html missing"
fi

if [ -f "frontend/vendor/leaflet/leaflet.js" ]; then
    echo "✓ Leaflet library downloaded"
else
    echo "✗ Leaflet library missing"
fi

# Test 4: FIRMS API probe
echo -e "\n[4/5] Testing FIRMS API..."
python backend/scripts/probe_firms.py 2>&1 | grep -E "(Use VIIRS|CANNOT PROCEED)" | head -2

# Test 5: Configuration
echo -e "\n[5/5] Checking configuration..."
if [ -f "../.env" ]; then
    echo "✓ .env file exists"
    if grep -q "NASA_FIRMS_MAP_KEY=" ../.env; then
        echo "✓ NASA_FIRMS_MAP_KEY configured"
    else
        echo "✗ NASA_FIRMS_MAP_KEY not configured"
    fi
else
    echo "✗ .env file missing"
fi

echo -e "\n=============================="
echo "Component tests complete"
echo "=============================="
