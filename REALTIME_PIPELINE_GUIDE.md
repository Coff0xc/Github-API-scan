# 实时管道使用指南 (P2)

## 概述

实时管道（Realtime Pipeline）提供基于WebSocket的实时事件推送，让Dashboard和监控系统能够即时获取扫描进度、Key发现和验证结果。

### 核心能力

- ✅ **实时推送** - WebSocket双向通信
- ✅ **事件系统** - 6种事件类型（发现/验证/告警/进度等）
- ✅ **多客户端** - 支持多个Dashboard同时连接
- ✅ **智能过滤** - 按平台/状态/价值筛选
- ✅ **自动重连** - 断线自动恢复
- ✅ **心跳检测** - 30秒心跳保活

---

## 架构设计

```
扫描器/验证器
    ↓ emit_event()
RealtimeHub（事件中心）
    ↓ broadcast()
WebSocket连接池
    ↓ 过滤+推送
客户端（Dashboard/监控系统）
```

### 组件说明

| 组件 | 文件 | 职责 |
|------|------|------|
| 服务端 | `realtime_pipeline.py` | WebSocket服务器+事件分发 |
| Python客户端 | `realtime_client_example.py` | Python客户端示例 |
| JS客户端 | `static/js/realtime.js` | Web Dashboard集成 |

---

## 事件类型

### 1. KEY_FOUND - Key发现

```json
{
  "event_type": "key_found",
  "timestamp": "2026-07-29T12:34:56",
  "data": {
    "platform": "openai",
    "api_key": "sk-proj-xxx...",
    "source_url": "https://github.com/user/repo"
  }
}
```

### 2. KEY_VALIDATED - Key验证完成

```json
{
  "event_type": "key_validated",
  "timestamp": "2026-07-29T12:35:01",
  "data": {
    "platform": "openai",
    "api_key": "sk-proj-xxx...",
    "status": "valid",
    "balance": 150.0,
    "model_tier": "GPT-4",
    "value_score": 75,
    "is_high_value": true
  }
}
```

### 3. HIGH_VALUE_KEY - 高价值Key告警

```json
{
  "event_type": "high_value_key",
  "timestamp": "2026-07-29T12:35:02",
  "data": {
    "platform": "openai",
    "api_key": "sk-proj-xxx...",
    "balance": 150.0,
    "model_tier": "GPT-4",
    "value_score": 75,
    "alert_level": "high"
  }
}
```

### 4. SCAN_PROGRESS - 扫描进度

```json
{
  "event_type": "scan_progress",
  "timestamp": "2026-07-29T12:35:10",
  "data": {
    "scanned": 50,
    "total": 100,
    "progress": 50.0,
    "keys_found": 10,
    "valid_keys": 5
  }
}
```

### 5. SCAN_COMPLETE - 扫描完成

```json
{
  "event_type": "scan_complete",
  "timestamp": "2026-07-29T12:40:00",
  "data": {
    "total_scanned": 100,
    "keys_found": 20,
    "valid_keys": 12,
    "high_value_keys": 3,
    "duration": 300.5,
    "keys_per_second": 0.33
  }
}
```

### 6. ERROR - 错误事件

```json
{
  "event_type": "error",
  "timestamp": "2026-07-29T12:35:30",
  "data": {
    "error": "Rate limit exceeded",
    "platform": "openai"
  }
}
```

---

## 服务端使用

### 启动服务器

```bash
# 方式1: 直接运行
python realtime_pipeline.py

# 方式2: 集成到主程序
from realtime_pipeline import start_realtime_server, realtime_hub

# 启动服务器（后台任务）
asyncio.create_task(start_realtime_server(host='0.0.0.0', port=8765))

# 发送事件
await realtime_hub.emit_key_found("openai", "sk-xxx", "https://...")
await realtime_hub.emit_key_validated("openai", "sk-xxx", "valid", ...)
```

### 事件发送API

```python
from realtime_pipeline import realtime_hub

# Key发现
await realtime_hub.emit_key_found(
    platform="openai",
    api_key="sk-xxx",
    source_url="https://github.com/..."
)

# Key验证完成
await realtime_hub.emit_key_validated(
    platform="openai",
    api_key="sk-xxx",
    status="valid",
    balance=100.0,
    model_tier="GPT-4",
    value_score=75,
    is_high_value=True
)

# 高价值Key告警（自动触发，也可手动）
await realtime_hub.emit_high_value_key(
    platform="openai",
    api_key="sk-xxx",
    balance=200.0,
    model_tier="GPT-5",
    value_score=85
)

# 扫描进度
await realtime_hub.emit_scan_progress(
    scanned=50,
    total=100,
    keys_found=10,
    valid_keys=5
)

# 扫描完成
await realtime_hub.emit_scan_complete(
    total_scanned=100,
    keys_found=20,
    valid_keys=12,
    high_value_keys=3,
    duration=300.5
)
```

---

## Python 客户端

### 基础连接

```python
from realtime_client_example import RealtimeClient

client = RealtimeClient("ws://localhost:8765/ws")

# 通用事件处理
async def on_event(data):
    print(f"{data['event_type']}: {data['data']}")

client.on('*', on_event)

await client.connect()
await client.listen()
```

### 过滤监听

```python
# 仅监听OpenAI平台的高价值Key
await client.connect(filters={
    'platforms': ['openai', 'anthropic'],
    'high_value_only': True
})

# 高价值Key处理
async def on_high_value(data):
    print(f"🔥 高价值Key: {data['api_key']}")
    print(f"   评分: {data['value_score']}/100")
    print(f"   余额: ${data['balance']}")

client.on('high_value_key', on_high_value)
```

### 进度监控

```python
async def on_progress(data):
    progress = data['progress']
    print(f"\r进度: {progress:.1f}%", end='')

async def on_complete(data):
    print(f"\n✓ 完成! 发现 {data['keys_found']} 个Key")

client.on('scan_progress', on_progress)
client.on('scan_complete', on_complete)
```

---

## Web Dashboard 集成

### 1. 引入脚本

```html
<script src="/static/js/realtime.js"></script>
```

### 2. 初始化连接

```javascript
// 创建实时管道实例
const pipeline = new RealtimePipeline('ws://localhost:8765/ws');

// 连接（可选过滤器）
pipeline.connect({
    platforms: ['openai', 'anthropic'],
    highValueOnly: true
});
```

### 3. 监听事件

```javascript
// Key发现
pipeline.on('key_found', (data) => {
    console.log('发现Key:', data.platform, data.api_key);
    updateKeyCounter();
});

// Key验证完成
pipeline.on('key_validated', (data) => {
    if (data.status === 'valid') {
        showNotification('验证成功', data.platform);
        refreshKeyList();
    }
});

// 高价值Key告警
pipeline.on('high_value_key', (data) => {
    showAlert(`🔥 高价值Key发现！\n评分: ${data.value_score}/100`);
    playSound();  // 播放提示音
});

// 扫描进度
pipeline.on('scan_progress', (data) => {
    updateProgressBar(data.progress);
    document.getElementById('scan-status').textContent = 
        `${data.scanned}/${data.total} (${data.keys_found} keys found)`;
});
```

### 4. 完整Dashboard集成

```javascript
// 使用集成类
const dashboard = {
    incrementCounter: (id) => { /* ... */ },
    refreshKeyList: () => { /* ... */ },
    highlightKey: (key) => { /* ... */ }
};

const realtime = new DashboardRealtimeIntegration(dashboard);
realtime.connect({ highValueOnly: true });

// 自动处理所有事件，无需手动监听
```

---

## 过滤器配置

### URL参数方式

```
ws://localhost:8765/ws?platforms=openai,anthropic&high_value_only=true
```

### Python客户端

```python
filters = {
    'platforms': ['openai', 'anthropic'],  # 仅这些平台
    'high_value_only': True                 # 仅高价值Key
}
await client.connect(filters=filters)
```

### JavaScript客户端

```javascript
pipeline.connect({
    platforms: ['openai', 'anthropic'],
    highValueOnly: true
});
```

### 动态更新过滤器

```python
# Python
await client.update_filters({
    'platforms': ['openai'],
    'high_value_only': False
})
```

```javascript
// JavaScript
pipeline.updateFilters({
    platforms: ['openai'],
    highValueOnly: false
});
```

---

## 命令系统

### 获取统计信息

```python
# Python
await client.get_stats()

# 响应:
{
  "event_type": "stats",
  "data": {
    "total_events": 150,
    "connected_clients": 3,
    "keys_found": 25,
    "keys_validated": 20,
    "high_value_keys": 5
  }
}
```

```javascript
// JavaScript
pipeline.getStats();
```

---

## 部署配置

### 独立部署

```bash
# 启动实时管道服务器
python realtime_pipeline.py

# 输出: 🚀 实时管道服务器启动: ws://0.0.0.0:8765/ws
```

### 集成到主程序

```python
# main.py
import asyncio
from realtime_pipeline import start_realtime_server, realtime_hub
from scanner import Scanner
from validator_deep import IntegratedDeepValidator

async def main():
    # 启动实时管道（后台）
    realtime_task = asyncio.create_task(
        start_realtime_server(host='0.0.0.0', port=8765)
    )

    # 扫描和验证
    scanner = Scanner()
    validator = IntegratedDeepValidator(db)

    async for key in scanner.scan():
        # 发送Key发现事件
        await realtime_hub.emit_key_found(
            key.platform, key.api_key, key.source_url
        )

        # 验证
        standard, deep = await validator.validate_with_depth(
            key.platform, key.api_key, key.base_url
        )

        # 发送验证完成事件
        await realtime_hub.emit_key_validated(
            key.platform, key.api_key, standard.status.value,
            deep.balance if deep else 0.0,
            deep.model_tier if deep else "",
            deep.value_score if deep else 0,
            deep.is_high_value if deep else False
        )

    await realtime_task

if __name__ == "__main__":
    asyncio.run(main())
```

### Docker部署

```dockerfile
# Dockerfile已包含实时管道
EXPOSE 8765

# docker-compose.yml
services:
  scanner:
    ports:
      - "8765:8765"  # 实时管道端口
```

---

## 性能优化

### 连接池管理

- 自动清理失效连接
- 心跳检测（30秒）
- 异常连接自动移除

### 事件过滤

- 服务端过滤减少带宽
- 客户端仅接收需要的事件
- 支持多级过滤组合

### 自动重连

```javascript
// JavaScript客户端自动重连
pipeline.reconnectInterval = 5000;  // 5秒后重连
pipeline.autoReconnect = true;
```

```python
# Python客户端需要手动实现重连逻辑
while True:
    try:
        await client.connect()
        await client.listen()
    except Exception as e:
        logger.error(f"连接断开: {e}")
        await asyncio.sleep(5)
```

---

## 安全建议

### 生产环境

1. **使用WSS** - 加密传输
   ```python
   # 需要SSL证书
   ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
   ssl_context.load_cert_chain('cert.pem', 'key.pem')
   ```

2. **认证机制** - Token验证
   ```javascript
   pipeline.connect({}, { headers: { 'Authorization': 'Bearer token' } });
   ```

3. **速率限制** - 防止滥用
   ```python
   # 限制每个客户端的事件接收速率
   ```

4. **CORS配置** - 限制来源
   ```python
   app.router.add_route('*', '/ws', websocket_handler, 
                        expect_handler=web.Request.json)
   ```

---

## 故障排查

### 连接失败

```bash
# 检查端口占用
netstat -an | grep 8765

# 检查防火墙
sudo ufw allow 8765
```

### 事件未收到

1. 检查过滤器配置
2. 查看服务端日志
3. 验证事件发送代码

### 频繁断线

1. 检查网络稳定性
2. 调整心跳间隔
3. 启用自动重连

---

## 完整示例

### 监控脚本

```python
import asyncio
from realtime_client_example import RealtimeClient

async def monitor():
    client = RealtimeClient()

    # 统计信息
    stats = {'total': 0, 'valid': 0, 'high_value': 0}

    async def on_validated(data):
        stats['total'] += 1
        if data['status'] == 'valid':
            stats['valid'] += 1
        if data['is_high_value']:
            stats['high_value'] += 1
            print(f"\n🔥 高价值Key #{stats['high_value']}")
            print(f"   平台: {data['platform']}")
            print(f"   评分: {data['value_score']}/100")
            print(f"   余额: ${data['balance']:.2f}")

    client.on('key_validated', on_validated)

    await client.connect()
    print("监控已启动，等待事件...")

    try:
        await client.listen()
    except KeyboardInterrupt:
        print(f"\n\n最终统计:")
        print(f"  总验证: {stats['total']}")
        print(f"  有效: {stats['valid']}")
        print(f"  高价值: {stats['high_value']}")

asyncio.run(monitor())
```

---

## 相关文档

- [P4_DEEP_VALIDATION_COMPLETE.md](./P4_DEEP_VALIDATION_COMPLETE.md) - 深度验证
- [WEB_DASHBOARD_GUIDE.md](./WEB_DASHBOARD_GUIDE.md) - Dashboard指南
- [DOCKER_GUIDE.md](./DOCKER_GUIDE.md) - Docker部署

---

**版本**: 1.0  
**更新时间**: 2026-07-29  
**作者**: Coff0xc
