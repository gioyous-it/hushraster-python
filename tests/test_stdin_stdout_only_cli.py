# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Regression tests for the binary-only stdin/stdout CLI."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = b"HushRaster stdin/stdout\x00\xff\n"


def run(*args, input_bytes):
    return subprocess.run(
        [sys.executable, "-m", "hushraster", *args], cwd=ROOT,
        input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=120, check=False,
    )


def test_all_implemented_standards_roundtrip_over_pipes():
    for standard in ("p1", "p2", "p3", "oi1", "d1", "ce1", "z1", "sl1"):
        encoded = run("encode", f"{standard}+", "--ppm", "1", input_bytes=PAYLOAD)
        assert encoded.returncode == 0, (standard, encoded.stderr)
        assert encoded.stdout.startswith(b"\x89PNG\r\n\x1a\n")
        decoded = run("decode", input_bytes=encoded.stdout)
        assert decoded.returncode == 0, (standard, decoded.stderr)
        assert decoded.stdout == PAYLOAD


def test_default_p2_roundtrip_and_ppm_default():
    encoded = run("encode", input_bytes=PAYLOAD)
    assert encoded.returncode == 0, encoded.stderr
    decoded = run("decode", input_bytes=encoded.stdout)
    assert decoded.returncode == 0, decoded.stderr
    assert decoded.stdout == PAYLOAD


def test_reserved_standards_fail_without_corrupting_stdout():
    for standard in ("e1", "l1"):
        result = run("encode", f"{standard}+", input_bytes=PAYLOAD)
        assert result.returncode != 0
        assert result.stdout == b""
