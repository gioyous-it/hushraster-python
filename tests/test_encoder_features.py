#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Tests for importable API, --redo semantics, blank canvas, and Android fallback."""
from __future__ import annotations

import errno
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import hushraster
from hushraster import (
    HushRasterError,
    create_blank_canvas,
    decode_image,
    encode_image,
    encode_repeated,
    minimum_canvas_size,
    parse_color,
)
from hushraster.cli import write_output
from hushraster.core import read_image, required_tiles, FORMAT_VERSION


def run_cli(*args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "hushraster", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == expected, (args, proc.returncode, proc.stdout, proc.stderr)
    return proc


def test_color_parser() -> None:
    assert parse_color("cyan") == (0, 255, 255)
    assert parse_color("FF") == (255, 255, 255)
    assert parse_color("0") == (0, 0, 0)
    assert parse_color("80") == (128, 128, 128)
    assert parse_color("abc") == (170, 187, 204)
    assert parse_color("#12ABEF") == (18, 171, 239)
    assert parse_color((1, 2, 3)) == (1, 2, 3)
    for bad in ("", "no-such-color", "abcd", "12345678", (1, 2, 999)):
        try:
            parse_color(bad)
        except HushRasterError:
            pass
        else:
            raise AssertionError(f"invalid color accepted: {bad!r}")


def test_import_api_and_blank_canvas() -> None:
    assert hushraster.__version__ == "1.0.1"
    for _name in ("encode_image", "decode_image", "encode_repeated", "create_blank_canvas"):
        assert callable(getattr(hushraster, _name))
    payload = b"a small blank-canvas payload\x00\xff"
    for compression in ("none",):
        canvas = create_blank_canvas(payload, "payload.bin", "80", compression=compression)
        assert canvas.mode == "RGB"
        assert canvas.getpixel((0, 0)) == (128, 128, 128)
        assert canvas.width % 8 == 0 and canvas.height % 8 == 0
        encoded, info = encode_image(canvas, payload, "payload.bin", compression=compression)
        recovered, _header, stats = decode_image(encoded, mode="strict")
        assert recovered == payload and stats["integrity_verified"]
        stored_len = info["stored_len"]
        tiles = (encoded.width // 8) * (encoded.height // 8)
        assert tiles >= required_tiles(stored_len, "payload.bin", FORMAT_VERSION)
        min_size = minimum_canvas_size(stored_len, "payload.bin")
        assert canvas.size == min_size


def test_standalone_barcode_survives_distributed_cutouts() -> None:
    """Deterministic adversarial-looking damage: many separated blank patches."""
    payload = b"HushRaster barcode crop test\x00\xff"
    canvas = create_blank_canvas(payload, "crop-test.bin", "80")
    barcode, _info = encode_repeated(canvas, payload, "crop-test.bin", verify=True)
    damaged = barcode.copy()
    draw = ImageDraw.Draw(damaged)
    rng = random.Random(181)
    masked = bytearray(damaged.width * damaged.height)

    # Erase 80 module-aligned 64x64 patches, approximately 16% of the raster
    # in this deterministic fixture. The scanner must still verify the digest.
    for _ in range(80):
        x = rng.randrange(damaged.width // 8) * 8
        y = rng.randrange(damaged.height // 8) * 8
        x1 = min(damaged.width, x + 64)
        y1 = min(damaged.height, y + 64)
        draw.rectangle((x, y, x1 - 1, y1 - 1), fill=(128, 128, 128))
        row = b"\x01" * (x1 - x)
        for yy in range(y, y1):
            start = yy * damaged.width + x
            masked[start:start + len(row)] = row

    damaged_fraction = sum(masked) / len(masked)
    assert damaged_fraction > 0.15, f"expected substantial masking, got {damaged_fraction:.2%}"
    recovered, _header, stats = decode_image(damaged, mode="strict")
    assert recovered == payload
    assert stats["integrity_verified"]


def _cover() -> Image.Image:
    image = Image.new("RGB", (176, 297), (128, 128, 128))
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 22, 160, 120), fill=(44, 126, 154))
    draw.ellipse((32, 140, 145, 260), fill=(240, 164, 57))
    return image


def test_redo_is_exactly_repeated_modulation() -> None:
    payload = b"redo should intensify but not change decoded bytes"
    cover = _cover()
    for redo in (1, 2, 5):
        actual, info = encode_repeated(cover, payload, "", redo=redo, resize=True)
        expected = cover
        for _ in range(redo):
            expected, _ = encode_image(expected, payload, "", resize=True, verify=False)
        assert np.array_equal(np.asarray(actual), np.asarray(expected)), f"redo={redo} differs from literal repeated encoding"
        recovered, _header, stats = decode_image(actual, mode="strict")
        assert recovered == payload and stats["integrity_verified"], f"redo={redo} did not verify"
        assert info["redo_passes"] == redo


def test_redo_128_and_cli_blank_examples() -> None:
    # Small payload keeps this test quick while exercising the requested 128-pass path.
    payload = b"QR"
    canvas = create_blank_canvas(payload, "", "80")
    encoded, info = encode_repeated(canvas, payload, "", redo=128)
    recovered, _meta, stats = decode_image(encoded, mode="strict")
    assert recovered == payload and stats["integrity_verified"]
    assert info["redo_passes"] == 128

    with tempfile.TemporaryDirectory(prefix="hushraster-blank-cli-") as temp:
        root = Path(temp)
        binary = root / "tiny.bin"
        binary.write_bytes(bytes(range(32)))
        output = root / "blank.png"
        encoded = subprocess.run(
            [sys.executable, "-m", "hushraster", "encode", "p2+"], cwd=ROOT,
            input=binary.read_bytes(), capture_output=True, timeout=120, check=False,
        )
        assert encoded.returncode == 0, encoded.stderr.decode(errors="replace")
        assert encoded.stdout.startswith(b"\x89PNG\r\n\x1a\n")
        output.write_bytes(encoded.stdout)
        recovered_path = root / "out.bin"
        decoded = subprocess.run(
            [sys.executable, "-m", "hushraster", "decode"], cwd=ROOT,
            input=output.read_bytes(), capture_output=True, timeout=120, check=False,
        )
        assert decoded.returncode == 0, decoded.stderr.decode(errors="replace")
        recovered_path.write_bytes(decoded.stdout)
        assert recovered_path.read_bytes() == binary.read_bytes()

        text_output = root / "blank-text.png"
        encoded_text = subprocess.run(
            [sys.executable, "-m", "hushraster", "encode", "p2+"], cwd=ROOT,
            input=b"hello cyan", capture_output=True, timeout=120, check=False,
        )
        assert encoded_text.returncode == 0, encoded_text.stderr.decode(errors="replace")
        text_output.write_bytes(encoded_text.stdout)
        text = subprocess.run(
            [sys.executable, "-m", "hushraster", "decode"], cwd=ROOT,
            input=text_output.read_bytes(), capture_output=True, timeout=120, check=False,
        )
        assert text.returncode == 0, text.stderr.decode(errors="replace")
        assert text.stdout == b"hello cyan"


def test_android_missing_link_fallback_and_no_clobber() -> None:
    with tempfile.TemporaryDirectory(prefix="hushraster-no-link-") as temp:
        root = Path(temp)
        target = root / "new.bin"
        # Simulate Android builds where the attribute is absent/not callable.
        with patch("hushraster.cli.os.link", new=None):
            write_output(target, b"atomic exclusive-create fallback")
            assert target.read_bytes() == b"atomic exclusive-create fallback"
            try:
                write_output(target, b"must not replace")
            except HushRasterError as exc:
                assert "already exists" in str(exc)
            else:
                raise AssertionError("no-link fallback overwrote an existing file")
            assert target.read_bytes() == b"atomic exclusive-create fallback"


def main() -> None:
    test_color_parser()
    test_import_api_and_blank_canvas()
    test_standalone_barcode_survives_distributed_cutouts()
    test_redo_is_exactly_repeated_modulation()
    test_redo_128_and_cli_blank_examples()
    test_android_missing_link_fallback_and_no_clobber()
    print("PASS: importable API; blank-canvas sizing/colors; standalone barcode strict recovery after 80 distributed cutouts masking >15% of pixels; redo equivalence and redo=128; CLI binary/text examples; Android missing-os.link fallback/no-clobber protection")


if __name__ == "__main__":
    main()
