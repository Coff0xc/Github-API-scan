// 实时管道 JavaScript 客户端
// 用于 Web Dashboard 的 WebSocket 集成

class RealtimePipeline {
    constructor(wsUrl = 'ws://localhost:8765/ws') {
        this.wsUrl = wsUrl;
        this.ws = null;
        this.reconnectInterval = 5000;
        this.reconnectTimer = null;
        this.handlers = {};
        this.isConnected = false;
        this.autoReconnect = true;
    }

    // 连接到服务器
    connect(filters = {}) {
        // 构建URL（带过滤器）
        let url = this.wsUrl;
        const params = [];

        if (filters.platforms && filters.platforms.length > 0) {
            params.push(`platforms=${filters.platforms.join(',')}`);
        }
        if (filters.highValueOnly) {
            params.push('high_value_only=true');
        }

        if (params.length > 0) {
            url += '?' + params.join('&');
        }

        console.log('[实时管道] 正在连接...', url);

        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            console.log('[实时管道] 已连接');
            this.isConnected = true;
            this.clearReconnectTimer();
            this.trigger('connected', { timestamp: new Date().toISOString() });
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleEvent(data);
            } catch (e) {
                console.error('[实时管道] 解析消息失败:', e);
            }
        };

        this.ws.onerror = (error) => {
            console.error('[实时管道] 连接错误:', error);
            this.trigger('error', { error });
        };

        this.ws.onclose = () => {
            console.log('[实时管道] 连接已关闭');
            this.isConnected = false;
            this.trigger('disconnected', { timestamp: new Date().toISOString() });

            if (this.autoReconnect) {
                this.scheduleReconnect();
            }
        };
    }

    // 断开连接
    disconnect() {
        this.autoReconnect = false;
        this.clearReconnectTimer();

        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    // 重连调度
    scheduleReconnect() {
        this.clearReconnectTimer();
        console.log(`[实时管道] ${this.reconnectInterval / 1000}秒后重连...`);

        this.reconnectTimer = setTimeout(() => {
            this.connect();
        }, this.reconnectInterval);
    }

    clearReconnectTimer() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }

    // 注册事件处理器
    on(eventType, handler) {
        if (!this.handlers[eventType]) {
            this.handlers[eventType] = [];
        }
        this.handlers[eventType].push(handler);
    }

    // 注销事件处理器
    off(eventType, handler) {
        if (!this.handlers[eventType]) return;

        const index = this.handlers[eventType].indexOf(handler);
        if (index > -1) {
            this.handlers[eventType].splice(index, 1);
        }
    }

    // 触发事件
    trigger(eventType, data) {
        if (this.handlers[eventType]) {
            this.handlers[eventType].forEach(handler => {
                try {
                    handler(data);
                } catch (e) {
                    console.error(`[实时管道] 处理器执行失败 (${eventType}):`, e);
                }
            });
        }

        // 通配符处理器
        if (this.handlers['*']) {
            this.handlers['*'].forEach(handler => {
                try {
                    handler(eventType, data);
                } catch (e) {
                    console.error('[实时管道] 通配符处理器执行失败:', e);
                }
            });
        }
    }

    // 处理接收到的事件
    handleEvent(message) {
        const { event_type, timestamp, data } = message;

        console.log(`[实时管道] ${event_type}:`, data);

        // 触发对应事件
        this.trigger(event_type, { timestamp, ...data });
    }

    // 发送命令
    sendCommand(command, params = {}) {
        if (!this.isConnected || !this.ws) {
            console.warn('[实时管道] 未连接，无法发送命令');
            return false;
        }

        const message = JSON.stringify({ command, ...params });
        this.ws.send(message);
        return true;
    }

    // 获取统计信息
    getStats() {
        return this.sendCommand('get_stats');
    }

    // 更新过滤器
    updateFilters(filters) {
        return this.sendCommand('update_filters', { filters });
    }
}

// Dashboard 集成示例
class DashboardRealtimeIntegration {
    constructor(dashboard) {
        this.dashboard = dashboard;
        this.pipeline = new RealtimePipeline();
        this.initHandlers();
    }

    initHandlers() {
        // Key 发现
        this.pipeline.on('key_found', (data) => {
            this.showNotification('发现新Key',
                `${data.platform}: ${data.api_key}`, 'info');
            this.dashboard.incrementCounter('keys-found');
        });

        // Key 验证完成
        this.pipeline.on('key_validated', (data) => {
            const status = data.status === 'valid' ? '有效' : '无效';
            this.showNotification('Key验证完成',
                `${data.platform}: ${status}`,
                data.status === 'valid' ? 'success' : 'warning');

            if (data.status === 'valid') {
                this.dashboard.incrementCounter('valid-keys');
            }

            // 更新Key列表
            this.dashboard.refreshKeyList();
        });

        // 高价值Key告警
        this.pipeline.on('high_value_key', (data) => {
            this.showNotification('🔥 高价值Key发现！',
                `${data.platform} | 评分: ${data.value_score}/100 | 余额: $${data.balance}`,
                'critical');

            this.dashboard.incrementCounter('high-value-keys');
            this.dashboard.highlightKey(data.api_key);
        });

        // 扫描进度
        this.pipeline.on('scan_progress', (data) => {
            this.dashboard.updateProgress(data.progress, data.scanned, data.total);
        });

        // 扫描完成
        this.pipeline.on('scan_complete', (data) => {
            this.showNotification('扫描完成',
                `发现 ${data.keys_found} 个Key，其中 ${data.valid_keys} 个有效`,
                'success');

            this.dashboard.showScanSummary(data);
        });

        // 连接状态
        this.pipeline.on('connected', () => {
            this.updateConnectionStatus(true);
        });

        this.pipeline.on('disconnected', () => {
            this.updateConnectionStatus(false);
        });
    }

    connect(filters = {}) {
        this.pipeline.connect(filters);
    }

    disconnect() {
        this.pipeline.disconnect();
    }

    showNotification(title, message, type = 'info') {
        // 创建通知元素
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <strong>${title}</strong>
            <p>${message}</p>
        `;

        // 添加到页面
        const container = document.getElementById('notifications');
        if (container) {
            container.appendChild(notification);

            // 3秒后自动移除
            setTimeout(() => {
                notification.classList.add('fade-out');
                setTimeout(() => notification.remove(), 300);
            }, 3000);
        }

        // 同时使用浏览器通知（需要权限）
        if (type === 'critical' && 'Notification' in window && Notification.permission === 'granted') {
            new Notification(title, { body: message });
        }
    }

    updateConnectionStatus(connected) {
        const indicator = document.getElementById('realtime-status');
        if (indicator) {
            indicator.className = connected ? 'status-connected' : 'status-disconnected';
            indicator.textContent = connected ? '实时连接' : '已断开';
        }
    }
}

// 使用示例（在 dashboard.html 中）
/*
<script>
    // 初始化实时管道
    const dashboard = {
        incrementCounter: (id) => {
            const el = document.getElementById(id);
            if (el) el.textContent = parseInt(el.textContent || 0) + 1;
        },
        refreshKeyList: () => {
            loadKeys(); // 刷新Key列表
        },
        highlightKey: (apiKey) => {
            // 高亮显示高价值Key
        },
        updateProgress: (progress, scanned, total) => {
            const bar = document.getElementById('progress-bar');
            if (bar) bar.style.width = progress + '%';
        },
        showScanSummary: (data) => {
            console.log('扫描完成:', data);
        }
    };

    const realtime = new DashboardRealtimeIntegration(dashboard);

    // 连接（仅高价值Key）
    realtime.connect({ highValueOnly: true });

    // 请求浏览器通知权限
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
</script>
*/
