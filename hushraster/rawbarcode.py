# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Dense, headerless HushRaster barcode transport.

The current format stores arbitrary bytes without compression or a HushRaster
metadata header. It uses COBS framing, CRC32, and systematic Reed-Solomon block
codes. Symbols are interleaved to spread localized damage across codewords.

The raster is a custom format, not QR Code or Data Matrix. Decoding is exact-grid
image decoding (not yet perspective/camera registration). The decoder also
retains a fallback for the previous three-copies-per-bit raw format.
"""
from __future__ import annotations

import binascii
import math
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw

QUIET = 1                   # one module around the symbol
FINDER_RESERVED = 4         # compact 4x4 asymmetric corner markers
FINDER_DRAWN = 4
RESERVED_MODULES = 3 * FINDER_RESERVED * FINDER_RESERVED
MODULE_SIZE = 1             # compact PNG output: one pixel per module
LEGACY_MODULE_SIZE = 4
LEGACY_QUIET = 4
LEGACY_FINDER = 8
MAX_PIXELS = 40_000_000
RS_LEVELS = (8, 16, 24, 32, 48)
RS_PRIMITIVE_POLY = 0x11D


class RawBarcodeError(ValueError):
    """The image is not a decodable HushRaster barcode or has damaged data."""


# GF(256), primitive polynomial x^8 + x^4 + x^3 + x^2 + 1.
_GF_EXP = [0] * 512
_GF_LOG = [0] * 256
_x = 1
for _i in range(255):
    _GF_EXP[_i] = _x
    _GF_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= RS_PRIMITIVE_POLY
for _i in range(255, 512):
    _GF_EXP[_i] = _GF_EXP[_i - 255]
del _x, _i


def _gf_mul(a: int, b: int) -> int:
    return 0 if not a or not b else _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _gf_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("division by zero in GF(256)")
    return 0 if a == 0 else _GF_EXP[(_GF_LOG[a] - _GF_LOG[b]) % 255]


def _alpha(power: int) -> int:
    return _GF_EXP[power % 255]


def _poly_eval_high(poly: bytes | bytearray | list[int], x: int) -> int:
    result = 0
    for coefficient in poly:
        result = _gf_mul(result, x) ^ coefficient
    return result


def _poly_eval_low(poly: list[int], x: int) -> int:
    result = 0
    power = 1
    for coefficient in poly:
        result ^= _gf_mul(coefficient, power)
        power = _gf_mul(power, x)
    return result


def _poly_mul(a: list[int], b: list[int]) -> list[int]:
    result = [0] * (len(a) + len(b) - 1)
    for i, ca in enumerate(a):
        if ca:
            for j, cb in enumerate(b):
                if cb:
                    result[i + j] ^= _gf_mul(ca, cb)
    return result


@lru_cache(maxsize=len(RS_LEVELS))
def _rs_generator(nsym: int) -> tuple[int, ...]:
    generator = [1]
    for i in range(nsym):
        generator = _poly_mul(generator, [1, _alpha(i)])
    return tuple(generator)


def _rs_encode(data: bytes, nsym: int) -> bytes:
    """Systematic shortened RS encoder, supporting 1..(255-nsym) data bytes."""
    if not 1 <= nsym < 255 or not 1 <= len(data) <= 255 - nsym:
        raise RawBarcodeError("Invalid Reed-Solomon block size")
    generator = _rs_generator(nsym)
    work = bytearray(data) + bytearray(nsym)
    for i in range(len(data)):
        coefficient = work[i]
        if coefficient:
            for j in range(1, len(generator)):
                work[i + j] ^= _gf_mul(generator[j], coefficient)
    return data + bytes(work[-nsym:])


def _solve_gf(matrix: list[list[int]], rhs: list[int]) -> list[int]:
    """Solve a square linear system over GF(256) using Gaussian elimination."""
    size = len(rhs)
    rows = [matrix[i][:] + [rhs[i]] for i in range(size)]
    for column in range(size):
        pivot = next((r for r in range(column, size) if rows[r][column]), None)
        if pivot is None:
            raise RawBarcodeError("Singular Reed-Solomon error-magnitude system")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        inverse = _gf_div(1, rows[column][column])
        rows[column] = [_gf_mul(v, inverse) for v in rows[column]]
        for r in range(size):
            if r == column or rows[r][column] == 0:
                continue
            factor = rows[r][column]
            rows[r] = [v ^ _gf_mul(factor, q) for v, q in zip(rows[r], rows[column])]
    return [rows[i][-1] for i in range(size)]


def _rs_decode(codeword: bytes, nsym: int) -> bytes:
    """Decode one (possibly shortened) RS block; correct up to nsym//2 symbols."""
    if not nsym or len(codeword) <= nsym or len(codeword) > 255:
        raise RawBarcodeError("Invalid shortened Reed-Solomon codeword length")
    syndromes = [_poly_eval_high(codeword, _alpha(i)) for i in range(nsym)]
    if not any(syndromes):
        return codeword

    # Berlekamp-Massey. Locator coefficients here are in low-order-first form.
    locator = [1] + [0] * nsym
    previous = [1] + [0] * nsym
    degree = 0
    distance = 1
    previous_discrepancy = 1
    for step in range(nsym):
        discrepancy = syndromes[step]
        for i in range(1, degree + 1):
            discrepancy ^= _gf_mul(locator[i], syndromes[step - i])
        if discrepancy == 0:
            distance += 1
            continue
        saved = locator.copy()
        scale = _gf_div(discrepancy, previous_discrepancy)
        for i in range(nsym + 1 - distance):
            if previous[i]:
                locator[i + distance] ^= _gf_mul(scale, previous[i])
        if 2 * degree <= step:
            degree = step + 1 - degree
            previous = saved
            previous_discrepancy = discrepancy
            distance = 1
        else:
            distance += 1

    locator = locator[:degree + 1]
    if degree == 0 or degree * 2 > nsym:
        raise RawBarcodeError("Too many symbol errors for this Reed-Solomon level")

    positions = []
    exponents = []
    for position in range(len(codeword)):
        exponent = len(codeword) - 1 - position
        if _poly_eval_low(locator, _alpha(-exponent)) == 0:
            positions.append(position)
            exponents.append(exponent)
    if len(positions) != degree:
        raise RawBarcodeError("Could not locate all Reed-Solomon symbol errors")

    # Solve syndromes S_j = sum(error_i * alpha^(j * exponent_i)) for magnitudes.
    matrix = [[_alpha(j * exponent) for exponent in exponents] for j in range(degree)]
    magnitudes = _solve_gf(matrix, syndromes[:degree])
    repaired = bytearray(codeword)
    for position, magnitude in zip(positions, magnitudes):
        repaired[position] ^= magnitude
    if any(_poly_eval_high(repaired, _alpha(i)) for i in range(nsym)):
        raise RawBarcodeError("Reed-Solomon correction did not validate")
    return bytes(repaired)


def cobs_encode(data: bytes) -> bytes:
    """COBS-frame bytes without compressing them."""
    out = bytearray([0])
    code_pos = 0
    code = 1
    for b in data:
        if b == 0:
            out[code_pos] = code
            code_pos = len(out)
            out.append(0)
            code = 1
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_pos] = code
                code_pos = len(out)
                out.append(0)
                code = 1
    out[code_pos] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        if code == 0:
            raise RawBarcodeError("Invalid zero inside COBS frame")
        i += 1
        end = i + code - 1
        if end > len(data):
            raise RawBarcodeError("Truncated COBS frame")
        out.extend(data[i:end])
        i = end
        if code != 0xFF and i < len(data):
            out.append(0)
    return bytes(out)


def _bits(data: bytes):
    for byte in data:
        for shift in range(7, -1, -1):
            yield (byte >> shift) & 1


def _bits_to_bytes(bits) -> bytes:
    result = bytearray()
    value = 0
    count = 0
    for bit in bits:
        value = (value << 1) | int(bit)
        count += 1
        if count == 8:
            result.append(value)
            value = 0
            count = 0
    return bytes(result)


def _reserved(x: int, y: int, width: int, height: int, finder: int = FINDER_RESERVED) -> bool:
    return ((x < finder and y < finder) or
            (x >= width - finder and y < finder) or
            (x < finder and y >= height - finder))


def _draw_finder(draw: ImageDraw.ImageDraw, ox: int, oy: int, module: int):
    """Draw a compact 5x5 bullseye corner marker."""
    for y in range(FINDER_DRAWN):
        for x in range(FINDER_DRAWN):
            dark = x in (0, FINDER_DRAWN - 1) or y in (0, FINDER_DRAWN - 1) or (x == 1 and y == 1)
            if dark:
                draw.rectangle((ox + x * module, oy + y * module,
                                ox + (x + 1) * module - 1, oy + (y + 1) * module - 1), fill=0)




def _has_finders(im: Image.Image, module: int, grid_w: int, grid_h: int, gx: int, gy: int) -> bool:
    """Reject unrelated images cheaply while tolerating one damaged finder."""
    origins = ((0, 0), (grid_w - FINDER_DRAWN, 0), (0, grid_h - FINDER_DRAWN))
    valid = 0
    for origin_x, origin_y in origins:
        matches = 0
        total = 0
        for y in range(FINDER_DRAWN):
            for x in range(FINDER_DRAWN):
                dark = x in (0, FINDER_DRAWN - 1) or y in (0, FINDER_DRAWN - 1) or (x == 1 and y == 1)
                px = gx + (origin_x + x) * module + module // 2
                py = gy + (origin_y + y) * module + module // 2
                is_dark = im.getpixel((px, py)) < 128
                matches += is_dark == dark
                total += 1
        if matches / total >= 0.72:
            valid += 1
    return valid >= 2


def _choose_ecc(frame_length: int) -> int:
    """Use light ECC on tiny symbols, scaling up to 24 correctable bytes/block."""
    if frame_length <= 32:
        return 8       # up to 4 erroneous byte symbols per block
    if frame_length <= 128:
        return 16      # up to 8
    if frame_length <= 192:
        return 32      # up to 16
    return 48          # up to 24


def _encoded_byte_capacity(payload_frame_len: int, nsym: int) -> int:
    blocks = math.ceil(payload_frame_len / (255 - nsym))
    return payload_frame_len + nsym * blocks


def _geometry(payload_frame_len: int, nsym: int, max_pixels: int, module_size: int) -> tuple[int, int, int]:
    """Find a compact near-square grid whose dimensions imply valid RS blocks."""
    minimum_bytes = _encoded_byte_capacity(payload_frame_len, nsym)
    target_modules = RESERVED_MODULES + 8 * minimum_bytes
    side = math.sqrt(target_modules)
    max_width = max(64, math.ceil(side * 2))
    best = None
    # Check widths across a broad range so row increments cannot skip every
    # valid shortened-RS tail. A data byte is 8 modules; no compression is used.
    for grid_w in range(8, max_width + 1):
        base_h = max(8, math.ceil(target_modules / grid_w))
        extra_rows = max(8, math.ceil(255 * 8 / grid_w) + 3)
        for grid_h in range(base_h, base_h + extra_rows + 1):
            usable_modules = grid_w * grid_h - RESERVED_MODULES
            if usable_modules < 0:
                continue
            codeword_count = usable_modules // 8
            if codeword_count < minimum_bytes:
                continue
            blocks = math.ceil(codeword_count / 255)
            tail_len = codeword_count - 255 * (blocks - 1)
            if tail_len <= nsym:
                continue  # a shortened RS block must contain data and parity
            data_capacity = codeword_count - nsym * blocks
            if data_capacity < payload_frame_len:
                continue
            width_px = (grid_w + 2 * QUIET) * module_size
            height_px = (grid_h + 2 * QUIET) * module_size
            area_px = width_px * height_px
            if area_px > max_pixels:
                continue
            # A small shape penalty avoids an unnecessarily long narrow raster
            # when a nearly-square layout costs almost the same number of pixels.
            score = (area_px + (grid_w - grid_h) ** 2, area_px, abs(grid_w - grid_h))
            if best is None or score < best[0]:
                best = (score, grid_w, grid_h, codeword_count)
        # No early stop: a slightly wider/taller grid can have fewer total pixels
        # once quiet-zone and row-rounding overhead is included.
    if best is None:
        raise RawBarcodeError(
            "The barcode exceeds the pixel safety limit or cannot fit a valid error-correction layout. "
            "Split the payload or increase max_pixels."
        )
    return best[1], best[2], best[3]


def _interleave(blocks: list[bytes]) -> bytes:
    out = bytearray()
    for offset in range(max(map(len, blocks), default=0)):
        for block in blocks:
            if offset < len(block):
                out.append(block[offset])
    return bytes(out)


def _deinterleave(stream: bytes, nsym: int) -> list[bytes]:
    total = len(stream)
    if total <= nsym:
        raise RawBarcodeError("Insufficient bytes for Reed-Solomon frame")
    block_count = math.ceil(total / 255)
    tail_len = total - 255 * (block_count - 1)
    if tail_len <= nsym:
        raise RawBarcodeError("Invalid shortened Reed-Solomon tail")
    lengths = [255] * (block_count - 1) + [tail_len]
    blocks = [bytearray(length) for length in lengths]
    source_index = 0
    for offset in range(max(lengths)):
        for block_index, block_len in enumerate(lengths):
            if offset < block_len:
                blocks[block_index][offset] = stream[source_index]
                source_index += 1
    if source_index != total:
        raise RawBarcodeError("Invalid interleaved block length")
    return [bytes(block) for block in blocks]


def _rs_restore(stream: bytes, nsym: int) -> bytes:
    blocks = _deinterleave(stream, nsym)
    data = bytearray()
    for block in blocks:
        repaired = _rs_decode(block, nsym)
        data.extend(repaired[:-nsym])
    return bytes(data)


def _parse_frame(data: bytes) -> bytes:
    delimiter = data.find(b"\x00")
    if delimiter <= 0 or len(data) < delimiter + 5:
        # Even an empty user payload has a non-empty COBS frame (0x01).
        raise RawBarcodeError("No complete raw-payload frame found")
    framed = data[:delimiter]
    crc_bytes = data[delimiter + 1:delimiter + 5]
    try:
        payload = cobs_decode(framed)
    except RawBarcodeError as exc:
        raise RawBarcodeError(f"Raw-payload framing is damaged: {exc}") from exc
    expected = int.from_bytes(crc_bytes, "big")
    actual = binascii.crc32(payload) & 0xFFFFFFFF
    if expected != actual:
        raise RawBarcodeError("Payload CRC32 mismatch; barcode is damaged or is not a HushRaster raw barcode")
    return payload


def encode_bytes(payload: bytes, *, max_pixels: int = MAX_PIXELS, module_size: int = MODULE_SIZE) -> Image.Image:
    """Render arbitrary bytes as a compact headerless monochrome barcode.

    The default is one pixel per symbol module. ``module_size`` may be raised
    for larger, more camera-friendly displays without changing encoded data.
    """
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("payload must be bytes-like")
    if isinstance(module_size, bool) or not isinstance(module_size, int) or not 1 <= module_size <= 32:
        raise ValueError("module_size must be an integer from 1 to 32")
    payload = bytes(payload)
    crc = binascii.crc32(payload) & 0xFFFFFFFF
    # This is framing and integrity only. The user payload is never compressed.
    frame = cobs_encode(payload) + b"\x00" + crc.to_bytes(4, "big")
    nsym = _choose_ecc(len(frame))
    grid_w, grid_h, codeword_count = _geometry(len(frame), nsym, max_pixels, module_size)
    blocks_count = math.ceil(codeword_count / 255)
    data_capacity = codeword_count - nsym * blocks_count
    padded_data = frame + (b"\xA5" * (data_capacity - len(frame)))
    data_block_size = 255 - nsym
    blocks = [_rs_encode(padded_data[i:i + data_block_size], nsym)
              for i in range(0, len(padded_data), data_block_size)]
    wire = _interleave(blocks)
    if len(wire) != codeword_count:
        raise RawBarcodeError("Internal error: Reed-Solomon byte count did not match grid capacity")

    image_w = (grid_w + 2 * QUIET) * module_size
    image_h = (grid_h + 2 * QUIET) * module_size
    image = Image.new("1", (image_w, image_h), 1)
    draw = ImageDraw.Draw(image)
    gx = QUIET * module_size
    gy = QUIET * module_size
    _draw_finder(draw, gx, gy, module_size)
    _draw_finder(draw, gx + (grid_w - FINDER_DRAWN) * module_size, gy, module_size)
    _draw_finder(draw, gx, gy + (grid_h - FINDER_DRAWN) * module_size, module_size)

    bit_iter = iter(_bits(wire))
    for y in range(grid_h):
        for x in range(grid_w):
            if _reserved(x, y, grid_w, grid_h):
                continue
            bit = next(bit_iter, None)
            if bit:
                px = gx + x * module_size
                py = gy + y * module_size
                draw.rectangle((px, py, px + module_size - 1, py + module_size - 1), fill=0)
    return image.convert("RGB")


def _decode_rs_grid(image: Image.Image, *, module_size: int, max_pixels: int) -> bytes:
    im = image.convert("L")
    width, height = im.size
    if width % module_size or height % module_size:
        raise RawBarcodeError("Image dimensions do not align to barcode modules")
    grid_w = width // module_size - 2 * QUIET
    grid_h = height // module_size - 2 * QUIET
    if grid_w < 8 or grid_h < 8:
        raise RawBarcodeError("Image dimensions are too small for a HushRaster barcode")
    grid_x, grid_y = QUIET * module_size, QUIET * module_size
    if not _has_finders(im, module_size, grid_w, grid_h, grid_x, grid_y):
        raise RawBarcodeError("HushRaster corner finder patterns were not recognized")
    bits = []
    for y in range(grid_h):
        for x in range(grid_w):
            if _reserved(x, y, grid_w, grid_h):
                continue
            px = grid_x + x * module_size + module_size // 2
            py = grid_y + y * module_size + module_size // 2
            bits.append(1 if im.getpixel((px, py)) < 128 else 0)
    codeword_count = len(bits) // 8
    if codeword_count <= 0:
        raise RawBarcodeError("No data modules found")
    stream = _bits_to_bytes(bits[:codeword_count * 8])
    errors = []
    # The parity level is not stored in a metadata header; try each standardized
    # HushRaster level and accept only a CRC32-verified payload.
    for nsym in (48, 32, 24, 16, 8):
        block_count = math.ceil(codeword_count / 255)
        tail_len = codeword_count - 255 * (block_count - 1)
        if tail_len <= nsym or codeword_count - nsym * block_count < 6:
            continue
        try:
            data = _rs_restore(stream, nsym)
            return _parse_frame(data)
        except RawBarcodeError as exc:
            errors.append(str(exc))
    raise RawBarcodeError("No valid Reed-Solomon/CRC frame found" + (f" ({errors[-1]})" if errors else ""))


def _decode_legacy_repetition(image: Image.Image, *, max_pixels: int) -> bytes:
    """Read P1 triple-bit repetition raster at any supported module scale."""
    im = image.convert("L")
    width, height = im.size
    failures = []
    for module in range(1, 33):
        if width % module or height % module:
            continue
        grid_w = width // module - 2 * LEGACY_QUIET
        grid_h = height // module - 2 * LEGACY_QUIET
        if grid_w < 32 or grid_h < 16:
            continue
        grid_x = grid_y = LEGACY_QUIET * module
        bits = []
        for y in range(grid_h):
            for x in range(grid_w):
                if ((x < LEGACY_FINDER and y < LEGACY_FINDER) or
                    (x >= grid_w - LEGACY_FINDER and y < LEGACY_FINDER) or
                    (x < LEGACY_FINDER and y >= grid_h - LEGACY_FINDER)):
                    continue
                px = grid_x + x * module + module // 2
                py = grid_y + y * module + module // 2
                bits.append(1 if im.getpixel((px, py)) < 128 else 0)
        decoded_bits = [1 if sum(bits[i:i + 3]) >= 2 else 0
                        for i in range(0, len(bits) - 2, 3)]
        try:
            return _parse_frame(_bits_to_bytes(decoded_bits))
        except RawBarcodeError as exc:
            failures.append(str(exc))
    raise RawBarcodeError("No valid P1 triple-repetition frame found" + (f" ({failures[-1]})" if failures else ""))


def encode_p1_bytes(payload: bytes, *, max_pixels: int = MAX_PIXELS, module_size: int = LEGACY_MODULE_SIZE) -> Image.Image:
    """Encode P1 with triple-bit repetition; module size is 1..32 pixels."""
    if isinstance(module_size, bool) or not isinstance(module_size, int) or not 1 <= module_size <= 32:
        raise ValueError("module_size must be an integer from 1 to 32")
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("payload must be bytes-like")
    payload = bytes(payload)
    crc = binascii.crc32(payload) & 0xFFFFFFFF
    frame = cobs_encode(payload) + b"\x00" + crc.to_bytes(4, "big")
    repeated = [bit for bit in _bits(frame) for _ in range(3)]
    finder = LEGACY_FINDER
    grid_w = max(32, math.ceil(math.sqrt(len(repeated) + 3 * finder * finder)))
    grid_h = max(16, math.ceil((len(repeated) + 3 * finder * finder) / grid_w))
    while grid_w * grid_h - 3 * finder * finder < len(repeated):
        grid_h += 1
    image_w = (grid_w + 2 * LEGACY_QUIET) * module_size
    image_h = (grid_h + 2 * LEGACY_QUIET) * module_size
    if image_w * image_h > max_pixels:
        raise RawBarcodeError(
            f"P1 barcode would be {image_w}x{image_h} ({image_w * image_h:,} pixels), "
            f"exceeding the {max_pixels:,}-pixel safety limit"
        )
    image = Image.new("1", (image_w, image_h), 1)
    draw = ImageDraw.Draw(image)
    gx = gy = LEGACY_QUIET * module_size
    # P1 used the older 8x8 reserved areas and 7x7 finder design.
    def draw_p1_finder(ox: int, oy: int):
        for fy in range(7):
            for fx in range(7):
                dark = fx in (0, 6) or fy in (0, 6) or (2 <= fx <= 4 and 2 <= fy <= 4)
                if dark:
                    x0 = ox + fx * module_size
                    y0 = oy + fy * module_size
                    draw.rectangle((x0, y0, x0 + module_size - 1, y0 + module_size - 1), fill=0)
    draw_p1_finder(gx, gy)
    draw_p1_finder(gx + (grid_w - 7) * module_size, gy)
    draw_p1_finder(gx, gy + (grid_h - 7) * module_size)
    bit_index = 0
    for y in range(grid_h):
        for x in range(grid_w):
            if ((x < finder and y < finder) or
                (x >= grid_w - finder and y < finder) or
                (x < finder and y >= grid_h - finder)):
                continue
            if bit_index < len(repeated) and repeated[bit_index]:
                x0 = gx + x * module_size
                y0 = gy + y * module_size
                draw.rectangle((x0, y0, x0 + module_size - 1, y0 + module_size - 1), fill=0)
            bit_index += 1
    return image.convert("RGB")


def decode_with_standard(image: Image.Image, *, standard: str | None = None,
                         max_pixels: int = MAX_PIXELS) -> tuple[bytes, str]:
    """Decode a standalone barcode and return (payload, detected standard)."""
    if image.width * image.height > max_pixels:
        raise RawBarcodeError(f"Image exceeds the {max_pixels:,}-pixel safety limit")
    requested = standard.lower().removesuffix("+") if standard else None
    if requested not in (None, "p1", "p2"):
        raise RawBarcodeError(f"{requested.upper()} is not a standalone raw-barcode decoder")
    failures = []
    if requested in (None, "p2"):
        im = image
        for module_size in range(1, 33):
            if image.width % module_size or image.height % module_size:
                continue
            try:
                return _decode_rs_grid(im, module_size=module_size, max_pixels=max_pixels), "p2"
            except RawBarcodeError as exc:
                failures.append(str(exc))
        if requested == "p2":
            raise RawBarcodeError(f"Not a valid P2 (Panda 2) barcode ({failures[-1] if failures else 'no matching grid'})")
    if requested in (None, "p1"):
        try:
            return _decode_legacy_repetition(image, max_pixels=max_pixels), "p1"
        except RawBarcodeError as exc:
            failures.append(str(exc))
        if requested == "p1":
            raise RawBarcodeError(f"Not a valid P1 (Panda 1) barcode ({failures[-1]})")
    raise RawBarcodeError("No P2 or P1 standalone barcode could be identified" + (f" ({failures[-1]})" if failures else ""))

def decode_image(image: Image.Image, *, max_pixels: int = MAX_PIXELS) -> bytes:
    """Decode P2 or the previous P1 raster, verifying CRC32."""
    payload, _standard = decode_with_standard(image, max_pixels=max_pixels)
    return payload


def decode_file(path: str | Path, *, max_pixels: int = MAX_PIXELS) -> bytes:
    try:
        with Image.open(path) as im:
            im.load()
            return decode_image(im, max_pixels=max_pixels)
    except RawBarcodeError:
        raise
    except Exception as exc:
        raise RawBarcodeError(f"Cannot read barcode image: {exc}") from exc
