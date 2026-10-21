# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""HushRaster 1.0.1 multi-standard barcode transport and legacy IMGMod codec.

Use :func:`encode_barcode` and :func:`decode_barcode` for the new standalone
black-and-white transport. The older :func:`encode_image` and :func:`decode_image`
functions are retained for legacy IMGMod compatibility.
"""
__version__ = "1.0.1"

from .core import HushRasterError, decode_image, encode_image, read_image
from .rawbarcode import (
    RawBarcodeError, encode_bytes as encode_barcode, decode_image as decode_barcode,
    encode_p1_bytes as encode_panda1_barcode, decode_with_standard as decode_barcode_with_standard,
)
from .standards import STANDARDS
from .newstandards import (
    NewBarcodeError, encode_p3, encode_oi2, encode_ce1, encode_z1,
    decode_p3, decode_oi2, decode_ce1, decode_z1, decode_new_standard,
)
from .slbarcode import SL1Error, encode_sl1, decode_sl1
from .encoder import (
    MAX_REDO,
    create_blank_canvas,
    encode_repeated,
    minimum_canvas_size,
    parse_color,
)

__all__ = [
    "HushRasterError",
    "RawBarcodeError",
    "encode_barcode",
    "decode_barcode",
    "encode_panda1_barcode",
    "decode_barcode_with_standard",
    "STANDARDS",
    "NewBarcodeError",
    "encode_p3",
    "encode_oi2",
    "encode_ce1",
    "encode_z1",
    "decode_p3",
    "decode_oi2",
    "decode_ce1",
    "decode_z1",
    "decode_new_standard",
    "SL1Error",
    "encode_sl1",
    "decode_sl1",
    "decode_image",
    "encode_image",
    "read_image",
    "encode_repeated",
    "create_blank_canvas",
    "minimum_canvas_size",
    "parse_color",
    "MAX_REDO",
    "__version__",
]
