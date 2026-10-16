from __future__ import annotations

import argparse
import errno
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image

from .encoder import MAX_REDO, create_blank_canvas, encode_repeated, parse_color

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
    compression = "z" if a.zlib_compression else "none"
    return redo, compression


def _print_encoding_summary(out: Path, encoded: Image.Image, info: dict, payload_len: int,
                            compression: str, *, source: Path | None = None,
                            payload_path: Path | None = None, blank_color=None):
    if source is None:
        print("Input image: generated blank canvas" + (f" RGB {blank_color}" if blank_color is not None else ""))
    else:
        print(f"Input image: {source}")
    if payload_path is not None:
        print(f"Payload: {payload_path} ({payload_len:,} bytes)")
    if info["compression"] == "z":
        print(f"Compression: zlib level 1 (explicitly requested)\nStored body: {info['stored_len']:,} bytes ({info['compression_ratio']:.1%} of original)")
    else:
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


def cmd_encode(a):
    inputs = [Path(value).expanduser() for value in a.inputs]
    on_blank = getattr(a, "on_blank", None)
    redo, compression = _encoder_settings(a)
    if on_blank is not None:
        if len(inputs) != 2:
            raise HushRasterError("With --on-blank COLOR, use: encode PAYLOAD_FILE OUTPUT.png --on-blank COLOR")
        payload_path, out = inputs
        src = None
        if not payload_path.is_file():
            raise HushRasterError(f"Payload not found: {payload_path}")
        payload = payload_path.read_bytes()
        filename = "" if a.no_filename else payload_path.name
        color = parse_color(on_blank)
        image = create_blank_canvas(payload, filename, color, compression, max_pixels=a.max_pixels)
    else:
        if len(inputs) != 3:
            raise HushRasterError("Use: encode IMAGE_FILE PAYLOAD_FILE OUTPUT.png (or PAYLOAD_FILE OUTPUT.png --on-blank COLOR)")
        src, payload_path, out = inputs
        if not src.is_file():
            raise HushRasterError(f"Image not found: {src}")
        if not payload_path.is_file():
            raise HushRasterError(f"Payload not found: {payload_path}")
        payload = payload_path.read_bytes()
        filename = "" if a.no_filename else payload_path.name
        image = read_image(src)
        color = None
    if out.resolve() in {p.resolve() for p in (src, payload_path) if p is not None}:
        raise HushRasterError("Output must not overwrite the input image or payload")
    _check_output_format(out)
    encoded, info = encode_repeated(
        image, payload, filename, redo=redo, resize=a.resize,
        max_pixels=a.max_pixels, compression=compression, verify=True,
    )
    save_verified_png(encoded, out, payload, force=a.force)
    print(f"HushRaster {VERSION}: encoded")
    _print_encoding_summary(out, encoded, info, len(payload), compression,
                            source=src, payload_path=payload_path, blank_color=color)
    return 0


def cmd_encode_text(a):
    inputs = list(a.inputs)
    on_blank = getattr(a, "on_blank", None)
    redo, compression = _encoder_settings(a)
    if on_blank is not None:
        if len(inputs) != 2:
            raise HushRasterError("With --on-blank COLOR, use: encode-text TEXT OUTPUT.png --on-blank COLOR")
        text_value, out_value = inputs
        src = None
        payload_path = None
        out = Path(out_value).expanduser()
        payload = text_value.encode("utf-8")
        color = parse_color(on_blank)
        image = create_blank_canvas(payload, "", color, compression, max_pixels=a.max_pixels)
    else:
        if len(inputs) != 3:
            raise HushRasterError("Use: encode-text IMAGE TEXT OUTPUT.png (or TEXT OUTPUT.png --on-blank COLOR)")
        src = Path(inputs[0]).expanduser()
        text_value, out_value = inputs[1], inputs[2]
        payload_path = None
        out = Path(out_value).expanduser()
        if not src.is_file():
            raise HushRasterError(f"Image not found: {src}")
        payload = text_value.encode("utf-8")
        image = read_image(src)
        color = None
    if src is not None and out.resolve() == src.resolve():
        raise HushRasterError("Output must not overwrite input image")
    _check_output_format(out)
    encoded, info = encode_repeated(
        image, payload, "", redo=redo, resize=a.resize,
        max_pixels=a.max_pixels, compression=compression, verify=True,
    )
    save_verified_png(encoded, out, payload, force=a.force)
    print(f"Encoded {len(payload):,} UTF-8 bytes using {'zlib' if compression == 'z' else 'raw storage'} to {out} ({encoded.width}x{encoded.height})")
    print(f"Body error correction: {info['error_correction']} ({info['stored_len']:,} pre-ECC bytes → {info['wire_body_len']:,} wire bytes)")
    print(f"Encoder passes (--redo): {info.get('redo_passes', 1)}")
    if color is not None:
        print(f"Blank canvas color: RGB {color}")
    print("Verification: final strict in-memory decode and saved-PNG read-back both passed.")
    if compression == "z":
        print(f"Stored compressed body before error correction: {info['stored_len']:,} bytes")
    return 0

def cmd_decode(a, text=False):
    src = Path(a.image).expanduser()
    if not src.is_file():
        raise HushRasterError(f"Image not found: {src}")
    payload, meta, stats = _decode_args(a)
    _warn_if_needed(stats, a.focus)
    if not stats.get("integrity_verified") and not getattr(a, "allow_unverified", False):
        raise HushRasterError(
            "Refusing to write or print recovered bytes because their integrity was not verified. "
            "Keep the carrier and retry with --mode strict for verified-only decoding, or add "
            "--allow-unverified only if you knowingly accept potentially incorrect/incomplete bytes."
        )
    if text:
        try:
            textval = payload.decode("utf-8")
        except UnicodeDecodeError as e:
            raise HushRasterError("Recovered payload is not valid UTF-8; use decode to recover raw bytes") from e
        if a.output:
            out = Path(a.output).expanduser()
            if out.resolve() == src.resolve():
                raise HushRasterError("Output must not overwrite input image")
            write_output(out, payload, a.force)
            print(f"Text saved to: {out}")
        else:
            sys.stdout.write(textval)
            if not textval.endswith("\n"):
                sys.stdout.write("\n")
    else:
        if a.pipe:
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
            return 0
        if a.output:
            out = Path(a.output).expanduser()
        else:
            out = Path(Path(meta["filename"]).name if meta["filename"] else "recovered.bin").expanduser()
        if out.resolve() == src.resolve():
            raise HushRasterError("Output must not overwrite input image")
        write_output(out, payload, a.force)
        if stats.get("integrity_verified"):
            details = []
            if stats.get("ecc_corrected_symbols"):
                details.append(f"SECDED corrected {stats['ecc_corrected_symbols']} codeword bit error(s)")
            if stats.get("repair_bits"):
                details.append(f"repaired {stats['repair_bits']} low-confidence bit vote(s)")
            suffix = f" ({'; '.join(details)})" if details else ""
            print(f"Recovered and verified {len(payload):,} bytes: {out}{suffix}")
        elif a.focus and stats.get("warning"):
            print(f"Output written ({len(payload):,} bytes): {out}")
        elif stats.get("uncertain"):
            print(f"Best-effort output written ({len(payload):,} bytes; NOT verified): {out}")
        else:
            print(f"Output written ({len(payload):,} bytes; integrity unverified): {out}")
    return 0


def cmd_inspect(a):
    src = Path(a.image).expanduser()
    if not src.is_file():
        raise HushRasterError(f"Image not found: {src}")
    payload, meta, stats = _decode_args(a)
    _warn_if_needed(stats, a.focus)
    state = "verified" if stats.get("integrity_verified") else (
        "decoded" if a.focus and stats.get("warning") else
        ("uncertain reconstruction" if stats.get("uncertain") else "integrity unverified")
    )
    print(f"HushRaster payload: {state}\nDecoded bytes: {len(payload):,}\nOriginal uncompressed length from header: {meta['raw_len']:,}")
    print(f"Stored body before ECC: {meta['stored_len']:,} bytes\nWire body length: {stats.get('wire_body_len', meta['stored_len']):,} bytes")
    print(f"Error correction: {stats.get('error_correction', 'none')}\nCompression method in header: {meta['compression']}\nCompression method used: {stats['compression_used']}")
    if stats.get("ecc_corrected_symbols"):
        print(f"ECC repair: corrected {stats['ecc_corrected_symbols']} Hamming SECDED codeword bit error(s)")
    print(f"Original filename: {meta['filename'] or '(not stored)'}\nOriginal grid: {meta['grid_w']}x{meta['grid_h']} blocks")
    if stats.get("repair_bits"):
        print(f"Repair: verified by integrity tag after changing {stats['repair_bits']} low-confidence bit vote(s)")
    if a.show_full_raw_data:
        print(f"Header raw hex: {meta['raw'].hex()}")
    return 0


def cmd_capacity(a):
    im = read_image(Path(a.image).expanduser())
    tiles = (im.width // 8) * (im.height // 8)
    lo, hi = 0, max(0, tiles // (8 * REPEAT))
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if required_tiles(mid, "") <= tiles:
            lo = mid
        else:
            hi = mid - 1
    print(f"Resolution: {im.width}x{im.height}\n8x8 blocks: {tiles:,}\nApproximate maximum raw payload without filename metadata (uncompressed): {lo:,} bytes")
    print("With --zlib, capacity depends on the compressed size of the specific payload.")
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


def _add_encoding_options(parser, text=False):
    parser.add_argument("--resize", action="store_true", help="explicitly upscale a too-small existing cover (blank canvases size themselves automatically)")
    parser.add_argument("--max-pixels", type=int, default=MAX_PIXELS)
    parser.add_argument("--zlib", "-z", dest="zlib_compression", action="store_true",
                        help="explicitly compress payload with fast zlib level 1 before embedding (default: raw/uncompressed)")
    parser.add_argument("--redo", type=int, default=1, help=f"apply the encoder repeatedly to its own output (default: 1; max: {MAX_REDO})")
    parser.add_argument("--on-blank", metavar="COLOR", default=None,
                        help="create a minimum-size solid-color canvas instead of reading a cover (e.g. cyan, FF, 0, 80, #12ABEF)")
    parser.add_argument("--force", "-f", action="store_true", help="overwrite output if it exists")
    if not text:
        parser.add_argument("--no-filename", action="store_true", help="do not store source filename in hidden header")


def _add_decode_options(parser):
    parser.add_argument("--max-search-width", type=int, default=8192)
    parser.add_argument("--mode", choices=MODES, default="best",
                        help="best/depends/default: adaptive; strict: verified output only; fast: top-left-only; reconstruct: deeper repair + partial recovery")
    force = parser.add_mutually_exclusive_group()
    force.add_argument("--force-zlib", dest="force_zlib", action="store_true", help="force zlib decompression regardless of the header")
    force.add_argument("--force-no-zlib", dest="force_no_zlib", action="store_true", help="treat the stored body as raw regardless of the header")
    parser.add_argument("--focus", action="store_true", help="suppress recovery/uncertainty warnings")


def build_parser():
    p = argparse.ArgumentParser(prog="hushraster", description="Hide arbitrary bytes in images with explicit, opt-in zlib compression (HushRaster 1.0).")
    p.add_argument("--version", action="version", version=f"HushRaster {VERSION}")
    s = p.add_subparsers(dest="cmd", required=True)

    e = s.add_parser("encode", help="encode a file into an image")
    e.add_argument("inputs", nargs="+", metavar="PATH", help="IMAGE PAYLOAD OUTPUT; or PAYLOAD OUTPUT with --on-blank COLOR")
    _add_encoding_options(e)
    e.set_defaults(func=cmd_encode)

    et = s.add_parser("encode-text", help="encode a text string into an image")
    et.add_argument("inputs", nargs="+", metavar="VALUE", help="IMAGE TEXT OUTPUT; or TEXT OUTPUT with --on-blank COLOR")
    _add_encoding_options(et, text=True)
    et.set_defaults(func=cmd_encode_text)

    d = s.add_parser("decode", help="decode raw bytes from an image")
    d.add_argument("image"); d.add_argument("output", nargs="?")
    d.add_argument("--pipe", action="store_true", help="write raw bytes to stdout instead of a file")
    d.add_argument("--force", "-f", action="store_true", help="overwrite output if it exists")
    d.add_argument("--allow-unverified", action="store_true", help="permit output when the payload integrity check failed or was bypassed")
    _add_decode_options(d)
    d.set_defaults(func=cmd_decode)

    dt = s.add_parser("decode-text", help="decode UTF-8 text from an image")
    dt.add_argument("image"); dt.add_argument("output", nargs="?")
    dt.add_argument("--force", "-f", action="store_true", help="overwrite output if it exists")
    dt.add_argument("--allow-unverified", action="store_true", help="permit output when the payload integrity check failed or was bypassed")
    _add_decode_options(dt)
    dt.set_defaults(func=lambda a: cmd_decode(a, True))

    i = s.add_parser("inspect", help="read payload metadata and verify/decode the payload")
    i.add_argument("image"); i.add_argument("--show-full-raw-data", action="store_true")
    _add_decode_options(i)
    i.set_defaults(func=cmd_inspect)

    c = s.add_parser("capacity", help="estimate uncompressed capacity")
    c.add_argument("image"); c.set_defaults(func=cmd_capacity)

    q = s.add_parser("compare", help="compare source and encoded RGB images")
    q.add_argument("original"); q.add_argument("encoded"); q.set_defaults(func=cmd_compare)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except HushRasterError as e:
        print(f"hushraster: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
