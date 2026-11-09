"""
凭据导出。

明文导出默认只写脱敏值。完整值需要 --reveal。
加密导出把完整记录放进 Fernet 密文，密钥写到旁边的 .key 文件。
"""

import csv
import json
from datetime import datetime
from typing import Optional

from database import Database, KeyStatus
from utils import mask_key


def _load_keys(db_path: str, status_filter: Optional[str]):
    from rich.console import Console

    console = Console()
    db = Database(db_path)
    if status_filter:
        try:
            status = KeyStatus(status_filter)
            keys = db.get_keys_by_status(status)
        except ValueError:
            console.print(f"[red]无效状态: {status_filter}[/]")
            return None
    else:
        keys = db.get_valid_keys()

    if not keys:
        console.print("[yellow]没有符合条件的 Key[/]")
        return None
    return keys


def export_keys(db_path: str, output_file: str, status_filter: str = None, reveal: bool = False):
    """导出 Key。reveal 为 False 时 Key 列脱敏。"""
    from rich.console import Console

    console = Console()
    keys = _load_keys(db_path, status_filter)
    if not keys:
        return

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# GitHub Secret Scanner 导出结果\n")
        f.write(f"# 时间: {datetime.now().isoformat()}\n")
        f.write(f"# 数量: {len(keys)}\n")
        f.write(f"# 明文 Key: {'是' if reveal else '否（已脱敏，完整值需 --reveal）'}\n")
        f.write("=" * 60 + "\n\n")

        for key in keys:
            shown = key.api_key if reveal else mask_key(key.api_key)
            f.write(f"平台: {key.platform}\n")
            f.write(f"状态: {key.status}\n")
            f.write(f"Key: {shown}\n")
            f.write(f"URL: {key.base_url}\n")
            f.write(f"来源: {key.source_url}\n")
            f.write("-" * 40 + "\n\n")

    if reveal:
        console.print(f"[yellow]已导出 {len(keys)} 个完整 Key 到 {output_file}。文件等同于凭据，用完即删。[/]")
    else:
        console.print(f"[green]已导出 {len(keys)} 个脱敏记录到 {output_file}[/]")


def export_keys_csv(db_path: str, output_file: str, status_filter: str = None, reveal: bool = False):
    """导出 CSV。reveal 为 False 时 api_key 列脱敏。"""
    from rich.console import Console

    console = Console()
    keys = _load_keys(db_path, status_filter)
    if not keys:
        return

    fieldnames = [
        "id", "platform", "status", "api_key", "base_url",
        "source_url", "model_tier", "rpm", "found_time",
    ]

    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key in keys:
            writer.writerow({
                "id": getattr(key, "id", ""),
                "platform": key.platform,
                "status": key.status,
                "api_key": key.api_key if reveal else mask_key(key.api_key),
                "base_url": key.base_url,
                "source_url": key.source_url,
                "model_tier": key.model_tier,
                "rpm": key.rpm,
                "found_time": key.found_time.isoformat() if getattr(key, "found_time", None) else "",
            })

    note = "完整 Key" if reveal else "脱敏记录"
    console.print(f"[green]已导出 {len(keys)} 条{note}到 CSV: {output_file}[/]")


def export_keys_encrypted(db_path: str, output_file: str, status_filter: str = None):
    """用一次性 Fernet 密钥加密导出。密钥写入 output_file.key。"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("需要安装 cryptography: pip install cryptography")
        return

    from rich.console import Console

    console = Console()
    keys = _load_keys(db_path, status_filter)
    if not keys:
        return

    encryption_key = Fernet.generate_key()
    cipher = Fernet(encryption_key)
    data = [{
        "platform": k.platform,
        "api_key": k.api_key,
        "base_url": k.base_url,
        "status": k.status,
        "source_url": k.source_url,
    } for k in keys]
    encrypted_data = cipher.encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    with open(output_file, "wb") as f:
        f.write(encrypted_data)
    key_file = output_file + ".key"
    with open(key_file, "wb") as f:
        f.write(encryption_key)

    console.print(f"[green]已加密导出 {len(keys)} 个 Key[/]")
    console.print(f"[cyan]数据文件: {output_file}[/]")
    console.print(f"[cyan]密钥文件: {key_file}[/]")
    console.print("[yellow]密钥文件可以解开全部凭据，请与数据文件分开保管。[/]")


def decrypt_keys(encrypted_file: str, key_file: str):
    """解密导出文件，终端只打印脱敏后的 Key。"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("需要安装 cryptography: pip install cryptography")
        return

    from rich.console import Console

    console = Console()
    try:
        with open(key_file, "rb") as f:
            encryption_key = f.read()
        cipher = Fernet(encryption_key)
        with open(encrypted_file, "rb") as f:
            encrypted_data = f.read()
        keys = json.loads(cipher.decrypt(encrypted_data).decode("utf-8"))
    except Exception as e:
        console.print(f"[red]解密失败: {e}[/]")
        return

    console.print(f"[green]成功解密 {len(keys)} 个 Key（终端只显示脱敏值）[/]")
    for i, key in enumerate(keys[:3]):
        console.print(f"\n[cyan]Key {i + 1}:[/]")
        console.print(f"  平台: {key.get('platform', '')}")
        console.print(f"  Key: {mask_key(key.get('api_key', ''))}")
        console.print(f"  URL: {key.get('base_url', '')}")
    if len(keys) > 3:
        console.print(f"\n[yellow]还有 {len(keys) - 3} 个 Key 未在终端展开[/]")
