#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Secret Scanner Pro - v2.2 智能缓存版主程序

v2.2 新特性：
1. 智能缓存系统 - 3层缓存架构，减少重复验证 30-50%
2. 批量验证支持 - 按域名分组，降低网络开销 20-30%
3. 域名健康度追踪 - 避免验证死域名，提升效率

v2.1 优化（保留）：
1. 连接池管理 - 复用 HTTP 连接
2. 智能重试机制 - 指数退避
3. 动态队列管理 - 根据内存压力自动调整
4. 性能监控系统 - 实时延迟和吞吐量统计

基于 v2.0 优化：
- 异步数据库 (AsyncDatabase) - 性能提升 3-5倍
- asyncio.Queue 替代 queue.Queue - 消除阻塞
- 配置验证 - 启动时检查
"""

import sys
import signal
import asyncio
import threading
import time
import argparse
import csv
from datetime import datetime
from typing import Optional

from config import config
from database import Database, KeyStatus
from async_database import AsyncDatabase, try_enable_uvloop
from scanner import start_scanner
from ui import Dashboard
from source_pastebin import start_pastebin_scanner
from source_gist import start_gist_scanner
from source_searchcode import start_searchcode_scanner
from source_gitlab import start_gitlab_scanner
from source_realtime import start_realtime_scanner

# v2.1 优化模块
from performance_monitor import get_monitor
from connection_pool import get_connection_pool, close_connection_pool
from queue_manager import create_queue

# v2.2 新增模块
from cache_manager import get_cache_manager, close_cache_manager, CacheConfig
from batch_validator import BatchConfig

from loguru import logger


# ============================================================================
#                          配置验证
# ============================================================================

class ConfigValidator:
    """配置验证器"""

    @staticmethod
    def validate() -> tuple[bool, list[str]]:
        """验证配置有效性"""
        errors = []

        if not config.github_tokens or not any(config.github_tokens):
            errors.append("未配置 GitHub Tokens")

        if not config.db_path:
            errors.append("数据库路径未配置")

        if config.proxy_url:
            if not config.proxy_url.startswith(('http://', 'https://', 'socks5://')):
                errors.append(f"代理地址格式错误: {config.proxy_url}")

        return len(errors) == 0, errors


# ============================================================================
#                          v2.2 智能缓存版扫描器
# ============================================================================

class OptimizedSecretScannerV22:
    """v2.2 智能缓存版密钥扫描系统"""

    def __init__(self, enable_pastebin: bool = False, enable_gist: bool = False,
                 enable_searchcode: bool = False, enable_gitlab: bool = False,
                 enable_realtime: bool = False, pastebin_api_key: str = "",
                 enable_performance_monitor: bool = True,
                 enable_cache: bool = True):
        self.stop_event = threading.Event()

        # 使用动态队列（v2.1）
        self.result_queue = None  # 将在 start() 中初始化
        self.use_dynamic_queue = True

        # 异步数据库
        self.async_db: Optional[AsyncDatabase] = None

        # 同步数据库
        self.db = Database(config.db_path)

        self.dashboard = Dashboard()

        # v2.1 性能监控
        self.performance_monitor = None
        self.enable_performance_monitor = enable_performance_monitor

        # v2.2 缓存管理
        self.cache_manager = None
        self.enable_cache = enable_cache

        self.scanner_thread = None
        self.validator_threads = []
        self.pastebin_thread = None
        self.gist_thread = None
        self.searchcode_thread = None
        self.gitlab_thread = None
        self.realtime_thread = None

        # 扫描源开关
        self.enable_pastebin = enable_pastebin
        self.enable_gist = enable_gist
        self.enable_searchcode = enable_searchcode
        self.enable_gitlab = enable_gitlab
        self.enable_realtime = enable_realtime
        self.pastebin_api_key = pastebin_api_key

        # 信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """信号处理"""
        self.stop()

    async def _init_async_resources(self):
        """初始化异步资源"""
        # 初始化异步数据库
        self.async_db = AsyncDatabase(config.db_path)
        await self.async_db.init()
        logger.info("异步数据库初始化完成")

        # 初始化连接池（v2.1）
        pool = await get_connection_pool()
        logger.info(f"连接池初始化完成 (最大连接: {pool.config.max_connections})")

        # v2.2: 初始化缓存管理器
        if self.enable_cache:
            self.cache_manager = await get_cache_manager(CacheConfig(
                validation_ttl=3600.0,  # 1小时
                domain_health_ttl=1800.0,  # 30分钟
                key_fingerprint_ttl=86400.0  # 24小时
            ))
            logger.info("缓存管理器已启动")

        # 初始化性能监控（v2.1）
        if self.enable_performance_monitor:
            self.performance_monitor = get_monitor()
            await self.performance_monitor.start()
            logger.info("性能监控已启动")

        # 初始化动态队列（v2.1）
        if self.use_dynamic_queue:
            self.result_queue = create_queue(
                initial_size=1000,
                auto_adjust=True,
                memory_threshold=80.0
            )
            await self.result_queue.start()
            logger.info("动态队列已启动 (初始大小: 1000)")
        else:
            self.result_queue = asyncio.Queue(maxsize=10000)

    def start(self):
        """启动扫描系统"""
        # 配置验证
        is_valid, errors = ConfigValidator.validate()
        if not is_valid:
            logger.error("配置验证失败:")
            for error in errors:
                logger.error(f"  - {error}")
            sys.exit(1)

        logger.info("配置验证通过")
        logger.info("=" * 60)
        logger.info("GitHub Secret Scanner Pro v2.2")
        logger.info("=" * 60)

        # 尝试启用 uvloop
        try_enable_uvloop()

        # 初始化异步资源
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._init_async_resources())

        # 初始化仪表盘统计
        self.dashboard.update_stats(
            total_tokens=len(config.github_tokens),
            is_running=True
        )

        # 启动验证器（v2.2: 使用优化版验证器）
        from validator_async import start_validators
        self.validator_threads = start_validators(
            self.result_queue,
            self.async_db,
            self.stop_event,
            dashboard=self.dashboard,
            num_workers=2,
            # v2.2: 传递缓存和批量验证配置
            cache_config=CacheConfig() if self.enable_cache else None,
            batch_config=BatchConfig()
        )

        # 启动 GitHub 扫描器
        self.scanner_thread = start_scanner(
            self.result_queue,
            self.async_db,
            self.stop_event,
            dashboard=self.dashboard
        )

        # 启动其他扫描源
        if self.enable_pastebin:
            self.pastebin_thread = start_pastebin_scanner(
                self.result_queue,
                self.stop_event,
                dashboard=self.dashboard,
                api_key=self.pastebin_api_key
            )
            self.dashboard.add_log("[Pastebin] 扫描源已启用", "INFO")

        if self.enable_gist:
            self.gist_thread = start_gist_scanner(
                self.result_queue,
                self.stop_event,
                dashboard=self.dashboard
            )
            self.dashboard.add_log("[Gist] 扫描源已启用", "INFO")

        if self.enable_searchcode:
            self.searchcode_thread = start_searchcode_scanner(
                self.result_queue,
                self.stop_event,
                dashboard=self.dashboard
            )
            self.dashboard.add_log("[SearchCode] 扫描源已启用", "INFO")

        if self.enable_gitlab:
            self.gitlab_thread = start_gitlab_scanner(
                self.result_queue,
                self.stop_event,
                dashboard=self.dashboard
            )
            self.dashboard.add_log("[GitLab] 扫描源已启用", "INFO")

        if self.enable_realtime:
            self.realtime_thread = start_realtime_scanner(
                self.result_queue,
                self.stop_event,
                dashboard=self.dashboard
            )
            self.dashboard.add_log("[Realtime] 实时监控已启用", "INFO")

        # 启动 TUI
        with self.dashboard.start():
            try:
                while not self.stop_event.is_set():
                    # 更新队列大小
                    if self.use_dynamic_queue:
                        queue_size = self.result_queue.qsize()
                    else:
                        queue_size = self.result_queue.qsize()

                    self.dashboard.update_stats(queue_size=queue_size)

                    # v2.1: 更新性能监控统计
                    if self.performance_monitor:
                        stats = self.performance_monitor.get_validation_stats()
                        if stats['total'] > 0:
                            self.dashboard.add_log(
                                f"[Monitor] 验证: {stats['total']} | "
                                f"成功率: {stats['success_rate']:.1f}% | "
                                f"延迟P95: {stats['latency']['p95_ms']:.1f}ms",
                                "INFO"
                            )

                    # v2.2: 更新缓存统计
                    if self.cache_manager:
                        cache_stats = self.cache_manager.get_stats()
                        validation_stats = cache_stats.get('validation', {})
                        if validation_stats.get('hits', 0) + validation_stats.get('misses', 0) > 0:
                            self.dashboard.add_log(
                                f"[Cache] 命中率: {validation_stats.get('hit_rate', 0):.1f}% | "
                                f"大小: {validation_stats.get('size', 0)}",
                                "INFO"
                            )

                    self.dashboard.refresh()
                    time.sleep(0.25)
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()

    def stop(self):
        """停止系统"""
        if self.stop_event.is_set():
            return

        logger.info("正在停止扫描系统...")
        self.dashboard.stop()
        self.stop_event.set()

        # 获取事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 关闭异步资源
        async def cleanup():
            # v2.2: 打印缓存报告
            if self.cache_manager:
                logger.info("=" * 60)
                logger.info("缓存统计报告")
                logger.info("=" * 60)
                stats = self.cache_manager.get_stats()
                logger.info(f"验证缓存命中率: {stats['validation']['hit_rate']:.1f}%")
                logger.info(f"域名健康追踪: {stats['domain_health']['size']} 个")
                logger.info(f"死域名数量: {stats['domain_health']['dead']}")

            # v2.1: 打印性能报告
            if self.performance_monitor:
                logger.info("=" * 60)
                logger.info("性能监控报告")
                logger.info("=" * 60)
                self.performance_monitor.print_report()
                await self.performance_monitor.stop()

            # 关闭动态队列
            if self.use_dynamic_queue and self.result_queue:
                await self.result_queue.stop()
                logger.info("动态队列已关闭")

            # v2.2: 关闭缓存管理器
            if self.enable_cache:
                await close_cache_manager()
                logger.info("缓存管理器已关闭")

            # 关闭连接池
            await close_connection_pool()
            logger.info("连接池已关闭")

            # 关闭异步数据库
            if self.async_db:
                await self.async_db.close()
                logger.info("异步数据库已关闭")

        loop.run_until_complete(cleanup())

        # 等待线程结束
        threads = [
            self.scanner_thread,
            self.pastebin_thread,
            self.gist_thread,
            self.searchcode_thread,
            self.gitlab_thread,
            self.realtime_thread
        ] + self.validator_threads

        for thread in threads:
            if thread and thread.is_alive():
                thread.join(timeout=5)

        logger.info("扫描系统已停止")


# ============================================================================
#                          导出功能（保持兼容）
# ============================================================================

def export_keys(db_path: str, output_file: str, status_filter: str = None):
    """导出 Key (明文)"""
    from rich.console import Console

    console = Console()
    db = Database(db_path)

    if status_filter:
        try:
            status = KeyStatus(status_filter)
            keys = db.get_keys_by_status(status)
        except ValueError:
            console.print(f"[red]无效状态: {status_filter}[/]")
            return
    else:
        keys = db.get_valid_keys()

    if not keys:
        console.print("[yellow]没有符合条件的 Key[/]")
        return

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# GitHub Secret Scanner 导出结果\n")
        f.write(f"# 时间: {datetime.now().isoformat()}\n")
        f.write(f"# 数量: {len(keys)}\n")
        f.write("=" * 60 + "\n\n")

        for key in keys:
            f.write(f"平台: {key.platform}\n")
            f.write(f"状态: {key.status}\n")
            f.write(f"Key: {key.api_key}\n")
            f.write(f"URL: {key.base_url}\n")
            f.write(f"信息: {key.balance}\n")
            f.write(f"来源: {key.source_url}\n")
            f.write("-" * 40 + "\n\n")

    console.print(f"[green]✓ 已导出 {len(keys)} 个 Key 到 {output_file}[/]")


def export_keys_csv(db_path: str, output_file: str, status_filter: str = None):
    """导出 Key 到 CSV 文件"""
    from rich.console import Console

    console = Console()
    db = Database(db_path)

    if status_filter:
        try:
            status = KeyStatus(status_filter)
            keys = db.get_keys_by_status(status)
        except ValueError:
            console.print(f"[red]无效状态: {status_filter}[/]")
            return
    else:
        keys = db.get_valid_keys()

    if not keys:
        console.print("[yellow]没有符合条件的 Key[/]")
        return

    fieldnames = [
        "id", "platform", "status", "api_key", "base_url", "balance",
        "source_url", "model_tier", "rpm", "is_high_value", "found_time",
    ]

    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key in keys:
            writer.writerow({
                "id": getattr(key, "id", ""),
                "platform": key.platform,
                "status": key.status,
                "api_key": key.api_key,
                "base_url": key.base_url,
                "balance": key.balance,
                "source_url": key.source_url,
                "model_tier": key.model_tier,
                "rpm": key.rpm,
                "is_high_value": int(bool(getattr(key, "is_high_value", False))),
                "found_time": key.found_time.isoformat() if getattr(key, "found_time", None) else "",
            })

    console.print(f"[green]✓ 已导出 {len(keys)} 个 Key 到 CSV: {output_file}[/]")


def show_stats(db_path: str):
    """显示统计"""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    console = Console()
    db = Database(db_path)
    stats = db.get_stats()

    table = Table(show_header=False, box=box.ROUNDED)
    table.add_column("项目", style="cyan")
    table.add_column("数量", justify="right", style="white")

    table.add_row("总 Key 数", str(stats['total']))
    table.add_row("", "")

    statuses = stats.get('statuses', {})
    table.add_row("[green]有效[/]", f"[green]{statuses.get('valid', 0)}[/]")
    table.add_row("[yellow]配额耗尽[/]", f"[yellow]{statuses.get('quota_exceeded', 0)}[/]")
    table.add_row("[red]无效[/]", f"[red]{statuses.get('invalid', 0)}[/]")
    table.add_row("[magenta]连接错误[/]", f"[magenta]{statuses.get('connection_error', 0)}[/]")

    if stats.get('platforms'):
        table.add_row("", "")
        table.add_row("[bold]平台分布[/]", "")
        for platform, count in stats['platforms'].items():
            table.add_row(f"  {platform}", str(count))

    console.print(Panel(table, title="数据库统计", border_style="cyan"))


# ============================================================================
#                          主函数
# ============================================================================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="GitHub Secret Scanner Pro v2.2 - 智能缓存版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
v2.2 新特性:
  - 智能缓存: 3层缓存架构，减少重复验证 30-50%
  - 批量验证: 按域名分组，降低网络开销 20-30%
  - 域名健康度: 避免验证死域名，提升效率

v2.1 优化（保留）:
  - 连接池管理: 复用 HTTP 连接，减少开销
  - 智能重试: 指数退避，提高成功率
  - 动态队列: 根据内存压力自动调整
  - 性能监控: 实时延迟和吞吐量统计
        """
    )

    parser.add_argument('--export', type=str, metavar='FILE', help='导出 Key 到文本文件')
    parser.add_argument('--export-csv', type=str, metavar='CSV', help='导出 Key 到 CSV 文件')
    parser.add_argument('--status', type=str, help='导出状态过滤 (valid/quota_exceeded)')
    parser.add_argument('--stats', action='store_true', help='显示统计')
    parser.add_argument('--db', type=str, default='leaked_keys.db', help='数据库路径')
    parser.add_argument('--proxy', type=str, help='代理地址')

    # v2.1 优化选项
    parser.add_argument('--no-monitor', action='store_true', help='禁用性能监控')
    parser.add_argument('--no-dynamic-queue', action='store_true', help='禁用动态队列')

    # v2.2 新增选项
    parser.add_argument('--no-cache', action='store_true', help='禁用智能缓存')

    # 扫描源选项
    parser.add_argument('--pastebin', action='store_true', help='启用 Pastebin 扫描源')
    parser.add_argument('--pastebin-key', type=str, default='', help='Pastebin Pro API Key')
    parser.add_argument('--gist', action='store_true', help='启用 GitHub Gist 扫描源')
    parser.add_argument('--searchcode', action='store_true', help='启用 SearchCode 扫描源')
    parser.add_argument('--gitlab', action='store_true', help='启用 GitLab Snippets 扫描源')
    parser.add_argument('--realtime', action='store_true', help='启用实时监控 (GitHub Events)')
    parser.add_argument('--all-sources', action='store_true', help='启用所有扫描源')

    args = parser.parse_args()

    if args.proxy:
        config.proxy_url = args.proxy
    if args.db:
        config.db_path = args.db

    # 导出模式
    if args.export or args.export_csv:
        if args.export:
            export_keys(config.db_path, args.export, args.status)
        if args.export_csv:
            export_keys_csv(config.db_path, args.export_csv, args.status)
        return

    # 统计模式
    if args.stats:
        show_stats(config.db_path)
        return

    # 扫描模式
    enable_pastebin = args.pastebin or args.all_sources
    enable_gist = args.gist or args.all_sources
    enable_searchcode = args.searchcode or args.all_sources
    enable_gitlab = args.gitlab or args.all_sources
    enable_realtime = args.realtime or args.all_sources

    scanner = OptimizedSecretScannerV22(
        enable_pastebin=enable_pastebin,
        enable_gist=enable_gist,
        enable_searchcode=enable_searchcode,
        enable_gitlab=enable_gitlab,
        enable_realtime=enable_realtime,
        pastebin_api_key=args.pastebin_key,
        enable_performance_monitor=not args.no_monitor,
        enable_cache=not args.no_cache
    )

    # 应用动态队列设置
    if args.no_dynamic_queue:
        scanner.use_dynamic_queue = False
        logger.info("动态队列已禁用")

    scanner.start()


if __name__ == "__main__":
    main()
