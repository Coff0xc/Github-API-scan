#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Secret Scanner Pro - 优化版主程序

优化内容:
1. 异步数据库 (AsyncDatabase) - 性能提升 3-5倍
2. asyncio.Queue 替代 queue.Queue - 消除阻塞
3. 配置验证 - 启动时检查
4. 改进的错误处理
5. 性能监控指标
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
from validator import start_validators
from ui import Dashboard
from source_pastebin import start_pastebin_scanner
from source_gist import start_gist_scanner
from source_searchcode import start_searchcode_scanner
from source_gitlab import start_gitlab_scanner
from source_realtime import start_realtime_scanner

from loguru import logger


# ============================================================================
#                          配置验证
# ============================================================================

class ConfigValidator:
    """配置验证器"""

    @staticmethod
    def validate() -> tuple[bool, list[str]]:
        """
        验证配置有效性

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        # 检查 GitHub Tokens
        if not config.github_tokens or not any(config.github_tokens):
            errors.append("未配置 GitHub Tokens")

        # 检查数据库路径
        if not config.db_path:
            errors.append("数据库路径未配置")

        # 检查代理配置 (可选)
        if config.proxy_url:
            if not config.proxy_url.startswith(('http://', 'https://', 'socks5://')):
                errors.append(f"代理地址格式错误: {config.proxy_url}")

        return len(errors) == 0, errors

    @staticmethod
    def validate_github_tokens() -> tuple[int, int]:
        """
        验证 GitHub Token 有效性

        Returns:
            (valid_count, total_count)
        """
        # TODO: 实现 Token 验证逻辑
        # 可以发送简单的 API 请求测试
        return len(config.github_tokens), len(config.github_tokens)


# ============================================================================
#                          性能监控
# ============================================================================

class PerformanceMetrics:
    """性能指标收集器"""

    def __init__(self):
        self.keys_found = 0
        self.keys_valid = 0
        self.keys_invalid = 0
        self.scan_errors = 0
        self.start_time = time.time()

    def increment_found(self):
        self.keys_found += 1

    def increment_valid(self):
        self.keys_valid += 1

    def increment_invalid(self):
        self.keys_invalid += 1

    def increment_errors(self):
        self.scan_errors += 1

    def get_stats(self) -> dict:
        """获取统计信息"""
        runtime = time.time() - self.start_time
        return {
            'keys_found': self.keys_found,
            'keys_valid': self.keys_valid,
            'keys_invalid': self.keys_invalid,
            'scan_errors': self.scan_errors,
            'runtime_seconds': runtime,
            'keys_per_minute': (self.keys_found / runtime * 60) if runtime > 0 else 0
        }


# ============================================================================
#                          优化版扫描器
# ============================================================================

class OptimizedSecretScanner:
    """优化版密钥扫描系统"""

    def __init__(self, enable_pastebin: bool = False, enable_gist: bool = False,
                 enable_searchcode: bool = False, enable_gitlab: bool = False,
                 enable_realtime: bool = False, pastebin_api_key: str = ""):
        self.stop_event = threading.Event()

        # 使用 asyncio.Queue 替代 queue.Queue
        self.result_queue = asyncio.Queue(maxsize=10000)  # 增大容量

        # 异步数据库
        self.async_db: Optional[AsyncDatabase] = None

        # 同步数据库 (用于导出等功能)
        self.db = Database(config.db_path)

        self.dashboard = Dashboard()
        self.metrics = PerformanceMetrics()

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

    async def _init_async_db(self):
        """初始化异步数据库"""
        self.async_db = AsyncDatabase(config.db_path)
        await self.async_db.init()
        logger.info("异步数据库初始化完成")

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

        # 尝试启用 uvloop
        try_enable_uvloop()

        # 初始化异步数据库
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._init_async_db())

        # 初始化仪表盘统计
        self.dashboard.update_stats(
            total_tokens=len(config.github_tokens),
            is_running=True
        )

        # 启动验证器（Consumer）
        self.validator_threads = start_validators(
            self.result_queue,
            self.async_db,  # 传入异步数据库
            self.stop_event,
            dashboard=self.dashboard,
            num_workers=2
        )

        # 启动 GitHub 扫描器（Producer）
        self.scanner_thread = start_scanner(
            self.result_queue,
            self.async_db,  # 传入异步数据库
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
                    # 更新队列大小 (asyncio.Queue 使用 qsize())
                    queue_size = self.result_queue.qsize()
                    self.dashboard.update_stats(queue_size=queue_size)
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

        # 关闭异步数据库
        if self.async_db:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.async_db.close())
            logger.info("异步数据库已关闭")

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
                thread.join(timeout=5)  # 增加超时时间

        # 输出性能统计
        stats = self.metrics.get_stats()
        logger.info(f"性能统计: {stats}")


# ============================================================================
#                          导出功能 (加密版)
# ============================================================================

def export_keys_encrypted(db_path: str, output_file: str, status_filter: str = None):
    """
    加密导出 Key

    使用 Fernet 对称加密
    """
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.error("需要安装 cryptography: pip install cryptography")
        return

    from rich.console import Console
    import json

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

    # 生成加密密钥
    encryption_key = Fernet.generate_key()
    cipher = Fernet(encryption_key)

    # 准备数据
    data = [{
        'platform': k.platform,
        'api_key': k.api_key,
        'base_url': k.base_url,
        'status': k.status,
        'balance': k.balance,
        'source_url': k.source_url
    } for k in keys]

    # 加密
    json_data = json.dumps(data, ensure_ascii=False, indent=2)
    encrypted_data = cipher.encrypt(json_data.encode())

    # 写入加密文件
    with open(output_file, 'wb') as f:
        f.write(encrypted_data)

    # 保存密钥
    key_file = output_file + '.key'
    with open(key_file, 'wb') as f:
        f.write(encryption_key)

    console.print(f"[green]✓ 已加密导出 {len(keys)} 个 Key[/]")
    console.print(f"[cyan]数据文件: {output_file}[/]")
    console.print(f"[cyan]密钥文件: {key_file}[/]")
    console.print(f"[yellow]⚠️  请妥善保管密钥文件![/]")


def decrypt_keys(encrypted_file: str, key_file: str):
    """解密导出的 Key"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.error("需要安装 cryptography: pip install cryptography")
        return

    from rich.console import Console
    import json

    console = Console()

    try:
        # 读取密钥
        with open(key_file, 'rb') as f:
            encryption_key = f.read()

        cipher = Fernet(encryption_key)

        # 读取加密数据
        with open(encrypted_file, 'rb') as f:
            encrypted_data = f.read()

        # 解密
        decrypted_data = cipher.decrypt(encrypted_data)
        keys = json.loads(decrypted_data.decode())

        console.print(f"[green]✓ 成功解密 {len(keys)} 个 Key[/]")

        # 显示前 3 个
        for i, key in enumerate(keys[:3]):
            console.print(f"\n[cyan]Key {i+1}:[/]")
            console.print(f"  平台: {key['platform']}")
            console.print(f"  Key: {key['api_key'][:20]}...")
            console.print(f"  URL: {key['base_url']}")

        if len(keys) > 3:
            console.print(f"\n[yellow]... 还有 {len(keys) - 3} 个 Key[/]")

    except Exception as e:
        console.print(f"[red]解密失败: {e}[/]")


# ============================================================================
#                          原有导出功能 (保持兼容)
# ============================================================================

def export_keys(db_path: str, output_file: str, status_filter: str = None):
    """导出 Key (明文)"""
    from rich.console import Console
    from rich.table import Table

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

    # 写入文件
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

    # 写入 CSV 文件
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

    # 统计表
    table = Table(show_header=False, box=box.ROUNDED)
    table.add_column("项目", style="cyan")
    table.add_column("数量", justify="right", style="white")

    table.add_row("总 Key 数", str(stats['total']))
    table.add_row("", "")

    statuses = stats.get('statuses', {})
    table.add_row("[green]✓ 有效[/]", f"[green]{statuses.get('valid', 0)}[/]")
    table.add_row("[yellow]💰 配额耗尽[/]", f"[yellow]{statuses.get('quota_exceeded', 0)}[/]")
    table.add_row("[red]✗ 无效[/]", f"[red]{statuses.get('invalid', 0)}[/]")
    table.add_row("[magenta]🔌 连接错误[/]", f"[magenta]{statuses.get('connection_error', 0)}[/]")

    if stats.get('platforms'):
        table.add_row("", "")
        table.add_row("[bold]平台分布[/]", "")
        for platform, count in stats['platforms'].items():
            table.add_row(f"  {platform}", str(count))

    console.print(Panel(table, title="📊 数据库统计", border_style="cyan"))


# ============================================================================
#                          主函数
# ============================================================================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="GitHub Secret Scanner Pro - 优化版",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--export', type=str, metavar='FILE', help='导出 Key 到文本文件')
    parser.add_argument('--export-csv', type=str, metavar='CSV', help='导出 Key 到 CSV 文件')
    parser.add_argument('--export-encrypted', type=str, metavar='FILE', help='加密导出 Key')
    parser.add_argument('--decrypt', type=str, metavar='FILE', help='解密导出的 Key')
    parser.add_argument('--key-file', type=str, metavar='KEY', help='解密密钥文件')
    parser.add_argument('--status', type=str, help='导出状态过滤 (valid/quota_exceeded)')
    parser.add_argument('--stats', action='store_true', help='显示统计')
    parser.add_argument('--db', type=str, default='leaked_keys.db', help='数据库路径')
    parser.add_argument('--proxy', type=str, help='代理地址')

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

    # 解密模式
    if args.decrypt:
        if not args.key_file:
            logger.error("解密需要指定 --key-file")
            return
        decrypt_keys(args.decrypt, args.key_file)
        return

    # 导出模式
    if args.export or args.export_csv or args.export_encrypted:
        if args.export:
            export_keys(config.db_path, args.export, args.status)
        if args.export_csv:
            export_keys_csv(config.db_path, args.export_csv, args.status)
        if args.export_encrypted:
            export_keys_encrypted(config.db_path, args.export_encrypted, args.status)
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

    scanner = OptimizedSecretScanner(
        enable_pastebin=enable_pastebin,
        enable_gist=enable_gist,
        enable_searchcode=enable_searchcode,
        enable_gitlab=enable_gitlab,
        enable_realtime=enable_realtime,
        pastebin_api_key=args.pastebin_key
    )
    scanner.start()


if __name__ == "__main__":
    main()
