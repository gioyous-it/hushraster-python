# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

from PIL import Image

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


def roundtrip(standard: str, payload: bytes, ppm: int):
    png = run(["encode", f"{standard}+", "--ppm", str(ppm)], payload)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    recovered = run(["decode"], png)
    assert recovered == payload
    return Image.open(io.BytesIO(png)).copy(), png


def test_p2_out_qual_hd_and_min_roundtrip():
    payload = b"Hello, World!"
    hd, _ = roundtrip("p2", payload, 4)
    minimum, _ = roundtrip("p2", payload, 1)
    assert minimum.width < hd.width and minimum.height < hd.height


def test_p1_out_qual_hd_and_min_roundtrip():
    payload = b"Hello, World!"
    hd, _ = roundtrip("p1", payload, 4)
    minimum, _ = roundtrip("p1", payload, 1)
    assert minimum.width < hd.width and minimum.height < hd.height


def test_standalone_oi_is_visible_and_decodable():
    payload = b"Hello, World!"
    png = run(["encode", "oi+", "--on-blank", "cyan"], payload)
    with Image.open(io.BytesIO(png)) as im:
        im.load()
        assert len(im.convert("RGB").getcolors(maxcolors=1_000_000) or []) > 2
    assert run(["decode"], png) == payload
