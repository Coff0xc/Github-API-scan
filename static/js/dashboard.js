// 本机面板默认展示发现记录，不展示密钥表。

let currentPage = 0;
const pageSize = 50;
let platformChart = null;
let statusChart = null;
let allFindings = [];

const DISPOSITION_LABELS = {
    open: '待处置',
    notified: '已通知',
    rotated: '已轮换',
    false_positive: '误报',
};

document.addEventListener('DOMContentLoaded', () => {
    loadFindings();
    loadStats();
    initCharts();
    setupEventListeners();

    setInterval(loadStats, 5000);
    setInterval(loadFindings, 10000);
});

function setupEventListeners() {
    document.getElementById('filter-disposition').addEventListener('change', () => {
        currentPage = 0;
        renderCurrentPage();
    });

    document.getElementById('filter-platform').addEventListener('change', () => {
        currentPage = 0;
        renderCurrentPage();
    });

    document.getElementById('search-input').addEventListener('input', debounce(() => {
        currentPage = 0;
        renderCurrentPage();
    }, 300));

    document.getElementById('prev-btn').addEventListener('click', () => {
        if (currentPage > 0) {
            currentPage--;
            renderCurrentPage();
        }
    });

    document.getElementById('next-btn').addEventListener('click', () => {
        currentPage++;
        renderCurrentPage();
    });

    const tokenInput = document.getElementById('dashboard-token');
    tokenInput.value = sessionStorage.getItem('dashboardToken') || '';
    tokenInput.addEventListener('change', () => {
        sessionStorage.setItem('dashboardToken', tokenInput.value.trim());
    });

    document.getElementById('findings-tbody').addEventListener('change', (event) => {
        const select = event.target;
        if (!select.classList.contains('disposition-select')) {
            return;
        }
        setDisposition(select.dataset.fingerprint, select.value, select);
    });
}

async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        const counts = stats.dispositions || {};

        document.getElementById('total-findings').textContent = stats.total_keys || 0;
        document.getElementById('open-findings').textContent = counts.open || 0;
        document.getElementById('notified-findings').textContent = counts.notified || 0;
        document.getElementById('rotated-findings').textContent = counts.rotated || 0;

        if (stats.is_running) {
            document.getElementById('status-text').textContent = '扫描中';
            document.querySelector('.status-indicator').style.background = '#10b981';
        } else {
            document.getElementById('status-text').textContent = '空闲';
            document.querySelector('.status-indicator').style.background = '#6b7280';
        }

        updateCharts(stats);
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

async function loadFindings() {
    try {
        const response = await fetch('/api/findings');
        const data = await response.json();
        allFindings = Array.isArray(data.findings) ? data.findings : [];
        fillPlatforms(allFindings);
        renderCurrentPage();
    } catch (error) {
        console.error('Failed to load findings:', error);
        document.getElementById('findings-tbody').innerHTML =
            '<tr><td colspan="5" class="loading">发现记录加载失败</td></tr>';
    }
}

function fillPlatforms(findings) {
    const select = document.getElementById('filter-platform');
    const selected = select.value;
    const names = [...new Set(findings.map(item => item.platform).filter(Boolean))].sort();
    select.innerHTML = '<option value="">全部</option>';
    names.forEach(platform => {
        const option = document.createElement('option');
        option.value = platform;
        option.textContent = platform;
        select.appendChild(option);
    });
    if (names.includes(selected)) {
        select.value = selected;
    }
}

function filteredFindings() {
    const disposition = document.getElementById('filter-disposition').value;
    const platform = document.getElementById('filter-platform').value;
    const search = document.getElementById('search-input').value.trim().toLowerCase();

    return allFindings.filter(item => {
        if (disposition && item.disposition !== disposition) {
            return false;
        }
        if (platform && item.platform !== platform) {
            return false;
        }
        if (!search) {
            return true;
        }
        const haystack = [
            item.fingerprint,
            item.preview,
            item.location,
            item.repo,
            item.path,
            item.platform,
        ].join(' ').toLowerCase();
        return haystack.includes(search);
    });
}

function renderCurrentPage() {
    const rows = filteredFindings();
    const start = currentPage * pageSize;
    const page = rows.slice(start, start + pageSize);
    renderFindings(page);
    updatePagination(rows.length);
}

function renderFindings(findings) {
    const tbody = document.getElementById('findings-tbody');

    if (findings.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="loading">没有发现记录</td></tr>';
        return;
    }

    tbody.innerHTML = findings.map(item => {
        const disposition = item.disposition || 'open';
        const label = DISPOSITION_LABELS[disposition] || disposition;
        return `
        <tr>
            <td class="fingerprint">${escapeHtml(item.fingerprint || '')}</td>
            <td><span class="platform-badge">${escapeHtml(item.platform || '')}</span></td>
            <td><code class="key-text">${escapeHtml(item.preview || '')}</code></td>
            <td>${locationCell(item.location)}</td>
            <td>${dispositionSelect(item.fingerprint, disposition)}</td>
        </tr>`;
    }).join('');
}

function dispositionSelect(fingerprint, current) {
    const options = Object.entries(DISPOSITION_LABELS).map(([value, label]) => {
        const selected = value === current ? ' selected' : '';
        return `<option value="${value}"${selected}>${label}</option>`;
    }).join('');
    return `<select class="disposition-select" data-fingerprint="${escapeHtml(fingerprint || '')}" data-current="${escapeHtml(current)}">${options}</select>`;
}

async function setDisposition(fingerprint, disposition, select) {
    const message = document.getElementById('disposition-message');
    const token = (document.getElementById('dashboard-token').value || '').trim();
    sessionStorage.setItem('dashboardToken', token);
    message.textContent = '正在更新处置状态';
    try {
        const response = await fetch('/api/findings/disposition', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Token': token,
            },
            body: JSON.stringify({ fingerprint, disposition }),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
            select.value = select.dataset.current || 'open';
            message.textContent = body.error || '处置状态没有写回';
            return;
        }
        select.dataset.current = disposition;
        const row = allFindings.find(item => item.fingerprint === fingerprint);
        if (row) {
            row.disposition = disposition;
        }
        message.textContent = '已更新';
        loadStats();
    } catch (error) {
        select.value = select.dataset.current || 'open';
        message.textContent = '处置状态没有写回';
        console.error(error);
    }
}

function locationCell(location) {
    const value = location || '';
    if (!value) {
        return '-';
    }
    const safe = escapeHtml(value);
    if (/^https?:\/\//i.test(value)) {
        return `<a href="${safe}" target="_blank" rel="noopener" class="source-link">${safe}</a>`;
    }
    return safe;
}

function updatePagination(total) {
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (currentPage > totalPages - 1) {
        currentPage = totalPages - 1;
    }
    document.getElementById('page-info').textContent =
        `第 ${currentPage + 1} / ${totalPages} 页（${total} 条）`;

    document.getElementById('prev-btn').disabled = currentPage === 0;
    document.getElementById('next-btn').disabled = currentPage >= totalPages - 1;
}

function initCharts() {
    const platformCtx = document.getElementById('platformChart').getContext('2d');
    const statusCtx = document.getElementById('statusChart').getContext('2d');

    platformChart = new Chart(platformCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: '发现',
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
            labels: ['待处置', '已通知', '已轮换', '误报'],
            datasets: [{
                data: [0, 0, 0, 0],
                backgroundColor: ['#2563eb', '#f59e0b', '#10b981', '#6b7280'],
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
        }
    });
}

function updateCharts(stats) {
    if (platformChart && stats.top_platforms) {
        platformChart.data.labels = stats.top_platforms.map(p => p.platform);
        platformChart.data.datasets[0].data = stats.top_platforms.map(p => p.count);
        platformChart.update();
    }

    if (statusChart) {
        const counts = stats.dispositions || {};
        statusChart.data.datasets[0].data = [
            counts.open || 0,
            counts.notified || 0,
            counts.rotated || 0,
            counts.false_positive || 0,
        ];
        statusChart.update();
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
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
