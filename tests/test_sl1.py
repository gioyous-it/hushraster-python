# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import binascii
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from hushraster.slbarcode import (
    HEIGHT_MODULES, MAX_BAR_MODULES, MIN_BAR_MODULES, QUIET,
    MAGIC, LEGACY_MAGIC, DATA_BYTES, PARITY_BYTES, CODEWORD_BYTES,
    MAX_PIXELS, decode_sl1, encode_sl1, _interleave,
)
from hushraster.rawbarcode import _rs_encode

ROOT = Path(__file__).resolve().parents[1]

def run(args, payload=b""):
    return subprocess.run(
        [sys.executable, "-m", "hushraster", *args], cwd=ROOT, input=payload,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90, check=False,
    )

def _bar_nibble(image: Image.Image, index: int, ppm: int) -> int:
    x = (QUIET + 2 * index) * ppm + ppm // 2
    dark_modules = 0
    for row in range(QUIET, HEIGHT_MODULES - QUIET):
        y = row * ppm + ppm // 2
        r, g, b = image.convert("RGB").getpixel((x, y))
        dark_modules += r < 128 and g < 128 and b < 128
    return max(0, min(15, dark_modules - MIN_BAR_MODULES))

def _replace_bar_height(image: Image.Image, index: int, nibble: int, ppm: int) -> None:
    draw = ImageDraw.Draw(image)
    x0 = (QUIET + 2 * index) * ppm
    x1 = x0 + ppm - 1
    bottom = image.height - QUIET * ppm - 1
    draw.rectangle((x0, 0, x1, image.height - 1), fill="white")
    height = (MIN_BAR_MODULES + nibble) * ppm
    draw.rectangle((x0, bottom - height + 1, x1, bottom), fill="black")

def test_pipe_cli_outputs_actual_single_row_bar_png_and_auto_decodes():
    payload = b"HushRaster SL1 sample: https://gioyous.it/hushraster/sl1"
    encoded = run(["encode", "sl1+", "--ppm", "2"], payload)
    assert encoded.returncode == 0, encoded.stderr.decode(errors="replace")
    assert encoded.stdout.startswith(b"\x89PNG\r\n\x1a\n")
    image = Image.open(__import__("io").BytesIO(encoded.stdout)).convert("RGB")
    assert image.height == HEIGHT_MODULES * 2
    colors = image.getcolors(maxcolors=2)
    assert colors is not None
    assert {color for _count, color in colors} <= {(255, 255, 255), (0, 0, 0)}
    decoded = run(["decode"], encoded.stdout)
    assert decoded.returncode == 0, decoded.stderr.decode(errors="replace")
    assert decoded.stdout == payload
    explicitly_decoded = run(["decode", "sl1+"], encoded.stdout)
    assert explicitly_decoded.returncode == 0, explicitly_decoded.stderr.decode(errors="replace")
    assert explicitly_decoded.stdout == payload

def test_sl1_corrects_16_unknown_byte_symbol_errors_in_one_codeword():
    payload = b"ecc proof"
    image = encode_sl1(payload, ppm=1)
    original = image.copy()
    # Alter the two nibbles representing each of the first 16 interleaved bytes.
    # This is at the advertised per-codeword correction limit (32 parity symbols).
    for bar in range(32):
        new_nibble = (_bar_nibble(original, bar, 1) + 1) % 16
        _replace_bar_height(image, bar, new_nibble, 1)
    assert decode_sl1(image) == payload

def test_sl1_variable_heights_and_empty_payload():
    image = encode_sl1(b"", ppm=2)
    assert decode_sl1(image) == b""
    assert image.height == HEIGHT_MODULES * 2
    levels = {_bar_nibble(image, i, 2) for i in range((image.width // 2 - 1) // 2)}
    assert len(levels) > 1


def test_sl1_uses_compact_identifier_and_reads_legacy_images():
    assert len(MAGIC) == 1
    assert len(LEGACY_MAGIC) == 4
    payload = b"compact identifier test"
    assert decode_sl1(encode_sl1(payload, ppm=2)) == payload

    # Build an image using the former four-byte SL1 identifier to guard
    # backward compatibility with existing 1.0.1 images.
    crc = (binascii.crc32(payload) & 0xFFFFFFFF).to_bytes(4, "big")
    frame = LEGACY_MAGIC + len(payload).to_bytes(4, "big") + payload + crc
    blocks = [
        _rs_encode(frame[pos:pos + DATA_BYTES], PARITY_BYTES)
        for pos in range(0, len(frame), DATA_BYTES)
    ]
    wire = _interleave(blocks)
    ppm = 2
    width = (len(wire) * 4 + 1) * ppm
    height = HEIGHT_MODULES * ppm
    legacy = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(legacy)
    center_y = height // 2
    for index in range(len(wire) * 2):
        value = wire[index // 2]
        nibble = value >> 4 if index % 2 == 0 else value & 0x0F
        bar_height = (MIN_BAR_MODULES + nibble) * ppm
        x0 = (QUIET + 2 * index) * ppm
        y0 = center_y - bar_height // 2
        draw.rectangle((x0, y0, x0 + ppm - 1, y0 + bar_height - 1), fill="black")
    assert decode_sl1(legacy) == payload

