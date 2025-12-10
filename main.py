#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Secret Scanner Pro - 主程序入口

================================================================================
                              ⚠️ 免责声明 ⚠️
================================================================================
本项目仅用于安全研究和授权测试，严禁用于非法扫描。
使用者需自行承担法律责任。
================================================================================

特性：
- Rich TUI 仪表盘实时显示
- 熵值过滤 + 域名黑名单
- AsyncIO + aiohttp 高并发验证 (100 并发)
- aiohttp 异步批量下载文件
- 深度价值评估 (GPT-4 探测、余额检测、RPM 透视)
- Producer-Consumer 架构
"""

import sys
import signal
import queue
import threading
import time
import argparse
import csv
from datetime import datetime

from config import config
from database import Database, KeyStatus
from scanner import start_scanner
from validator import start_validators
from ui import Dashboard


class SecretScanner:
    """密钥扫描系统主类"""
    
    def __init__(self):
        self.stop_event = threading.Event()
        self.result_queue = queue.Queue(maxsize=1000)
        self.db = Database(config.db_path)
        self.dashboard = Dashboard()
        
        self.scanner_thread = None
        self.validator_threads = []
        
        # 信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理"""
        self.stop()
    
    def start(self):
        """启动扫描系统"""
        # 初始化仪表盘统计
        self.dashboard.update_stats(
            total_tokens=len(config.github_tokens),
            is_running=True
        )
        
        # 启动验证器（Consumer）
        # 注意：每个线程内部使用 asyncio + aiohttp，实现 100 并发
        # 因此只需 1-2 个线程即可达到极高吞吐
        self.validator_threads = start_validators(
            self.result_queue,
            self.db,
            self.stop_event,
            dashboard=self.dashboard,
            num_workers=2  # 2 线程 x 100 并发 = 200 并发验证
        )
        
        # 启动扫描器（Producer）
        self.scanner_thread = start_scanner(
            self.result_queue,
            self.db,
            self.stop_event,
            dashboard=self.dashboard
        )
        
        # 启动 TUI
        with self.dashboard.start():
            try:
                while not self.stop_event.is_set():
                    # 更新队列大小
                    self.dashboard.update_stats(queue_size=self.result_queue.qsize())
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
        
        self.dashboard.stop()
        self.stop_event.set()
        
        if self.scanner_thread and self.scanner_thread.is_alive():
            self.scanner_thread.join(timeout=3)
        
        for thread in self.validator_threads:
            if thread.is_alive():
                thread.join(timeout=1)


def export_keys(db_path: str, output_file: str, status_filter: str = None):
    """导出 Key"""
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
        "id",
        "platform",
        "status",
        "api_key",
        "base_url",
        "balance",
        "source_url",
        "model_tier",
        "rpm",
        "is_high_value",
        "found_time",
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


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="GitHub Secret Scanner Pro",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--export', type=str, metavar='FILE', help='导出 Key 到文本文件')
    parser.add_argument('--export-csv', type=str, metavar='CSV', help='导出 Key 到 CSV 文件')
    parser.add_argument('--status', type=str, help='导出状态过滤 (valid/quota_exceeded)')
    parser.add_argument('--stats', action='store_true', help='显示统计')
    parser.add_argument('--db', type=str, default='leaked_keys.db', help='数据库路径')
    parser.add_argument('--proxy', type=str, help='代理地址')
    
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
    scanner = SecretScanner()
    scanner.start()


if __name__ == "__main__":
    main()
