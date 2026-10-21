#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""End-to-end CLI tests for both launchers, real files, and safe overwrite rules."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "hushraster.py"
TEXT = "I am proudly hidden, here, In this Image."


def run(args: list[str], *, module: bool = False, expect_ok: bool = True) -> subprocess.CompletedProcess[str]:
    prefix = [sys.executable, "-m", "hushraster"] if module else [sys.executable, str(SCRIPT)]
    result = subprocess.run(
        prefix + args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
        check=False,
    )
    if expect_ok and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {prefix + args!r}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    if not expect_ok and result.returncode == 0:
        raise AssertionError(f"command unexpectedly succeeded: {prefix + args!r}")
    return result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="hushraster-cli-smoke-") as temporary:
        d = Path(temporary)
        cover = d / "cover.png"
        text_image = d / "text-hidden.png"
        binary_image = d / "binary-hidden.png"
        binary = d / "payload.bin"
        recovered = d / "recovered.bin"

        # A square cover with capacity for the short test payloads avoids making
        # the general CLI smoke test spend time in the separate resize regression.
        Image.new("RGB", (1320, 1320), (128, 128, 128)).save(cover)

        # Native HushRaster commands create a standalone barcode, without a cover image.
        barcode = d / "standalone-text.png"
        run(["encode-text", "p2+", TEXT, str(barcode)])
        scanned = run(["scan-text", str(barcode)])
        assert scanned.stdout == TEXT + "\n", repr(scanned.stdout)
        assert Image.open(barcode).size[0] > 0 and Image.open(barcode).size[1] > 0

        barcode_payload = d / "standalone-payload.bin"
        barcode_payload.write_bytes(bytes(range(8)) + b"\x00HRS1\xff")
        binary_barcode = d / "standalone-binary.png"
        run(["encode", "p2+", str(barcode_payload), str(binary_barcode)], module=True)
        barcode_recovered = d / "standalone-recovered.bin"
        run(["scan", str(binary_barcode), str(barcode_recovered)])
        assert barcode_recovered.read_bytes() == barcode_payload.read_bytes()

        # P1 remains explicitly encodable and is auto-detected without a selector.
        p1_barcode = d / "p1-text.png"
        run(["encode-text", "p1+", TEXT, str(p1_barcode)])
        assert run(["decode-text", str(p1_barcode)]).stdout == TEXT + "\n"
        assert "HushRaster P1 (Panda 1)" in run(["inspect", "p1+", str(p1_barcode)]).stdout

        # Encoding must name a standard; registered-but-unimplemented standards fail clearly.
        run(["encode-text", TEXT, str(d / "missing-standard.png")], expect_ok=False)
        run(["encode-text", "e1+", TEXT, str(d / "e1.png")], expect_ok=False)
        assert "P2 (Panda 2)" in run(["standards"]).stdout

        # OI standalone generation needs no origin image; decoding auto-detects it.
        oi_barcode = d / "oi-text.png"
        run(["encode-text", "oi+", TEXT, str(oi_barcode), "--force"])
        assert run(["decode-text", str(oi_barcode)]).stdout == TEXT + "\n"
        assert "HushRaster OI (OverImage)" in run(["inspect", str(oi_barcode)]).stdout
        oi_binary = d / "oi-payload.png"
        run(["encode", "oi+", str(barcode_payload), str(oi_binary), "--force"])
        oi_recovered = d / "oi-recovered.bin"
        run(["decode", str(oi_binary), str(oi_recovered), "--force"])
        assert oi_recovered.read_bytes() == barcode_payload.read_bytes()

        # IMGMod remains available, but has its own namespace.
        run(["imgmod", "encode-text", str(cover), TEXT, str(text_image), "--force"])
        decoded_text = run(["decode-text", str(text_image)])
        assert decoded_text.stdout == TEXT + "\n", repr(decoded_text.stdout)

        # Binary includes embedded NUL/FF bytes and varied byte values.
        payload = bytes(range(8)) + b"\x00\xffHRS1\x80\x00"
        binary.write_bytes(payload)
        run(["imgmod", "encode", str(cover), str(binary), str(binary_image), "--force"], module=True)
        run(["decode", str(binary_image), str(recovered), "--force"])
        assert recovered.read_bytes() == payload, "binary CLI round-trip was not byte-exact"

        # No-clobber is a data-integrity invariant; failures must not mutate targets.
        preserved_png = text_image.read_bytes()
        run(["imgmod", "encode-text", str(cover), "replacement", str(text_image)], expect_ok=False)
        assert text_image.read_bytes() == preserved_png, "no-clobber encode mutated its existing destination"

        protected = d / "protected.bin"
        original = b"keep this existing file intact\x00"
        protected.write_bytes(original)
        run(["decode", str(binary_image), str(protected)], expect_ok=False)
        assert protected.read_bytes() == original, "no-clobber decode mutated its existing destination"

    print("PASS: script/module launchers; standalone barcode text and binary round-trips; IMGMod text/binary round-trips; Unicode and NUL/FF bytes; no-clobber target preservation")


if __name__ == "__main__":
    main()
