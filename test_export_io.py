"""export_io 的脱敏、过滤与加密往返测试。"""

import csv
import json

from cryptography.fernet import Fernet

from database import Database, LeakedKey, KeyStatus
from export_io import (
    decrypt_keys,
    export_keys,
    export_keys_csv,
    export_keys_encrypted,
)
from utils import mask_key

SECRET_VALID = "sk-proj-Val1dAb12Cd34E5f6G7h8I9j0K1l2M3n4"
SECRET_INVALID = "sk-proj-Inval1dAb12Cd34E5f6G7h8I9j0K1l2"


def _seed(db_path):
    db = Database(db_path)
    assert db.insert_key(LeakedKey(
        platform="openai", api_key=SECRET_VALID,
        base_url="https://api.openai.com/v1",
        status=KeyStatus.VALID.value,
        source_url="https://github.com/acme/a/blob/1/.env",
    ))
    assert db.insert_key(LeakedKey(
        platform="openai", api_key=SECRET_INVALID,
        base_url="https://api.openai.com/v1",
        status=KeyStatus.INVALID.value,
        source_url="https://github.com/acme/b/blob/2/.env",
    ))


def test_csv_export_masked_by_default_and_reveal(tmp_path):
    db_path = str(tmp_path / "k.db")
    _seed(db_path)

    masked = str(tmp_path / "masked.csv")
    export_keys_csv(db_path, masked)
    text = open(masked, encoding="utf-8").read()
    rows = list(csv.DictReader(open(masked, encoding="utf-8")))
    # 无 status 过滤时走 get_valid_keys()：invalid 行不导出
    assert len(rows) == 1
    assert SECRET_VALID not in text
    assert mask_key(SECRET_VALID) in text

    revealed = str(tmp_path / "full.csv")
    export_keys_csv(db_path, revealed, reveal=True)
    text = open(revealed, encoding="utf-8").read()
    assert SECRET_VALID in text
    assert SECRET_INVALID not in text  # 过滤逻辑与脱敏无关


def test_text_export_status_filter_and_masking(tmp_path):
    db_path = str(tmp_path / "k.db")
    _seed(db_path)

    out = str(tmp_path / "valid.txt")
    export_keys(db_path, out, status_filter="valid")
    text = open(out, encoding="utf-8").read()
    assert mask_key(SECRET_VALID) in text   # 脱敏形式在
    assert SECRET_VALID not in text         # 明文不在
    assert mask_key(SECRET_INVALID) not in text  # invalid 行被过滤


def test_invalid_status_filter_writes_nothing(tmp_path, capsys):
    db_path = str(tmp_path / "k.db")
    _seed(db_path)
    export_keys(db_path, str(tmp_path / "nope.txt"), status_filter="bogus")
    assert not (tmp_path / "nope.txt").exists()
    assert "无效状态" in capsys.readouterr().out


def test_encrypted_export_roundtrip_and_wrong_key(tmp_path):
    db_path = str(tmp_path / "k.db")
    _seed(db_path)

    blob = str(tmp_path / "out.bin")
    export_keys_encrypted(db_path, blob, status_filter="valid")
    key_file = blob + ".key"
    assert (tmp_path / "out.bin").exists()
    assert (tmp_path / "out.bin.key").exists()

    cipher = Fernet(open(key_file, "rb").read())
    data = json.loads(cipher.decrypt(open(blob, "rb").read()).decode("utf-8"))
    assert [d["api_key"] for d in data] == [SECRET_VALID]

    raised = False
    try:
        Fernet(Fernet.generate_key()).decrypt(open(blob, "rb").read())
    except Exception:
        raised = True
    assert raised


def test_decrypt_keys_masks_terminal_output(tmp_path, capsys):
    db_path = str(tmp_path / "k.db")
    _seed(db_path)
    blob = str(tmp_path / "out.bin")
    export_keys_encrypted(db_path, blob)

    decrypt_keys(blob, blob + ".key")
    out = capsys.readouterr().out
    assert "成功解密 1 个 Key" in out  # 无过滤时只导 valid 行
    assert SECRET_VALID not in out
    assert "..." in out
