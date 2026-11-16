"""Installable entry: python -m aikeyscan and aikeyscan match main_v2.2.py --help."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent


def _run(args, *, executable=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    cmd = [executable or sys.executable, *args]
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _assert_help(result):
    combined = result.stdout + result.stderr
    assert result.returncode == 0
    assert "allow-public-sources" in combined
    assert "findings-json" in combined
    assert "target-org" in combined
    assert "live-only" in combined
    assert "baseline" in combined
    assert "since-ref" in combined


def test_script_help_still_works():
    _assert_help(_run(["main_v2.2.py", "--help"]))


def test_module_help():
    _assert_help(_run(["-m", "aikeyscan", "--help"]))


def test_console_script_help():
    exe = shutil.which("aikeyscan")
    if not exe:
        pytest.skip("aikeyscan console script is not on PATH")
    result = subprocess.run(
        [exe, "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    _assert_help(result)


def test_cli_main_help_exits_zero():
    from aikeyscan.cli import main

    with pytest.raises(SystemExit) as raised:
        main(["--help"])
    assert raised.value.code == 0
