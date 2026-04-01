"""
异步验证器适配器 - 支持 AsyncDatabase

核心改进:
1. 完全异步化,消除阻塞
2. 使用 asyncio.Queue
3. 批量数据库操作
4. 改进的错误处理
"""

import asyncio
from typing import Optional
from loguru import logger

from validator import (
    validate_key_async,
    CircuitBreaker,
    MAX_CONCURRENCY
)
from async_database import AsyncDatabase
from database import LeakedKey, KeyStatus


async def async_validator_worker(
    result_queue: asyncio.Queue,
    async_db: AsyncDatabase,
    stop_event,
    dashboard=None,
    worker_id: int = 0
):
    """
    异步验证器工作线程

    Args:
        result_queue: asyncio.Queue 结果队列
        async_db: AsyncDatabase 异步数据库
        stop_event: threading.Event 停止信号
        dashboard: Dashboard UI实例
        worker_id: 工作线程ID
    """
    circuit_breaker = CircuitBreaker()
    processed_count = 0

    logger.info(f"[Validator-{worker_id}] 异步验证器启动")

    try:
        while not stop_event.is_set():
            try:
                # 使用 asyncio.wait_for 避免永久阻塞
                key = await asyncio.wait_for(
                    result_queue.get(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[Validator-{worker_id}] 队列读取错误: {e}")
                continue

            try:
                # 检查是否已存在
                if await async_db.key_exists(key.api_key):
                    logger.debug(f"[Validator-{worker_id}] Key 已存在,跳过: {key.api_key[:20]}...")
                    continue

                # 先插入数据库 (状态为 pending)
                await async_db.queue_insert(key)

                # 异步验证
                status, balance, model_tier, rpm, is_high_value = await validate_key_async(
                    key.platform,
                    key.api_key,
                    key.base_url,
                    circuit_breaker=circuit_breaker
                )

                # 更新状态
                await async_db.update_key_status(
                    key.api_key,
                    status,
                    balance,
                    model_tier,
                    rpm,
                    is_high_value
                )

                processed_count += 1

                # 更新 UI
                if dashboard:
                    if status == KeyStatus.VALID:
                        dashboard.increment_valid()
                        dashboard.add_log(
                            f"[✓] {key.platform} | {balance} | {key.api_key[:20]}...",
                            "SUCCESS"
                        )
                    elif status == KeyStatus.QUOTA_EXCEEDED:
                        dashboard.increment_quota_exceeded()
                        dashboard.add_log(
                            f"[💰] {key.platform} | 配额耗尽 | {key.api_key[:20]}...",
                            "WARNING"
                        )
                    elif status == KeyStatus.INVALID:
                        dashboard.increment_invalid()
                    elif status == KeyStatus.CONNECTION_ERROR:
                        dashboard.increment_connection_error()

                # 每处理 10 个 Key 输出一次统计
                if processed_count % 10 == 0:
                    logger.info(f"[Validator-{worker_id}] 已处理 {processed_count} 个 Key")

            except Exception as e:
                logger.error(f"[Validator-{worker_id}] 验证异常: {e}")
                if dashboard:
                    dashboard.add_log(f"[✗] 验证错误: {str(e)[:50]}", "ERROR")

    except asyncio.CancelledError:
        logger.info(f"[Validator-{worker_id}] 收到取消信号")
    finally:
        logger.info(f"[Validator-{worker_id}] 验证器停止,共处理 {processed_count} 个 Key")


def start_async_validators(
    result_queue: asyncio.Queue,
    async_db: AsyncDatabase,
    stop_event,
    dashboard=None,
    num_workers: int = 2
):
    """
    启动异步验证器

    Args:
        result_queue: asyncio.Queue
        async_db: AsyncDatabase
        stop_event: threading.Event
        dashboard: Dashboard
        num_workers: 工作线程数

    Returns:
        List[asyncio.Task]
    """
    import threading

    tasks = []

    def run_async_workers():
        """在新线程中运行异步工作器"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 创建工作任务
        worker_tasks = []
        for i in range(num_workers):
            task = loop.create_task(
                async_validator_worker(
                    result_queue,
                    async_db,
                    stop_event,
                    dashboard,
                    worker_id=i
                )
            )
            worker_tasks.append(task)

        # 运行直到停止
        try:
            loop.run_until_complete(asyncio.gather(*worker_tasks))
        except Exception as e:
            logger.error(f"验证器异常: {e}")
        finally:
            loop.close()

    # 启动线程
    thread = threading.Thread(target=run_async_workers, daemon=True)
    thread.start()

    return [thread]
