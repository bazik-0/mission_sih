// Mission SIH - Industrial Fire Detection System
// Main application logic

import { MapManager } from './map.js';
import { API } from './api.js';
import { UIManager } from './ui.js';

class App {
    constructor() {
        this.mapManager = null;
        this.api = new API();
        this.uiManager = new UIManager(this.api);
        this.currentFilters = {};
    }

    async init() {
        console.log('Initializing Mission SIH application...');

        // Initialize map
        this.mapManager = new MapManager();
        await this.mapManager.init();

        // Initialize UI
        this.uiManager.init(this.mapManager);

        // Load health status
        await this.loadHealth();

        // Load initial data
        await this.loadHotspots();

        // Set up event listeners
        this.setupEventListeners();

        // Refresh health every 30 seconds
        setInterval(() => this.loadHealth(), 30000);

        console.log('Application initialized');
    }

    async loadHealth() {
        try {
            const health = await this.api.getHealth();
            this.uiManager.updateStatusBar(health);
        } catch (error) {
            console.error('Failed to load health:', error);
        }
    }

    async loadHotspots() {
        try {
            this.uiManager.showLoading(true);

            // Build filter params
            const params = new URLSearchParams();

            // Get current map bounds
            const bounds = this.mapManager.map.getBounds();
            const bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;
            params.append('bbox', bbox);

            // Apply filters
            if (this.currentFilters.dateFrom) {
                params.append('date_from', this.currentFilters.dateFrom);
            }
            if (this.currentFilters.dateTo) {
                params.append('date_to', this.currentFilters.dateTo);
            }
            if (this.currentFilters.group) {
                params.append('final_group', this.currentFilters.group);
            }
            if (this.currentFilters.label) {
                params.append('final_label', this.currentFilters.label);
            }
            if (this.currentFilters.decision) {
                params.append('decision_path', this.currentFilters.decision);
            }
            if (this.currentFilters.minProb > 0) {
                params.append('min_probability', this.currentFilters.minProb);
            }

            const data = await this.api.getHotspots(params);
            this.mapManager.updateHotspots(data);

            // Update stats
            await this.loadStats();

            this.uiManager.showLoading(false);
        } catch (error) {
            console.error('Failed to load hotspots:', error);
            this.uiManager.showLoading(false);
            this.uiManager.showError('Failed to load hotspots: ' + error.message);
        }
    }

    async loadStats() {
        try {
            const bounds = this.mapManager.map.getBounds();
            const bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;

            const params = new URLSearchParams({ bbox });
            if (this.currentFilters.dateFrom) {
                params.append('date_from', this.currentFilters.dateFrom);
            }
            if (this.currentFilters.dateTo) {
                params.append('date_to', this.currentFilters.dateTo);
            }

            const stats = await this.api.getStats(params);
            this.uiManager.updateStats(stats);
        } catch (error) {
            console.error('Failed to load stats:', error);
        }
    }

    setupEventListeners() {
        // Apply filters button
        document.getElementById('btn-apply-filters').addEventListener('click', () => {
            this.applyFilters();
        });

        // Reset filters button
        document.getElementById('btn-reset-filters').addEventListener('click', () => {
            this.resetFilters();
        });

        // Export buttons
        document.getElementById('btn-export-csv').addEventListener('click', () => {
            this.exportData('csv');
        });

        document.getElementById('btn-export-geojson').addEventListener('click', () => {
            this.exportData('geojson');
        });

        // Manual ingest button
        document.getElementById('btn-ingest').addEventListener('click', () => {
            this.triggerIngest();
        });

        // Min probability slider
        const slider = document.getElementById('filter-min-prob');
        const value = document.getElementById('filter-min-prob-value');
        slider.addEventListener('input', (e) => {
            value.textContent = `${Math.round(e.target.value * 100)}%`;
        });

        // Map move end - reload data
        this.mapManager.map.on('moveend', () => {
            this.loadHotspots();
        });

        // Hotspot click - show detail
        this.mapManager.on('hotspotClick', async (hotspotId) => {
            await this.showHotspotDetail(hotspotId);
        });
    }

    applyFilters() {
        this.currentFilters = {
            dateFrom: document.getElementById('filter-date-from').value,
            dateTo: document.getElementById('filter-date-to').value,
            group: document.getElementById('filter-group').value,
            label: document.getElementById('filter-label').value,
            decision: document.getElementById('filter-decision').value,
            minProb: parseFloat(document.getElementById('filter-min-prob').value)
        };

        this.loadHotspots();
    }

    resetFilters() {
        document.getElementById('filter-date-from').value = '';
        document.getElementById('filter-date-to').value = '';
        document.getElementById('filter-group').value = '';
        document.getElementById('filter-label').value = '';
        document.getElementById('filter-decision').value = '';
        document.getElementById('filter-min-prob').value = 0;
        document.getElementById('filter-min-prob-value').textContent = '0%';

        this.currentFilters = {};
        this.loadHotspots();
    }

    async exportData(format) {
        try {
            const bounds = this.mapManager.map.getBounds();
            const bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;

            const params = new URLSearchParams({ format, bbox });
            if (this.currentFilters.dateFrom) {
                params.append('date_from', this.currentFilters.dateFrom);
            }
            if (this.currentFilters.dateTo) {
                params.append('date_to', this.currentFilters.dateTo);
            }
            if (this.currentFilters.group) {
                params.append('final_group', this.currentFilters.group);
            }
            if (this.currentFilters.label) {
                params.append('final_label', this.currentFilters.label);
            }

            // Trigger download
            window.location.href = `/api/export?${params.toString()}`;
        } catch (error) {
            console.error('Export failed:', error);
            this.uiManager.showError('Export failed: ' + error.message);
        }
    }

    async triggerIngest() {
        if (!confirm('Trigger manual ingestion? This will fetch the latest data from FIRMS.')) {
            return;
        }

        try {
            this.uiManager.showLoading(true);
            const result = await this.api.triggerIngest(1);
            alert(`Ingestion complete:\n${result.rows_classified} hotspots classified\n${result.rows_mlp} via MLP\n${result.rows_volcano} volcano\n${result.rows_no_match} no match`);
            await this.loadHealth();
            await this.loadHotspots();
        } catch (error) {
            console.error('Ingest failed:', error);
            this.uiManager.showError('Ingest failed: ' + error.message);
        } finally {
            this.uiManager.showLoading(false);
        }
    }

    async showHotspotDetail(hotspotId) {
        try {
            const detail = await this.api.getHotspotDetail(hotspotId);
            this.uiManager.showHotspotDetail(detail);
        } catch (error) {
            console.error('Failed to load hotspot detail:', error);
            this.uiManager.showError('Failed to load detail: ' + error.message);
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const app = new App();
    app.init();
});
