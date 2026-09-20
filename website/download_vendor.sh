#!/bin/bash
# Download vendor libraries for the frontend

set -e

VENDOR_DIR="website/frontend/vendor"
mkdir -p "$VENDOR_DIR"

echo "Downloading vendor libraries..."

# Leaflet 1.9.4
echo "Downloading Leaflet..."
mkdir -p "$VENDOR_DIR/leaflet"
curl -L -o "$VENDOR_DIR/leaflet/leaflet.js" https://unpkg.com/leaflet@1.9.4/dist/leaflet.js
curl -L -o "$VENDOR_DIR/leaflet/leaflet.css" https://unpkg.com/leaflet@1.9.4/dist/leaflet.css
mkdir -p "$VENDOR_DIR/leaflet/images"
curl -L -o "$VENDOR_DIR/leaflet/images/marker-icon.png" https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png
curl -L -o "$VENDOR_DIR/leaflet/images/marker-icon-2x.png" https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png
curl -L -o "$VENDOR_DIR/leaflet/images/marker-shadow.png" https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png

# Leaflet.markercluster 1.5.3
echo "Downloading Leaflet.markercluster..."
mkdir -p "$VENDOR_DIR/leaflet.markercluster"
curl -L -o "$VENDOR_DIR/leaflet.markercluster/leaflet.markercluster.js" https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js
curl -L -o "$VENDOR_DIR/leaflet.markercluster/MarkerCluster.css" https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css
curl -L -o "$VENDOR_DIR/leaflet.markercluster/MarkerCluster.Default.css" https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css

# Chart.js 4.4.0
echo "Downloading Chart.js..."
mkdir -p "$VENDOR_DIR/chart"
curl -L -o "$VENDOR_DIR/chart/chart.min.js" https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js

echo "Vendor libraries downloaded successfully!"
