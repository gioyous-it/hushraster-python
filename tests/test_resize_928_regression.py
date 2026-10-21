#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Regression test for low-level image-modulation resize and error recovery.

This uses a deterministic synthetic cover because the user's original photo is
not included in the recovered project archive. It is not a substitute for testing
that exact photo.
"""
import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from hushraster.core import encode_image, decode_image, HushRasterError

PAYLOAD = b"I am proudly hidden, here, In this Image."

def main():
    cover = Image.new("RGB", (176, 297), (128, 128, 128))
    draw = ImageDraw.Draw(cover)
    draw.ellipse((100, 20, 150, 70), fill=(230, 220, 170))
    draw.polygon([(0, 180), (60, 100), (110, 180)], fill=(50, 100, 60))
    draw.rectangle((0, 210, 176, 297), fill=(45, 90, 50))

    encoded, info = encode_image(cover, PAYLOAD, "", resize=True)
    assert info["resized"] is True
    # v3 includes SECDED error-correction bits, so auto-resize grows beyond the
    # earlier v2 928x1560 result rather than silently dropping ECC.
    assert encoded.size == (1008, 1696), encoded.size

    out, meta, stats = decode_image(encoded)
    assert out == PAYLOAD
    assert stats["integrity_verified"]

    for mode in ("best", "depends", "default", "strict", "fast", "reconstruct"):
        out, meta, stats = decode_image(encoded, mode=mode)
        assert out == PAYLOAD, mode
        assert stats["integrity_verified"], mode

    for fmt, quality in (("JPEG", 90), ("JPEG", 75), ("WEBP", 90), ("WEBP", 75)):
        stream = io.BytesIO()
        encoded.save(stream, format=fmt, quality=quality, method=6)
        stream.seek(0)
        candidate = Image.open(stream).convert("RGB")
        out, meta, stats = decode_image(candidate)
        assert out == PAYLOAD, (fmt, quality)
        assert stats["integrity_verified"], (fmt, quality)

    # Edge crops that retain the top-left anchor are expected to decode.
    for box in ((0, 0, int(encoded.width * .9), encoded.height),
                (0, 0, encoded.width, int(encoded.height * .9))):
        out, meta, stats = decode_image(encoded.crop(box))
        assert out == PAYLOAD and stats["integrity_verified"], box

    # The center header must survive a center crop even when top-left is gone.
    center = encoded.crop((int(encoded.width * .1), int(encoded.height * .1),
                           int(encoded.width * .9), int(encoded.height * .9)))
    out, meta, stats = decode_image(center, mode="strict")
    assert out == PAYLOAD and stats["integrity_verified"], "center crop did not verify"

    # Off-center crop removes the top-left corner but preserves the lower/right
    # boundaries and enough of the spatially duplicated center header.
    off_center = encoded.crop((int(encoded.width * .1), int(encoded.height * .1),
                               encoded.width, encoded.height))
    out, meta, stats = decode_image(off_center, mode="strict")
    assert out == PAYLOAD and stats["integrity_verified"], "off-center corner crop did not verify"
    assert str(stats["anchor"]).startswith("center-copy (right/bottom)"), stats["anchor"]

    # Remove the entire top-left bootstrap region from the carrier while keeping
    # the center header copy. This specifically guards the old fallback bug.
    import numpy as np
    gw, gh = encoded.width // 8, encoded.height // 8
    pristine = cover.crop((0, 0, (cover.width // 8) * 8, (cover.height // 8) * 8))
    pristine = pristine.resize(encoded.size, Image.Resampling.LANCZOS)
    arr = np.array(encoded.convert("RGB"), copy=True)
    base = np.asarray(pristine.convert("RGB"))
    for slot in range(4096):
        x, y = (slot % gw) * 8, (slot // gw) * 8
        arr[y:y+8, x:x+8, :] = base[y:y+8, x:x+8, :]
    top_left_destroyed = Image.fromarray(arr, "RGB")
    out, meta, stats = decode_image(top_left_destroyed, mode="strict")
    assert out == PAYLOAD and stats["integrity_verified"]
    assert str(stats["anchor"]).startswith("center-copy"), stats["anchor"]

    print("PASS: v3 resize roundtrip; all six decoder modes; JPEG/WebP Q75/Q90; right/bottom, centered and off-center crops; top-left-header loss recovery")

if __name__ == "__main__":
    main()
