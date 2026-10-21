# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import binascii
import math
import random

from PIL import Image, ImageDraw
import pytest

from hushraster.rawbarcode import (
    RawBarcodeError,
    _reserved,
    _rs_decode,
    _rs_encode,
    cobs_decode,
    cobs_encode,
    decode_image,
    encode_bytes,
)


@pytest.mark.parametrize("payload", [
    b"", b"hello", b"\0", b"\0\0\0", bytes(range(256)),
    b"A" * 10000, bytes(range(256)) * 20,
])
def test_headerless_raw_round_trip(payload: bytes) -> None:
    image = encode_bytes(payload)
    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert max(image.size) < 2000
    assert decode_image(image) == payload


def test_cobs_round_trip_and_no_zero_inside_encoded_frame() -> None:
    for payload in (b"", b"\0", b"abc", bytes(range(256)), b"\0abc\0\xff"):
        encoded = cobs_encode(payload)
        assert b"\0" not in encoded
        assert cobs_decode(encoded) == payload


@pytest.mark.parametrize("nsym", [8, 16, 24, 32, 48])
def test_reed_solomon_corrects_half_parity_symbols(nsym: int) -> None:
    rng = random.Random(1000 + nsym)
    capacity = 255 - nsym
    original = bytes(rng.randrange(256) for _ in range(min(100, capacity)))
    encoded = bytearray(_rs_encode(original, nsym))
    error_count = nsym // 2
    positions = rng.sample(range(len(encoded)), error_count)
    for pos in positions:
        encoded[pos] ^= rng.randrange(1, 256)
    restored = _rs_decode(bytes(encoded), nsym)
    assert restored == _rs_encode(original, nsym)
    assert restored[:-nsym] == original


def _data_module_positions(image: Image.Image):
    grid_w = image.width - 2
    grid_h = image.height - 2
    positions = []
    for y in range(grid_h):
        for x in range(grid_w):
            if not _reserved(x, y, grid_w, grid_h):
                positions.append((x + 1, y + 1))
    return positions


def _flip_wire_byte_symbols(image: Image.Image, byte_indexes: list[int]) -> Image.Image:
    damaged = image.copy()
    pixels = damaged.load()
    positions = _data_module_positions(damaged)
    for byte_index in byte_indexes:
        x, y = positions[byte_index * 8]  # flip one bit in each distinct RS symbol
        old = pixels[x, y]
        pixels[x, y] = (0, 0, 0) if old[0] > 127 else (255, 255, 255)
    return damaged


def test_byte_level_error_correction_recovers_four_damaged_symbols() -> None:
    payload = b"Hello, World!"
    clean = encode_bytes(payload)
    damaged = _flip_wire_byte_symbols(clean, [0, 1, 2, 3])
    assert decode_image(damaged) == payload


def test_crc_rejects_more_symbol_errors_than_selected_level_can_correct() -> None:
    clean = encode_bytes(b"Hello, World!")  # short payload uses RS(?,8): corrects 4 symbols
    damaged = _flip_wire_byte_symbols(clean, [0, 1, 2, 3, 4])
    with pytest.raises(RawBarcodeError):
        decode_image(damaged)


def test_module_size_is_configurable_and_decoder_detects_it() -> None:
    payload = b"modules can be larger when needed"
    for module_size in (1, 2, 4, 7):
        image = encode_bytes(payload, module_size=module_size)
        assert decode_image(image) == payload


def test_rejects_unaligned_non_barcode_image() -> None:
    with pytest.raises(RawBarcodeError):
        decode_image(Image.new("RGB", (100, 100), "white"))



def test_interleaving_spreads_a_burst_over_multiple_rs_blocks() -> None:
    payload = bytes((i * 29) % 256 for i in range(1200))
    clean = encode_bytes(payload)
    # With RS(255,207), adjacent wire bytes are interleaved across blocks.
    damaged = _flip_wire_byte_symbols(clean, list(range(24)))
    assert decode_image(damaged) == payload


def _legacy_repeat_barcode(payload: bytes) -> Image.Image:
    """Construct a prior three-votes-per-bit raw barcode for compatibility tests."""
    crc = binascii.crc32(payload) & 0xFFFFFFFF
    frame = cobs_encode(payload) + b"\x00" + crc.to_bytes(4, "big")
    repeated = [bit for byte in frame for bit in ((byte >> shift) & 1 for shift in range(7, -1, -1)) for _ in range(3)]
    grid_w = max(32, math.ceil(math.sqrt(len(repeated) + 3 * 8 * 8)))
    rows = max(16, math.ceil((len(repeated) + 3 * 8 * 8) / grid_w))
    while grid_w * rows - 3 * 8 * 8 < len(repeated):
        rows += 1
    module, quiet, finder = 4, 4, 8
    image = Image.new("1", ((grid_w + 2 * quiet) * module, (rows + 2 * quiet) * module), 1)
    draw = ImageDraw.Draw(image)
    gx = gy = quiet * module
    def old_finder(ox: int, oy: int):
        for y in range(7):
            for x in range(7):
                dark = x in (0, 6) or y in (0, 6) or (2 <= x <= 4 and 2 <= y <= 4)
                if dark:
                    draw.rectangle((ox + x * module, oy + y * module,
                                    ox + (x + 1) * module - 1, oy + (y + 1) * module - 1), fill=0)
    old_finder(gx, gy)
    old_finder(gx + (grid_w - 7) * module, gy)
    old_finder(gx, gy + (rows - 7) * module)
    bit_index = 0
    for y in range(rows):
        for x in range(grid_w):
            if ((x < finder and y < finder) or
                (x >= grid_w - finder and y < finder) or
                (x < finder and y >= rows - finder)):
                continue
            if bit_index < len(repeated) and repeated[bit_index]:
                px, py = gx + x * module, gy + y * module
                draw.rectangle((px, py, px + module - 1, py + module - 1), fill=0)
            bit_index += 1
    return image.convert("RGB")


def test_previous_three_repeat_headerless_barcode_remains_decodable() -> None:
    payload = b"previous raw HushRaster format"
    assert decode_image(_legacy_repeat_barcode(payload)) == payload
