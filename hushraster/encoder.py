"""Encoder-only convenience helpers for HushRaster.

These helpers are deliberately outside ``core.py``: the on-image format and
all decoding code remain unchanged.  They are also usable independently of
HushRaster's command-line interface.
"""
from __future__ import annotations

import math
import re
import zlib
from typing import Sequence

from PIL import Image, ImageColor

from .core import (
    FORMAT_VERSION,
    MAX_PIXELS,
    PREFIX_REGION,
    HushRasterError,
    encode_image,
    required_tiles,
)

MAX_REDO = 256


def parse_color(value: str | Sequence[int]) -> tuple[int, int, int]:
    """Parse a blank-canvas color.

    Accepted examples: ``"cyan"``, ``"FF"`` (gray #FFFFFF), ``"0"``
    (black), ``"80"`` (gray #808080), ``"abc"`` (#AABBCC), and
    ``"#12ABEF"``. Alpha values are intentionally not accepted.
    """
    if not isinstance(value, str):
        try:
            parts = tuple(int(component) for component in value)
        except (TypeError, ValueError) as exc:
            raise HushRasterError("Canvas color must be a color name, hex string, or RGB triple") from exc
        if len(parts) != 3 or any(component < 0 or component > 255 for component in parts):
            raise HushRasterError("RGB canvas color must contain exactly three integers from 0 to 255")
        return parts  # type: ignore[return-value]

    raw = value.strip()
    if not raw:
        raise HushRasterError("Canvas color cannot be empty")
    if raw.lower().startswith("0x"):
        raw = raw[2:]
    if raw.startswith("#"):
        raw = raw[1:]
        if re.fullmatch(r"[0-9a-fA-F]{1,2}", raw):
            shade = int(raw, 16)
            return shade, shade, shade
        if re.fullmatch(r"[0-9a-fA-F]{3}", raw):
            return tuple(int(ch * 2, 16) for ch in raw)  # type: ignore[return-value]
        if re.fullmatch(r"[0-9a-fA-F]{6}", raw):
            return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
        raise HushRasterError(
            f"Invalid hex canvas color {value!r}; use 1-2 hex digits for gray, "
            "3 or 6 digits for RGB, or a named color"
        )
    if re.fullmatch(r"[0-9a-fA-F]{1,2}", raw):
        shade = int(raw, 16)
        return shade, shade, shade
    if re.fullmatch(r"[0-9a-fA-F]{3}", raw):
        return tuple(int(ch * 2, 16) for ch in raw)  # type: ignore[return-value]
    if re.fullmatch(r"[0-9a-fA-F]{6}", raw):
        return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    try:
        rgb = ImageColor.getrgb(raw)
    except (ValueError, TypeError) as exc:
        raise HushRasterError(
            f"Unknown canvas color {value!r}; use a Pillow/CSS color name or a 1-, 2-, 3-, or 6-digit hex value"
        ) from exc
    if len(rgb) != 3:
        raise HushRasterError("Canvas color must be opaque RGB; alpha/transparent colors are not supported")
    return tuple(int(component) for component in rgb)  # type: ignore[return-value]


def minimum_canvas_size(stored_length: int, filename: str = "", max_pixels: int = MAX_PIXELS) -> tuple[int, int]:
    """Return a minimum-size, near-square, block-aligned carrier for the body.

    The dimensions satisfy HushRaster's two separate 4096-tile bootstrap
    anchors and its existing header/body capacity calculation. To avoid
    absurdly tall/narrow "minimum area" images caused by integer factorization,
    it first chooses the smallest feasible carrier whose grid aspect ratio is
    at most 1.10; only near the hard pixel ceiling does it fall back to the
    smallest feasible area regardless of aspect ratio. Dimensions are pixels.
    """
    if stored_length < 0:
        raise HushRasterError("Stored payload length cannot be negative")
    try:
        limit = min(int(max_pixels), MAX_PIXELS)
    except (TypeError, ValueError) as exc:
        raise HushRasterError("max_pixels must be a positive integer") from exc
    if limit < 64:
        raise HushRasterError("max_pixels must allow at least one 8x8 tile")
    max_tiles = limit // 64
    needed = required_tiles(stored_length, filename, FORMAT_VERSION)
    if needed > max_tiles:
        raise HushRasterError(
            f"This payload needs at least {needed:,} 8x8 tiles ({needed * 64:,} pixels), "
            f"exceeding the {limit:,}-pixel safety limit. Use a smaller payload or explicitly "
            "raise --max-pixels within the codec's hard limit."
        )

    # Near-square dimensions are substantially more useful as image carriers
    # (and resemble a QR-like canvas) than a mathematically smaller but very
    # tall strip. Search all legal grid widths; 65,535 is the format limit.
    best_near: tuple[int, float, int, int] | None = None
    best_any: tuple[int, float, int, int] | None = None
    max_width_tiles = min(65535, max_tiles)
    for gw in range(1, max_width_tiles + 1):
        region_h = (PREFIX_REGION + gw - 1) // gw
        gh = max((needed + gw - 1) // gw, 3 * region_h)
        while True:
            center_y0 = (gh - region_h) // 2
            center_start = center_y0 * gw
            total = gw * gh
            if center_start >= PREFIX_REGION and center_start + PREFIX_REGION <= total:
                break
            gh += 1
        area = gw * gh
        if area > max_tiles or gh > 65535:
            continue
        ratio = max(gw, gh) / min(gw, gh)
        candidate = (area, ratio, gw, gh)
        if best_any is None or candidate[:2] < best_any[:2]:
            best_any = candidate
        if ratio <= 1.10 and (best_near is None or candidate[:2] < best_near[:2]):
            best_near = candidate
        # Widths past the point where width^2 exceeds the hard tile budget
        # cannot produce a valid candidate; the grid height is never < width
        # for the searched near-square orientation until the transposed form
        # becomes relevant, which is included by searching all legal widths.
    best = best_near or best_any
    if best is None:
        raise HushRasterError(
            f"Could not construct a valid blank carrier within {limit:,} pixels for this payload."
        )
    _, _, gw, gh = best
    return gw * 8, gh * 8


def create_blank_canvas(
    payload: bytes,
    filename: str = "",
    color: str | Sequence[int] = "0",
    compression: str = "none",
    max_pixels: int = MAX_PIXELS,
) -> Image.Image:
    """Create the minimum-area blank RGB canvas needed for a payload.

    ``compression`` matches :func:`hushraster.encode_image`: ``"none"`` is
    the default and ``"z"`` explicitly applies zlib level 1 before sizing.
    """
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise HushRasterError("payload must be bytes-like")
    if compression not in ("none", "z"):
        raise HushRasterError("Compression must be 'none' or 'z'")
    body_len = len(zlib.compress(bytes(payload), level=1)) if compression == "z" else len(payload)
    size = minimum_canvas_size(body_len, filename, max_pixels=max_pixels)
    return Image.new("RGB", size, parse_color(color))


def encode_repeated(
    image: Image.Image,
    payload: bytes,
    filename: str = "",
    *,
    redo: int = 1,
    resize: bool = False,
    max_pixels: int = MAX_PIXELS,
    compression: str = "none",
    verify: bool = True,
) -> tuple[Image.Image, dict]:
    """Apply the existing encoder to its own output ``redo`` times.

    The implementation is mathematically equivalent to repeating the same
    additive tile modulation in a loop, but computes the cumulative pixel
    deltas in one pass. Each encode pass adds the same signed two-level
    pattern to each assigned tile and clips after every pass; because the
    signal never changes sign, ``clip(base + redo * delta)`` is identical to
    repeatedly applying that clipped addition. This makes values such as
    ``--redo 128`` practical without changing the format or decoder.
    """
    import numpy as np

    if isinstance(redo, bool) or not isinstance(redo, int) or redo < 1:
        raise HushRasterError("--redo must be a positive integer (at least 1)")
    if redo > MAX_REDO:
        raise HushRasterError(f"--redo is limited to {MAX_REDO} passes for resource safety")
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise HushRasterError("payload must be bytes-like")
    payload_bytes = bytes(payload)

    if redo == 1:
        encoded, info = encode_image(
            image, payload_bytes, filename, resize=resize,
            max_pixels=max_pixels, compression=compression, verify=verify,
        )
    else:
        # Generate the exact one-pass output, then infer its clipped per-pixel
        # signal relative to the base carrier. No headers, bits, slots, or
        # decoder logic are modified by this encoder-only enhancement.
        once, info = encode_image(
            image, payload_bytes, filename, resize=resize,
            max_pixels=max_pixels, compression=compression, verify=False,
        )
        base = image
        base_w = max(8, (base.width // 8) * 8)
        base_h = max(8, (base.height // 8) * 8)
        if base.size != (base_w, base_h):
            base = base.crop((0, 0, base_w, base_h))
        if base.size != once.size:
            base = base.resize(once.size, Image.Resampling.LANCZOS)
        base_array = np.asarray(base.convert("RGB"), dtype=np.int16)
        once_array = np.asarray(once.convert("RGB"), dtype=np.int16)
        delta = once_array - base_array
        boosted = np.clip(base_array + delta * redo, 0, 255).astype("uint8")
        from PIL import Image as PILImage
        encoded = PILImage.fromarray(boosted, "RGB")

        if verify:
            from .core import decode_image
            try:
                recovered, _header, stats = decode_image(encoded, mode="strict")
            except HushRasterError as exc:
                raise HushRasterError(
                    f"Encoder self-check failed after {redo} redo passes; output was not accepted. "
                    f"Try a lower --redo value or a different blank color/cover. Underlying decoder error: {exc}"
                ) from exc
            if recovered != payload_bytes or not stats.get("integrity_verified"):
                raise HushRasterError(
                    f"Encoder self-check failed after {redo} redo passes: recovered bytes did not "
                    "exactly match the input payload and integrity tag. Try a lower --redo value."
                )
    info = dict(info)
    info["redo_passes"] = redo
    return encoded, info

