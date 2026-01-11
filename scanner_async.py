"""
异步扫描器适配器 - 支持 AsyncDatabase

核心改进:
1. 使用 asyncio.Queue
2. 异步数据库去重
3. 批量操作优化
"""

import asyncio
import threading
from loguru import logger

from scanner import (
    scan_github_code,
    extract_keys_from_content,
    should_skip_file
)
from async_database import AsyncDatabase
from database import LeakedKey
from config import config


async def async_scanner_worker(
    result_queue: asyncio.Queue,
    async_db: AsyncDatabase,
    stop_event,
    dashboard=None
):
    """
    异步扫描器工作线程

    Args:
        result_queue: asyncio.Queue 结果队列
        async_db: AsyncDatabase 异步数据库
        stop_event: threading.Event 停止信号
        dashboard: Dashboard UI实例
    """
    logger.info("[Scanner] 异步扫描器启动")

    scanned_count = 0
    found_count = 0

    try:
        # 使用 GitHub API 扫描
        for keyword in config.search_keywords:
            if stop_event.is_set():
                break

            try:
                # 扫描 GitHub (这部分仍然是同步的,因为 PyGithub 不支持异步)
                results = scan_github_code(keyword, dashboard)

                for file_info in results:
                    if stop_event.is_set():
                        break

                    # 检查文件是否应该跳过
                    should_skip, reason = should_skip_file(
                        file_info.get('path', ''),
                        file_info.get('size', 0)
                    )
                    if should_skip:
                        logger.debug(f"跳过文件: {reason}")
                        continue

                    # 检查是否已扫描 (异步)
                    file_sha = file_info.get('sha', '')
                    if file_sha and await async_db.is_blob_scanned(file_sha):
                        logger.debug(f"文件已扫描: {file_sha[:8]}")
                        continue

                    # 提取 Key
                    content = file_info.get('content', '')
                    keys = extract_keys_from_content(
                        content,
                        file_info.get('path', ''),
                        file_info.get('html_url', '')
                    )

                    # 标记为已扫描
                    if file_sha:
                        await async_db.mark_blob_scanned(file_sha)

                    scanned_count += 1

                    # 将 Key 放入队列
                    for key in keys:
                        # 异步检查是否已存在
                        if not await async_db.key_exists(key.api_key):
                            await result_queue.put(key)
                            found_count += 1

                            if dashboard:
                                dashboard.increment_found()
                                dashboard.add_log(
                                    f"[+] {key.platform} | {key.api_key[:20]}...",
                                    "INFO"
                                )

                    # 每扫描 10 个文件输出一次统计
                    if scanned_count % 10 == 0:
                        logger.info(f"[Scanner] 已扫描 {scanned_count} 个文件, 发现 {found_count} 个 Key")

            except Exception as e:
                logger.error(f"[Scanner] 扫描关键词 '{keyword}' 时出错: {e}")
                if dashboard:
                    dashboard.add_log(f"[✗] 扫描错误: {str(e)[:50]}", "ERROR")

    except asyncio.CancelledError:
        logger.info("[Scanner] 收到取消信号")
    finally:
        logger.info(f"[Scanner] 扫描器停止, 共扫描 {scanned_count} 个文件, 发现 {found_count} 个 Key")


def start_async_scanner(
    result_queue: asyncio.Queue,
    async_db: AsyncDatabase,
    stop_event,
    dashboard=None
):
    """
    启动异步扫描器

    Args:
        result_queue: asyncio.Queue
        async_db: AsyncDatabase
        stop_event: threading.Event
        dashboard: Dashboard

    Returns:
        threading.Thread
    """

    def run_async_scanner():
        """在新线程中运行异步扫描器"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(
                async_scanner_worker(
                    result_queue,
                    async_db,
                    stop_event,
                    dashboard
                )
            )
        except Exception as e:
            logger.error(f"扫描器异常: {e}")
        finally:
            loop.close()

    # 启动线程
    thread = threading.Thread(target=run_async_scanner, daemon=True)
    thread.start()

    return thread
