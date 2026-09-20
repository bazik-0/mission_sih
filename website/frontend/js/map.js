// Map manager for Leaflet

export class MapManager {
    constructor() {
        this.map = null;
        this.hotspotsLayer = null;
        this.osmLayer = null;
        this.listeners = {};
        this.colors = {
            // Groups
            'industrial': '#d97706',
            'natural': '#16a34a',
            'volcano': '#dc2626',
            'unclassified': '#6b7280',
            // Industrial classes
            'gas_flare': '#f59e0b',
            'industrial_facility': '#ea580c',
            'mine': '#b45309',
            'oil_gas': '#d97706',
            'power_plant': '#f97316',
            'quarry': '#c2410c',
            // Natural classes
            'Forest': '#16a34a',
            'Agriculture': '#65a30d',
            'Volcano': '#dc2626',
            'Unclassified': '#6b7280'
        };
    }

    async init() {
        // Create map centered on India
        this.map = L.map('map', {
            center: [22.5, 82.5],
            zoom: 5,
            minZoom: 4,
            maxZoom: 18
        });

        // Set bounds to India region
        const indiaBounds = L.latLngBounds(
            L.latLng(6.0, 68.0),   // Southwest
            L.latLng(37.5, 97.5)   // Northeast
        );
        this.map.setMaxBounds(indiaBounds);

        // Add base layers
        const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 19
        });

        const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles © Esri',
            maxZoom: 19
        });

        // Add OSM as default
        osmLayer.addTo(this.map);

        // Layer control
        const baseLayers = {
            'OpenStreetMap': osmLayer,
            'Satellite': satelliteLayer
        };

        // Initialize marker cluster group for hotspots
        this.hotspotsLayer = L.markerClusterGroup({
            maxClusterRadius: 50,
            spiderfyOnMaxZoom: true,
            showCoverageOnHover: false,
            zoomToBoundsOnClick: true
        });
        this.map.addLayer(this.hotspotsLayer);

        // OSM infrastructure layer (initially empty)
        this.osmLayer = L.layerGroup();

        const overlays = {
            'Hotspots': this.hotspotsLayer,
            'Infrastructure': this.osmLayer
        };

        L.control.layers(baseLayers, overlays).addTo(this.map);

        // Create legend
        this.createLegend();

        console.log('Map initialized');
    }

    updateHotspots(geojson) {
        // Clear existing hotspots
        this.hotspotsLayer.clearLayers();

        if (!geojson.features || geojson.features.length === 0) {
            console.log('No hotspots to display');
            return;
        }

        // Add markers
        geojson.features.forEach(feature => {
            const { coordinates } = feature.geometry;
            const props = feature.properties;

            // Get color based on label
            const color = this.colors[props.final_label] || this.colors[props.final_group] || '#6b7280';

            // Create circle marker
            const marker = L.circleMarker([coordinates[1], coordinates[0]], {
                radius: 6,
                fillColor: color,
                color: '#fff',
                weight: 1,
                opacity: 1,
                fillOpacity: 0.8
            });

            // Add popup
            const popup = `
                <div style="font-size: 12px;">
                    <strong>${props.final_label}</strong><br>
                    <strong>Group:</strong> ${props.final_group}<br>
                    <strong>Date:</strong> ${props.acq_date}<br>
                    <strong>Time:</strong> ${this.formatTime(props.acq_time)} UTC<br>
                    <strong>FRP:</strong> ${props.frp.toFixed(2)} MW<br>
                    <strong>Brightness:</strong> ${props.brightness.toFixed(1)} K<br>
                    <strong>Confidence:</strong> ${props.confidence}<br>
                    <strong>Path:</strong> ${props.decision_path}<br>
                    <button onclick="window.app?.showHotspotDetail(${props.id})" style="margin-top:8px;padding:4px 8px;">View Details</button>
                </div>
            `;
            marker.bindPopup(popup);

            // Add click handler
            marker.on('click', () => {
                this.emit('hotspotClick', props.id);
            });

            this.hotspotsLayer.addLayer(marker);
        });

        console.log(`Displayed ${geojson.features.length} hotspots`);

        // Show truncation warning if needed
        if (geojson.metadata?.truncated) {
            console.warn(`Results truncated: showing ${geojson.metadata.count} of ${geojson.metadata.total_count}`);
        }
    }

    async loadInfrastructure() {
        // Load OSM infrastructure for current bounds
        const bounds = this.map.getBounds();
        const bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;

        try {
            const response = await fetch(`/api/infrastructure?bbox=${bbox}`);
            const geojson = await response.json();

            this.osmLayer.clearLayers();

            geojson.features.forEach(feature => {
                const { coordinates } = feature.geometry;
                const props = feature.properties;

                const marker = L.circleMarker([coordinates[1], coordinates[0]], {
                    radius: 4,
                    fillColor: '#8b5cf6',
                    color: '#fff',
                    weight: 1,
                    opacity: 1,
                    fillOpacity: 0.6
                });

                marker.bindPopup(`
                    <div style="font-size: 12px;">
                        <strong>Infrastructure</strong><br>
                        <strong>Type:</strong> ${props.category}
                    </div>
                `);

                this.osmLayer.addLayer(marker);
            });

            console.log(`Loaded ${geojson.features.length} infrastructure points`);
        } catch (error) {
            console.error('Failed to load infrastructure:', error);
        }
    }

    createLegend() {
        const legend = L.control({ position: 'bottomright' });

        legend.onAdd = () => {
            const div = L.DomUtil.create('div', 'legend');
            div.innerHTML = '<h4>Classification</h4>';

            const items = [
                { label: 'Industrial', color: this.colors.industrial },
                { label: 'Natural', color: this.colors.natural },
                { label: 'Volcano', color: this.colors.volcano },
                { label: 'Unclassified', color: this.colors.unclassified }
            ];

            items.forEach(item => {
                div.innerHTML += `
                    <div class="legend-item">
                        <div class="legend-color" style="background-color: ${item.color}"></div>
                        <span>${item.label}</span>
                    </div>
                `;
            });

            return div;
        };

        legend.addTo(this.map);
    }

    formatTime(acqTime) {
        // Format HHMM integer as HH:MM
        const str = String(acqTime).padStart(4, '0');
        return `${str.slice(0, 2)}:${str.slice(2)}`;
    }

    on(event, handler) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        this.listeners[event].push(handler);
    }

    emit(event, data) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(handler => handler(data));
        }
    }
}
