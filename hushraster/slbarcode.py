# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""SL1: single-row, variable-height bar transport with Reed-Solomon recovery.

Every visible mark is a solid vertical bar. Four bits are represented by one
of 16 bar heights. The raster has a fixed height and no finder shapes, logos,
text, or decorative geometry. This decoder expects the original raster grid;
Reed-Solomon correction repairs symbol errors but does not perform perspective
or arbitrary-resize correction.
"""
from __future__ import annotations

import binascii
import math
from PIL import Image, ImageDraw

from .rawbarcode import _rs_encode, _rs_decode

MAGIC = b"\x10"  # Compact one-byte identifier: two very short leading bars.
LEGACY_MAGIC = b"SL1\x00"  # Read older 1.0.1 SL1 images without breaking them.
DATA_BYTES = 223
PARITY_BYTES = 32
CODEWORD_BYTES = DATA_BYTES + PARITY_BYTES
QUIET = 1
MIN_BAR_MODULES = 5
MAX_BAR_MODULES = MIN_BAR_MODULES + 15
HEIGHT_MODULES = MAX_BAR_MODULES + 2 * QUIET
MAX_PPM = 32
MAX_PIXELS = 40_000_000


class SL1Error(ValueError):
    """An invalid or damaged SL1 barcode."""


def _interleave(blocks: list[bytes]) -> bytes:
    out = bytearray()
    for column in range(max(map(len, blocks), default=0)):
        for block in blocks:
            if column < len(block):
                out.append(block[column])
    return bytes(out)


def _infer_block_lengths(wire_length: int) -> list[int]:
    """Infer shortened RS codeword lengths from the raster's exact width."""
    if wire_length < len(MAGIC) + 8 + PARITY_BYTES:
        raise SL1Error("SL1 data stream is too short")
    # The original data length is wire_length - parity_bytes * block_count.
    for count in range(1, math.ceil(wire_length / (DATA_BYTES + PARITY_BYTES)) + 2):
        data_length = wire_length - count * PARITY_BYTES
        if (count - 1) * DATA_BYTES < data_length <= count * DATA_BYTES:
            last_data = data_length - (count - 1) * DATA_BYTES
            return [CODEWORD_BYTES] * (count - 1) + [last_data + PARITY_BYTES]
    raise SL1Error("SL1 width does not match a valid shortened Reed-Solomon stream")


def _deinterleave(stream: bytes, lengths: list[int]) -> list[bytes]:
    if not lengths or sum(lengths) != len(stream):
        raise SL1Error("Invalid SL1 interleaved codeword length")
    blocks = [bytearray(length) for length in lengths]
    offset = 0
    for column in range(max(lengths)):
        for block_index, block in enumerate(blocks):
            if column < lengths[block_index]:
                blocks[block_index][column] = stream[offset]
                offset += 1
    if offset != len(stream):
        raise SL1Error("Invalid SL1 interleaving layout")
    return [bytes(block) for block in blocks]


def encode_sl1(payload: bytes, *, ppm: int = 4, max_pixels: int = MAX_PIXELS) -> Image.Image:
    """Encode bytes as a single linear row of equally spaced bars of varying height."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("payload must be bytes-like")
    payload = bytes(payload)
    if isinstance(ppm, bool) or not isinstance(ppm, int) or not 1 <= ppm <= MAX_PPM:
        raise SL1Error(f"--ppm must be an integer from 1 through {MAX_PPM}")
    if isinstance(max_pixels, bool) or not isinstance(max_pixels, int) or max_pixels < 1:
        raise SL1Error("--max-pixels must be a positive integer")
    if len(payload) > 0xFFFFFFFF:
        raise SL1Error("Payload exceeds the 4-byte length field")

    crc = (binascii.crc32(payload) & 0xFFFFFFFF).to_bytes(4, "big")
    frame = MAGIC + len(payload).to_bytes(4, "big") + payload + crc
    blocks = [
        _rs_encode(frame[pos:pos + DATA_BYTES], PARITY_BYTES)
        for pos in range(0, len(frame), DATA_BYTES)
    ]
    wire = _interleave(blocks)

    # One nibble per bar. A bar's height, not its width or spacing, carries the nibble.
    bar_count = len(wire) * 2
    width_modules = bar_count * 2 + 1  # one-module left and right quiet margins
    width_px = width_modules * ppm
    height_px = HEIGHT_MODULES * ppm
    if width_px * height_px > min(max_pixels, MAX_PIXELS):
        raise SL1Error(
            f"SL1 would need {width_px * height_px:,} pixels, above the "
            f"{min(max_pixels, MAX_PIXELS):,}-pixel limit; lower --ppm or split the payload"
        )

    image = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(image)
    center_y = (HEIGHT_MODULES * ppm) // 2
    for bar_index in range(bar_count):
        byte = wire[bar_index // 2]
        nibble = (byte >> 4) if bar_index % 2 == 0 else (byte & 0x0F)
        bar_height = (MIN_BAR_MODULES + nibble) * ppm
        x0 = (QUIET + 2 * bar_index) * ppm
        x1 = x0 + ppm - 1
        # Each bar is centred on the same horizontal midline.
        y0 = center_y - (bar_height // 2)
        y1 = y0 + bar_height - 1
        draw.rectangle((x0, y0, x1, y1), fill="black")
    return image


def is_sl1_geometry(image: Image.Image, *, max_pixels: int = MAX_PIXELS) -> bool:
    """Cheap geometry gate used by automatic standard detection."""
    if not isinstance(image, Image.Image) or image.width <= 0 or image.height <= 0:
        return False
    if image.width * image.height > min(max_pixels, MAX_PIXELS):
        return False
    if image.height % HEIGHT_MODULES:
        return False
    ppm = image.height // HEIGHT_MODULES
    if not 1 <= ppm <= MAX_PPM or image.width % ppm:
        return False
    width_modules = image.width // ppm
    if width_modules < (4 * (len(MAGIC) + 8 + PARITY_BYTES) + 1):
        return False
    return (width_modules - 1) % 4 == 0


def decode_sl1(image: Image.Image, *, max_pixels: int = MAX_PIXELS) -> bytes:
    """Decode SL1 bytes, correcting up to 16 unknown byte-symbol errors/codeword."""
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a Pillow Image")
    if image.width <= 0 or image.height <= 0 or image.width * image.height > min(max_pixels, MAX_PIXELS):
        raise SL1Error(f"Image exceeds the {min(max_pixels, MAX_PIXELS):,}-pixel safety limit")
    if not is_sl1_geometry(image, max_pixels=max_pixels):
        raise SL1Error("Image dimensions do not match the SL1 linear-bar grid")

    im = image.convert("RGB")
    ppm = im.height // HEIGHT_MODULES
    width_modules = im.width // ppm
    wire_length = (width_modules - 1) // 4
    block_lengths = _infer_block_lengths(wire_length)
    bar_count = wire_length * 2
    levels: list[int] = []

    # Sampling module centres makes a missing segment or altered bar height an
    # ordinary nibble/symbol error that RS can repair, rather than a hard failure.
    for bar_index in range(bar_count):
        x = ((QUIET + 2 * bar_index) * ppm) + ppm // 2
        dark_modules = 0
        for y_module in range(QUIET, HEIGHT_MODULES - QUIET):
            y = y_module * ppm + ppm // 2
            r, g, b = im.getpixel((x, y))
            if r < 128 and g < 128 and b < 128:
                dark_modules += 1
        # Clamp damaged/extreme measurements to a valid symbol. The RS layer
        # then decides whether the number of altered byte symbols is recoverable.
        nibble = min(15, max(0, int(round(dark_modules)) - MIN_BAR_MODULES))
        levels.append(nibble)

    wire_out = bytearray()
    for pos in range(0, len(levels), 2):
        wire_out.append((levels[pos] << 4) | levels[pos + 1])
    blocks = _deinterleave(bytes(wire_out), block_lengths)
    decoded = bytearray()
    try:
        for block in blocks:
            decoded.extend(_rs_decode(block, PARITY_BYTES)[:-PARITY_BYTES])
    except Exception as exc:
        raise SL1Error(f"SL1 Reed-Solomon recovery failed: {exc}") from exc

    raw = bytes(decoded)
    # New images use a one-byte identifier to keep the opening pattern tiny.
    # Accept the previous four-byte identifier as well for existing SL1 images.
    if raw.startswith(MAGIC):
        marker_length = len(MAGIC)
    elif raw.startswith(LEGACY_MAGIC):
        marker_length = len(LEGACY_MAGIC)
    else:
        raise SL1Error("Invalid SL1 data marker")
    if len(raw) < marker_length + 8:
        raise SL1Error("SL1 data stream is too short")
    length = int.from_bytes(raw[marker_length:marker_length + 4], "big")
    start = marker_length + 4
    end = start + length
    if end + 4 > len(raw):
        raise SL1Error("Declared SL1 payload exceeds decoded data")
    payload = raw[start:end]
    stored_crc = int.from_bytes(raw[end:end + 4], "big")
    expected_crc = binascii.crc32(payload) & 0xFFFFFFFF
    if stored_crc != expected_crc:
        raise SL1Error("SL1 payload CRC32 mismatch")
    return payload
