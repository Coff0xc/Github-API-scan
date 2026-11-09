// Local findings dashboard. The table never renders a raw key.

let currentPage = 0;
const pageSize = 50;
let platformChart = null;
let statusChart = null;
let allFindings = [];
let lang = "en";

const I18N = {
    en: {
        title: "Findings",
        all: "All",
        open: "Open",
        notified: "Notified",
        rotated: "Rotated",
        false_positive: "False positive",
        platforms: "Platforms",
        dispositionChart: "Disposition",
        disposition: "Disposition",
        platform: "Platform",
        fingerprint: "Fingerprint",
        preview: "Preview",
        location: "Location",
        searchLabel: "Search",
        search: "Fingerprint, location, or preview",
        token: "Token",
        loading: "Loading",
        empty: "No findings yet.",
        loadError: "Could not load findings.",
        idle: "Idle",
        scanning: "Scanning",
        prev: "Previous",
        next: "Next",
        updating: "Saving disposition…",
        updated: "Disposition saved.",
        saveError: "Disposition was not saved.",
        findingsCount: "Findings",
    },
    zh: {
        title: "发现记录",
        all: "全部",
        open: "待处置",
        notified: "已通知",
        rotated: "已轮换",
        false_positive: "误报",
        platforms: "平台",
        dispositionChart: "处置状态",
        disposition: "处置",
        platform: "平台",
        fingerprint: "指纹",
        preview: "预览",
        location: "位置",
        searchLabel: "搜索",
        search: "指纹、位置或预览",
        token: "令牌",
        loading: "加载中",
        empty: "没有发现记录",
        loadError: "发现记录加载失败",
        idle: "空闲",
        scanning: "扫描中",
        prev: "上一页",
        next: "下一页",
        updating: "正在更新处置状态",
        updated: "已更新",
        saveError: "处置状态没有写回",
        findingsCount: "发现",
    },
};

const DISPOSITIONS = ["open", "notified", "rotated", "false_positive"];

document.addEventListener("DOMContentLoaded", () => {
    lang = preferredLang();
    applyLanguage();
    loadFindings();
    loadStats();
    initCharts();
    setupEventListeners();

    setInterval(loadStats, 5000);
    setInterval(loadFindings, 10000);
});

function t(key) {
    return (I18N[lang] && I18N[lang][key]) || I18N.en[key] || key;
}

function preferredLang() {
    const query = new URLSearchParams(window.location.search).get("lang");
    if (query === "en" || query === "zh") {
        return query;
    }
    const saved = localStorage.getItem("dashboardLang");
    if (saved === "en" || saved === "zh") {
        return saved;
    }
    return (navigator.language || "").toLowerCase().startsWith("zh") ? "zh" : "en";
}

function applyLanguage() {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    document.title = t("title");
    document.querySelectorAll("[data-i18n]").forEach((node) => {
        node.textContent = t(node.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
        node.placeholder = t(node.getAttribute("data-i18n-placeholder"));
    });
    document.querySelectorAll("[data-set-lang]").forEach((button) => {
        button.setAttribute("aria-pressed", button.getAttribute("data-set-lang") === lang ? "true" : "false");
    });
    rebuildDispositionFilter();
    if (platformChart) {
        platformChart.data.datasets[0].label = t("findingsCount");
        platformChart.update();
    }
    if (statusChart) {
        statusChart.data.labels = DISPOSITIONS.map((name) => t(name));
        statusChart.update();
    }
    if (allFindings.length || document.getElementById("findings-tbody").children.length) {
        renderCurrentPage();
    }
}

function rebuildDispositionFilter() {
    const select = document.getElementById("filter-disposition");
    const selected = select.value;
    select.innerHTML = `<option value="">${escapeHtml(t("all"))}</option>` +
        DISPOSITIONS.map((name) => `<option value="${name}">${escapeHtml(t(name))}</option>`).join("");
    select.value = selected;
}

function setupEventListeners() {
    document.getElementById("filter-disposition").addEventListener("change", () => {
        currentPage = 0;
        renderCurrentPage();
    });

    document.getElementById("filter-platform").addEventListener("change", () => {
        currentPage = 0;
        renderCurrentPage();
    });

    document.getElementById("search-input").addEventListener("input", debounce(() => {
        currentPage = 0;
        renderCurrentPage();
    }, 300));

    document.getElementById("prev-btn").addEventListener("click", () => {
        if (currentPage > 0) {
            currentPage--;
            renderCurrentPage();
        }
    });

    document.getElementById("next-btn").addEventListener("click", () => {
        currentPage++;
        renderCurrentPage();
    });

    document.querySelectorAll("[data-set-lang]").forEach((button) => {
        button.addEventListener("click", () => {
            lang = button.getAttribute("data-set-lang");
            localStorage.setItem("dashboardLang", lang);
            applyLanguage();
            loadStats();
        });
    });

    const tokenInput = document.getElementById("dashboard-token");
    tokenInput.value = sessionStorage.getItem("dashboardToken") || "";
    tokenInput.addEventListener("change", () => {
        sessionStorage.setItem("dashboardToken", tokenInput.value.trim());
    });

    document.getElementById("findings-tbody").addEventListener("change", (event) => {
        const select = event.target;
        if (!select.classList.contains("disposition-select")) {
            return;
        }
        setDisposition(select.dataset.fingerprint, select.value, select);
    });
}

async function loadStats() {
    try {
        const response = await fetch("/api/stats");
        const stats = await response.json();
        const counts = stats.dispositions || {};

        document.getElementById("total-findings").textContent = stats.total_keys || 0;
        document.getElementById("open-findings").textContent = counts.open || 0;
        document.getElementById("notified-findings").textContent = counts.notified || 0;
        document.getElementById("rotated-findings").textContent = counts.rotated || 0;

        const statusText = document.getElementById("status-text");
        const dot = document.querySelector(".status-indicator");
        if (stats.is_running) {
            statusText.textContent = t("scanning");
            dot.style.background = "#059669";
        } else {
            statusText.textContent = t("idle");
            dot.style.background = "#9aa6b2";
        }

        updateCharts(stats);
    } catch (error) {
        console.error("Failed to load stats:", error);
    }
}

async function loadFindings() {
    try {
        const response = await fetch("/api/findings");
        const data = await response.json();
        allFindings = Array.isArray(data.findings) ? data.findings : [];
        fillPlatforms(allFindings);
        renderCurrentPage();
    } catch (error) {
        console.error("Failed to load findings:", error);
        document.getElementById("findings-tbody").innerHTML =
            `<tr><td colspan="5" class="loading">${escapeHtml(t("loadError"))}</td></tr>`;
    }
}

function fillPlatforms(findings) {
    const select = document.getElementById("filter-platform");
    const selected = select.value;
    const names = [...new Set(findings.map((item) => item.platform).filter(Boolean))].sort();
    select.innerHTML = `<option value="">${escapeHtml(t("all"))}</option>`;
    names.forEach((platform) => {
        const option = document.createElement("option");
        option.value = platform;
        option.textContent = platform;
        select.appendChild(option);
    });
    if (names.includes(selected)) {
        select.value = selected;
    }
}

function filteredFindings() {
    const disposition = document.getElementById("filter-disposition").value;
    const platform = document.getElementById("filter-platform").value;
    const search = document.getElementById("search-input").value.trim().toLowerCase();

    return allFindings.filter((item) => {
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
        ].join(" ").toLowerCase();
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
    const tbody = document.getElementById("findings-tbody");

    if (findings.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="loading">${escapeHtml(t("empty"))}</td></tr>`;
        return;
    }

    tbody.innerHTML = findings.map((item) => {
        const disposition = item.disposition || "open";
        return `
        <tr>
            <td class="fingerprint" title="${escapeHtml(item.fingerprint || "")}">${escapeHtml(shortFingerprint(item.fingerprint))}</td>
            <td><span class="platform-badge">${escapeHtml(item.platform || "")}</span></td>
            <td><code class="key-text">${escapeHtml(item.preview || "")}</code></td>
            <td>${locationCell(item)}</td>
            <td>${dispositionSelect(item.fingerprint, disposition)}</td>
        </tr>`;
    }).join("");
}

function shortFingerprint(value) {
    const text = value || "";
    if (text.length <= 18) {
        return text;
    }
    return `${text.slice(0, 8)}…${text.slice(-6)}`;
}

function dispositionSelect(fingerprint, current) {
    const options = DISPOSITIONS.map((value) => {
        const selected = value === current ? " selected" : "";
        return `<option value="${value}"${selected}>${escapeHtml(t(value))}</option>`;
    }).join("");
    return `<select class="disposition-select status-${escapeHtml(current)}" data-fingerprint="${escapeHtml(fingerprint || "")}" data-current="${escapeHtml(current)}">${options}</select>`;
}

async function setDisposition(fingerprint, disposition, select) {
    const message = document.getElementById("disposition-message");
    const token = (document.getElementById("dashboard-token").value || "").trim();
    sessionStorage.setItem("dashboardToken", token);
    message.textContent = t("updating");
    try {
        const response = await fetch("/api/findings/disposition", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-API-Token": token,
            },
            body: JSON.stringify({ fingerprint, disposition }),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
            select.value = select.dataset.current || "open";
            message.textContent = body.error || t("saveError");
            return;
        }
        select.dataset.current = disposition;
        select.className = `disposition-select status-${disposition}`;
        const row = allFindings.find((item) => item.fingerprint === fingerprint);
        if (row) {
            row.disposition = disposition;
        }
        message.textContent = t("updated");
        loadStats();
    } catch (error) {
        select.value = select.dataset.current || "open";
        message.textContent = t("saveError");
        console.error(error);
    }
}

function locationCell(item) {
    const value = item.location || "";
    if (!value) {
        return "-";
    }
    const place = readableLocation(item);
    const inner = `<span class="loc"><span class="loc-repo">${escapeHtml(place.repo)}</span><span class="loc-path">${escapeHtml(place.path)}</span></span>`;
    if (/^https?:\/\//i.test(value)) {
        return `<a href="${escapeHtml(value)}" target="_blank" rel="noopener" class="source-link" title="${escapeHtml(value)}">${inner}</a>`;
    }
    return inner;
}

function readableLocation(item) {
    const repo = item.repo || "";
    const path = item.path || "";
    if (repo || path) {
        return { repo: repo || path, path: repo ? path : "" };
    }
    return { repo: item.location || "-", path: "" };
}

function updatePagination(total) {
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (currentPage > totalPages - 1) {
        currentPage = totalPages - 1;
    }
    const label = lang === "zh"
        ? `第 ${currentPage + 1} / ${totalPages} 页 · ${total} 条`
        : `Page ${currentPage + 1} of ${totalPages} · ${total}`;
    document.getElementById("page-info").textContent = label;
    document.getElementById("prev-btn").disabled = currentPage === 0;
    document.getElementById("next-btn").disabled = currentPage >= totalPages - 1;
}

function chartFont() {
    return { family: '"Segoe UI", sans-serif', size: 12 };
}

function initCharts() {
    const platformCtx = document.getElementById("platformChart").getContext("2d");
    const statusCtx = document.getElementById("statusChart").getContext("2d");
    const common = {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
    };

    platformChart = new Chart(platformCtx, {
        type: "bar",
        data: {
            labels: [],
            datasets: [{
                label: t("findingsCount"),
                data: [],
                backgroundColor: "#1d4ed8",
                borderRadius: 6,
                maxBarThickness: 28,
            }],
        },
        options: {
            ...common,
            plugins: {
                legend: { display: false },
                tooltip: { titleFont: chartFont(), bodyFont: chartFont() },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { precision: 0, stepSize: 1, color: "#5d6b7c", font: chartFont() },
                    grid: { color: "#eef2f6" },
                    border: { display: false },
                },
                x: {
                    ticks: { color: "#5d6b7c", font: chartFont() },
                    grid: { display: false },
                    border: { display: false },
                },
            },
        },
    });

    statusChart = new Chart(statusCtx, {
        type: "doughnut",
        data: {
            labels: DISPOSITIONS.map((name) => t(name)),
            datasets: [{
                data: [0, 0, 0, 0],
                backgroundColor: ["#1d4ed8", "#d97706", "#059669", "#94a3b8"],
                borderWidth: 2,
                borderColor: "#ffffff",
                hoverOffset: 0,
            }],
        },
        options: {
            ...common,
            cutout: "68%",
            plugins: {
                legend: {
                    position: "right",
                    labels: {
                        boxWidth: 10,
                        boxHeight: 10,
                        padding: 12,
                        color: "#142033",
                        font: chartFont(),
                    },
                },
            },
        },
    });
}

function updateCharts(stats) {
    if (platformChart && stats.top_platforms) {
        platformChart.data.labels = stats.top_platforms.map((item) => item.platform);
        platformChart.data.datasets[0].data = stats.top_platforms.map((item) => item.count);
        platformChart.data.datasets[0].label = t("findingsCount");
        platformChart.update();
    }

    if (statusChart) {
        const counts = stats.dispositions || {};
        statusChart.data.labels = DISPOSITIONS.map((name) => t(name));
        statusChart.data.datasets[0].data = DISPOSITIONS.map((name) => counts[name] || 0);
        statusChart.update();
    }
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
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
