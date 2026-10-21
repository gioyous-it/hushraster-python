# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Regression tests for the 200 added standards and R1's logo resilience."""
from __future__ import annotations

import binascii

import pytest

from hushraster.standards import ADDITIONAL_TREES, STANDARDS, _ADDITIONAL_METHODS, standard_listing
import hushraster.newstandards as ns


NEW_CODES = [f"{tree}{n}" for tree in ADDITIONAL_TREES for n in range(1, 11)]
PAYLOAD = b"HushRaster extra standards\x00\xff\n" + bytes(range(12))


def _center_h_logo(image, code="r1", ppm=4, block=7):
    width, height = ns._get_grid(image, ppm)
    before = ns._read_binary_symbols(
        image, width, height, ppm, diagonal=False, striped=False,
        styled_tree="r", single_finder=True,
    )
    pixels = image.load()
    x0, y0 = (width - block) // 2, (height - block) // 2
    # Opaque white logo tile with a black pixel-cell H. Each cell hides data.
    for y in range(y0, y0 + block):
        for x in range(x0, x0 + block):
            color = (0, 0, 0) if (x - x0 in (1, 5) or (y - y0 == 3 and 1 <= x - x0 <= 5)) else (255, 255, 255)
            for sy in range(ppm):
                for sx in range(ppm):
                    pixels[(x + 1) * ppm + sx, (y + 1) * ppm + sy] = color
    after = ns._read_binary_symbols(
        image, width, height, ppm, diagonal=False, striped=False,
        styled_tree="r", single_finder=True,
    )
    return before, after, width, height


def test_exactly_200_additional_standards_registered():
    assert len(ADDITIONAL_TREES) == 20
    assert len(NEW_CODES) == len(set(NEW_CODES)) == 200
    assert all(code in STANDARDS and code in ns.VARIANT_METHODS for code in NEW_CODES)
    assert len(STANDARDS) == 280
    listing = standard_listing()
    assert "200 additional standards" in listing
    assert "sl1+" in listing and "variable heights" in listing
    assert all(code.upper() in listing for code in NEW_CODES)


@pytest.mark.parametrize("ppm", [1, 4])
@pytest.mark.parametrize("code", NEW_CODES)
def test_every_new_standard_roundtrips_at_compact_and_readable_density(code, ppm):
    image = ns.encode_variant(PAYLOAD, code, ppm=ppm)
    assert ns.decode_new_standard(image, code) == PAYLOAD


def test_all_new_tree_glyphs_are_distinct_and_low_density_is_supported():
    assert len(ns._STYLE_CORE_GLYPHS) == 20
    assert len(set(ns._STYLE_CORE_GLYPHS)) == 20
    rendered = []
    for tree in ADDITIONAL_TREES:
        code = f"{tree}1"
        image = ns.encode_variant(PAYLOAD, code, ppm=4)
        assert ns.decode_new_standard(image, code) == PAYLOAD
        rendered.append(image.tobytes())
    assert len(set(rendered)) == 20


@pytest.mark.parametrize("tree", list(ADDITIONAL_TREES))
def test_auto_detection_finds_each_additional_tree(tree):
    code = f"{tree}1"
    image = ns.encode_variant(PAYLOAD, code, ppm=4)
    decoded, detected = ns.decode_auto_new(image)
    assert decoded == PAYLOAD
    assert detected == code


def test_added_standards_have_unique_in_band_ids_or_their_own_finder_level():
    frames = {}
    for code in NEW_CODES:
        frame = ns._frame_variant(PAYLOAD, code, ns.VARIANT_METHODS[code])
        if code in {"r1", "r2", "r3", "r4", "r5"}:
            # These formats intentionally identify themselves with their unique finder and ECC level.
            assert not frame.startswith(b"HR")
            assert ns.VARIANT_METHODS[code] in ns._FULL_RS_METHODS
        else:
            marker = b"HR" + code.upper().encode("ascii") + b"\x00"
            assert frame.startswith(marker)
            assert marker not in frames, (code, frames.get(marker))
            frames[marker] = code
    assert len(frames) == 195


def test_new_finder_signatures_are_unique_within_binary_alphabet():
    codes = ["p3", "d1", "z1", *[code for code in ns.VARIANT_METHODS if not code.startswith("ce")]]
    templates = [ns._generated_template(code) if code not in ns.TEMPLATES else ns.TEMPLATES[code] for code in codes]
    assert len(templates) == len(set(templates))


def test_r1_single_finder_is_asymmetric_and_orientation_distinguishing():
    import numpy as np
    template = np.asarray([[ns._template_value("r1", x, y) for x in range(5)] for y in range(5)])
    assert not np.array_equal(template, np.rot90(template))
    assert not np.array_equal(template, np.rot90(template, 2))
    assert not np.array_equal(template, np.fliplr(template))
    assert not np.array_equal(template, np.flipud(template))


def test_r1_uses_single_finder_and_compact_length_prefix():
    code = "r1"
    payload = b"tiny\x00\xff"
    image = ns.encode_variant(payload, code, ppm=1)
    width, height = ns._get_grid(image, 1)
    assert len(ns._read_positions(width, height, single_finder=True)) == width * height - 25
    assert len(ns._read_positions(width, height)) == width * height - 75
    bitstream = ns._read_binary_symbols(image, width, height, 1, diagonal=False, striped=False, styled_tree="r", single_finder=True)
    raw = ns._bits_to_bytes(bitstream)
    assert raw[0] == len(payload)
    assert ns.decode_new_standard(image, code) == payload
    assert ns.decode_auto_new(image)[0] == payload


@pytest.mark.parametrize(("code", "parity"), [("r1", 32), ("r2", 48), ("r3", 24), ("r4", 16), ("r5", 64)])
def test_resilient_rs_levels_correct_their_full_symbol_error_budget(code, parity):
    payload = bytes(range(80))
    image = ns.encode_variant(payload, code, ppm=1)
    width, height = ns._get_grid(image, 1)
    single = code == "r1"
    positions = ns._read_positions(width, height, single_finder=single)
    # R1–R5 start with a compact length byte, then RS(payload || CRC32).
    body_start = 8
    pixels = image.load()
    for byte_index in range(parity // 2):
        for bit_index in range(8):
            x, y = positions[body_start + byte_index * 8 + bit_index]
            old = pixels[x + 1, y + 1]
            pixels[x + 1, y + 1] = (0, 0, 0) if sum(old) >= 384 else (255, 255, 255)
    assert ns.decode_new_standard(image, code) == payload


@pytest.mark.parametrize("ppm", [1, 4])
def test_r1_opaque_center_logo_corrupts_fewer_than_16_symbols_and_recovers_exact_bytes(ppm):
    payload = b"HushRaster R1 logo-resilience demo: 16 bytes of coded payload"
    image = ns.encode_variant(payload, "r1", ppm=ppm)
    before, after, width, height = _center_h_logo(image, ppm=ppm, block=7)
    rs_body = ns._rs_interleaved_encode(
        payload + (binascii.crc32(payload) & 0xFFFFFFFF).to_bytes(4, "big"), 32
    )
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b and 8 <= i < 8 + len(rs_body) * 8]
    damaged_symbols = {i // 8 - 1 for i in changed}
    assert 0 < len(damaged_symbols) <= 16, (len(damaged_symbols), width, height)
    assert ns.decode_new_standard(image, "r1") == payload
    decoded, code = ns.decode_auto_new(image)
    assert decoded == payload
    assert code == "r1"


def test_resilient_extended_length_roundtrip():
    payload = bytes(range(256))
    for code in ("r1", "r2", "r3", "r4", "r5"):
        image = ns.encode_variant(payload, code, ppm=1)
        assert ns.decode_new_standard(image, code) == payload


def test_cli_accepts_multiletter_new_tree_selectors():
    from hushraster.cli import _normalize_cli_standard
    for code in ("a1", "aa10", "br2", "cp10", "st1", "r1"):
        assert _normalize_cli_standard(["encode", code + "+"]) == ["encode", "--standard", code]
