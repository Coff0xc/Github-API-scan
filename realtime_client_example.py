"""
实时管道客户端示例

演示如何连接和使用WebSocket实时通知
"""

import asyncio
import json
from datetime import datetime

import aiohttp
from loguru import logger


class RealtimeClient:
    """实时管道客户端"""

    def __init__(self, ws_url: str = "ws://localhost:8765/ws"):
        self.ws_url = ws_url
        self.ws = None
        self.session = None
        self.running = False
        self.handlers = {}

    async def connect(self, filters: dict = None):
        """连接到服务器"""
        self.session = aiohttp.ClientSession()

        # 构建URL（带过滤器）
        url = self.ws_url
        if filters:
            params = []
            if 'platforms' in filters:
                params.append(f"platforms={','.join(filters['platforms'])}")
            if filters.get('high_value_only'):
                params.append("high_value_only=true")
            if params:
                url += '?' + '&'.join(params)

        self.ws = await self.session.ws_connect(url)
        self.running = True
        logger.success(f"✓ 已连接到实时管道: {url}")

    async def disconnect(self):
        """断开连接"""
        self.running = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
        logger.info("已断开连接")

    def on(self, event_type: str, handler):
        """注册事件处理器"""
        self.handlers[event_type] = handler

    async def listen(self):
        """监听事件"""
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        event_type = data.get('event_type')

                        # 调用对应的处理器
                        if event_type in self.handlers:
                            await self.handlers[event_type](data)
                        elif '*' in self.handlers:  # 通配符处理器
                            await self.handlers['*'](data)

                    except json.JSONDecodeError:
                        logger.warning(f"无效的JSON: {msg.data}")

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket错误: {self.ws.exception()}")
                    break

        except Exception as e:
            logger.error(f"监听异常: {e}")
        finally:
            self.running = False

    async def send_command(self, command: str, **kwargs):
        """发送命令到服务器"""
        if self.ws:
            data = {'command': command, **kwargs}
            await self.ws.send_json(data)

    async def get_stats(self):
        """获取统计信息"""
        await self.send_command('get_stats')

    async def update_filters(self, filters: dict):
        """更新过滤器"""
        await self.send_command('update_filters', filters=filters)


# 示例用法
async def example_basic():
    """基础示例 - 监听所有事件"""
    print("\n" + "=" * 70)
    print("示例 1: 基础监听")
    print("=" * 70)

    client = RealtimeClient()

    # 通用事件处理器
    async def on_event(data):
        event_type = data['event_type']
        timestamp = data['timestamp']
        event_data = data['data']

        print(f"\n[{timestamp}] {event_type.upper()}")
        print(f"  数据: {json.dumps(event_data, ensure_ascii=False, indent=2)}")

    client.on('*', on_event)

    await client.connect()
    await client.listen()


async def example_filtered():
    """过滤示例 - 仅监听OpenAI高价值Key"""
    print("\n" + "=" * 70)
    print("示例 2: 过滤监听（仅OpenAI高价值Key）")
    print("=" * 70)

    client = RealtimeClient()

    # 高价值Key处理器
    async def on_high_value_key(data):
        key_data = data['data']
        print(f"\n🔥 高价值Key发现！")
        print(f"  平台: {key_data['platform']}")
        print(f"  Key: {key_data['api_key']}")
        print(f"  余额: ${key_data['balance']:.2f}")
        print(f"  模型: {key_data['model_tier']}")
        print(f"  评分: {key_data['value_score']}/100")

    client.on('high_value_key', on_high_value_key)

    # 连接时设置过滤器
    await client.connect(filters={
        'platforms': ['openai'],
        'high_value_only': True
    })

    await client.listen()


async def example_progress_monitoring():
    """进度监控示例"""
    print("\n" + "=" * 70)
    print("示例 3: 扫描进度监控")
    print("=" * 70)

    client = RealtimeClient()

    # 进度处理器
    async def on_progress(data):
        progress_data = data['data']
        progress = progress_data['progress']
        scanned = progress_data['scanned']
        total = progress_data['total']
        keys_found = progress_data['keys_found']

        print(f"\r进度: {progress:.1f}% ({scanned}/{total}) | 发现Key: {keys_found}", end='')

    # 完成处理器
    async def on_complete(data):
        complete_data = data['data']
        print(f"\n\n✓ 扫描完成！")
        print(f"  总扫描: {complete_data['total_scanned']}")
        print(f"  发现Key: {complete_data['keys_found']}")
        print(f"  有效Key: {complete_data['valid_keys']}")
        print(f"  高价值: {complete_data['high_value_keys']}")
        print(f"  耗时: {complete_data['duration']:.2f}秒")
        print(f"  速度: {complete_data['keys_per_second']:.2f} keys/s")

    client.on('scan_progress', on_progress)
    client.on('scan_complete', on_complete)

    await client.connect()
    await client.listen()


async def example_interactive():
    """交互示例 - 支持命令"""
    print("\n" + "=" * 70)
    print("示例 4: 交互式客户端")
    print("=" * 70)
    print("命令: stats - 获取统计 | filter - 更新过滤器 | quit - 退出")
    print("=" * 70)

    client = RealtimeClient()

    # 事件处理器
    async def on_event(data):
        event_type = data['event_type']
        if event_type not in ['heartbeat', 'stats']:
            print(f"\n[事件] {event_type}: {data['data']}")

    client.on('*', on_event)

    await client.connect()

    # 启动监听任务
    listen_task = asyncio.create_task(client.listen())

    # 交互循环（简化版 - 实际需要用aioconsole）
    print("\n提示: 实际使用需要 aioconsole 库支持交互输入")
    print("示例命令已预设为获取统计信息...\n")

    # 模拟命令
    await asyncio.sleep(2)
    await client.get_stats()

    # 等待几秒钟
    await asyncio.sleep(5)

    # 清理
    await client.disconnect()
    listen_task.cancel()


async def main():
    """主函数 - 选择示例运行"""
    print("=" * 70)
    print("实时管道客户端示例")
    print("=" * 70)
    print("\n可用示例:")
    print("1. 基础监听 - 监听所有事件")
    print("2. 过滤监听 - 仅监听OpenAI高价值Key")
    print("3. 进度监控 - 扫描进度实时显示")
    print("4. 交互式客户端 - 支持命令操作")

    print("\n注意: 运行前需要先启动实时管道服务器")
    print("命令: python realtime_pipeline.py")

    # 这里默认运行示例4（交互式）
    # 实际使用时可以添加命令行参数选择
    await example_interactive()


if __name__ == "__main__":
    asyncio.run(main())
