"""HushRaster 1.0 image-data codec and Python library.

The low-level codec can be imported directly from :mod:`hushraster`. Encoder-
only convenience helpers add blank-canvas generation and repeated embedding
without changing the file format or decoder.
"""
__version__ = "1.0"

from .core import HushRasterError, decode_image, encode_image, read_image
from .encoder import (
    MAX_REDO,
    create_blank_canvas,
    encode_repeated,
    minimum_canvas_size,
    parse_color,
)

__all__ = [
    "HushRasterError",
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
