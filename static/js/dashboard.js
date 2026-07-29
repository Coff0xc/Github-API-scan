// Dashboard JavaScript

let currentPage = 0;
const pageSize = 100;
let platformChart = null;
let statusChart = null;

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    loadPlatforms();
    loadStats();
    loadKeys();
    initCharts();
    setupEventListeners();

    // Auto-refresh every 5 seconds
    setInterval(loadStats, 5000);
    setInterval(loadKeys, 10000);
});

// Setup event listeners
function setupEventListeners() {
    document.getElementById('filter-status').addEventListener('change', () => {
        currentPage = 0;
        loadKeys();
    });

    document.getElementById('filter-platform').addEventListener('change', () => {
        currentPage = 0;
        loadKeys();
    });

    document.getElementById('search-input').addEventListener('input', debounce(() => {
        currentPage = 0;
        loadKeys();
    }, 500));

    document.getElementById('export-btn').addEventListener('click', exportKeys);
    document.getElementById('prev-btn').addEventListener('click', () => {
        if (currentPage > 0) {
            currentPage--;
            loadKeys();
        }
    });

    document.getElementById('next-btn').addEventListener('click', () => {
        currentPage++;
        loadKeys();
    });
}

// Load statistics
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();

        document.getElementById('total-keys').textContent = stats.total_keys || 0;
        document.getElementById('valid-keys').textContent = stats.valid_keys || 0;
        document.getElementById('high-value-keys').textContent = stats.high_value_keys || 0;
        document.getElementById('invalid-keys').textContent = stats.invalid_keys || 0;

        // Update status
        if (stats.is_running) {
            document.getElementById('status-text').textContent = 'Running';
            document.querySelector('.status-indicator').style.background = '#10b981';
        } else {
            document.getElementById('status-text').textContent = 'Idle';
            document.querySelector('.status-indicator').style.background = '#6b7280';
        }

        // Update charts
        updateCharts(stats);
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// Load platforms list
async function loadPlatforms() {
    try {
        const response = await fetch('/api/platforms');
        const platforms = await response.json();

        const select = document.getElementById('filter-platform');
        platforms.forEach(platform => {
            const option = document.createElement('option');
            option.value = platform;
            option.textContent = platform;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load platforms:', error);
    }
}

// Load keys
async function loadKeys() {
    const status = document.getElementById('filter-status').value;
    const platform = document.getElementById('filter-platform').value;
    const search = document.getElementById('search-input').value;

    const params = new URLSearchParams({
        limit: pageSize,
        offset: currentPage * pageSize,
    });

    if (status) params.append('status', status);
    if (platform) params.append('platform', platform);
    if (search) params.append('search', search);

    try {
        const response = await fetch(`/api/keys?${params}`);
        const data = await response.json();

        renderKeys(data.keys);
        updatePagination(data.total);
    } catch (error) {
        console.error('Failed to load keys:', error);
        document.getElementById('keys-tbody').innerHTML =
            '<tr><td colspan="6" class="loading">Failed to load keys</td></tr>';
    }
}

// Render keys table
function renderKeys(keys) {
    const tbody = document.getElementById('keys-tbody');

    if (keys.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="loading">No keys found</td></tr>';
        return;
    }

    tbody.innerHTML = keys.map(key => `
        <tr>
            <td><span class="platform-badge">${escapeHtml(key.platform)}</span></td>
            <td><code class="key-text">${maskKey(key.api_key)}</code></td>
            <td><span class="status-badge status-${key.status}">${formatStatus(key.status)}</span></td>
            <td>${escapeHtml(key.info || '-')}</td>
            <td><a href="${escapeHtml(key.source_url)}" target="_blank" class="source-link">View</a></td>
            <td>${formatDate(key.found_time)}</td>
        </tr>
    `).join('');
}

// Update pagination
function updatePagination(total) {
    const totalPages = Math.ceil(total / pageSize);
    document.getElementById('page-info').textContent =
        `Page ${currentPage + 1} of ${totalPages} (${total} total)`;

    document.getElementById('prev-btn').disabled = currentPage === 0;
    document.getElementById('next-btn').disabled = currentPage >= totalPages - 1;
}

// Initialize charts
function initCharts() {
    const platformCtx = document.getElementById('platformChart').getContext('2d');
    const statusCtx = document.getElementById('statusChart').getContext('2d');

    platformChart = new Chart(platformCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Keys',
                data: [],
                backgroundColor: '#2563eb',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true }
            }
        }
    });

    statusChart = new Chart(statusCtx, {
        type: 'doughnut',
        data: {
            labels: ['Valid', 'Invalid', 'Quota Exceeded'],
            datasets: [{
                data: [0, 0, 0],
                backgroundColor: ['#10b981', '#ef4444', '#f59e0b'],
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
        }
    });
}

// Update charts
function updateCharts(stats) {
    if (platformChart && stats.top_platforms) {
        platformChart.data.labels = stats.top_platforms.map(p => p.platform);
        platformChart.data.datasets[0].data = stats.top_platforms.map(p => p.count);
        platformChart.update();
    }

    if (statusChart) {
        statusChart.data.datasets[0].data = [
            stats.valid_keys || 0,
            stats.invalid_keys || 0,
            stats.quota_exceeded || 0
        ];
        statusChart.update();
    }
}

// Export keys
async function exportKeys() {
    const status = document.getElementById('filter-status').value;
    const platform = document.getElementById('filter-platform').value;

    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (platform) params.append('platform', platform);

    window.location.href = `/api/export?${params}`;
}

// Utility functions
function maskKey(key) {
    if (key.length <= 10) return key;
    return key.substring(0, 8) + '...' + key.substring(key.length - 4);
}

function formatStatus(status) {
    return status.replace('_', ' ').toUpperCase();
}

function formatDate(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    return date.toLocaleString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
