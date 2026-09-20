// UI Manager for status bar, stats, and detail panel

export class UIManager {
    constructor(api) {
        this.api = api;
        this.statsChart = null;
    }

    init(mapManager) {
        this.mapManager = mapManager;
        console.log('UI Manager initialized');
    }

    updateStatusBar(health) {
        // Data source
        const sourceEl = document.getElementById('status-source');
        if (health.data_source === 'VIIRS_NOAA20_SP') {
            sourceEl.textContent = 'VIIRS NOAA-20 (Standard Processing)';
            sourceEl.style.color = 'var(--color-warning)';
        } else {
            sourceEl.textContent = health.data_source || 'Unknown';
        }

        // Latest acquisition date
        const dateEl = document.getElementById('status-date');
        if (health.latest_acquisition_date) {
            dateEl.textContent = `${health.latest_acquisition_date} (SP lag ~3 months)`;
        } else {
            dateEl.textContent = 'No data yet';
        }

        // Last ingest time
        const ingestEl = document.getElementById('status-ingest');
        if (health.last_ingest_time) {
            const date = new Date(health.last_ingest_time);
            ingestEl.textContent = this.formatDateTime(date);
        } else {
            ingestEl.textContent = 'Not yet run';
        }

        // Error
        const errorDiv = document.getElementById('status-error');
        const errorText = document.getElementById('status-error-text');
        if (health.last_error) {
            errorText.textContent = health.last_error;
            errorDiv.style.display = 'flex';
        } else {
            errorDiv.style.display = 'none';
        }

        // Populate label filter options
        if (health.model_classes) {
            const labelSelect = document.getElementById('filter-label');
            const currentValue = labelSelect.value;

            // Clear existing options except "All"
            labelSelect.innerHTML = '<option value="">All</option>';

            health.model_classes.forEach(cls => {
                const option = document.createElement('option');
                option.value = cls;
                option.textContent = cls;
                labelSelect.appendChild(option);
            });

            // Add special classes
            ['Volcano', 'Unclassified'].forEach(cls => {
                const option = document.createElement('option');
                option.value = cls;
                option.textContent = cls;
                labelSelect.appendChild(option);
            });

            // Restore previous value
            if (currentValue) {
                labelSelect.value = currentValue;
            }
        }
    }

    updateStats(stats) {
        const summaryEl = document.getElementById('stats-summary');

        // Build summary HTML
        let html = `<div class="stat-row"><strong>Total:</strong> <span>${stats.total.toLocaleString()}</span></div>`;

        // By group
        if (stats.by_group) {
            html += '<div style="margin-top: 8px; font-weight: 600;">By Group:</div>';
            Object.entries(stats.by_group).forEach(([group, count]) => {
                html += `<div class="stat-row"><span>${group}:</span> <span>${count.toLocaleString()}</span></div>`;
            });
        }

        summaryEl.innerHTML = html;

        // Update chart
        this.updateStatsChart(stats.by_day);
    }

    updateStatsChart(byDay) {
        const canvas = document.getElementById('stats-chart');
        const ctx = canvas.getContext('2d');

        // Destroy previous chart
        if (this.statsChart) {
            this.statsChart.destroy();
        }

        if (!byDay || byDay.length === 0) {
            return;
        }

        // Prepare data
        const labels = byDay.map(d => d.date);
        const data = byDay.map(d => d.count);

        this.statsChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Detections per Day',
                    data: data,
                    borderColor: 'rgb(37, 99, 235)',
                    backgroundColor: 'rgba(37, 99, 235, 0.1)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        display: true,
                        ticks: {
                            maxTicksLimit: 5,
                            font: {
                                size: 10
                            }
                        }
                    },
                    y: {
                        display: true,
                        beginAtZero: true,
                        ticks: {
                            font: {
                                size: 10
                            }
                        }
                    }
                }
            }
        });
    }

    showHotspotDetail(detail) {
        const contentEl = document.getElementById('detail-content');

        // Build detail HTML
        let html = '<div class="detail-section">';
        html += '<h4>Location</h4>';
        html += `<div class="detail-row"><span class="label">Latitude:</span><span class="value">${detail.latitude.toFixed(5)}</span></div>`;
        html += `<div class="detail-row"><span class="label">Longitude:</span><span class="value">${detail.longitude.toFixed(5)}</span></div>`;
        html += '</div>';

        // Acquisition time
        html += '<div class="detail-section">';
        html += '<h4>Acquisition</h4>';
        html += `<div class="detail-row"><span class="label">Date:</span><span class="value">${detail.acq_date}</span></div>`;
        html += `<div class="detail-row"><span class="label">Time (UTC):</span><span class="value">${this.formatTime(detail.acq_time)}</span></div>`;
        html += `<div class="detail-row"><span class="label">Time (IST):</span><span class="value">${this.toIST(detail.acq_date, detail.acq_time)}</span></div>`;
        html += `<div class="detail-row"><span class="label">Source:</span><span class="value">${detail.source}</span></div>`;
        html += '</div>';

        // FIRMS data
        html += '<div class="detail-section">';
        html += '<h4>FIRMS Data</h4>';
        html += `<div class="detail-row"><span class="label">FRP:</span><span class="value">${detail.firms.frp.toFixed(2)} MW</span></div>`;
        html += `<div class="detail-row"><span class="label">Brightness (ti4):</span><span class="value">${detail.firms.brightness.toFixed(1)} K</span></div>`;
        html += `<div class="detail-row"><span class="label">Bright T31 (ti5):</span><span class="value">${detail.firms.bright_t31.toFixed(1)} K</span></div>`;
        html += `<div class="detail-row"><span class="label">Confidence:</span><span class="value">${detail.firms.confidence}</span></div>`;
        html += `<div class="detail-row"><span class="label">Day/Night:</span><span class="value">${detail.firms.daynight === 'D' ? 'Day' : 'Night'}</span></div>`;

        // FIRMS type with explanation
        const typeExplanation = {
            0: 'Presumed vegetation fire',
            1: 'Active volcano',
            2: 'Other static land source',
            3: 'Offshore detection'
        };
        const typeText = detail.firms.type !== null ? `${detail.firms.type} (${typeExplanation[detail.firms.type] || 'Unknown'})` : 'N/A';
        html += `<div class="detail-row"><span class="label">FIRMS Type:</span><span class="value">${typeText}</span></div>`;
        html += '</div>';

        // Classification
        html += '<div class="detail-section">';
        html += '<h4>Classification</h4>';
        html += `<div class="detail-row"><span class="label">Final Label:</span><span class="value"><strong>${detail.classification.final_label}</strong></span></div>`;
        html += `<div class="detail-row"><span class="label">Group:</span><span class="value">${detail.classification.final_group}</span></div>`;
        html += `<div class="detail-row"><span class="label">Decision Path:</span><span class="value">${detail.classification.decision_path}</span></div>`;

        if (detail.classification.predicted_class) {
            html += `<div class="detail-row"><span class="label">Predicted Class:</span><span class="value">${detail.classification.predicted_class}</span></div>`;
        }
        html += '</div>';

        // Probabilities
        if (detail.classification.probabilities) {
            html += '<div class="detail-section">';
            html += '<h4>Probabilities</h4>';

            // Sort by probability descending
            const probs = Object.entries(detail.classification.probabilities)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 3); // Top 3

            probs.forEach(([cls, prob]) => {
                const percentage = (prob * 100).toFixed(1);
                html += `
                    <div class="probability-bar">
                        <div class="prob-label">
                            <span>${cls}</span>
                            <span>${percentage}%</span>
                        </div>
                        <div class="prob-fill">
                            <div class="prob-value" style="width: ${percentage}%"></div>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
        }

        // Matching
        if (detail.matching.distance_m !== null) {
            html += '<div class="detail-section">';
            html += '<h4>Nearest Match</h4>';
            html += `<div class="detail-row"><span class="label">Source:</span><span class="value">${detail.matching.matched_from || 'N/A'}</span></div>`;
            html += `<div class="detail-row"><span class="label">Distance:</span><span class="value">${detail.matching.distance_m.toFixed(0)} m</span></div>`;
            if (detail.matching.landuse_year_used) {
                html += `<div class="detail-row"><span class="label">Land-use Year:</span><span class="value">${detail.matching.landuse_year_used}</span></div>`;
            }
            html += '</div>';
        }

        contentEl.innerHTML = html;
    }

    formatTime(acqTime) {
        // Format HHMM integer as HH:MM
        const str = String(acqTime).padStart(4, '0');
        return `${str.slice(0, 2)}:${str.slice(2)}`;
    }

    toIST(dateStr, acqTime) {
        // Convert UTC time to IST (UTC+5:30)
        const str = String(acqTime).padStart(4, '0');
        const hours = parseInt(str.slice(0, 2));
        const minutes = parseInt(str.slice(2));

        const utcDate = new Date(`${dateStr}T${str.slice(0, 2)}:${str.slice(2)}:00Z`);
        const istDate = new Date(utcDate.getTime() + (5.5 * 60 * 60 * 1000));

        return istDate.toLocaleTimeString('en-IN', {
            hour: '2-digit',
            minute: '2-digit',
            timeZone: 'Asia/Kolkata'
        });
    }

    formatDateTime(date) {
        const now = new Date();
        const diff = now - date;
        const minutes = Math.floor(diff / 60000);

        if (minutes < 60) {
            return `${minutes} minutes ago`;
        } else if (minutes < 1440) {
            const hours = Math.floor(minutes / 60);
            return `${hours} hour${hours > 1 ? 's' : ''} ago`;
        } else {
            return date.toLocaleString();
        }
    }

    showLoading(show) {
        const container = document.querySelector('.container');
        if (show) {
            container.classList.add('loading');
        } else {
            container.classList.remove('loading');
        }
    }

    showError(message) {
        alert(`Error: ${message}`);
    }
}
