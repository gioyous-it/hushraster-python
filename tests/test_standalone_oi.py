# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, payload=b""):
    result = subprocess.run(
        [sys.executable, "-m", "hushraster", *args], cwd=ROOT,
        input=payload, capture_output=True, timeout=120, check=False,
    )
    assert result.returncode == 0, (
        f"command failed: {args!r}\nstdout={result.stdout!r}\nstderr={result.stderr.decode(errors='replace')}"
    )
    return result.stdout


def test_oi_standalone_text_needs_no_origin_image():
    payload = b"Hello, World!"
    image = run(["encode", "oi+"], payload)
    assert run(["decode"], image) == payload
    inspection = run(["inspect"], image).decode()
    assert "HushRaster OI (OverImage)" in inspection


def test_oi_standalone_binary_roundtrip_needs_no_origin_image():
    payload = b"OI standalone\x00\xff payload"
    image = run(["encode", "oi+", "--on-blank", "cyan"], payload)
    assert run(["decode"], image) == payload
