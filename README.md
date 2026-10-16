# HushRaster 1.0

[![Tests](https://github.com/gioyous-it/hushraster-python/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/gioyous-it/hushraster-python/actions/workflows/tests.yml)
[![License: GPL-3.0-only](https://img.shields.io/badge/Code%20license-GPL--3.0--only-blue.svg)](LICENSE)
[![Format specification: CC0](https://img.shields.io/badge/Format%20specification-CC0--1.0-lightgrey.svg)](LICENSES/CC0-1.0.txt)

**Repository:** <https://github.com/gioyous-it/hushraster-python>

**Maintainer:** `gioyous-it`

HushRaster hides arbitrary bytes inside a PNG carrier using low-amplitude, block-pattern modulation. It is a hiding format/utility, **not an encryption system**. Payloads are stored raw by default; compression happens only when explicitly requested with `-z` / `--zlib`. Encrypt a payload separately before encoding if confidentiality is needed.

## Two separate licenses

- **Python implementation, CLI, and project code:** GNU General Public License v3.0 only (**GPL-3.0-only**). See [`LICENSE`](LICENSE).
- **HushRaster format standard/specification:** **CC0 1.0 Universal**. See [`FORMAT.md`](FORMAT.md) and [`LICENSES/CC0-1.0.txt`](LICENSES/CC0-1.0.txt). The standard is dedicated to the public domain to the extent permitted by law.

The CC0 dedication applies to the format specification/standard, **not** to the Python implementation. Conversely, the software's GPL license does not restrict independent implementations of the CC0 standard. Third-party dependencies retain their own licenses.

The application version remains HushRaster 1.0 while the development format is revision 3. The current decoder also reads revision-2 development files from the previous build; other earlier drafts are not guaranteed to be compatible.

## What this build does

- Works as `python3 hushraster.py ...`, `python3 -m hushraster ...`, or the installed `hushraster ...` command.
- Provides an importable Python library (`import hushraster`) with low-level image encoding/decoding and encoder-only helpers for repeated modulation and generated blank canvases.
- `--redo N` makes the encoder repeatedly apply its modulation effect to its own output. The default is `1`; the current safety limit is `256`. It changes visual strength, not the format or decoding procedure.
- `--on-blank COLOR` lets `encode` or `encode-text` build a solid-color, minimum-size near-square carrier automatically, with no input image required.
- Encodes arbitrary raw bytes, including binary files and embedded NUL bytes.
- Stores a hidden header with a compression method ID (`0` = raw, `1` = `z`/zlib), stored-body length, original uncompressed length, block-grid dimensions, optional original filename, CRC32 header check, and truncated SHA-256 payload integrity tag.
- Duplicates the bootstrap header in the top-left and center of the image. Uses stronger header voting and CRC-guided repair of up to four low-confidence header-bit decisions. The header is never printed in normal encode/decode output unless `inspect --show-full-raw-data` is explicitly requested.
- Uses 26-way voting for the bootstrap header, 47-way voting for the remaining header, and 19-way voting for body wire bits. Revision 3 spatially spreads every header bit's copies throughout each bootstrap region instead of relying on a random layout.
- Applies extended Hamming (13,8) SECDED error correction to the body in format revision 3. It corrects a single flipped wire bit per codeword and detects double-bit errors; the separate SHA-256 payload tag verifies the final result.
- Each single encoding pass changes any RGB channel by no more than **±2 integer levels**. `--redo N` intentionally accumulates that signal across passes, so total changes can be larger or reach channel saturation.
- Self-verifies every encoded image in strict mode, then saves a temporary PNG, reopens it, and verifies it before installation. Uses atomic replacement/installation where supported, with a verified no-clobber fallback for filesystems such as Android shared storage that disallow hard links. A failed verification does not replace an existing destination.
- Writes decoded outputs through a temporary file, uses no-clobber installation by default, and verifies the fallback copy. By default, the CLI refuses unverified recovered bytes; `--allow-unverified` is an explicit escape hatch for forensic/best-effort recovery.
- Rejects carriers above a hard 40-million-pixel safety limit before creating large RGB arrays and quickly rejects impossible guessed header dimensions.
- Verifies exact recoveries before marking them trusted; best-effort modes may return explicitly unverified data with warnings.
- Does not encrypt, upload, or send the hidden data anywhere.
- Uses Pillow and NumPy only; no external error-correction package is needed.

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
python3 -m pip install ./HushRaster-1.0-GitHub.zip
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

## Examples

Hide a file without compression (the default; body bytes are stored raw):

```bash
python3 hushraster.py encode cover.png secret.zip hidden.png
```

Repeat the visual embedding effect while keeping the exact same stored payload and decoder:

```bash
python3 hushraster.py encode cover.png secret.zip hidden-redo-50.png --redo 50
python3 -m hushraster encode-text cover.png "Hello from HushRaster" text-redo-128.png --redo 128
```

`--redo 1` is the default and applies the normal effect once. Larger numbers amplify the pattern through repeated equivalent modulation; extreme values can saturate pixel channels, so the encoder always performs a final strict self-check and refuses to install an output that no longer decodes correctly. The limit is currently 256 passes.

Generate a carrier without an existing image. The canvas is created at a minimum-size, near-square block-grid resolution that can contain the body and both headers:

```bash
# Encode a file on a mid-gray canvas and emphasize the pattern 128 times.
python3 hushraster.py encode secret.zip secret-qr.png --on-blank 80 --redo 128

# Cyan canvas for text; no cover.png argument is needed.
python3 -m hushraster encode-text "Hello, world!" cyan-text.png --on-blank cyan

# White, black, RGB hex, or color names are accepted too.
python3 hushraster.py encode secret.zip white.png --on-blank FF
python3 hushraster.py encode secret.zip black.png --on-blank 0
python3 hushraster.py encode secret.zip custom.png --on-blank 12ABEF
```

Canvas color rules: one or two hex digits mean grayscale (`80` → `#808080`, `FF` → white, `0` → black); three or six hex digits mean RGB (`abc` → `#AABBCC`); common Pillow/CSS color names such as `cyan` also work. Quote hex values starting with `#` in shells where `#` starts a comment.

The same encoder helpers are available from Python:

```python
from hushraster import create_blank_canvas, encode_repeated, decode_image

payload = b"example payload\x00\xff"
canvas = create_blank_canvas(payload, filename="payload.bin", color="80")
encoded, info = encode_repeated(canvas, payload, filename="payload.bin", redo=8)
encoded.save("hidden.png")
recovered, header, stats = decode_image(encoded, mode="strict")
assert recovered == payload and stats["integrity_verified"]
```

Explicitly apply fast lossless zlib compression before embedding:

```bash
python3 hushraster.py encode cover.png secret.txt hidden.png --zlib
# or: -z
```

Compression is never automatic. With `--zlib`, HushRaster uses zlib level 1 and records method `z` in the hidden header—even if the result is larger than the original.

Decode to the filename recovered from the header (or use `python3 -m hushraster`):

```bash
python3 -m hushraster decode hidden.jpg
```

Choose a specific output path:

```bash
python3 hushraster.py decode hidden.webp recovered.zip
```

Force raw bytes to standard output instead of creating a file:

```bash
python3 hushraster.py decode hidden.webp --pipe > recovered.zip
```

Override the header's compression declaration only when you deliberately need to: 

```bash
python3 hushraster.py decode hidden.png --force-zlib
python3 hushraster.py decode hidden.png --force-no-zlib
```

Normally decoding follows the compression method in the header. `--force-zlib` forces zlib decompression; `--force-no-zlib` returns the stored body as raw bytes. Forced interpretations can bypass ordinary integrity validation and are warned about. The options are mutually exclusive.

Choose the decode/recovery strategy with `--mode`:

- `best` (default), `depends`, `default`: adaptive header search and checksum-guided body-bit repair; if only uncertain data remains, may return a best-effort result with a warning.
- `strict`: requires the HushRaster integrity tag to verify and does no speculative body reconstruction (unless you explicitly use a force-compression override).
- `fast`: checks the top-left header anchor only and skips expensive body repair; use it when speed matters more than crop tolerance.
- `reconstruct`: more aggressive body-bit repair and best-effort recovery of a decompressed zlib prefix if the compressed stream is damaged.

For uncertain results, HushRaster warns on standard error. The command-line `decode` and `decode-text` commands now refuse to print or save payload bytes unless the payload integrity tag verifies. To deliberately extract best-effort/uncertain bytes for forensic recovery, pass `--allow-unverified`; this is separate from `--force`, which only controls overwriting an existing output path. `--focus` suppresses warnings but does not certify data and does not bypass this guard. A checksum-verified repair is reported as verified. An uncertain reconstruction may be incomplete or wrong, so keep the original carrier and do not treat such output as trustworthy without checking it.


Encode text raw by default, or explicitly compress it:

```bash
python3 -m hushraster encode-text cover.png 'secret text' hidden.png
python3 -m hushraster encode-text cover.png 'repeated text ' hidden-z.png -z
python3 -m hushraster decode-text hidden.webp
```

Do not store the original filename:

```bash
python3 hushraster.py encode cover.png secret.zip hidden.png --no-filename
```

Inspect header metadata. The raw header bytes are shown only when explicitly requested:

```bash
python3 hushraster.py inspect hidden.png
python3 hushraster.py inspect hidden.png --show-full-raw-data
```

Compare the original and encoded images:

```bash
python3 hushraster.py compare cover.png hidden.png
```

If the cover is too small, encoding fails by default rather than silently resizing the image. Explicitly opt in to resizing if you accept that the carrier's dimensions and appearance will change:

```bash
python3 hushraster.py encode cover.png secret.zip hidden.png --resize
```

Encoded carriers are saved as PNG. For lossy-format testing or transport, re-encode that PNG as JPEG or WebP; decode can then read the resulting JPEG/WebP image.

## Tested behavior

The included regression test generates a 1536×1536 landscape illustration and hides a 95-byte binary payload, plus a separate small-cover regression that explicitly exercises auto-resizing. On this test image:

- PNG round-trip: passed.
- A dedicated forced-resize test starts from a small 176×297 cover, confirms `--resize` actually enlarges it, then successfully decodes the PNG, JPEG Q75, and WebP Q75 outputs. The final carrier is 1328×2232 for the 95-byte regression payload in the current build.
- JPEG quality 75 and 90: passed.
- WebP quality 75 and 90: passed.
- JPEG quality 50: passed on the tested generated carrier.
- WebP quality 50: passed on the tested generated carrier; other images and encoders can behave differently.
- 10% crop from the right, bottom, or both right and bottom: passed.
- Center crop removing about 10% from each edge: passed.
- JPEG quality 75 followed by a 10%-per-edge center crop: passed.
- JPEG quality 85 → WebP quality 85 → 10% right crop: passed.
- Same-size RGB difference: maximum channel delta 2; every pixel stayed within 2 levels per channel; mean absolute channel error 1.913/255; normalized similarity 99.250%.

These are reproducible results for the included generated image and Pillow's encoders, **not a guarantee for every photo, social platform, codec implementation, quality setting, or processing chain**. Real social services may resize, rotate, strip pixels, or apply multiple transformations.

### Crop limitations

The duplicated header and offset search passed tested top-left-preserving edge crops, centered crops, and an off-center crop that removes the original top-left corner while retaining the lower/right edges. Arbitrary cropping still cannot be guaranteed when a crop removes both header locations or too many payload copies.

### Visibility and capacity trade-off

This format deliberately uses much more space than LSB-only hiding to survive compression. The test payload was 95 bytes on a 1536×1536 source cover that auto-resized to a 1728×1728 encoded carrier. Capacity depends heavily on image dimensions and filename length. The ±2 channel cap limits pixel changes, but it cannot mathematically guarantee invisibility for every image; the included amplified-difference image makes the modifications visible on purpose.

Revision 3 adds extended Hamming SECDED to spatial redundancy, majority voting, and integrity checks. A Hamming codeword corrects one flipped bit or detects two flipped bits; more complicated damage can exceed this capability. For damaged zlib bodies, `best` and `reconstruct` can additionally try flipping low-confidence voted bits and validate candidates with zlib’s stream checksum plus HushRaster’s payload digest. If exact recovery fails, they may return an explicitly uncertain best-effort result; raw arbitrary bytes have no language/filetype heuristics and cannot always be reconstructed meaningfully. Correlated compression damage can still defeat recovery.

## Regression tests and images

The focused compression/reconstruction regression verifies raw-by-default storage, opt-in zlib, revision-2 compatibility, the header method marker, `--force-zlib` / `--force-no-zlib`, `depends` / `default` aliases, SECDED correction, checksum-guided multi-bit recovery, and strict-mode behavior. `tests/test_resize_928_regression.py` also verifies right/bottom and centered/off-center crop recovery plus decoding after deliberately destroying the top-left bootstrap copy. `tests/test_cli_smoke.py` performs subprocess-level text and binary round-trips through both launchers and verifies that failed no-clobber operations leave existing targets untouched.

Run the main image/crop regression suite and the fast compression/reconstruction suite:

```bash
python3 tests/run_tests.py
python3 tests/test_resize_928_regression.py
python3 tests/test_compression_recovery.py
python3 tests/test_failsafe.py
```

The script saves the original, encoded carrier, JPEG/WebP results, cropped examples, amplified difference image, visual comparison sheet, and `test-report.json` in `test-results/`.


## GitHub repository and contributions

Canonical repository: <https://github.com/gioyous-it/hushraster-python>

- Latest `main` branch source ZIP: <https://github.com/gioyous-it/hushraster-python/archive/refs/heads/main.zip>
- Releases and versioned source archives: <https://github.com/gioyous-it/hushraster-python/releases>
- Issues and bug reports: <https://github.com/gioyous-it/hushraster-python/issues>

The repository includes `.gitignore`, `MANIFEST.in`, `pyproject.toml`, package entry points, a cross-version GitHub Actions workflow, and tests for the library API, both CLI launch styles, blank canvases, redo pixel equivalence, and the Android no-`os.link` fallback. Generated image samples and local build artifacts are excluded from the source release.

Contributions to the implementation are subject to GPL-3.0-only. The HushRaster format specification remains CC0-1.0. Before submitting a contribution, ensure you have the rights to contribute it under the applicable license. See [`LICENSE`](LICENSE) and [`LICENSES/CC0-1.0.txt`](LICENSES/CC0-1.0.txt).
