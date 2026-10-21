# HushRaster 1.0.1 — A Collection of Distinct Raster Barcode Standards

[![Tests](https://github.com/gioyous-it/hushraster-python/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/gioyous-it/hushraster-python/actions/workflows/tests.yml)
[![License: GPL-3.0-only](https://img.shields.io/badge/Code%20license-GPL--3.0--only-blue.svg)](LICENSE)
[![Format specification: CC0](https://img.shields.io/badge/Format%20specification-CC0--1.0-lightgrey.svg)](LICENSES/CC0-1.0.txt)

**Repository:** <https://github.com/gioyous-it/hushraster-python>

**Maintainer:** [gioyous.it](https://gioyous.it)

HushRaster is a **high-contrast raster barcode** for arbitrary binary data and UTF-8 text. Its default standalone barcode is black-and-white, grows with the payload, and carries the original bytes without a HushRaster-specific header or compression. It uses COBS framing, a trailing CRC32, interleaved Reed–Solomon error correction, and three compact finder patterns. The CLI defaults to `--ppm 4`; use `--ppm 1` for the smallest PNG. It is a HushRaster-specific format, not QR Code; ordinary QR apps cannot scan it, and its scanner is not a perspective-correcting camera reader. The format has no QR Version 40 ceiling, although this implementation uses a configurable pixel safety limit (40 million pixels by default). HushRaster is **not encryption**: encrypt sensitive payloads separately.

The old low-amplitude image-overlay codec remains available only as the separate **IMGMod** compatibility extension in [`IMGMOD.md`](IMGMOD.md). It uses its legacy header-based format and is planned for removal in HushRaster 2.0.
## Two separate licenses

- **Python implementation, CLI, and project code:** GNU General Public License v3.0 only (**GPL-3.0-only**). See [`LICENSE`](LICENSE).
- **HushRaster format standard/specification:** **CC0 1.0 Universal**. See [`FORMAT.md`](FORMAT.md) and [`LICENSES/CC0-1.0.txt`](LICENSES/CC0-1.0.txt). The standard is dedicated to the public domain to the extent permitted by law.

The CC0 dedication applies to the format specification/standard, **not** to the Python implementation. Conversely, the software's GPL license does not restrict independent implementations of the CC0 standard. Third-party dependencies retain their own licenses.

HushRaster is a family of barcode standards selected by short name. An encoding command may select a standard using a lowercase name with a trailing `+` (for example `p12+`); when omitted, it defaults to P2. Decoding and inspection can force a standard too, but normally auto-detect it. See [`STANDARDS.md`](STANDARDS.md).

## Standards in this build

HushRaster has **27 numbered design trees** plus OI and the reserved E1/L1 entries. The original trees are **P1–P13** (Panda), **D1–D11** (Diagonal), **CE1–CE11** (Colored Elephant), **Z1–Z11** (Zebra), **M1–M10** (Mosaic), **H1–H10** (Hexa), and **T1–T10** (Triangle). This release adds **200 distinct standards across 20 more trees**: A (Arc), B (Braid), F (Facet), G (Grid), I (Iris), J (Junction), K (Keystone), N (Nexus), Q (Quick), R (Resilient), S (Spiral), U (Umbra), V (Vector), W (Weave), X (Cross), Y (Asymmetric), AA (Adaptive Array), BR (Bridge), CP (Compact Payload), and ST (Staggered). Each new tree has ten numbered standards, distinct visual glyphs, a unique finder signature and a concrete framing/coding method. A shared tree is a design lineage, never compatibility with an earlier standard.

D1 (`d1+`) is raw diagonal encoding with no checksum or error correction. D2 (`d2+`) adds Reed–Solomon error correction and CRC32. `d+` is intentionally not a selector; the old `oi2+` spelling remains an alias for D1. The CE tree uses five-colour base-5 cells, Z uses striped monochrome modules, and OI remains the legacy modulation format (`oi+` creates a standalone carrier; `imgmod` is the file-based overlay exception). E1 and L1 remain reserved.

Run `python3 -m hushraster standards` to list every selector and its encoding/integrity characteristics. Normal `encode`, `decode`, `inspect`, and `capacity` commands use stdin/stdout; only `imgmod` needs explicit image paths. See [`STANDARDS.md`](STANDARDS.md) for the complete registry and pipe examples.

### Recommended high-resilience format: R1 (`r1+`)

R1 is the flagship candidate when we need a compact custom barcode with strong correction and room for a centered logo. It uses one asymmetric 5×5 finder (rather than three QR-style finders), a one-byte payload length for payloads up to 254 bytes, and a five-byte extended length for larger payloads. Reed–Solomon with 32 parity symbols protects the payload and CRC32 together and corrects up to **16 unknown byte-symbol errors per codeword**. Coded symbols are interleaved across blocks for larger payloads.

R1 is not always smaller than P2: its stronger fixed parity takes space, especially for tiny payloads. In a real 61-byte test payload, the P2 image was 29×29 modules (841 modules), while R1 was 29×32 modules (928 modules), about 10.3% more area. The R1 sample still decoded byte-for-byte after an opaque 7×7-module center-logo overlay. This is a regression test in the project, not a claim that arbitrary logos, camera angles, print damage or recompression are guaranteed to work. R1 is a promising format for branded asset/part labels in controlled scanners; it is not QR-compatible and needs real print/camera benchmarking before commercial deployment. See [`evidence/R1-Compactness-and-ECC-Evidence.png`](evidence/R1-Compactness-and-ECC-Evidence.png) for the measured comparison and the recovered logo-overlay sample.

## What this build does

- Works as `python3 hushraster.py ...`, `python3 -m hushraster ...`, or the installed `hushraster ...` command.
- Generates P2 standalone high-contrast PNGs with arbitrary binary data or UTF-8 text, or P1 for compatibility.
- Auto-detects P1, P2, P3, SL1, OI and all registered numbered standards, including 200 additional A/B/F/G/I/J/K/N/Q/R/S/U/V/W/X/Y/AA/BR/CP/ST variants; OI/IMGMod legacy images use the legacy decoder.
- Preserves arbitrary bytes exactly, including NULs, without a P1/P2 HushRaster metadata header or zlib compression. P2 uses COBS framing, CRC32 and adaptive interleaved Reed–Solomon blocks.
- Verifies generated PNG bytes by decoding them before writing to stdout; output is not interleaved with diagnostics.
- Refuses to write or print unverified OI decoded bytes by default; `--allow-unverified` is an explicit escape hatch for forensic/best-effort recovery.
- Uses a configurable 40-million-pixel default raster safety limit (`--max-pixels` is available on encode and decode). It does not encrypt or transmit payloads.
- Uses Pillow and NumPy; no external error-correction package is needed.

## Installation

Python 3.10+ is required. The project is packaged with `pyproject.toml`, supports an importable library, and provides a `hushraster` command after installation.

### Install the latest version directly from GitHub

The following URL downloads GitHub's automatically generated ZIP snapshot of the **latest commit on the `main` branch**. It is not a `git+...` URL and does not require Git to be installed:

```bash
python3 -m pip install "https://github.com/gioyous-it/hushraster-python/archive/refs/heads/main.zip"
hushraster --help
```

To upgrade to the latest `main` snapshot later:

```bash
python3 -m pip install --upgrade --force-reinstall "https://github.com/gioyous-it/hushraster-python/archive/refs/heads/main.zip"
```

This command assumes the repository's default branch is named `main`. If the default branch is renamed, update `main` in the URL. A branch ZIP tracks the latest commit on that branch; it is not a pinned, reproducible release. For a fixed version, install from a tagged release ZIP instead.

### Install a downloaded ZIP or local checkout

If you downloaded a source ZIP to your computer, install it by its local path:

```bash
python3 -m pip install ./<downloaded-source-archive>.zip
hushraster --help
```

Or clone the repository and install it in a virtual environment:

```bash
git clone https://github.com/gioyous-it/hushraster-python.git
cd hushraster-python
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
hushraster --help
python tests/test_encoder_features.py
```

If you prefer not to install the project itself, install the runtime dependencies and run it from the extracted folder:

```bash
python3 -m pip install -r requirements.txt
python3 hushraster.py --help
python3 -m hushraster --help
```

For a source-copy import, place only the `hushraster/` package directory on Python's import path. With Pillow and NumPy installed, `import hushraster` and `from hushraster import encode_image, decode_image` work without the CLI launcher file.

## Pipe-based CLI examples

Normal `encode` reads arbitrary raw bytes from stdin and writes a PNG to stdout. `decode` reads PNG bytes from stdin and writes the recovered raw bytes to stdout. Diagnostics go to stderr, so redirection and pipes remain binary-safe.

```bash
# Encode a file or text into a PNG
python3 -m hushraster encode < algo.txt > img.png
python3 -m hushraster encode <<< "o algo" > img.png
echo "algo" | python3 -m hushraster encode > img.png

# Recover exact bytes, including NULs and non-UTF-8 bytes
python3 -m hushraster decode < img.png > algo.txt

# Select a standard and raster density (default P2, default --ppm 4)
cat secret.zip | python3 -m hushraster encode p2+ --ppm 4 > secret.png
cat secret.zip | python3 -m hushraster encode p3+ --ppm 1 > secret-min.png
python3 -m hushraster decode p3+ < secret-min.png > recovered.zip

python3 -m hushraster standards
python3 -m hushraster inspect < img.png
```

The short standard name must be followed by `+` when selecting an encoding standard. Without a selector, `encode` defaults to P2. `--ppm` is pixels per module, defaults to 4, and accepts values 1–32. Lower values produce smaller PNGs. `decode` writes only payload bytes to stdout; diagnostics go to stderr. It restores arbitrary bytes rather than forcing UTF-8 text or choosing an output filename.

### Standards at a glance

- **P1 — Panda 1:** triple repetition and CRC32.
- **P2 — Panda 2:** interleaved Reed–Solomon error correction and CRC32; default.
- **P3 — Panda 3:** minimal raw payload with a length prefix; no checksum or error correction.
- **OI — OverImage:** legacy visible modulation pattern on a generated carrier. `oi+` is canonical; `oi1+` remains a compatibility alias.
- **D1–D11 — Diagonal:** a distinct standalone diagonal-module format tree; D2 uses Reed–Solomon correction and CRC32.
- **CE1–CE11 — Colored Elephant:** five-colour base-5 format tree with distinct coding strategies; CE9 uses Reed–Solomon correction.
- **Z1–Z11 — Zebra:** a distinct striped monochrome format tree.
- **E1** and **L1:** reserved.

### Legacy IMGMod mode

`imgmod` is the only command that takes explicit input/output image paths because it modifies an existing image. For example, `cat secret.zip | python3 -m hushraster imgmod encode photo.png image-with-data.png`. Use top-level `encode` for standalone barcodes.

### Python API

```python
from hushraster.rawbarcode import encode_bytes, decode_image

payload = b"example payload\x00\xff"
barcode = encode_bytes(payload, module_size=1)
barcode.save("barcode.png")
recovered = decode_image(barcode)
assert recovered == payload
```

The new `hushraster.rawbarcode` API implements the headerless standalone transport. The older `hushraster.core` API remains only for legacy IMGMod compatibility and no longer encodes compressed payloads.

## Error detection and tested behavior

- Adaptive Reed–Solomon correction (8, 16, 32, or 48 parity symbols per block) corrects corrupted byte symbols. Block interleaving spreads localized damage, and CRC32 verifies the recovered payload.
- The raster includes three compact finder patterns and a one-module quiet zone. The CLI default is `--ppm 4`; use `--ppm 1` for the smallest raster. The decoder expects a grid-aligned PNG; it is not a general camera/perspective scanner.
- The new standalone format has no HushRaster metadata header and does not compress payloads. COBS framing is reversible and supports embedded NUL bytes.
- The custom format is not QR Code. Generic QR readers will not scan it, and CRC32 is error detection rather than cryptographic authentication.
- Legacy IMGMod tests still cover header-based data embedding and decoding. They are separate from the new standalone-barcode transport.

Run focused tests:

```bash
python3 tests/test_encoder_features.py
python3 tests/test_failsafe.py
python3 tests/test_cli_smoke.py
python3 tests/test_resize_928_regression.py
```

## Fun Facts

1. The standard selector ends with `+`; the bytes being encoded or decoded always travel through stdin/stdout.

## GitHub repository and contributions

Canonical repository: <https://github.com/gioyous-it/hushraster-python>

- Latest `main` branch source ZIP: <https://github.com/gioyous-it/hushraster-python/archive/refs/heads/main.zip>
- Releases and versioned source archives: <https://github.com/gioyous-it/hushraster-python/releases>
- Issues and bug reports: <https://github.com/gioyous-it/hushraster-python/issues>

The repository includes `.gitignore`, `MANIFEST.in`, `pyproject.toml`, package entry points, a cross-version GitHub Actions workflow, and regression tests for all numbered formats, pipe-based CLI selectors, legacy IMGMod, blank canvases, and Android filesystem fallbacks. Generated image samples and local build artifacts are excluded from the source release.

Contributions to the implementation are subject to GPL-3.0-only. The HushRaster format specification remains CC0-1.0. Before submitting a contribution, ensure you have the rights to contribute it under the applicable license. See [`LICENSE`](LICENSE) and [`LICENSES/CC0-1.0.txt`](LICENSES/CC0-1.0.txt).


### Output image density

Standalone encoders use `--ppm N` (pixels per module), default `4`. Set `--ppm 1` for the smallest raster, or use a larger value for a barcode that is easier to view or print. This replaces the former `--out-qual` flag.

## SL1 linear-bar format

SL1 (`sl1+`) encodes each four-bit symbol as the height of a vertical bar. Its image is one row of equally wide bars centred on the same horizontal midline; there are no finder shapes or decorative elements. A compact one-byte identifier uses just two opening bars, and existing images with the previous four-byte identifier remain readable. The wire frame includes payload length and CRC32, and uses shortened Reed–Solomon codewords with 32 parity symbols (up to 16 unknown byte-symbol errors per codeword).

```sh
printf 'HushRaster SL1 sample' | python3 -m hushraster encode sl1+ --ppm 4 > sl1.png
python3 -m hushraster decode < sl1.png
```
