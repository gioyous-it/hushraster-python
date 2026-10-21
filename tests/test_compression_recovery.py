# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Regression tests: new encoders must never create zlib-compressed payloads."""
from __future__ import annotations

import pytest
from PIL import Image

from hushraster.core import HushRasterError, encode_image
from hushraster.encoder import create_blank_canvas


def test_legacy_encoder_rejects_compression() -> None:
    payload = b"Repeated payload " * 100
    cover = Image.new("RGB", (1536, 1536), (128, 128, 128))
    with pytest.raises(HushRasterError, match="compression is no longer supported"):
        encode_image(cover, payload, "old.bin", compression="z")
    with pytest.raises(HushRasterError, match="compression is no longer supported"):
        create_blank_canvas(payload, "old.bin", "80", compression="z")


def test_raw_headerless_transport_does_not_compress() -> None:
    from hushraster.rawbarcode import decode_image, encode_bytes

    payload = b"Repeated payload " * 100
    image = encode_bytes(payload)
    assert decode_image(image) == payload
