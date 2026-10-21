# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""End-to-end checks for the pipe-only public CLI."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, *, input_bytes=b""):
    return subprocess.run([sys.executable, "-m", "hushraster", *args], cwd=ROOT,
                          input=input_bytes, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=45, check=False)


def test_encode_png_stdout_decode_raw_stdout():
    payload = b"raw\x00bytes\xff\n"
    for standard in ("p1", "p2", "p3", "oi", "d1", "ce1", "z1", "m1", "h1", "t1", "sl1"):
        enc = run(["encode", f"{standard}+", "--ppm", "1"], input_bytes=payload)
        assert enc.returncode == 0, (standard, enc.stderr.decode(errors="replace"))
        assert enc.stdout.startswith(b"\x89PNG\r\n\x1a\n")
        dec = run(["decode", f"{standard}+"], input_bytes=enc.stdout)
        assert dec.returncode == 0, (standard, dec.stderr.decode(errors="replace"))
        assert dec.stdout == payload


def test_default_standard_is_p2():
    payload = b"default P2\x00"
    enc = run(["encode", "--ppm", "1"], input_bytes=payload)
    assert enc.returncode == 0, enc.stderr.decode(errors="replace")
    dec = run(["decode"], input_bytes=enc.stdout)
    assert dec.returncode == 0, dec.stderr.decode(errors="replace")
    assert dec.stdout == payload


def test_d1_selector_and_d_shorthand_rules():
    payload = b"diagonal\x00"
    encoded = run(["encode", "d1+", "--ppm", "1"], input_bytes=payload)
    assert encoded.returncode == 0, encoded.stderr.decode(errors="replace")
    assert run(["decode", "d1+"], input_bytes=encoded.stdout).stdout == payload
    wrong = run(["encode", "d+"], input_bytes=payload)
    assert wrong.returncode != 0
    assert wrong.stdout == b""


def test_reserved_standards_fail_without_png_stdout():
    for standard in ("e1", "l1"):
        result = run(["encode", f"{standard}+"], input_bytes=b"x")
        assert result.returncode != 0
        assert result.stdout == b""
        assert any(word in result.stderr.lower() for word in (b"reserved", b"planned", b"not implemented"))


def test_cli_dispatches_distinct_new_family_codecs():
    # Keep subprocess coverage representative; the 200-format unit suite exercises every selector.
    payload = b"family selector dispatch\x00\xff"
    for standard in ("p12", "d2", "ce9", "r1", "aa1"):
        encoded = run(["encode", f"{standard}+", "--ppm", "1"], input_bytes=payload)
        assert encoded.returncode == 0, (standard, encoded.stderr.decode(errors="replace"))
        decoded = run(["decode", f"{standard}+"], input_bytes=encoded.stdout)
        assert decoded.returncode == 0, (standard, decoded.stderr.decode(errors="replace"))
        assert decoded.stdout == payload, standard
