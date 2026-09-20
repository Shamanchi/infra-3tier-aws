"""CLI-тесты через subprocess: без сети."""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "app.main", *args],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_cli_validate_ok() -> None:
    proc = _run("validate", "--file", "examples/topology.json")
    assert proc.returncode == 0
    assert "OK: topology is valid" in proc.stdout


def test_cli_validate_missing_file() -> None:
    proc = _run("validate", "--file", "examples/nope.json")
    assert proc.returncode == 2


def test_cli_generate(tmp_path: Path) -> None:
    out = tmp_path / "generated.tf"
    proc = _run("generate", "--cidr", "10.0.0.0/16", "--azs", "2", "--out", str(out))
    assert proc.returncode == 0
    assert out.exists()
    assert 'resource "aws_vpc" "main"' in out.read_text(encoding="utf-8")


@pytest.mark.integration()
def test_cli_generate_bad_cidr() -> None:
    """Интеграционный по маркеру: плохой CIDR, без сети."""
    proc = _run("generate", "--cidr", "oops", "--azs", "2", "--out", "out.tf")
    assert proc.returncode == 2
