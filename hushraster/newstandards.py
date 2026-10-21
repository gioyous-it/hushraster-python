# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""HushRaster standalone barcode encoders and decoders for all raster families.

P3 and OI2 are deliberately raw: they store a length and exact payload bytes,
without compression, checksum, or error correction. CE1 adds a CRC32 check and
uses a base-5 alphabet across five exact RGB colours. Z1 is a monochrome striped
variant with a CRC32 check but no error correction.
"""
from __future__ import annotations

import binascii
import hashlib
import math
from functools import lru_cache
from typing import Iterable

import numpy as np
from PIL import Image

from .standards import ADDITIONAL_TREES, _ADDITIONAL_METHODS

MAX_PIXELS = 40_000_000
DEFAULT_PPM = 4
MIN_PPM = 1
MAX_PPM = 32
QUIET_MODULES = 1
FINDER_SIZE = 5

# These visual trees use distinct negative/positive microglyphs at readable densities.
# At ppm=1 or 2 every microglyph collapses to a single binary module for compactness.
STYLE_TREE_CODES = tuple(ADDITIONAL_TREES)
_STYLE_INDEX = {code: index for index, code in enumerate(STYLE_TREE_CODES)}
_FULL_RS_METHODS = {"rs16": 16, "rs24": 24, "rs32": 32, "rs48": 48, "rs64": 64}

# Palette order is part of CE1's wire format: black, white, red, green, blue.
CE1_PALETTE: tuple[tuple[int, int, int], ...] = (
    (0, 0, 0),
    (255, 255, 255),
    (255, 0, 0),
    (0, 192, 0),
    (0, 0, 255),
)

# Each standard has a different corner marker, so simple/raw formats are not
# casually misidentified as one another during auto-detection.
TEMPLATES: dict[str, tuple[tuple[int, ...], ...]] = {
    "p3": (
        (1, 1, 1, 1, 1),
        (1, 0, 0, 0, 1),
        (1, 0, 1, 0, 1),
        (1, 0, 0, 0, 1),
        (1, 1, 1, 1, 1),
    ),
    "oi2": (
        (1, 1, 1, 1, 1),
        (1, 0, 0, 1, 1),
        (1, 0, 1, 0, 1),
        (1, 1, 0, 0, 1),
        (1, 1, 1, 1, 1),
    ),
    "ce1": (
        (0, 1, 2, 3, 4),
        (1, 0, 0, 0, 1),
        (2, 0, 4, 0, 2),
        (3, 0, 0, 0, 3),
        (4, 3, 2, 1, 0),
    ),
    "z1": (
        (1, 0, 1, 0, 1),
        (0, 1, 0, 1, 0),
        (1, 0, 1, 0, 1),
        (0, 1, 0, 1, 0),
        (1, 0, 1, 0, 1),
    ),
}



class NewBarcodeError(ValueError):
    """An invalid or undecodable standalone HushRaster barcode."""


def _length_prefix(payload: bytes) -> bytes:
    if len(payload) > 0xFFFFFFFF:
        raise NewBarcodeError("Payload exceeds the 4-byte (4 GiB) length field")
    return len(payload).to_bytes(4, "big") + payload


def _bits(data: bytes) -> list[int]:
    return [(byte >> shift) & 1 for byte in data for shift in range(7, -1, -1)]


def _bits_to_bytes(bits: Iterable[int]) -> bytes:
    result = bytearray()
    value = 0
    count = 0
    for bit in bits:
        value = (value << 1) | (int(bit) & 1)
        count += 1
        if count == 8:
            result.append(value)
            value = 0
            count = 0
    return bytes(result)


def _reserved(x: int, y: int, width: int, height: int, *, single_finder: bool = False) -> bool:
    f = FINDER_SIZE
    if single_finder:
        return x < f and y < f
    return (x < f and y < f) or (x >= width - f and y < f) or (x < f and y >= height - f)


def _data_positions(width: int, height: int, *, single_finder: bool = False) -> Iterable[tuple[int, int]]:
    for y in range(height):
        for x in range(width):
            if not _reserved(x, y, width, height, single_finder=single_finder):
                yield x, y


def _geometry(needed_modules: int, ppm: int, max_pixels: int, *, single_finder: bool = False) -> tuple[int, int]:
    if isinstance(ppm, bool) or not isinstance(ppm, int) or not MIN_PPM <= ppm <= MAX_PPM:
        raise NewBarcodeError(f"--ppm must be an integer from {MIN_PPM} through {MAX_PPM}")
    if isinstance(max_pixels, bool) or not isinstance(max_pixels, int) or max_pixels < 1:
        raise NewBarcodeError("--max-pixels must be a positive integer")
    max_pixels = min(max_pixels, MAX_PIXELS)
    finder_count = 1 if single_finder else 3
    finder_modules = finder_count * FINDER_SIZE * FINDER_SIZE
    minimum_side = FINDER_SIZE + 1 if single_finder else 2 * FINDER_SIZE + 1
    total_modules = max(needed_modules + finder_modules, minimum_side * minimum_side)
    side = max(minimum_side, math.ceil(math.sqrt(total_modules)))
    candidates: list[tuple[int, float, int]] = []
    # Keep barcode dimensions roughly square. Pure minimum-area factor pairs can
    # accidentally produce long, narrow strips which are poor scan targets.
    start = max(minimum_side, int(side / 1.20))
    end = int(side * 1.20) + 2
    for width in range(start, end + 1):
        height = max(minimum_side, (total_modules + width - 1) // width)
        ratio = max(width, height) / min(width, height)
        if ratio > 1.20:
            continue
        area = width * height
        if area - finder_modules < needed_modules:
            continue
        pixel_area = (width + 2 * QUIET_MODULES) * (height + 2 * QUIET_MODULES) * ppm * ppm
        if pixel_area <= max_pixels:
            candidates.append((area, ratio, width))
    if not candidates:
        minimum = (minimum_side + 2) ** 2 * ppm * ppm
        if minimum > max_pixels:
            raise NewBarcodeError(f"--max-pixels is too small; this barcode needs at least {minimum:,} raster pixels")
        raise NewBarcodeError(f"Barcode would exceed the {max_pixels:,}-pixel safety limit; lower --ppm or use a smaller payload")
    _area, _ratio, width = min(candidates)
    height = max(minimum_side, (total_modules + width - 1) // width)
    while width * height - finder_modules < needed_modules:
        height += 1
    if (width + 2) * (height + 2) * ppm * ppm > max_pixels:
        raise NewBarcodeError(f"Barcode would exceed the {max_pixels:,}-pixel safety limit")
    return width, height


def _generated_template(standard: str) -> tuple[tuple[int, ...], ...]:
    """Stable per-standard finder template; visual signatures are part of each format."""
    import hashlib
    digest = hashlib.sha256(("HushRaster finder:" + standard.upper()).encode("ascii")).digest()
    colored = standard.startswith("ce")
    alphabet = 5 if colored else 2
    values = []
    for y in range(FINDER_SIZE):
        row = []
        for x in range(FINDER_SIZE):
            byte = digest[(y * FINDER_SIZE + x) % len(digest)]
            row.append(byte % alphabet)
        values.append(tuple(row))
    return tuple(values)


def _template_value(standard: str, x: int, y: int) -> int:
    template = TEMPLATES.get(standard)
    if template is None:
        template = _generated_template(standard)
    return template[y % FINDER_SIZE][x % FINDER_SIZE]


_STYLE_CORE_GLYPHS = (
    ("..##", "#..#", "#...", "...."),  # Arc
    ("#...", ".#..", "..#.", "...#"),  # Braid
    ("....", ".##.", ".##.", "...."),  # Facet
    ("#..#", "....", "....", "#..#"),  # Grid
    (".#..", "#..#", "..#.", "...."),  # Iris
    (".#..", "#...", "...#", "..#."),  # Junction
    ("....", ".#..", "###.", "...."),  # Keystone
    ("#..#", ".##.", "....", "...."),  # Nexus
    ("#...", ".#..", "..##", "...."),  # Quick
    ("#...", "...#", "..#.", "#..."),  # Resilient
    ("###.", "...#", "..#.", ".##."),  # Spiral
    ("....", ".#..", "###.", ".#.."),  # Umbra
    ("...#", "..#.", ".##.", "..#."),  # Vector
    (".#.#", "....", "#.#.", "...."),  # Weave
    ("....", ".#..", "####", ".#.."),  # Cross
    ("#...", "##..", ".#..", "...."),  # Asymmetric
    ("#..#", ".##.", "....", "#..."),  # Adaptive Array
    ("####", "....", ".##.", "...."),  # Bridge
    ("#.#.", "....", ".#.#", "...."),  # Compact Payload
    ("#...", ".#..", "...#", "..#."),  # Staggered
)


def _styled_core(style: int, u: float, v: float) -> bool:
    """Sample a sparse 4x4 tree glyph; its inverse is the encoded one glyph."""
    gx = min(3, max(0, int((u + 1.0) * 2.0)))
    gy = min(3, max(0, int((v + 1.0) * 2.0)))
    return _STYLE_CORE_GLYPHS[style][gy][gx] == "#"


@lru_cache(maxsize=640)
def _styled_mask(style: int, ppm: int) -> np.ndarray:
    """Vectorized 4x4 microglyph bitmap at a requested module pitch."""
    glyph = np.asarray([[cell == "#" for cell in row] for row in _STYLE_CORE_GLYPHS[style]], dtype=bool)
    axis = np.minimum(3, ((np.arange(ppm, dtype=np.float64) + 0.5) * 4.0 / ppm).astype(np.int64))
    return glyph[axis[:, None], axis[None, :]]


def _make_raster(
    standard: str,
    symbols: list[int],
    *,
    ppm: int,
    max_pixels: int,
    diagonal: bool = False,
    striped: bool = False,
    colored: bool = False,
    mosaic: bool = False,
    hexagonal: bool = False,
    triangular: bool = False,
    styled_tree: str | None = None,
) -> Image.Image:
    needed = len(symbols) if colored else len(symbols)
    single_finder = standard == "r1"
    width, height = _geometry(needed, ppm, max_pixels, single_finder=single_finder)
    rows, cols = height + 2, width + 2
    raster = np.full((rows * ppm, cols * ppm, 3), 255, dtype=np.uint8)
    positions = list(_data_positions(width, height, single_finder=single_finder))
    if len(symbols) > len(positions):
        raise NewBarcodeError("Internal error: generated grid does not fit the payload")
    # Binary formats put zero padding after the data. CE1 uses the opposite
    # alignment: leading base-5 zero symbols preserve its packed integer.
    if colored:
        padded = [0] * (len(positions) - len(symbols)) + symbols
    else:
        padded = symbols + [0] * (len(positions) - len(symbols))
    by_position = dict(zip(positions, padded))

    for y in range(height):
        for x in range(width):
            py0 = (y + QUIET_MODULES) * ppm
            px0 = (x + QUIET_MODULES) * ppm
            if _reserved(x, y, width, height, single_finder=single_finder):
                if x < FINDER_SIZE and y < FINDER_SIZE:
                    fx, fy = x, y
                elif x >= width - FINDER_SIZE and y < FINDER_SIZE:
                    fx, fy = x - (width - FINDER_SIZE), y
                else:
                    fx, fy = x, y - (height - FINDER_SIZE)
                val = _template_value(standard, fx, fy)
                if colored:
                    color = CE1_PALETTE[val]
                else:
                    color = (0, 0, 0) if val else (255, 255, 255)
                raster[py0:py0 + ppm, px0:px0 + ppm] = color
                continue
            val = by_position[(x, y)]
            if colored:
                raster[py0:py0 + ppm, px0:px0 + ppm] = CE1_PALETTE[val]
            elif diagonal and ppm >= 2:
                # Diagonal tree: each module is an actual data-bearing slash glyph.
                for delta in range(ppm):
                    raster[py0 + delta, px0 + (ppm - 1 - delta if val else delta)] = (0, 0, 0)
            elif mosaic and ppm >= 2:
                # Mosaic tree: a checker-cell is encoded by its diagonal phase.
                # At ppm=1 it falls back to a solid module for maximum density.
                for sy in range(ppm):
                    for sx in range(ppm):
                        if ((sx + sy) & 1) == int(bool(val)):
                            raster[py0 + sy, px0 + sx] = (0, 0, 0)
            elif hexagonal and ppm >= 3:
                # Hexa tree: black hexagonal outline with the centre carrying bit 0/1.
                mid = (ppm - 1) / 2
                for sy in range(ppm):
                    for sx in range(ppm):
                        nx = abs((sx - mid) / max(mid, 0.5))
                        ny = abs((sy - mid) / max(mid, 0.5))
                        inside = nx <= 1.0 and ny <= 1.0 and (nx + 0.58 * ny) <= 1.0
                        ring = inside and (nx >= 0.48 or ny >= 0.58)
                        if ring:
                            raster[py0 + sy, px0 + sx] = (0, 0, 0)
                centre = int(round(mid))
                if val:
                    raster[py0 + centre, px0 + centre] = (0, 0, 0)
            elif triangular and ppm >= 3:
                # Triangle tree: 0 is an upward triangle; 1 is a downward triangle.
                for sy in range(ppm):
                    yy = (sy + 0.5) / ppm
                    half_width = 0.5 * (1.0 - yy if val else yy)
                    for sx in range(ppm):
                        xx = (sx + 0.5) / ppm
                        if abs(xx - 0.5) <= half_width:
                            raster[py0 + sy, px0 + sx] = (0, 0, 0)
            elif styled_tree is not None and ppm >= 4:
                style_index = _STYLE_INDEX[styled_tree]
                core = _styled_mask(style_index, ppm)
                # All style cores occupy < 45% of a cell; their inverse fills > 55%.
                dark = core if not val else ~core
                raster[py0:py0 + ppm, px0:px0 + ppm] = np.where(dark[:, :, None], 0, 255).astype(np.uint8)
            else:
                bit = val
                if striped:
                    bit ^= (x + y) & 1
                if bit:
                    raster[py0:py0 + ppm, px0:px0 + ppm] = (0, 0, 0)

    return Image.fromarray(raster, "RGB")


def encode_p3(payload: bytes, *, ppm: int = DEFAULT_PPM, max_pixels: int = MAX_PIXELS) -> Image.Image:
    """Encode length-prefixed raw bytes: no CRC, compression, or error correction."""
    frame = _length_prefix(bytes(payload))
    return _make_raster("p3", _bits(frame), ppm=ppm, max_pixels=max_pixels)


def encode_oi2(payload: bytes, *, ppm: int = DEFAULT_PPM, max_pixels: int = MAX_PIXELS) -> Image.Image:
    """Encode a real diagonal-cell barcode, independent of OI1/IMGMod."""
    payload = bytes(payload)
    if len(payload) > 0xFFFFFFFF:
        raise NewBarcodeError("Payload exceeds the 4-byte (4 GiB) length field")
    frame = b"OI2\x00" + len(payload).to_bytes(4, "big") + payload
    return _make_raster("oi2", _bits(frame), ppm=ppm, max_pixels=max_pixels, diagonal=True)


def encode_d1(payload: bytes, *, ppm: int = DEFAULT_PPM, max_pixels: int = MAX_PIXELS) -> Image.Image:
    """Encode the canonical D1 diagonal format with its own HRD1 wire marker.

    D1 intentionally uses length framing only: no checksum or error correction.
    The decoder still accepts legacy OI2-marked images for transition compatibility.
    """
    payload = bytes(payload)
    if len(payload) > 0xFFFFFFFF:
        raise NewBarcodeError("Payload exceeds the 4-byte (4 GiB) length field")
    frame = b"HRD1\x00" + len(payload).to_bytes(4, "big") + payload
    return _make_raster("d1", _bits(frame), ppm=ppm, max_pixels=max_pixels, diagonal=True)


def encode_z1(payload: bytes, *, ppm: int = DEFAULT_PPM, max_pixels: int = MAX_PIXELS) -> Image.Image:
    """Encode a checker-striped monochrome barcode with CRC32, without ECC."""
    payload = bytes(payload)
    frame = b"ZB1\x00" + _length_prefix(payload)
    frame += (binascii.crc32(payload) & 0xFFFFFFFF).to_bytes(4, "big")
    return _make_raster("z1", _bits(frame), ppm=ppm, max_pixels=max_pixels, striped=True)


def _base5_digits(value: int) -> list[int]:
    if value == 0:
        return [0]
    digits: list[int] = []
    while value:
        value, digit = divmod(value, 5)
        digits.append(digit)
    digits.reverse()
    return digits


def encode_ce1(payload: bytes, *, ppm: int = DEFAULT_PPM, max_pixels: int = MAX_PIXELS) -> Image.Image:
    """Encode data through five exact RGB colours; 1 module carries one base-5 digit."""
    payload = bytes(payload)
    if len(payload) > 0xFFFFFFFF:
        raise NewBarcodeError("Payload exceeds the 4-byte (4 GiB) length field")
    crc = (binascii.crc32(payload) & 0xFFFFFFFF).to_bytes(4, "big")
    # Leading 0x43 avoids leading-zero loss in integer packing. The terminal
    # 0x01 protects any zero bytes at the tail of the frame during conversion.
    frame = b"CE1\x00" + len(payload).to_bytes(4, "big") + payload + crc + b"\x01"
    digits = _base5_digits(int.from_bytes(frame, "big"))
    return _make_raster("ce1", digits, ppm=ppm, max_pixels=max_pixels, colored=True)


def _as_image(image: Image.Image) -> Image.Image:
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a Pillow Image")
    if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_PIXELS:
        raise NewBarcodeError(f"Image exceeds the {MAX_PIXELS:,}-pixel safety limit")
    return image.convert("RGB")


def _get_grid(im: Image.Image, ppm: int) -> tuple[int, int] | None:
    if im.width % ppm or im.height % ppm:
        return None
    width, height = im.width // ppm - 2, im.height // ppm - 2
    if width < 2 * FINDER_SIZE + 1 or height < 2 * FINDER_SIZE + 1:
        return None
    return width, height


def _possible_ppms(im: Image.Image) -> list[int]:
    """Only test module sizes that divide both raster dimensions."""
    from math import gcd
    upper = min(MAX_PPM, gcd(im.width, im.height))
    return [ppm for ppm in range(1, upper + 1) if im.width % ppm == 0 and im.height % ppm == 0]


def _rgb_module(im: Image.Image, x: int, y: int, ppm: int) -> tuple[int, int, int]:
    return tuple(int(v) for v in im.getpixel(((x + 1) * ppm + ppm // 2, (y + 1) * ppm + ppm // 2)))


def _is_dark(rgb: tuple[int, int, int]) -> bool:
    return sum(rgb) < 384


def _finders_match(im: Image.Image, standard: str, width: int, height: int, ppm: int, *, colored: bool, single_finder: bool = False) -> bool:
    origins = ((0, 0),) if single_finder else ((0, 0), (width - FINDER_SIZE, 0), (0, height - FINDER_SIZE))
    for ox, oy in origins:
        for fy in range(FINDER_SIZE):
            for fx in range(FINDER_SIZE):
                expected = _template_value(standard, fx, fy)
                actual = _rgb_module(im, ox + fx, oy + fy, ppm)
                if colored:
                    if _nearest_palette(actual) != expected:
                        return False
                elif _is_dark(actual) != bool(expected):
                    return False
    return True


def _nearest_palette(rgb: tuple[int, int, int]) -> int:
    return min(range(5), key=lambda i: sum((rgb[c] - CE1_PALETTE[i][c]) ** 2 for c in range(3)))


def _read_positions(width: int, height: int, *, single_finder: bool = False) -> list[tuple[int, int]]:
    return list(_data_positions(width, height, single_finder=single_finder))


def _read_binary_symbols(
    im: Image.Image, width: int, height: int, ppm: int, *, diagonal: bool,
    striped: bool, mosaic: bool = False, hexagonal: bool = False,
    triangular: bool = False, styled_tree: str | None = None, single_finder: bool = False,
) -> list[int]:
    result: list[int] = []
    dark_map = None
    if styled_tree is not None and ppm >= 4:
        rgb_array = np.asarray(im.convert("RGB"), dtype=np.uint8)
        dark_map = np.max(rgb_array, axis=2) < 200
    for x, y in _read_positions(width, height, single_finder=single_finder):
        x0, y0 = (x + 1) * ppm, (y + 1) * ppm
        if diagonal and ppm >= 2:
            main = anti = 0
            for offset in range(ppm):
                if _is_dark(tuple(int(v) for v in im.getpixel((x0 + offset, y0 + offset)))):
                    main += 1
                if _is_dark(tuple(int(v) for v in im.getpixel((x0 + ppm - 1 - offset, y0 + offset)))):
                    anti += 1
            bit = 1 if anti > main else 0
        elif mosaic and ppm >= 2:
            even = odd = 0
            for sy in range(ppm):
                for sx in range(ppm):
                    if _is_dark(tuple(int(v) for v in im.getpixel((x0 + sx, y0 + sy)))):
                        if (sx + sy) & 1:
                            odd += 1
                        else:
                            even += 1
            bit = 1 if odd > even else 0
        elif hexagonal and ppm >= 3:
            bit = 1 if _is_dark(tuple(int(v) for v in im.getpixel((x0 + ppm // 2, y0 + ppm // 2)))) else 0
        elif triangular and ppm >= 3:
            top = bottom = 0
            for sy in range(ppm):
                for sx in range(ppm):
                    if _is_dark(tuple(int(v) for v in im.getpixel((x0 + sx, y0 + sy)))):
                        if sy < ppm / 2:
                            top += 1
                        elif sy > (ppm - 1) / 2:
                            bottom += 1
            bit = 1 if top > bottom else 0
        elif styled_tree is not None and ppm >= 4:
            assert dark_map is not None
            dark = int(np.count_nonzero(dark_map[y0:y0 + ppm, x0:x0 + ppm]))
            bit = int(dark > (ppm * ppm / 2))
        else:
            bit = 1 if _is_dark(_rgb_module(im, x, y, ppm)) else 0
        if striped:
            bit ^= (x + y) & 1
        result.append(bit)
    return result


def _parse_length_frame(bits: list[int], *, standard: str, magic: bytes = b"", crc: bool = False) -> bytes:
    raw = _bits_to_bytes(bits)
    header_len = len(magic) + 4
    if len(raw) < header_len:
        raise NewBarcodeError("Not enough data modules for a payload-length header")
    if magic and raw[:len(magic)] != magic:
        raise NewBarcodeError(f"Invalid {standard.upper()} marker")
    start = len(magic)
    length = int.from_bytes(raw[start:start + 4], "big")
    body_start = header_len
    required = body_start + length + (4 if crc else 0)
    if len(raw) < required:
        raise NewBarcodeError("Declared payload length extends beyond available barcode modules")
    payload = raw[body_start:body_start + length]
    if crc:
        got = int.from_bytes(raw[body_start + length:required], "big")
        expected = binascii.crc32(payload) & 0xFFFFFFFF
        if got != expected:
            raise NewBarcodeError("CRC32 mismatch")
    return payload


def _decode_binary(im: Image.Image, standard: str, *, max_pixels: int = MAX_PIXELS) -> bytes:
    im = _as_image(im)
    if im.width * im.height > max_pixels:
        raise NewBarcodeError(f"Image exceeds the {max_pixels:,}-pixel safety limit")
    failures: list[str] = []
    for ppm in _possible_ppms(im):
        geometry = _get_grid(im, ppm)
        if geometry is None:
            continue
        width, height = geometry
        if not _finders_match(im, standard, width, height, ppm, colored=False):
            continue
        try:
            bits = _read_binary_symbols(
                im, width, height, ppm,
                diagonal=(standard in ("oi2", "d1")), striped=(standard == "z1"),
            )
            return _parse_length_frame(
                bits,
                standard=standard,
                magic=(b"HRD1\x00" if standard == "d1" else
                       b"OI2\x00" if standard == "oi2" else
                       b"ZB1\x00" if standard == "z1" else b""),
                crc=(standard == "z1"),
            )
        except NewBarcodeError as exc:
            failures.append(str(exc))
    suffix = f" ({failures[-1]})" if failures else ""
    raise NewBarcodeError(f"No valid {standard.upper()} barcode found{suffix}")


def decode_p3(image: Image.Image, *, max_pixels: int = MAX_PIXELS) -> bytes:
    return _decode_binary(image, "p3", max_pixels=max_pixels)


def decode_oi2(image: Image.Image, *, max_pixels: int = MAX_PIXELS) -> bytes:
    return _decode_binary(image, "oi2", max_pixels=max_pixels)


def decode_d1(image: Image.Image, *, max_pixels: int = MAX_PIXELS) -> bytes:
    """Decode canonical D1, with fallback to the former OI2 wire marker."""
    try:
        return _decode_binary(image, "d1", max_pixels=max_pixels)
    except NewBarcodeError as current_error:
        try:
            return decode_oi2(image, max_pixels=max_pixels)
        except NewBarcodeError:
            raise current_error


def decode_z1(image: Image.Image, *, max_pixels: int = MAX_PIXELS) -> bytes:
    return _decode_binary(image, "z1", max_pixels=max_pixels)


def decode_ce1(image: Image.Image, *, max_pixels: int = MAX_PIXELS) -> bytes:
    im = _as_image(image)
    if im.width * im.height > max_pixels:
        raise NewBarcodeError(f"Image exceeds the {max_pixels:,}-pixel safety limit")
    failures: list[str] = []
    for ppm in _possible_ppms(im):
        geometry = _get_grid(im, ppm)
        if geometry is None:
            continue
        width, height = geometry
        if not _finders_match(im, "ce1", width, height, ppm, colored=True):
            continue
        digits = [_nearest_palette(_rgb_module(im, x, y, ppm)) for x, y in _read_positions(width, height)]
        number = 0
        for digit in digits:
            number = number * 5 + digit
        if number == 0:
            failures.append("empty base-5 body")
            continue
        raw = number.to_bytes(max(1, (number.bit_length() + 7) // 8), "big")
        if not raw.startswith(b"CE1\x00") or len(raw) < 13:
            failures.append("invalid CE1 marker/header")
            continue
        length = int.from_bytes(raw[4:8], "big")
        required = 8 + length + 4 + 1
        if len(raw) < required or raw[required - 1] != 1:
            failures.append("invalid CE1 payload length or terminator")
            continue
        payload = raw[8:8 + length]
        stored_crc = int.from_bytes(raw[8 + length:12 + length], "big")
        if stored_crc != (binascii.crc32(payload) & 0xFFFFFFFF):
            failures.append("CRC32 mismatch")
            continue
        return payload
    suffix = f" ({failures[-1]})" if failures else ""
    raise NewBarcodeError(f"No valid CE1 barcode found{suffix}")


# Every numbered variant below has a standard-specific wire marker, data transform,
# and finder signature. Family membership describes the rendering concept, not
# backwards-compatible aliasing to a previous member.
VARIANT_METHODS: dict[str, str] = {}
for _i, _method in zip(range(4, 14), (
    "rawcrc", "repbyte3", "repbit3", "repbyte5", "mask", "bitrev",
    "interleave", "hamming", "rs8", "parity8",
)):
    VARIANT_METHODS[f"p{_i}"] = _method
for _i, _method in zip(range(2, 12), (
    "rs8", "hamming", "repbyte3", "repbit3", "repbyte5",
    "interleave", "mask", "bitrev", "parity8", "delta",
)):
    VARIANT_METHODS[f"d{_i}"] = _method
for _family in ("ce", "z"):
    for _i, _method in zip(range(2, 12), (
        "repbyte3", "repbit3", "repbyte5", "mask", "bitrev",
        "interleave", "hamming", "rs8", "parity8", "delta",
    )):
        VARIANT_METHODS[f"{_family}{_i}"] = _method
# Three additional format trees each have ten numbered, individually framed
# standards. Their module graphics (mosaic, hexagonal, triangular) are intrinsic
# to the tree; numbered entries have unique wire IDs and per-standard finder maps.
for _family in ("m", "h", "t"):
    for _i, _method in zip(range(1, 11), (
        "repbyte3", "repbit3", "repbyte5", "mask", "bitrev",
        "interleave", "hamming", "rs8", "parity8", "delta",
    )):
        VARIANT_METHODS[f"{_family}{_i}"] = _method

# The 20 added trees each define ten concrete encodings with individual wire IDs.
for _family, _methods in _ADDITIONAL_METHODS.items():
    for _i, _method in enumerate(_methods, start=1):
        VARIANT_METHODS[f"{_family}{_i}"] = _method


def _rs_body_size(data_length: int, parity: int) -> int:
    if data_length <= 0:
        return 0
    capacity = 255 - parity
    return data_length + parity * math.ceil(data_length / capacity)


def _body_size(length: int, method: str) -> int:
    if method == "repbyte3": return length * 3
    if method == "repbit3": return length * 3
    if method == "repbyte5": return length * 5
    if method == "hamming": return (length * 14 + 7) // 8
    if method == "rs8": return length + 8 * ((length + 246) // 247)
    if method == "parity8": return length + ((length + 7) // 8)
    if method in _FULL_RS_METHODS:
        # These levels protect the payload CRC inside the RS code, too.
        data_length = length + 4
        return _rs_body_size(data_length, _FULL_RS_METHODS[method])
    return length


def _mask_bytes(data: bytes, code: str) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < len(data):
        out.extend(hashlib.sha256(b"HushRaster mask v1:" + code.upper().encode("ascii") + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(a ^ b for a, b in zip(data, out))


def _reverse_byte(value: int) -> int:
    value = ((value & 0xF0) >> 4) | ((value & 0x0F) << 4)
    value = ((value & 0xCC) >> 2) | ((value & 0x33) << 2)
    return ((value & 0xAA) >> 1) | ((value & 0x55) << 1)


def _hamming_encode(data: bytes) -> bytes:
    bits: list[int] = []
    for byte in data:
        for nibble in (byte >> 4, byte & 15):
            d1, d2, d3, d4 = ((nibble >> 3) & 1, (nibble >> 2) & 1, (nibble >> 1) & 1, nibble & 1)
            p1, p2, p4 = d1 ^ d2 ^ d4, d1 ^ d3 ^ d4, d2 ^ d3 ^ d4
            bits.extend((p1, p2, d1, p4, d2, d3, d4))
    bits.extend([0] * ((-len(bits)) % 8))
    return _bits_to_bytes(bits)


def _hamming_decode(data: bytes, original_length: int) -> bytes:
    bits = _bits(data)[:original_length * 14]
    output = bytearray()
    nibbles = []
    if len(bits) != original_length * 14:
        raise NewBarcodeError("Truncated Hamming body")
    for off in range(0, len(bits), 7):
        word = [0] + bits[off:off + 7]
        syndrome = (word[1] ^ word[3] ^ word[5] ^ word[7]) \
            | ((word[2] ^ word[3] ^ word[6] ^ word[7]) << 1) \
            | ((word[4] ^ word[5] ^ word[6] ^ word[7]) << 2)
        if syndrome:
            word[syndrome] ^= 1
        nibbles.append((word[3] << 3) | (word[5] << 2) | (word[6] << 1) | word[7])
    for i in range(0, len(nibbles), 2):
        output.append((nibbles[i] << 4) | nibbles[i + 1])
    return bytes(output)


def _rs_interleaved_encode(data: bytes, parity: int) -> bytes:
    """Encode shortened RS codewords and interleave their symbols round-robin."""
    from .rawbarcode import _rs_encode
    capacity = 255 - parity
    chunks = [data[i:i + capacity] for i in range(0, len(data), capacity)]
    if not chunks:
        chunks = [b"\x00"]
    words = [_rs_encode(chunk, parity) for chunk in chunks]
    out = bytearray()
    for column in range(max(map(len, words))):
        for word in words:
            if column < len(word):
                out.append(word[column])
    return bytes(out)


def _rs_interleaved_decode(data: bytes, data_length: int, parity: int) -> bytes:
    """Undo _rs_interleaved_encode and repair all codewords up to parity//2 errors."""
    from .rawbarcode import _rs_decode, RawBarcodeError
    capacity = 255 - parity
    chunk_lengths = [min(capacity, data_length - offset) for offset in range(0, data_length, capacity)]
    if not chunk_lengths:
        chunk_lengths = [1]
    words = [bytearray(n + parity) for n in chunk_lengths]
    expected_size = sum(map(len, words))
    if len(data) < expected_size:
        raise NewBarcodeError("Truncated high-correction Reed-Solomon body")
    cursor = 0
    for column in range(max(map(len, words))):
        for word in words:
            if column < len(word):
                word[column] = data[cursor]
                cursor += 1
    recovered = bytearray()
    try:
        for word, expected in zip(words, chunk_lengths):
            recovered.extend(_rs_decode(bytes(word), parity)[:expected])
    except RawBarcodeError as exc:
        raise NewBarcodeError(f"Reed-Solomon could not repair this block: {exc}") from exc
    return bytes(recovered)[:data_length]


def _encode_body(payload: bytes, code: str, method: str) -> bytes:
    if method in ("rawcrc",): return payload
    if method == "repbyte3": return b"".join(bytes((b, b, b)) for b in payload)
    if method == "repbit3":
        return _bits_to_bytes([bit for bit in _bits(payload) for _ in range(3)])
    if method == "repbyte5": return b"".join(bytes((b, b, b, b, b)) for b in payload)
    if method == "mask": return _mask_bytes(payload, code)
    if method == "bitrev": return bytes(_reverse_byte(b) for b in payload)
    if method == "interleave":
        out = bytearray()
        for offset in range(0, len(payload), 8):
            block = payload[offset:offset + 8]
            out.extend(block[::2]); out.extend(block[1::2])
        return bytes(out)
    if method == "hamming": return _hamming_encode(payload)
    if method == "rs8":
        from .rawbarcode import _rs_encode
        return b"".join(_rs_encode(payload[i:i + 247], 8) for i in range(0, len(payload), 247))
    if method == "parity8":
        out = bytearray()
        for offset in range(0, len(payload), 8):
            block = payload[offset:offset + 8]
            out.extend(block); parity = 0
            for b in block: parity ^= b
            out.append(parity)
        return bytes(out)
    if method == "delta":
        out = bytearray(); prev = 0
        for b in payload:
            out.append(b ^ prev); prev = b
        return bytes(out)
    raise NewBarcodeError(f"Unknown variant method {method!r}")


def _decode_body(body: bytes, length: int, code: str, method: str) -> bytes:
    if method == "rawcrc": payload = body[:length]
    elif method == "repbyte3":
        payload = bytes((body[i] & body[i+1]) | (body[i] & body[i+2]) | (body[i+1] & body[i+2]) for i in range(0, length * 3, 3))
    elif method == "repbit3":
        bits = _bits(body)[:length * 24]
        if len(bits) != length * 24: raise NewBarcodeError("Truncated triplicated-bit body")
        payload = _bits_to_bytes([(bits[i] + bits[i+1] + bits[i+2] >= 2) for i in range(0, len(bits), 3)])
    elif method == "repbyte5":
        payload = bytes(_majority_byte(body[i:i+5]) for i in range(0, length * 5, 5))
    elif method == "mask": payload = _mask_bytes(body[:length], code)
    elif method == "bitrev": payload = bytes(_reverse_byte(b) for b in body[:length])
    elif method == "interleave":
        out = bytearray()
        for offset in range(0, length, 8):
            n = min(8, length - offset); half = (n + 1) // 2; block = body[offset:offset+n]
            out.extend(block[i] for i in range(half))
            out.extend(block[half + i] for i in range(n - half))
        # Undo [even positions][odd positions].
        shuffled = bytes(out); payload_out = bytearray()
        pos = 0
        for offset in range(0, length, 8):
            n = min(8, length - offset); half = (n + 1) // 2
            block = shuffled[pos:pos+n]; pos += n; restore = [0] * n
            restore[::2] = block[:half]; restore[1::2] = block[half:]
            payload_out.extend(restore)
        payload = bytes(payload_out)
    elif method == "hamming": payload = _hamming_decode(body, length)
    elif method == "rs8":
        from .rawbarcode import _rs_decode
        out = bytearray(); pos = 0
        for offset in range(0, length, 247):
            n = min(247, length - offset); word_len = n + 8
            out.extend(_rs_decode(body[pos:pos+word_len], 8)[:n]); pos += word_len
        payload = bytes(out)
    elif method == "parity8":
        out = bytearray(); pos = 0
        for offset in range(0, length, 8):
            n = min(8, length - offset); block = body[pos:pos+n]; pos += n
            if len(block) != n or pos >= len(body): raise NewBarcodeError("Truncated block-parity body")
            parity = 0
            for b in block: parity ^= b
            if parity != body[pos]: raise NewBarcodeError("Block parity mismatch")
            pos += 1; out.extend(block)
        payload = bytes(out)
    elif method == "delta":
        out = bytearray(); prev = 0
        for b in body[:length]:
            current = b ^ prev; out.append(current); prev = current
        payload = bytes(out)
    else: raise NewBarcodeError(f"Unknown variant method {method!r}")
    if len(payload) != length:
        raise NewBarcodeError(f"{code.upper()} decoded wrong body length")
    return payload


def _majority_byte(values: bytes) -> int:
    if len(values) != 5: raise NewBarcodeError("Truncated fivefold-repeat body")
    out = 0
    for bit in range(8):
        count = sum((v >> bit) & 1 for v in values)
        out |= (count >= 3) << bit
    return out


def _frame_variant(payload: bytes, code: str, method: str) -> bytes:
    if len(payload) > 0xFFFFFFFF: raise NewBarcodeError("Payload exceeds the 4-byte length field")
    magic = b"HR" + code.upper().encode("ascii") + b"\x00"
    crc = (binascii.crc32(payload) & 0xFFFFFFFF).to_bytes(4, "big")
    if method in _FULL_RS_METHODS:
        # R-tree uses its unique finder as its standard identifier, avoiding an in-band magic
        # string. Tiny payloads use a one-byte length; larger payloads use an extended length.
        length_prefix = (bytes((len(payload),)) if len(payload) < 255
                         else b"\xff" + len(payload).to_bytes(4, "big"))
        body = _rs_interleaved_encode(payload + crc, _FULL_RS_METHODS[method])
        return length_prefix + body
    body = _encode_body(payload, code, method)
    return magic + len(payload).to_bytes(4, "big") + body + crc


def _parse_variant_frame(raw: bytes, code: str, method: str) -> bytes:
    if method in _FULL_RS_METHODS:
        if not raw:
            raise NewBarcodeError(f"Invalid {code.upper()} length header")
        if raw[0] == 0xFF:
            if len(raw) < 5:
                raise NewBarcodeError("Truncated extended payload length")
            length, offset = int.from_bytes(raw[1:5], "big"), 5
        else:
            length, offset = raw[0], 1
        body_len = _body_size(length, method); end = offset + body_len
        if len(raw) < end:
            raise NewBarcodeError("Declared payload exceeds barcode data")
        repaired = _rs_interleaved_decode(raw[offset:end], length + 4, _FULL_RS_METHODS[method])
        if len(repaired) != length + 4:
            raise NewBarcodeError("High-correction Reed-Solomon returned a truncated frame")
        payload, checksum = repaired[:length], repaired[length:length + 4]
        expected = (binascii.crc32(payload) & 0xFFFFFFFF).to_bytes(4, "big")
        if checksum != expected:
            raise NewBarcodeError("CRC32 mismatch after high-correction Reed-Solomon recovery")
        return payload

    magic = b"HR" + code.upper().encode("ascii") + b"\x00"
    if not raw.startswith(magic) or len(raw) < len(magic) + 8:
        raise NewBarcodeError(f"Invalid {code.upper()} marker/header")
    offset = len(magic); length = int.from_bytes(raw[offset:offset+4], "big"); offset += 4
    body_len = _body_size(length, method); end = offset + body_len
    if len(raw) < end + 4:
        raise NewBarcodeError("Declared payload exceeds barcode data")
    payload = _decode_body(raw[offset:end], length, code, method)
    checksum = int.from_bytes(raw[end:end+4], "big")
    if checksum != (binascii.crc32(payload) & 0xFFFFFFFF):
        raise NewBarcodeError("CRC32 mismatch after decoding/error correction")
    return payload


def _ce_map_digit(digit: int, shift: int, inverse: bool = False) -> int:
    if digit == 0: return 0
    return ((digit - 1 + (-shift if inverse else shift)) % 4) + 1


def _bytes_to_base5_cells(data: bytes) -> list[int]:
    """Encode each byte into four local base-5 cells, preserving byte boundaries."""
    cells: list[int] = []
    for byte in data:
        cells.extend((byte // 125, (byte // 25) % 5, (byte // 5) % 5, byte % 5))
    return cells


def _base5_cells_to_bytes(cells: list[int]) -> bytes:
    if len(cells) % 4:
        raise NewBarcodeError("Base-5 colour stream is not aligned to byte cells")
    out = bytearray()
    for i in range(0, len(cells), 4):
        value = cells[i] * 125 + cells[i+1] * 25 + cells[i+2] * 5 + cells[i+3]
        # A damaged colour cell may put a 4-digit value above 255; modulo keeps
        # it a byte-symbol error so repetition/RS can repair it downstream.
        out.append(value % 256)
    return bytes(out)


def encode_variant(payload: bytes, standard: str, *, ppm: int = DEFAULT_PPM, max_pixels: int = MAX_PIXELS) -> Image.Image:
    code = standard.lower().removesuffix("+")
    if code not in VARIANT_METHODS: raise NewBarcodeError(f"No encoder registered for {code.upper()}")
    method = VARIANT_METHODS[code]; frame = _frame_variant(bytes(payload), code, method)
    colored = code.startswith("ce")
    diagonal = code.startswith("d")
    striped = code.startswith("z")
    mosaic = code.startswith("m")
    hexagonal = code.startswith("h")
    triangular = code.startswith("t")
    styled_tree = next((family for family in STYLE_TREE_CODES if code.startswith(family) and code[len(family):].isdigit()), None)
    if colored:
        digits = _bytes_to_base5_cells(frame)
        # CE8 adds a per-colour-cell triple repeat in addition to its Hamming
        # codec, allowing one bad colour module per triplet to be repaired.
        if code == "ce8":
            digits = [digit for digit in digits for _ in range(3)]
        shift = int(code[2:]) % 4
        digits = [_ce_map_digit(d, shift) for d in digits]
        return _make_raster(code, digits, ppm=ppm, max_pixels=max_pixels, colored=True)
    return _make_raster(
        code, _bits(frame), ppm=ppm, max_pixels=max_pixels,
        diagonal=diagonal, striped=striped, mosaic=mosaic,
        hexagonal=hexagonal, triangular=triangular, styled_tree=styled_tree,
    )


def _decode_variant_binary(image: Image.Image, code: str, method: str, max_pixels: int) -> bytes:
    im = _as_image(image)
    if im.width * im.height > max_pixels: raise NewBarcodeError(f"Image exceeds the {max_pixels:,}-pixel safety limit")
    failures = []
    for ppm in _possible_ppms(im):
        geometry = _get_grid(im, ppm)
        if geometry is None: continue
        width, height = geometry
        single_finder = code == "r1"
        if not _finders_match(im, code, width, height, ppm, colored=False, single_finder=single_finder): continue
        styled_tree = next((family for family in STYLE_TREE_CODES if code.startswith(family) and code[len(family):].isdigit()), None)
        try:
            bits = _read_binary_symbols(
                im, width, height, ppm,
                diagonal=code.startswith("d"), striped=code.startswith("z"),
                mosaic=code.startswith("m"), hexagonal=code.startswith("h"),
                triangular=code.startswith("t"), styled_tree=styled_tree, single_finder=single_finder,
            )
            return _parse_variant_frame(_bits_to_bytes(bits), code, method)
        except NewBarcodeError as exc: failures.append(str(exc))
    suffix = f" ({failures[-1]})" if failures else ""
    raise NewBarcodeError(f"No valid {code.upper()} barcode found{suffix}")


def _decode_variant_color(image: Image.Image, code: str, method: str, max_pixels: int) -> bytes:
    im = _as_image(image)
    if im.width * im.height > max_pixels: raise NewBarcodeError(f"Image exceeds the {max_pixels:,}-pixel safety limit")
    failures = []
    shift = int(code[2:]) % 4
    repeat = 3 if code == "ce8" else 1
    magic = b"HR" + code.upper().encode("ascii") + b"\x00"
    for ppm in _possible_ppms(im):
        geometry = _get_grid(im, ppm)
        if geometry is None: continue
        width, height = geometry
        if not _finders_match(im, code, width, height, ppm, colored=True): continue
        digits = [_ce_map_digit(_nearest_palette(_rgb_module(im, x, y, ppm)), shift, inverse=True)
                  for x, y in _read_positions(width, height)]
        first_nonzero = next((i for i, digit in enumerate(digits) if digit), None)
        if first_nonzero is None: continue
        # The first magic byte 'H' is [0,2,4,2] in fixed-width base 5. CE8
        # repeats each colour digit three times before rasterization.
        start = first_nonzero - repeat
        if start < 0: continue
        stream = digits[start:]
        if repeat == 3:
            restored = []
            for off in range(0, len(stream) - 2, 3):
                group = stream[off:off+3]
                restored.append(max(range(5), key=group.count))
            stream = restored
        try:
            raw = _base5_cells_to_bytes(stream[:len(stream) - (len(stream) % 4)])
            if not raw.startswith(magic) or len(raw) < len(magic) + 8:
                raise NewBarcodeError("invalid colour format marker/header")
            length_offset = len(magic)
            length = int.from_bytes(raw[length_offset:length_offset+4], "big")
            required = len(magic) + 4 + _body_size(length, method) + 4
            if len(raw) < required:
                raise NewBarcodeError("declared payload exceeds colour data cells")
            return _parse_variant_frame(raw[:required], code, method)
        except NewBarcodeError as exc: failures.append(str(exc))
    suffix = f" ({failures[-1]})" if failures else ""
    raise NewBarcodeError(f"No valid {code.upper()} barcode found{suffix}")


def decode_new_standard(image: Image.Image, standard: str, *, max_pixels: int = MAX_PIXELS) -> bytes:
    code = standard.lower().removesuffix("+")
    if code == "sl1":
        from .slbarcode import decode_sl1
        try:
            return decode_sl1(image, max_pixels=max_pixels)
        except ValueError as exc:
            raise NewBarcodeError(str(exc)) from exc
    if code == "oi2":
        return decode_oi2(image, max_pixels=max_pixels)
    if code in ("d", "d1"):
        return decode_d1(image, max_pixels=max_pixels)
    if code == "p3": return decode_p3(image, max_pixels=max_pixels)
    if code == "ce1": return decode_ce1(image, max_pixels=max_pixels)
    if code == "z1": return decode_z1(image, max_pixels=max_pixels)
    method = VARIANT_METHODS.get(code)
    if method is None: raise NewBarcodeError(f"{code.upper()} is not an implemented standalone barcode standard")
    if code.startswith("ce"):
        return _decode_variant_color(image, code, method, max_pixels)
    return _decode_variant_binary(image, code, method, max_pixels)


def _finder_candidates(image: Image.Image, *, max_pixels: int = MAX_PIXELS) -> list[str]:
    """Identify matching standards by sampling finder templates once per candidate ppm.

    This is important now that the registry contains hundreds of formats: auto-detection
    must not fully attempt every decoder when the finder signatures already distinguish them.
    """
    im = _as_image(image)
    if im.width * im.height > max_pixels:
        raise NewBarcodeError(f"Image exceeds the {max_pixels:,}-pixel safety limit")
    candidates: list[str] = []
    standards = ["p3", "d1", "ce1", "z1", *VARIANT_METHODS]
    rgb_cache: dict[tuple[int, int, int, int], tuple[int, int, int]] = {}
    for ppm in _possible_ppms(im):
        geometry = _get_grid(im, ppm)
        if geometry is None:
            continue
        width, height = geometry
        samples = []
        origins = ((0, 0), (width - FINDER_SIZE, 0), (0, height - FINDER_SIZE))
        for ox, oy in origins:
            corner = []
            for fy in range(FINDER_SIZE):
                for fx in range(FINDER_SIZE):
                    key = (ox + fx, oy + fy, ppm, 1)
                    if key not in rgb_cache:
                        rgb_cache[key] = _rgb_module(im, ox + fx, oy + fy, ppm)
                    corner.append(rgb_cache[key])
            samples.append(corner)
        for standard in standards:
            colored = standard.startswith("ce")
            matches = True
            corner_count = 1 if standard == "r1" else len(origins)
            for corner_idx in range(corner_count):
                expected_idx = 0
                for fy in range(FINDER_SIZE):
                    for fx in range(FINDER_SIZE):
                        expected = _template_value(standard, fx, fy)
                        actual = samples[corner_idx][expected_idx]
                        expected_idx += 1
                        if colored:
                            if _nearest_palette(actual) != expected:
                                matches = False
                                break
                        elif _is_dark(actual) != bool(expected):
                            matches = False
                            break
                    if not matches:
                        break
                if not matches:
                    break
            if matches and standard not in candidates:
                candidates.append(standard)
    # SL1 has no finder shapes; its fixed-height linear grid is its structural signature.
    from .slbarcode import is_sl1_geometry
    if is_sl1_geometry(im, max_pixels=max_pixels) and "sl1" not in candidates:
        candidates.append("sl1")
    return candidates


def decode_auto_new(image: Image.Image, *, max_pixels: int = MAX_PIXELS) -> tuple[bytes, str]:
    candidates = _finder_candidates(image, max_pixels=max_pixels)
    failures: list[str] = []
    for standard in candidates:
        try:
            return decode_new_standard(image, standard, max_pixels=max_pixels), standard
        except (NewBarcodeError, ValueError) as exc:
            failures.append(f"{standard.upper()}: {exc}")
    suffix = "; ".join(failures[-8:])
    raise NewBarcodeError("No HushRaster standalone barcode found" + (f": {suffix}" if suffix else ". Finder signatures did not match any known standard."))

