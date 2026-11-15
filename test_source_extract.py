"""公共源提取走 content_variants + select_key_matches。"""

import queue
import threading

from config import COMPILED_KEY_PATTERNS
from scanner import extract_source_keys, select_key_matches
from source_gitlab import GitLabScanner
from source_pastebin import PastebinScanner
from source_realtime import RealtimeScanner
from source_searchcode import CodeResult, SearchCodeScanner

# openai 整段命中包住 together 的 64 位十六进制短命中
_HEX64 = "A1b2C3d4E5f67890" * 4
OVERLAP_TEXT = f"OPENAI_API_KEY=sk-{_HEX64}"
OVERLAP_OPENAI = f"sk-{_HEX64}"
SOURCE = "https://example.test/leak"


def test_select_key_matches_drops_contained_shorter_hit():
    matches = select_key_matches(COMPILED_KEY_PATTERNS, OVERLAP_TEXT)
    keys = [item[3] for item in matches]
    platforms = [item[2] for item in matches]
    assert OVERLAP_OPENAI in keys
    assert "openai" in platforms
    assert "together" not in platforms
    assert _HEX64 not in keys


def test_extract_source_keys_keeps_longest_only():
    results = extract_source_keys(COMPILED_KEY_PATTERNS, OVERLAP_TEXT, SOURCE)
    assert [r.platform for r in results] == ["openai"]
    assert results[0].api_key == OVERLAP_OPENAI
    assert results[0].source_url == SOURCE


def test_public_scanners_use_longest_match():
    stop = threading.Event()
    gitlab = GitLabScanner(queue.Queue(), stop)
    pastebin = PastebinScanner(queue.Queue(), stop)
    realtime = RealtimeScanner(queue.Queue(), stop)
    searchcode = SearchCodeScanner(queue.Queue(), stop)

    for found in (
        gitlab._extract_keys(OVERLAP_TEXT, SOURCE),
        pastebin._extract_keys(OVERLAP_TEXT, SOURCE),
        realtime._extract_keys(OVERLAP_TEXT, SOURCE),
        searchcode._extract_keys(CodeResult(
            id="1", filename="env", repo="acme/app", url=SOURCE,
            lines={"1": OVERLAP_TEXT},
        )),
    ):
        assert [r.platform for r in found] == ["openai"]
        assert found[0].api_key == OVERLAP_OPENAI


def test_extract_source_keys_decodes_percent_encoded_key():
    key = "sk-proj-Qw9Rt8Yu7Ip6Lk5Jh4Gf3Ds2Az1Xc0Vb"
    encoded = "sk-proj-Qw9%52t8Yu7Ip6Lk5Jh4Gf3Ds2Az1Xc0Vb"
    assert key not in encoded
    results = extract_source_keys(
        COMPILED_KEY_PATTERNS, f"API_KEY={encoded}", SOURCE,
    )
    assert [r.api_key for r in results] == [key]
    assert results[0].platform == "openai"


def test_extract_source_keys_skips_keys_already_in_db():
    from datetime import datetime
    from database import Database, LeakedKey, KeyStatus

    db = Database(":memory:")
    assert db.insert_key(LeakedKey(
        platform="openai",
        api_key=OVERLAP_OPENAI,
        base_url="https://api.openai.com/v1",
        status=KeyStatus.INVALID.value,
        found_time=datetime.now(),
    ))
    assert extract_source_keys(COMPILED_KEY_PATTERNS, OVERLAP_TEXT, SOURCE, db=db) == []
    assert [r.api_key for r in extract_source_keys(
        COMPILED_KEY_PATTERNS, OVERLAP_TEXT, SOURCE,
    )] == [OVERLAP_OPENAI]


def test_public_scanners_skip_keys_already_in_db():
    from datetime import datetime
    from database import Database, LeakedKey, KeyStatus
    from source_gist import GistScanner

    db = Database(":memory:")
    assert db.insert_key(LeakedKey(
        platform="openai",
        api_key=OVERLAP_OPENAI,
        base_url="https://api.openai.com/v1",
        status=KeyStatus.INVALID.value,
        found_time=datetime.now(),
    ))
    stop = threading.Event()
    for found in (
        GitLabScanner(queue.Queue(), stop, db=db)._extract_keys(OVERLAP_TEXT, SOURCE),
        PastebinScanner(queue.Queue(), stop, db=db)._extract_keys(OVERLAP_TEXT, SOURCE),
        RealtimeScanner(queue.Queue(), stop, db=db)._extract_keys(OVERLAP_TEXT, SOURCE),
        SearchCodeScanner(queue.Queue(), stop, db=db)._extract_keys(CodeResult(
            id="1", filename="env", repo="acme/app", url=SOURCE,
            lines={"1": OVERLAP_TEXT},
        )),
        GistScanner(queue.Queue(), stop, db=db)._extract_keys(OVERLAP_TEXT, SOURCE),
    ):
        assert found == []


def test_extract_source_keys_does_not_duplicate_plain_and_encoded():
    key = "sk-proj-Qw9Rt8Yu7Ip6Lk5Jh4Gf3Ds2Az1Xc0Vb"
    encoded = "sk-proj-Qw9%52t8Yu7Ip6Lk5Jh4Gf3Ds2Az1Xc0Vb"
    results = extract_source_keys(
        COMPILED_KEY_PATTERNS, f"{key}\n{encoded}", SOURCE,
    )
    assert [r.api_key for r in results] == [key]
