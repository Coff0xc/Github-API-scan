"""扫描线程用 queue.Queue.put(timeout=)，验证协程用 take_queued_result。"""

import asyncio
import importlib.util
import os
import queue
import threading

from scanner import ScanResult
from validator_optimized import take_queued_result


def _load_main():
    path = os.path.join(os.path.dirname(__file__), "main_v2.2.py")
    spec = importlib.util.spec_from_file_location("main_v2_2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


KEY = "sk-proj-Qw9Rt8Yu7Ip6Lk5Jh4Gf3Ds2Az1Xc0Vb"


def _item():
    return ScanResult(
        platform="openai",
        api_key=KEY,
        base_url="https://api.openai.com/v1",
        source_url="https://github.com/example/repo",
    )


def test_remote_main_uses_sync_queue():
    path = os.path.join(os.path.dirname(__file__), "main_v2.2.py")
    with open(path, encoding="utf-8") as handle:
        source = handle.read().replace("\r\n", "\n")
    assert "queue.Queue(maxsize=10000)" in source
    assert "from queue_manager import create_queue" not in source
    assert "asyncio.Queue(maxsize=10000)" not in source
    assert "self.db = Database(config.db_path)" in source
    assert "start_scanner(\n            self.result_queue,\n            self.db," in source
    main = _load_main()
    scanner = main.OptimizedSecretScannerV22(target_org="example")
    assert isinstance(scanner.result_queue, queue.Queue)


def test_asyncio_queue_put_rejects_timeout():
    pending = asyncio.Queue()
    try:
        pending.put(_item(), timeout=5)
    except TypeError:
        return
    raise AssertionError("asyncio.Queue.put must not accept timeout=")


def test_thread_put_timeout_reaches_take_queued_result():
    pending = queue.Queue(maxsize=10000)
    item = _item()
    errors = []

    def producer():
        try:
            pending.put(item, timeout=5)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=producer)
    thread.start()

    async def consume():
        return await take_queued_result(pending, timeout=2.0)

    got = asyncio.run(consume())
    thread.join(timeout=2)
    assert errors == []
    assert got is item
