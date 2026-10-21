# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import argparse
from io import BytesIO
import errno
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image

from .encoder import MAX_REDO, create_blank_canvas, encode_repeated, parse_color
from .rawbarcode import (
    RawBarcodeError, encode_bytes as encode_raw_barcode, decode_file as decode_raw_barcode,
    _choose_ecc as _choose_barcode_ecc, cobs_encode as _cobs_barcode_frame,
    encode_p1_bytes, decode_with_standard,
)
from .standards import STANDARDS, normalize_standard, standard_listing
from .newstandards import NewBarcodeError

from .core import (
    VERSION, HushRasterError, read_image, encode_image, decode_image,
    required_tiles, PREFIX, REPEAT, HEADER_REPEAT, HEADER_DATA_REPEAT, MAX_PIXELS,
)

MODES = ("best", "depends", "default", "strict", "fast", "reconstruct")


def _install_no_replace(temporary: Path, destination: Path) -> bool:
    """Install a completed temp file without overwriting an existing path.

    Returns True if an atomic hard-link install was available. Some Android
    shared-storage/FUSE filesystems reject hard links; on those filesystems we
    fall back to O_EXCL creation and copy, which still cannot clobber an older
    file and cleans up a partial new file on write failure.
    """
    # Some constrained Python builds (including certain Android runtimes)
    # expose no os.link attribute at all. Treat that exactly like a filesystem
    # that does not support hard links and use O_EXCL below.
    link = getattr(os, "link", None)
    if link is not None:
        try:
            link(temporary, destination)
            return True
        except FileExistsError as exc:
            raise HushRasterError(f"Output already exists: {destination} (use --force)") from exc
        except OSError as exc:
            unsupported = {
                errno.EPERM,
                errno.EOPNOTSUPP,
                getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
                errno.ENOSYS,
                errno.EXDEV,
            }
            if exc.errno not in unsupported:
                raise
    fd = None
    created = False
    try:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        created = True
        with os.fdopen(fd, "wb") as output, temporary.open("rb") as source:
            fd = None
            shutil.copyfileobj(source, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        return False
    except FileExistsError as exc:
        raise HushRasterError(f"Output already exists: {destination} (use --force)") from exc
    except Exception as exc:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if created:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        raise HushRasterError(f"Could not install output without overwriting an existing file: {exc}") from exc


def _file_sha256(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.digest()


def write_output(path: Path, data: bytes, force: bool = False):
    """Write recovered bytes safely, preserving old files on a failed write."""
    path = Path(path)
    temporary = None
    fd = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force:
            raise HushRasterError(f"Output already exists: {path} (use --force to overwrite)")
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        temporary = Path(temporary_name)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if force:
            os.replace(temporary, path)
        else:
            linked = _install_no_replace(temporary, path)
            if not linked:
                if path.stat().st_size != len(data) or _file_sha256(path) != hashlib.sha256(data).digest():
                    path.unlink(missing_ok=True)
                    raise HushRasterError("Copied decoded output failed read-back verification; output was removed.")
    except HushRasterError:
        raise
    except Exception as exc:
        raise HushRasterError(f"Could not safely write output {path}: {exc}") from exc
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def save_verified_png(image: Image.Image, path: Path, expected_payload: bytes, force: bool = False):
    """Save a PNG temporarily and install it only after strict read-back verification.

    The temporary file is in the destination directory so replacement cannot
    cross filesystems. Existing output is preserved if writing or verification
    fails. Hard-link-disabled filesystems use an exclusive-create/copy fallback
    and the installed PNG is strictly verified again.
    """
    path = Path(path)
    temporary = None
    fd = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force:
            raise HushRasterError(f"Output already exists: {path} (use --force)")
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp.png", dir=str(path.parent)
        )
        os.close(fd)
        fd = None
        temporary = Path(temporary_name)
        image.save(temporary, format="PNG")
        saved = read_image(temporary)
        recovered, _header, stats = decode_image(saved, mode="strict")
        if recovered != expected_payload or not stats.get("integrity_verified"):
            raise HushRasterError(
                "Saved PNG failed strict read-back verification; the requested output was not installed."
            )
        if force:
            os.replace(temporary, path)
        else:
            linked = _install_no_replace(temporary, path)
            if not linked:
                try:
                    saved_again = read_image(path)
                    recovered_again, _header_again, stats_again = decode_image(saved_again, mode="strict")
                    if recovered_again != expected_payload or not stats_again.get("integrity_verified"):
                        raise HushRasterError("Copied PNG failed strict read-back verification.")
                except Exception as exc:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    if isinstance(exc, HushRasterError):
                        raise
                    raise HushRasterError(f"Could not verify installed PNG: {exc}") from exc
    except HushRasterError:
        raise
    except Exception as exc:
        raise HushRasterError(f"Could not write and verify output PNG {path}: {exc}") from exc
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _warn_if_needed(stats, focus=False):
    warning = stats.get("warning")
    if warning and not focus:
        print(f"WARNING: {warning}", file=sys.stderr)


def _decode_args(a):
    forced = "z" if getattr(a, "force_zlib", False) else (
        "none" if getattr(a, "force_no_zlib", False) else None
    )
    return decode_image(
        read_image(Path(a.image).expanduser()),
        max_search_width=a.max_search_width,
        mode=a.mode,
        force_compression=forced,
    )


def _check_output_format(out: Path):
    if out.suffix.lower() != ".png":
        raise HushRasterError("Encoded carriers must be PNG; convert/re-encode to JPEG/WebP only for transport")


def _encoder_settings(a):
    redo = getattr(a, "redo", 1)
    if isinstance(redo, bool) or redo < 1 or redo > MAX_REDO:
        raise HushRasterError(f"--redo must be between 1 and {MAX_REDO}")
    # New CLI output is always uncompressed. The old low-level codec remains
    # available only for decoding historical IMGMod payloads.
    return redo, "none"


def _print_encoding_summary(out: Path, encoded: Image.Image, info: dict, payload_len: int,
                            compression: str, *, source: Path | None = None,
                            payload_path: Path | None = None, blank_color=None):
    if source is None:
        print("Input image: generated blank canvas" + (f" RGB {blank_color}" if blank_color is not None else ""))
    else:
        print(f"Input image: {source}")
    if payload_path is not None:
        print(f"Payload: {payload_path} ({payload_len:,} bytes)")
    print(f"Compression: none (raw body, {info['stored_len']:,} bytes)")
    print(f"Output: {out}\nResolution: {encoded.width}x{encoded.height}\nGrid: {info['grid_w']}x{info['grid_h']} blocks")
    print(f"Stored body bytes before error correction: {info['stored_len']:,}; wire body: {info['wire_body_len']:,} bytes")
    print(f"Error correction: {info['error_correction']}")
    print(f"Bit repetition: {REPEAT} votes per wire bit\nPer-channel modification limit per pass: ±2 levels")
    print(f"Encoder passes (--redo): {info.get('redo_passes', 1)}")
    if info.get("resized"):
        print("Auto-resized cover: yes")
    print(f"Header copies: top-left + center; header repetition: {HEADER_REPEAT} votes/bit; header remainder: {HEADER_DATA_REPEAT} votes/bit")
    print("Verification: final strict in-memory decode and saved-PNG read-back both passed.")
    print("Compression/crop survival is empirical; no lossy image pipeline can be guaranteed.")


def _save_raw_barcode(image: Image.Image, path: Path, expected_payload: bytes, force: bool = False):
    path = Path(path)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force:
            raise HushRasterError(f"Output already exists: {path} (use --force)")
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp.png", dir=str(path.parent))
        os.close(fd)
        temporary = Path(name)
        image.save(temporary, format="PNG")
        if decode_raw_barcode(temporary) != expected_payload:
            raise HushRasterError("Headerless barcode failed byte-exact read-back verification")
        if force:
            os.replace(temporary, path)
        else:
            _install_no_replace(temporary, path)
        temporary = None
    except (RawBarcodeError, OSError) as exc:
        raise HushRasterError(f"Could not safely save barcode: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _unsupported_standard(standard: str):
    item = STANDARDS[standard]
    if item.status in ("planned", "reserved"):
        raise HushRasterError(
            f"HushRaster {item.code} ({item.name}) is {item.status}: {item.description}. "
            "It is registered, but not implemented for encoding/decoding yet."
        )
    raise HushRasterError(f"HushRaster {item.code} is not supported for this operation")


def _save_newstandard_png(image: Image.Image, path: Path, payload: bytes, standard: str, force: bool, max_pixels: int):
    """Save a custom-standard PNG only after a byte-exact read-back check."""
    from .newstandards import decode_new_standard

    path = Path(path)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force:
            raise HushRasterError(f"Output already exists: {path} (use --force)")
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp.png", dir=str(path.parent))
        os.close(fd)
        temporary = Path(name)
        image.save(temporary, format="PNG")
        with Image.open(temporary) as stored:
            stored.load()
            recovered = decode_new_standard(stored, standard, max_pixels=max_pixels)
        if recovered != payload:
            raise HushRasterError(f"Saved {standard.upper()} PNG failed byte-exact read-back verification")
        if force:
            os.replace(temporary, path)
        else:
            _install_no_replace(temporary, path)
        temporary = None
    except HushRasterError:
        raise
    except Exception as exc:
        raise HushRasterError(f"Could not safely save {standard.upper()} barcode: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _encode_oi1(payload: bytes, a) -> Image.Image:
    """Generate the historical OI1 modulation on a generated grey carrier."""
    import numpy as np

    ppm = a.ppm
    scale = max(1, (ppm + 1) // 2)  # Legacy OI1 has 8px carrier tiles, not pixel modules.
    color = getattr(a, "on_blank", "808080")
    canvas = create_blank_canvas(payload, "", color=color, compression="none", max_pixels=a.max_pixels)
    if scale != 1:
        size = (canvas.width * scale, canvas.height * scale)
        if size[0] * size[1] > a.max_pixels:
            raise HushRasterError(
                f"OI1 at --ppm {ppm} needs {size[0]}x{size[1]} pixels; lower --ppm or raise --max-pixels"
            )
        canvas = canvas.resize(size, Image.Resampling.NEAREST)
    redo, compression = _encoder_settings(a)
    encoded, _info = encode_repeated(
        canvas, payload, "", redo=redo, max_pixels=a.max_pixels,
        compression=compression, verify=True,
    )
    base = np.asarray(canvas.convert("RGB").getpixel((0, 0)), dtype=np.int16)
    pixels = np.asarray(encoded.convert("RGB"), dtype=np.int16)
    visible = np.clip(base + (pixels - base) * 32, 0, 255).astype("uint8")
    return Image.fromarray(visible, "RGB")


def _png_bytes_and_verify(image: Image.Image, payload: bytes, standard: str, max_pixels: int) -> bytes:
    """Serialize PNG to memory and verify the exact bytes before writing stdout."""
    from .newstandards import decode_new_standard

    stream = BytesIO()
    image.save(stream, format="PNG")
    data = stream.getvalue()
    stream.seek(0)
    with Image.open(stream) as saved:
        saved.load()
        if standard in ("p1", "p2"):
            recovered, _detected = decode_with_standard(saved, standard=standard, max_pixels=max_pixels)
        elif standard == "oi1":
            recovered, _meta, stats = decode_image(saved, mode="strict")
            if not stats.get("integrity_verified"):
                raise HushRasterError("OI1 PNG failed strict integrity verification")
        else:
            recovered = decode_new_standard(saved, standard, max_pixels=max_pixels)
        if recovered != payload:
            raise HushRasterError(f"Generated {standard.upper()} PNG failed byte-exact read-back verification")
    return data


def cmd_encode(a):
    """Read arbitrary bytes from stdin; write a verified PNG to stdout."""
    payload = sys.stdin.buffer.read()
    standard = getattr(a, "standard", None) or "p2"
    if standard not in STANDARDS:
        raise HushRasterError(f"Unknown standard {standard!r}; use `standards` to list available standards")
    if standard in ("e1", "l1"):
        _unsupported_standard(standard)
    ppm = a.ppm
    if isinstance(ppm, bool) or not isinstance(ppm, int) or not 1 <= ppm <= 32:
        raise HushRasterError("--ppm must be an integer from 1 through 32")

    if standard == "p2":
        image = encode_raw_barcode(payload, max_pixels=a.max_pixels, module_size=ppm)
        detail = "interleaved Reed-Solomon correction + CRC32"
    elif standard == "p1":
        image = encode_p1_bytes(payload, max_pixels=a.max_pixels, module_size=ppm)
        detail = "triple-bit repetition + CRC32"
    elif standard == "oi1":
        image = _encode_oi1(payload, a)
        detail = "legacy standalone modulation on generated carrier"
    elif standard == "sl1":
        from .slbarcode import encode_sl1
        image = encode_sl1(payload, ppm=ppm, max_pixels=a.max_pixels)
        detail = "single row of variable-height vertical bars; CRC32 + Reed-Solomon (32 parity symbols)"
    elif standard in ("p3", "d1", "ce1", "z1"):
        from .newstandards import encode_ce1, encode_d1, encode_p3, encode_z1
        encoders = {"p3": encode_p3, "d1": encode_d1, "ce1": encode_ce1, "z1": encode_z1}
        image = encoders[standard](payload, ppm=ppm, max_pixels=a.max_pixels)
        detail = STANDARDS[standard].description
    else:
        from .newstandards import encode_variant
        image = encode_variant(payload, standard, ppm=ppm, max_pixels=a.max_pixels)
        detail = STANDARDS[standard].description

    png = _png_bytes_and_verify(image, payload, standard, a.max_pixels)
    sys.stdout.buffer.write(png)
    sys.stdout.buffer.flush()
    print(
        f"HushRaster {VERSION} {standard.upper()} ({STANDARDS[standard].name}): "
        f"encoded {len(payload):,} stdin bytes; PNG {image.width}x{image.height}; --ppm {ppm}; {detail}",
        file=sys.stderr,
    )
    return 0

def cmd_imgmod_encode(a):
    """Legacy origin-image overlay; payload bytes are read from stdin."""
    inputs = [Path(value).expanduser() for value in a.inputs]
    redo, compression = _encoder_settings(a)
    if len(inputs) != 2:
        raise HushRasterError("Use: imgmod encode IMAGE_FILE OUTPUT.png; payload bytes are read from stdin")
    source, out = inputs
    if not source.is_file():
        raise HushRasterError(f"Image not found: {source}")
    payload = sys.stdin.buffer.read()
    image = read_image(source)
    if out.resolve() == source.resolve():
        raise HushRasterError("Output must not overwrite the input image")
    _check_output_format(out)
    encoded, info = encode_repeated(
        image, payload, "", redo=redo, resize=a.resize,
        max_pixels=a.max_pixels, compression=compression, verify=True,
    )
    save_verified_png(encoded, out, payload, force=a.force)
    print(
        f"HushRaster {VERSION}: legacy IMGMod overlay encoded {len(payload):,} stdin bytes; "
        f"{encoded.width}x{encoded.height}; ECC {info['error_correction']}",
        file=sys.stderr,
    )
    return 0


def _legacy_decode(a):
    payload, meta, stats = _decode_args(a)
    _warn_if_needed(stats, getattr(a, "focus", False))
    if not stats.get("integrity_verified") and not getattr(a, "allow_unverified", False):
        raise HushRasterError(
            "OI1 integrity could not be verified. Refusing to output bytes; use --allow-unverified "
            "only when knowingly accepting potentially incorrect or incomplete data."
        )
    return payload, "oi1", {"meta": meta, "stats": stats}


def _decode_any(a, image=None):
    """Decode a PNG image supplied by the caller; normal commands never open paths."""
    if image is None:
        raw_png = sys.stdin.buffer.read()
        if not raw_png:
            raise HushRasterError("No PNG bytes received on stdin")
        try:
            image = read_image(BytesIO(raw_png))
        except Exception as exc:
            raise HushRasterError(f"Could not read PNG from stdin: {exc}") from exc
    standard = getattr(a, "standard", None)
    if standard in ("e1", "l1"):
        _unsupported_standard(standard)
    if standard == "oi1":
        payload, meta, stats = decode_image(image, max_search_width=a.max_search_width,
                                            mode=a.mode,
                                            force_compression=("z" if getattr(a, "force_zlib", False) else
                                                               "none" if getattr(a, "force_no_zlib", False) else None))
        _warn_if_needed(stats, getattr(a, "focus", False))
        if not stats.get("integrity_verified") and not getattr(a, "allow_unverified", False):
            raise HushRasterError("OI1 integrity could not be verified; use --allow-unverified only if you accept possibly incorrect data")
        return payload, "oi1", {"meta": meta, "stats": stats}
    if standard in ("p1", "p2"):
        try:
            payload, detected = decode_with_standard(image, standard=standard, max_pixels=a.max_pixels)
            return payload, detected, None
        except (RawBarcodeError, ValueError) as exc:
            raise HushRasterError(str(exc)) from exc
    if standard is not None:
        from .newstandards import decode_new_standard
        try:
            return decode_new_standard(image, standard, max_pixels=a.max_pixels), standard, None
        except (NewBarcodeError, ValueError) as exc:
            raise HushRasterError(str(exc)) from exc
    failures = []
    try:
        payload, detected = decode_with_standard(image, max_pixels=a.max_pixels)
        return payload, detected, None
    except (RawBarcodeError, ValueError) as exc:
        failures.append(f"P2/P1: {exc}")
    try:
        from .newstandards import decode_auto_new
        payload, detected = decode_auto_new(image, max_pixels=a.max_pixels)
        return payload, detected, None
    except Exception as exc:
        failures.append(f"P3/OI2/CE1/Z1: {exc}")
    try:
        payload, meta, stats = decode_image(image, max_search_width=a.max_search_width, mode=a.mode)
        _warn_if_needed(stats, getattr(a, "focus", False))
        if not stats.get("integrity_verified") and not getattr(a, "allow_unverified", False):
            raise HushRasterError("OI1 integrity could not be verified; use --allow-unverified only if you accept possibly incorrect data")
        return payload, "oi1", {"meta": meta, "stats": stats}
    except Exception as exc:
        failures.append(f"OI1: {exc}")
    raise HushRasterError("Could not identify a HushRaster barcode: " + " | ".join(failures))


def cmd_decode(a):
    """Read a PNG from stdin and write the exact recovered bytes to stdout."""
    payload, _standard, _details = _decode_any(a)
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()
    return 0

def _standard_description(code: str, payload: bytes, details=None) -> str:
    count = len(payload)
    if code == "p2":
        return f"HushRaster P2 (Panda 2): verified\nDecoded bytes: {count:,}\nError correction: interleaved Reed-Solomon + CRC32"
    if code == "p1":
        return f"HushRaster P1 (Panda 1): verified\nDecoded bytes: {count:,}\nError correction: triple-bit repetition + CRC32"
    if code == "p3":
        return f"HushRaster P3: decoded {count:,} bytes\nFraming: 32-bit payload length + literal payload\nChecksum: none\nError correction: none; damaged data is not detected"
    if code == "d1":
        return f"HushRaster D1 (Diagonal 1): decoded {count:,} bytes\nLayout: diagonal data modules on a white barcode canvas\nChecksum: none\nError correction: none"
    if code == "ce1":
        return f"HushRaster CE1 (Colored Elephant 1): verified {count:,} bytes\nEncoding: five-colour base-5 module symbols (black, white, red, green, blue)\nChecksum: CRC32\nError correction: none"
    if code == "z1":
        return f"HushRaster Z1 (Zebra 1): verified {count:,} bytes\nLayout: striped monochrome barcode\nChecksum: CRC32\nError correction: none"
    if code == "sl1":
        return (f"HushRaster SL1 (Scan Lonely 1): verified {count:,} bytes\n"
                "Layout: one row of equal-width vertical bars; height encodes each four-bit symbol\n"
                "Integrity: CRC32\nError correction: Reed-Solomon with 32 parity symbols per codeword; up to 16 byte-symbol errors per codeword")
    if details is None:
        item = STANDARDS.get(code)
        label = item.name if item else code.upper()
        return f"HushRaster {code.upper()} ({label}): verified {count:,} bytes\nFormat: {item.description if item else 'standalone barcode'}"
    meta, stats = details["meta"], details["stats"]
    state = "verified" if stats.get("integrity_verified") else ("uncertain reconstruction" if stats.get("uncertain") else "integrity unverified")
    return (
        f"HushRaster OI1 (OverImage 1): {state}\nDecoded bytes: {count:,}\n"
        f"Original uncompressed length: {meta['raw_len']:,}\nStored body before ECC: {meta['stored_len']:,} bytes\n"
        f"Wire body length: {stats.get('wire_body_len', meta['stored_len']):,} bytes\n"
        f"Error correction: {stats.get('error_correction', 'none')}\nCompression: {meta['compression']}\n"
        f"Original filename: {meta['filename'] or '(not stored)'}\nOriginal grid: {meta['grid_w']}x{meta['grid_h']} blocks"
    )


def cmd_inspect(a):
    raw_png = sys.stdin.buffer.read()
    if not raw_png:
        raise HushRasterError("No PNG bytes received on stdin")
    try:
        with Image.open(BytesIO(raw_png)) as opened:
            opened.load()
            image = opened.copy()
    except Exception as exc:
        raise HushRasterError(f"Could not read PNG from stdin: {exc}") from exc
    payload, standard, details = _decode_any(a, image)
    dimensions = f"{image.width}x{image.height}"
    print(_standard_description(standard, payload, details))
    print(f"Image dimensions: {dimensions}\nPixels per module: --ppm (default 4 when encoding)")
    if a.show_full_raw_data:
        print(f"Payload raw hex: {payload.hex()}")
    return 0


def cmd_standards(_a):
    print(standard_listing())
    return 0


def cmd_capacity(a):
    raw_png = sys.stdin.buffer.read()
    if not raw_png:
        raise HushRasterError("No PNG bytes received on stdin")
    try:
        im = read_image(BytesIO(raw_png))
    except Exception as exc:
        raise HushRasterError(f"Could not read PNG from stdin: {exc}") from exc
    tiles = (im.width // 8) * (im.height // 8)
    lo, hi = 0, max(0, tiles // (8 * REPEAT))
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if required_tiles(mid, "") <= tiles:
            lo = mid
        else:
            hi = mid - 1
    print(f"Resolution: {im.width}x{im.height}\n8x8 blocks: {tiles:,}\nApproximate maximum raw payload without filename metadata (uncompressed): {lo:,} bytes")
    print("This estimates legacy OI1/IMGMod capacity, not the capacity of P1/P2/P3/OI2/CE1/Z1.")
    return 0


def cmd_compare(a):
    x = read_image(Path(a.original).expanduser())
    y = read_image(Path(a.encoded).expanduser())
    if x.size != y.size:
        y = y.resize(x.size, Image.Resampling.LANCZOS)
    import numpy as np
    d = abs(np.asarray(x).astype("int16") - np.asarray(y).astype("int16"))
    print(f"Exact pixels: {100 * (d.max(axis=2) == 0).mean():.4f}%\nPixels within 2/channel: {100 * (d.max(axis=2) <= 2).mean():.4f}%\nMax channel delta: {int(d.max())}\nMean absolute channel error: {d.mean():.5f}/255\nNormalized similarity: {100 * (1 - d.mean() / 255):.6f}%")
    return 0


def _add_barcode_encoding_options(parser):
    parser.add_argument("--ppm", type=int, choices=range(1, 33), default=4,
                        help="pixels per barcode module (default: 4; use 1 for the smallest raster)")
    parser.add_argument("--max-pixels", type=int, default=MAX_PIXELS,
                        help="maximum generated/scanned raster pixels (default: 40,000,000)")


def _add_decode_options(parser):
    parser.add_argument("--max-pixels", type=int, default=MAX_PIXELS,
                        help="maximum raster pixels accepted by the scanner")
    parser.add_argument("--max-search-width", type=int, default=8192)
    parser.add_argument("--mode", choices=MODES, default="best",
                        help="legacy OI1 scanner mode: best/depends/default/strict/fast/reconstruct")
    force = parser.add_mutually_exclusive_group()
    force.add_argument("--force-zlib", dest="force_zlib", action="store_true", help=argparse.SUPPRESS)
    force.add_argument("--force-no-zlib", dest="force_no_zlib", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--focus", action="store_true", help="suppress legacy reconstruction warnings")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="hushraster",
        description="HushRaster barcode standards. Normal encode/decode/inspect/capacity commands use stdin/stdout only; imgmod is the legacy file-based exception.",
    )
    parser.add_argument("--version", action="version", version=f"HushRaster {VERSION}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    enc = sub.add_parser("encode", help="encode raw stdin bytes into a PNG written to stdout (defaults to P2)")
    enc.add_argument("--standard", choices=tuple(STANDARDS), help=argparse.SUPPRESS)
    _add_barcode_encoding_options(enc)
    enc.add_argument("--on-blank", default="808080", help="OI1 only: generated carrier colour (default: grey)")
    enc.add_argument("--redo", type=int, default=1, help=argparse.SUPPRESS)
    enc.add_argument("--resize", action="store_true", help=argparse.SUPPRESS)
    enc.add_argument("--no-filename", action="store_true", help=argparse.SUPPRESS)
    enc.set_defaults(func=cmd_encode)

    dec = sub.add_parser("decode", help="read a PNG from stdin and write exact recovered bytes to stdout")
    dec.add_argument("--standard", choices=tuple(STANDARDS), help=argparse.SUPPRESS)
    dec.add_argument("--allow-unverified", action="store_true", help="permit legacy OI1 recovery without a verified integrity status")
    _add_decode_options(dec)
    dec.set_defaults(func=cmd_decode)

    ins = sub.add_parser("inspect", help="read a PNG from stdin and report standard/integrity details")
    ins.add_argument("--standard", choices=tuple(STANDARDS), help=argparse.SUPPRESS)
    ins.add_argument("--show-full-raw-data", action="store_true")
    ins.add_argument("--allow-unverified", action="store_true")
    _add_decode_options(ins)
    ins.set_defaults(func=cmd_inspect)

    sub.add_parser("standards", help="list all registered HushRaster standards").set_defaults(func=cmd_standards)

    cap = sub.add_parser("capacity", help="estimate legacy OI1/IMGMod capacity from a PNG on stdin")
    cap.set_defaults(func=cmd_capacity)

    imgmod = sub.add_parser("imgmod", help="legacy OI1 modulation over an existing origin image")
    ims = imgmod.add_subparsers(dest="imgmod_cmd", required=True)
    ie = ims.add_parser("encode", help="modulate stdin bytes into an existing image (legacy OI1)")
    ie.add_argument("inputs", nargs="+", metavar="PATH", help="IMAGE_FILE OUTPUT.png; bytes come from stdin")
    ie.add_argument("--resize", action="store_true", help="upscale an undersized origin image when needed")
    ie.add_argument("--max-pixels", type=int, default=MAX_PIXELS)
    ie.add_argument("--redo", type=int, default=1)
    ie.add_argument("--force", "-f", action="store_true")
    ie.set_defaults(func=cmd_imgmod_encode)

    comp = ims.add_parser("compare", help="compare an original image with its IMGMod output")
    comp.add_argument("original")
    comp.add_argument("encoded")
    comp.set_defaults(func=cmd_compare)
    return parser


def _normalize_cli_standard(argv):
    values = list(sys.argv[1:] if argv is None else argv)
    actions = {"encode", "decode", "inspect"}
    if values and values[0] in actions and len(values) > 1 and values[1].lower().endswith("+"):
        requested = values[1].lower()[:-1]
        if requested == "oi":
            requested = "oi1"
        if requested == "oi2":
            requested = "d1"
        if requested not in STANDARDS:
            raise HushRasterError(
                f"Unknown HushRaster standard selector {values[1]!r}; use `hushraster standards` to list standards"
            )
        values = [values[0], "--standard", requested, *values[2:]]
    return values


def main(argv=None):
    try:
        values = _normalize_cli_standard(argv)
        args = build_parser().parse_args(values)
        if hasattr(args, "standard") and args.standard is not None:
            args.standard = normalize_standard(args.standard)
        return args.func(args)
    except (HushRasterError, RawBarcodeError, ValueError) as exc:
        print(f"hushraster: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
