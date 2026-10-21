#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Focused fail-safe tests for the evolving HushRaster 1.0.1 development format."""
from pathlib import Path
import argparse
import errno
import random
import sys
import tempfile
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hushraster.core import (  # noqa: E402
    FORMAT_VERSION,
    HushRasterError,
    _decode_center_prefix,
    _decode_prefix_for_width,
    _data_permutation,
    _ecc_wire_len,
    _hamming13_decode,
    _hamming13_encode,
    _modulate_tile,
    _prefix_permutation,
    bits,
    HEADER_REPEAT,
    PREFIX_REGION,
    decode_image,
    encode_image,
    read_image,
    required_tiles,
)
from hushraster.cli import _decode_any, save_verified_png, write_output  # noqa: E402
from hushraster.encoder import create_blank_canvas  # noqa: E402


def flip_wire_bit(data: bytes, bit_index: int) -> bytes:
    changed = bytearray(data)
    changed[bit_index // 8] ^= 1 << (7 - bit_index % 8)
    return bytes(changed)


def test_hamming_secdec() -> None:
    rng = random.Random(0x48525331)
    for length in (0, 1, 2, 7, 8, 41, 223, 224, 500):
        original = bytes(rng.randrange(256) for _ in range(length))
        wire = _hamming13_encode(original)
        assert len(wire) == _ecc_wire_len(length, 3)
        decoded, corrected = _hamming13_decode(wire, length)
        assert decoded == original and corrected == 0
        if length == 0:
            continue
        # Every one of the 13 codeword bit positions must be correctable.
        for bit_index in range(13):
            damaged = flip_wire_bit(wire, bit_index)
            decoded, corrected = _hamming13_decode(damaged, length)
            assert decoded == original and corrected == 1, (length, bit_index)
        # Any two flipped bits in one codeword must be detected, never silently
        # accepted as a valid codeword.
        for first in range(13):
            for second in range(first + 1, 13):
                damaged = flip_wire_bit(flip_wire_bit(wire, first), second)
                try:
                    _hamming13_decode(damaged, length)
                except HushRasterError:
                    pass
                else:
                    raise AssertionError(("double-bit error was not detected", length, first, second))


def test_revision2_fixture() -> None:
    fixture = ROOT / "tests" / "fixtures" / "legacy_v2.png"
    expected = (ROOT / "tests" / "fixtures" / "legacy_v2_payload.bin").read_bytes()
    recovered, header, stats = decode_image(read_image(fixture), mode="strict")
    assert FORMAT_VERSION == 3
    assert header["format_version"] == 2
    assert recovered == expected and stats["integrity_verified"]


def test_atomic_png_verification() -> None:
    cover = Image.new("RGB", (1536, 1536), (128, 128, 128))
    first_payload = b"first fully verified payload\x00"
    first_image, _ = encode_image(cover, first_payload, "", verify=True)
    test_combined_header_vote_recovery(first_image, first_payload, cover)

    with tempfile.TemporaryDirectory(prefix="hushraster-failsafe-") as temp_dir:
        target = Path(temp_dir) / "verified.png"
        save_verified_png(first_image, target, first_payload, force=False)
        original_file = target.read_bytes()
        recovered, _, stats = decode_image(read_image(target), mode="strict")
        assert recovered == first_payload and stats["integrity_verified"]

        # A mistaken expected payload must not replace the previously valid file,
        # even when --force semantics would otherwise permit replacement.
        try:
            save_verified_png(first_image, target, b"wrong expected bytes", force=True)
        except HushRasterError:
            pass
        else:
            raise AssertionError("invalid candidate PNG was installed")
        assert target.read_bytes() == original_file
        assert not list(Path(temp_dir).glob(".*.tmp.png")), "temporary file leaked after failed verification"

        # No-force must preserve the original; force must install a verified image.
        try:
            save_verified_png(first_image, target, first_payload, force=False)
        except HushRasterError:
            pass
        else:
            raise AssertionError("no-force save unexpectedly replaced the existing file")
        assert target.read_bytes() == original_file
        legacy_payload = (ROOT / "tests" / "fixtures" / "legacy_v2_payload.bin").read_bytes()
        legacy_image = read_image(ROOT / "tests" / "fixtures" / "legacy_v2.png")
        save_verified_png(legacy_image, target, legacy_payload, force=True)
        recovered, header, stats = decode_image(read_image(target), mode="strict")
        assert recovered == legacy_payload and stats["integrity_verified"] and header["format_version"] == 2
        assert not list(Path(temp_dir).glob(".*.tmp.png")), "temporary file leaked after successful verification"

        # Exercise the PNG no-clobber fallback on a filesystem where hard links
        # are disabled; the copied file must still decode and verify strictly.
        fallback_png = Path(temp_dir) / "fallback.png"
        with patch("hushraster.cli.os.link", side_effect=OSError(errno.EPERM, "hard links disabled")):
            save_verified_png(first_image, fallback_png, first_payload, force=False)
        fallback_recovered, _, fallback_stats = decode_image(read_image(fallback_png), mode="strict")
        assert fallback_recovered == first_payload and fallback_stats["integrity_verified"]


def test_capacity_accounts_for_ecc() -> None:
    raw_size = required_tiles(41, "", format_version=2)
    ecc_size = required_tiles(41, "", format_version=3)
    assert ecc_size > raw_size
    assert _ecc_wire_len(41, 3) == 67
    assert _ecc_wire_len(41, 2) == 41


def test_pixel_safety_preflight() -> None:
    class OversizedImage:
        width = 8001
        height = 5000

    oversized = OversizedImage()
    for operation in (
        lambda: encode_image(oversized, b"x", "", resize=True),
        lambda: decode_image(oversized),
    ):
        try:
            operation()
        except HushRasterError as exc:
            assert "pixel" in str(exc).lower() or "safety limit" in str(exc).lower()
        else:
            raise AssertionError("oversized image bypassed the codec pixel limit")


def test_blank_image_rejection() -> None:
    try:
        decode_image(Image.new("RGB", (256, 256), (128, 128, 128)))
    except HushRasterError as exc:
        assert "valid HushRaster header" in str(exc)
    else:
        raise AssertionError("a blank image was incorrectly accepted as a carrier")



def test_combined_header_vote_recovery(encoded: Image.Image | None = None, payload: bytes | None = None, base: Image.Image | None = None) -> None:
    if encoded is None or payload is None or base is None:
        payload = b"combined header vote recovery fixture\x00\xff"
        base = create_blank_canvas(payload, "combined-vote.bin", "80")
        encoded, _info = encode_image(base, payload, "combined-vote.bin")
    # Damage different prefix bits in opposite header anchors. The top-left
    # copy alone becomes invalid; the center copy alone also becomes invalid;
    # pooling the 52 votes per bit must recover the correct prefix. Reuse the
    # already-encoded fixture to keep the test suite fast.
    gw, gh = encoded.width // 8, encoded.height // 8
    prefix_meta = _decode_prefix_for_width(encoded, gw)
    assert prefix_meta is not None
    prefix_bits = list(bits(prefix_meta["prefix"]))
    top_bad = next(i for i, bit in enumerate(prefix_bits) if bit == 1)
    center_bad = next(i for i, bit in enumerate(prefix_bits) if bit == 0)
    prefix_order, _ = _prefix_permutation(FORMAT_VERSION)
    region_h = (PREFIX_REGION + gw - 1) // gw
    center_y0 = (gh - region_h) // 2
    center_start = center_y0 * gw
    pixels = __import__("numpy").array(encoded.convert("RGB"), copy=True)
    neutral = __import__("numpy").asarray(base.convert("RGB"))

    def rewrite_anchor_bit(bit_index: int, anchor: str, wrong_bit: int) -> None:
        # Flip the majority in one anchor by rewriting 14 of its 26 copies.
        for copy_index in range(14):
            logical = bit_index * HEADER_REPEAT + copy_index
            local_slot = prefix_order[logical]
            global_slot = local_slot if anchor == "top-left" else center_start + local_slot
            x, y = (global_slot % gw) * 8, (global_slot // gw) * 8
            pixels[y:y+8, x:x+8, :] = neutral[y:y+8, x:x+8, :]
            _modulate_tile(pixels, x, y, wrong_bit, local_slot)

    rewrite_anchor_bit(top_bad, "top-left", 0)
    rewrite_anchor_bit(center_bad, "center", 1)
    damaged = Image.fromarray(pixels, "RGB")
    assert _decode_prefix_for_width(damaged, gw) is None, "top-left anchor should be independently invalid"
    assert _decode_center_prefix(damaged, gw, gh) is None, "center anchor should be independently invalid"
    recovered, _header, stats = decode_image(damaged, mode="strict")
    assert recovered == payload and stats["integrity_verified"]
    assert stats["anchor"] == "combined-exact (top-left+center)", stats["anchor"]


def test_atomic_decoded_output_and_unverified_guard() -> None:
    with tempfile.TemporaryDirectory(prefix="hushraster-output-safety-") as temp_dir:
        root = Path(temp_dir)
        target = root / "recovered.bin"
        target.write_bytes(b"old verified bytes")
        try:
            write_output(target, b"must not overwrite", force=False)
        except HushRasterError:
            pass
        else:
            raise AssertionError("no-force decoded output overwrote an existing file")
        assert target.read_bytes() == b"old verified bytes"
        write_output(target, b"replacement", force=True)
        assert target.read_bytes() == b"replacement"
        # Exercise filesystems that forbid hard links (common on shared-storage
        # mounts): the exclusive-create fallback must still preserve old files.
        with patch("hushraster.cli.os.link", side_effect=OSError(errno.EPERM, "hard links disabled")):
            fallback_target = root / "fallback.bin"
            write_output(fallback_target, b"fallback bytes", force=False)
            assert fallback_target.read_bytes() == b"fallback bytes"
        assert not list(root.glob(".*.tmp")) and not list(root.glob(".*.tmp.png")), "temporary output leaked"

        args = argparse.Namespace(
            standard="oi1", max_search_width=8192, mode="best",
            force_zlib=False, force_no_zlib=False, focus=False,
            allow_unverified=False, max_pixels=40_000_000,
        )
        uncertain = (b"possibly damaged bytes", {"filename": ""}, {
            "integrity_verified": False, "uncertain": True,
            "warning": "simulated integrity failure", "compression_used": "none",
        })
        carrier = Image.new("RGB", (32, 32), (128, 128, 128))
        with patch("hushraster.cli.decode_image", return_value=uncertain):
            try:
                _decode_any(args, carrier)
            except HushRasterError as exc:
                assert "integrity could not be verified" in str(exc)
            else:
                raise AssertionError("CLI accepted unverified OI1 bytes without opt-in")
        args.allow_unverified = True
        with patch("hushraster.cli.decode_image", return_value=uncertain):
            recovered, code, details = _decode_any(args, carrier)
        assert recovered == b"possibly damaged bytes" and code == "oi1"
        assert details["stats"]["integrity_verified"] is False
        assert not list(root.glob(".*.tmp")), "temporary output leaked"

def main() -> None:
    test_hamming_secdec()
    test_revision2_fixture()
    test_atomic_png_verification()
    test_capacity_accounts_for_ecc()
    test_pixel_safety_preflight()
    test_blank_image_rejection()
    test_atomic_decoded_output_and_unverified_guard()
    print("PASS: Hamming SECDED single-bit correction and all double-bit detection pairs; legacy v2 fixture; combined-anchor vote recovery; atomic verified-PNG and decoded-output writes; unverified-output opt-in guard; ECC-aware capacity; image-size safety preflight; fast blank-image rejection")


if __name__ == "__main__":
    main()
