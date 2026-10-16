#!/usr/bin/env python3
"""Tests for importable API, --redo semantics, blank canvas, and Android fallback."""
from __future__ import annotations

import errno
import os
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
    assert hushraster.__version__ == "1.0"
    for _name in ("encode_image", "decode_image", "encode_repeated", "create_blank_canvas"):
        assert callable(getattr(hushraster, _name))
    payload = b"a small blank-canvas payload\x00\xff"
    for compression in ("none", "z"):
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
        result = run_cli("encode", str(binary), str(output), "--on-blank", "80", "--redo", "2")
        assert output.exists() and "generated blank canvas" in result.stdout and "Encoder passes (--redo): 2" in result.stdout
        recovered_path = root / "out.bin"
        run_cli("decode", str(output), str(recovered_path))
        assert recovered_path.read_bytes() == binary.read_bytes()

        text_output = root / "blank-text.png"
        run_cli("encode-text", "hello cyan", str(text_output), "--on-blank", "cyan")
        text = run_cli("decode-text", str(text_output))
        assert text.stdout == "hello cyan\n"


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
    test_redo_is_exactly_repeated_modulation()
    test_redo_128_and_cli_blank_examples()
    test_android_missing_link_fallback_and_no_clobber()
    print("PASS: importable API; blank-canvas color syntax and minimum capacity; redo pixel-equivalence for 1/2/5 passes; redo=128 strict decode; CLI blank binary/text examples; Android missing-os.link fallback and no-clobber protection")


if __name__ == "__main__":
    main()
