"""
UI 模块 - Rich TUI 仪表盘

使用 rich 库构建实时刷新的终端界面：
- Header: 状态栏
- Stats Panel: 统计数据
- Live Table: 有效 Key 列表
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
    """有效 Key 记录"""
    platform: str
    masked_key: str
    balance: str
    source: str
    found_time: str
    is_high_value: bool = False  # 高价值标记
    
    @property
    def platform_color(self) -> str:
        """根据平台和价值返回颜色"""
        # 高价值 Key 使用金色粗体
        if self.is_high_value:
            return "bold gold1"
        
        colors = {
            "openai": "green",
            "azure": "blue",
            "anthropic": "magenta",
            "gemini": "cyan",
            "relay": "yellow",
        }
        return colors.get(self.platform.lower(), "white")
    
    @property
    def balance_style(self) -> str:
        """余额显示样式"""
        if self.is_high_value:
            return "bold green"
        if "$" in self.balance:
            return "bold cyan"
        return "green"


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
    │              Valid Keys Table                │
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
            title="🔍 GitHub Secret Scanner Pro",
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
            Text("💰 配额耗尽", style="white"),
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
        """渲染有效 Key 表格（高价值特殊高亮）"""
        table = Table(
            show_header=True,
            header_style="bold white",
            box=box.SIMPLE,
            expand=True,
        )
        
        table.add_column("平台", style="bold", width=10)
        table.add_column("Key", width=20)
        table.add_column("状态/余额", width=15)
        table.add_column("来源", width=30)
        table.add_column("时间", width=10)
        
        # 显示最近的有效 Key（最多 10 条）
        # 高价值 Key 使用金色/绿色粗体高亮
        for record in self.valid_keys[-10:]:
            # 高价值 Key 特殊标记
            if record.is_high_value:
                platform_text = Text(f"⭐ {record.platform.upper()}", style="bold gold1")
                key_text = Text(record.masked_key, style="bold gold1")
                balance_text = Text(record.balance, style=record.balance_style)
            else:
                platform_text = Text(record.platform.upper(), style=record.platform_color)
                key_text = Text(record.masked_key, style=record.platform_color)
                balance_text = Text(record.balance, style=record.balance_style)
            
            table.add_row(
                platform_text,
                key_text,
                balance_text,
                record.source[:28] + "..." if len(record.source) > 30 else record.source,
                record.found_time,
            )
        
        if not self.valid_keys:
            table.add_row(
                Text("--", style="dim"),
                Text("等待有效 Key...", style="dim"),
                Text("--", style="dim"),
                Text("--", style="dim"),
                Text("--", style="dim")
            )
        
        # 根据是否有高价值 Key 设置边框颜色
        high_value_count = sum(1 for r in self.valid_keys if r.is_high_value)
        border_style = "gold1" if high_value_count > 0 else "green"
        title_prefix = f"💎 {high_value_count}个高价值 | " if high_value_count > 0 else ""
        
        return Panel(
            table,
            title=f"{title_prefix}🏆 有效 Key 列表 (The Treasure)",
            border_style=border_style,
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
            "HIGH": "bold gold1",      # 高价值 Key
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
        balance: str, 
        source: str,
        is_high_value: bool = False
    ):
        """
        添加有效 Key 记录
        
        Args:
            platform: 平台名称
            masked_key: 隐藏的 Key
            balance: 余额/状态信息
            source: 来源
            is_high_value: 是否为高价值 Key (GPT-4/有余额/Enterprise RPM)
        """
        record = ValidKeyRecord(
            platform=platform,
            masked_key=masked_key,
            balance=balance,
            source=source,
            found_time=datetime.now().strftime("%H:%M:%S"),
            is_high_value=is_high_value,
        )
        
        with self._lock:
            self.valid_keys.append(record)
            self.stats.valid_keys += 1
            
            # 高价值 Key 特殊日志
            if is_high_value:
                self.logs.append(
                    f"[dim]{datetime.now().strftime('%H:%M:%S')}[/] [bold gold1][💎 HIGH][/] "
                    f"发现高价值 Key: {platform.upper()} {masked_key}"
                )
    
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
