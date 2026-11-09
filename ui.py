"""
UI 模块 - Rich TUI 仪表盘

使用 rich 库构建实时刷新的终端界面：
- Header: 状态栏
- Stats Panel: 统计数据
- Live Table: 发现记录（平台、脱敏预览、状态、位置）
- Log Panel: 实时日志
- Footer: 进度条
"""

import threading
from datetime import datetime
from typing import List, Dict, Deque
from collections import deque
from dataclasses import dataclass, field

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.style import Style
from rich import box

from config import config


# ============================================================================
#                              数据模型
# ============================================================================

@dataclass
class DashboardStats:
    """仪表盘统计数据"""
    total_scanned: int = 0          # 总扫描文件数
    total_keys_found: int = 0       # 发现的 Key 总数
    valid_keys: int = 0             # 有效 Key 数
    invalid_keys: int = 0           # 无效 Key 数
    quota_exceeded: int = 0         # 配额耗尽数
    connection_errors: int = 0      # 连接错误数
    queue_size: int = 0             # 队列大小
    skipped_low_entropy: int = 0    # 低熵值跳过数
    skipped_blacklist: int = 0      # 黑名单跳过数
    current_keyword: str = ""       # 当前搜索关键词
    current_token_index: int = 0    # 当前 Token 索引
    total_tokens: int = 0           # Token 总数
    is_running: bool = True         # 是否运行中


@dataclass
class ValidKeyRecord:
    """终端里的一条发现。balance 和 is_high_value 仍接受旧调用，但不展示。"""
    platform: str
    masked_key: str
    source: str
    found_time: str
    status: str = "valid"
    balance: str = ""
    is_high_value: bool = False

    @property
    def platform_color(self) -> str:
        colors = {
            "openai": "green",
            "azure": "blue",
            "anthropic": "magenta",
            "gemini": "cyan",
            "relay": "yellow",
        }
        return colors.get(self.platform.lower(), "white")


# ============================================================================
#                              仪表盘类
# ============================================================================

class Dashboard:
    """
    Rich TUI 仪表盘
    
    布局：
    ┌─────────────────────────────────────────────┐
    │                   Header                     │
    ├─────────────────────────────────────────────┤
    │    Stats Panel    │      Log Panel          │
    ├─────────────────────────────────────────────┤
    │              Findings                         │
    ├─────────────────────────────────────────────┤
    │                   Footer                     │
    └─────────────────────────────────────────────┘
    """
    
    def __init__(self):
        self.console = Console()
        self.stats = DashboardStats()
        self.valid_keys: List[ValidKeyRecord] = []
        self.logs: Deque[str] = deque(maxlen=15)  # 保留最新 15 条日志
        self._lock = threading.Lock()
        self._live: Live = None
        
    def _create_layout(self) -> Layout:
        """创建布局"""
        layout = Layout()
        
        layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3),
        )
        
        layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=2),
        )
        
        layout["left"].split(
            Layout(name="stats", ratio=1),
        )
        
        layout["right"].split(
            Layout(name="logs", size=10),
            Layout(name="table", ratio=1),
        )
        
        return layout
    
    def _render_header(self) -> Panel:
        """渲染头部状态栏"""
        header_text = Text()
        
        # 状态
        header_text.append("状态: ", style="white")
        if self.stats.is_running:
            header_text.append("运行中", style="bold green")
        else:
            header_text.append("已停止", style="bold red")
        
        header_text.append("  │ Tokens: ", style="white")
        header_text.append(str(self.stats.current_token_index + 1), style="bold cyan")
        header_text.append("/", style="white")
        header_text.append(str(self.stats.total_tokens), style="white")
        
        header_text.append("  │ 代理: ", style="white")
        if config.proxy_url:
            header_text.append(config.proxy_url, style="bold cyan")
        else:
            header_text.append("直连模式", style="bold yellow")
        
        return Panel(
            header_text,
            title="AI API Key Scanner",
            title_align="center",
            border_style="cyan",
            box=box.ROUNDED,
        )
    
    def _render_stats(self) -> Panel:
        """渲染统计面板"""
        stats_table = Table(show_header=False, box=None, padding=(0, 1))
        stats_table.add_column("Label", style="white")
        stats_table.add_column("Value", justify="right")
        
        stats_table.add_row(
            Text("📁 扫描文件", style="white"),
            Text(f"{self.stats.total_scanned:,}", style="cyan")
        )
        stats_table.add_row(
            Text("🔑 发现 Key", style="white"),
            Text(f"{self.stats.total_keys_found:,}", style="yellow")
        )
        stats_table.add_row(
            Text("✅ 有效命中", style="bold white"),
            Text(f"{self.stats.valid_keys:,}", style="bold green")
        )
        stats_table.add_row(
            Text("❌ 无效", style="white"),
            Text(f"{self.stats.invalid_keys:,}", style="red")
        )
        stats_table.add_row(
            Text("⚠ 配额耗尽", style="white"),
            Text(f"{self.stats.quota_exceeded:,}", style="yellow")
        )
        stats_table.add_row(
            Text("🔌 连接错误", style="white"),
            Text(f"{self.stats.connection_errors:,}", style="magenta")
        )
        stats_table.add_row("", "")
        stats_table.add_row(
            Text("📤 待验证", style="dim"),
            Text(f"{self.stats.queue_size:,}", style="blue")
        )
        stats_table.add_row(
            Text("⏭️ 低熵跳过", style="dim"),
            Text(f"{self.stats.skipped_low_entropy:,}", style="dim")
        )
        stats_table.add_row(
            Text("🚫 黑名单", style="dim"),
            Text(f"{self.stats.skipped_blacklist:,}", style="dim")
        )
        
        return Panel(
            stats_table,
            title="📊 统计数据",
            border_style="white",
            box=box.ROUNDED,
        )
    
    def _render_logs(self) -> Panel:
        """渲染日志面板"""
        from rich.text import Text as RichText
        
        log_text = RichText()
        
        for log_entry in list(self.logs):
            # 解析日志条目
            log_text.append_text(RichText.from_markup(log_entry + "\n"))
        
        if not self.logs:
            log_text.append("等待日志...", style="dim")
        
        return Panel(
            log_text,
            title="📝 实时日志",
            border_style="white",
            box=box.ROUNDED,
        )
    
    def _render_table(self) -> Panel:
        """最近的发现：平台、脱敏预览、状态、位置。"""
        table = Table(
            show_header=True,
            header_style="bold white",
            box=box.SIMPLE,
            expand=True,
        )

        table.add_column("平台", style="bold", width=12)
        table.add_column("预览", width=22)
        table.add_column("状态", width=16)
        table.add_column("位置", width=36)

        for record in self.valid_keys[-10:]:
            location = record.source
            if len(location) > 36:
                location = location[:33] + "..."
            table.add_row(
                Text(record.platform, style=record.platform_color),
                Text(record.masked_key),
                Text(record.status, style="green"),
                Text(location),
            )

        if not self.valid_keys:
            table.add_row(
                Text("--", style="dim"),
                Text("等待发现", style="dim"),
                Text("--", style="dim"),
                Text("--", style="dim"),
            )

        return Panel(
            table,
            title="发现记录",
            border_style="green",
            box=box.ROUNDED,
        )
    
    def _render_footer(self) -> Panel:
        """渲染底部进度条"""
        keyword = self.stats.current_keyword or "准备中..."
        
        footer_text = Text()
        footer_text.append("🔍 当前搜索: ", style="white")
        footer_text.append(keyword[:50], style="bold cyan")
        footer_text.append("  │  ", style="dim")
        footer_text.append("按 ", style="dim")
        footer_text.append("Ctrl+C", style="bold yellow")
        footer_text.append(" 停止", style="dim")
        
        return Panel(
            footer_text,
            border_style="dim",
            box=box.ROUNDED,
        )
    
    def _render(self) -> Layout:
        """渲染完整布局"""
        layout = self._create_layout()
        
        with self._lock:
            layout["header"].update(self._render_header())
            layout["stats"].update(self._render_stats())
            layout["logs"].update(self._render_logs())
            layout["table"].update(self._render_table())
            layout["footer"].update(self._render_footer())
        
        return layout
    
    # ========================================================================
    #                           公共 API
    # ========================================================================
    
    def add_log(self, message: str, level: str = "INFO"):
        """添加日志条目"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # 根据级别设置颜色
        level_colors = {
            "INFO": "white",
            "SCAN": "cyan",
            "FOUND": "green",
            "VALID": "bold green",
            "HIGH": "bold green",
            "SKIP": "yellow",
            "WARN": "yellow",
            "ERROR": "red",
            "DEBUG": "dim",
        }
        color = level_colors.get(level, "white")
        
        formatted = f"[dim]{timestamp}[/] [{color}][{level}][/] {message}"
        
        with self._lock:
            self.logs.append(formatted)
    
    def add_valid_key(
        self,
        platform: str,
        masked_key: str,
        balance: str = "",
        source: str = "",
        is_high_value: bool = False,
        status: str = "valid",
    ):
        """记下一条存活发现。balance 和 is_high_value 被忽略，留给旧调用方。"""
        record = ValidKeyRecord(
            platform=platform,
            masked_key=masked_key,
            source=source,
            found_time=datetime.now().strftime("%H:%M:%S"),
            status=status or "valid",
            balance=balance,
            is_high_value=False,
        )

        with self._lock:
            self.valid_keys.append(record)
            self.stats.valid_keys += 1
    
    def update_stats(self, **kwargs):
        """更新统计数据"""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.stats, key):
                    if isinstance(value, int) and key not in ['current_token_index', 'total_tokens', 'queue_size']:
                        # 累加
                        setattr(self.stats, key, getattr(self.stats, key) + value)
                    else:
                        # 直接设置
                        setattr(self.stats, key, value)
    
    def increment_stat(self, stat_name: str, amount: int = 1):
        """增加统计值"""
        with self._lock:
            if hasattr(self.stats, stat_name):
                current = getattr(self.stats, stat_name)
                setattr(self.stats, stat_name, current + amount)
    
    def start(self) -> Live:
        """启动实时刷新"""
        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=4,
            screen=True,
        )
        return self._live
    
    def refresh(self):
        """手动刷新"""
        if self._live:
            self._live.update(self._render())
    
    def stop(self):
        """停止仪表盘"""
        with self._lock:
            self.stats.is_running = False


# 全局仪表盘实例
dashboard = Dashboard()
