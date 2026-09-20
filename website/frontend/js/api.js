// API client for Mission SIH backend

export class API {
    constructor() {
        this.baseURL = '/api';
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;

        try {
            const response = await fetch(url, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });

            if (!response.ok) {
                const error = await response.text();
                throw new Error(`HTTP ${response.status}: ${error}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`API request failed: ${endpoint}`, error);
            throw error;
        }
    }

    async getHealth() {
        return this.request('/health');
    }

    async getHotspots(params) {
        const query = params ? `?${params.toString()}` : '';
        return this.request(`/hotspots${query}`);
    }

    async getHotspotDetail(id) {
        return this.request(`/hotspots/${id}`);
    }

    async getStats(params) {
        const query = params ? `?${params.toString()}` : '';
        return this.request(`/stats${query}`);
    }

    async getInfrastructure(bbox) {
        const params = new URLSearchParams({ bbox });
        return this.request(`/infrastructure?${params.toString()}`);
    }

    async triggerIngest(days = 1) {
        return this.request(`/ingest?days=${days}`, {
            method: 'POST'
        });
    }
}
