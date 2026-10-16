#!/usr/bin/env python3
"""End-to-end CLI tests for both launchers, real files, and safe overwrite rules."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

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

        im = Image.new("RGB", (176, 297), (238, 229, 208))
        draw = ImageDraw.Draw(im)
        draw.rectangle((12, 22, 160, 120), fill=(44, 126, 154))
        draw.ellipse((32, 140, 145, 260), fill=(240, 164, 57))
        im.save(cover)

        # Exact phrase from the reported failure: 41 UTF-8 bytes, auto-resized.
        run(["encode-text", str(cover), TEXT, str(text_image), "--resize", "--force"])
        decoded_text = run(["decode-text", str(text_image)])
        assert decoded_text.stdout == TEXT + "\n", repr(decoded_text.stdout)

        # Binary includes every byte value and NUL/FF to catch text conversions.
        payload = bytes(range(256)) + b"\x00\xffHushRaster\x00\x80\x00"
        binary.write_bytes(payload)
        run(["encode", str(cover), str(binary), str(binary_image), "--resize", "--force"], module=True)
        run(["decode", str(binary_image), str(recovered), "--force"])
        assert recovered.read_bytes() == payload, "binary CLI round-trip was not byte-exact"

        # No-clobber is a data-integrity invariant; failures must not mutate targets.
        preserved_png = text_image.read_bytes()
        run(["encode-text", str(cover), "replacement", str(text_image), "--resize"], expect_ok=False)
        assert text_image.read_bytes() == preserved_png, "no-clobber encode mutated its existing destination"

        protected = d / "protected.bin"
        original = b"keep this existing file intact\x00"
        protected.write_bytes(original)
        run(["decode", str(binary_image), str(protected)], expect_ok=False)
        assert protected.read_bytes() == original, "no-clobber decode mutated its existing destination"

    print("PASS: script/module launchers; exact 41-byte phrase; resized PNG save/read-back; Unicode text decode; binary bytes 0..255 plus NUL/FF; no-clobber target preservation")


if __name__ == "__main__":
    main()
