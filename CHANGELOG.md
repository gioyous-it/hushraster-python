## 1.0.1 — SL1 correction and linear-bar encoding

- Added SL1 as a single horizontal row of equal-width vertical bars; bar height encodes each nibble and no finder or decorative shapes are drawn.
- Added shortened Reed–Solomon codewords with 32 parity symbols, interleaving, a protected frame length, and CRC32 verification.
- Integrated SL1 with pipe-based CLI encoding, explicit decoding, automatic detection, inspect output, and the public Python API.
- Added actual CLI-generated SL1 image fixtures and tests that alter 16 byte symbols in one codeword and verify recovery.

# HushRaster changelog

## 1.0.1 — Standard tree expansion, repairs, and version relabel

- Set the application/package and all new release artifacts to version `1.0.1`, as requested.
- Corrected the diagonal selector to `d1+`; `d+` is not accepted. `oi2+` remains a legacy alias for D1.
- Retained distinct P4–P13, D2–D11, CE2–CE11, and Z2–Z11 standards, with no compatibility-profile entries.
- Added three new design trees: M1–M10 (Mosaic checkerboard-phase cells), H1–H10 (Hexagonal-outline cells), and T1–T10 (up/down triangle glyphs). All 30 have their own wire marker, finder signature, and code-specific transform/coding method.
- D2 uses Reed–Solomon error correction and CRC32; D1 remains raw without checksum or correction.
- Fixed standards listing and per-standard encode/decode routing. Normal encode/decode/inspect operations use binary-safe stdin/stdout; IMGMod remains the explicit file-path exception.
- Expanded round-trip, auto-detection, wire-marker, finder-template, unique-rendering, and CLI selector regressions.
- Added 200 numbered standards across 20 new trees: A, B, F, G, I, J, K, N, Q, R, S, U, V, W, X, Y, AA, BR, CP, and ST. Every new tree has ten variants, a distinctive glyph family, and separately framed/coded formats.
- Added R1–R5 high-correction Resilient levels. R1 uses one asymmetric finder, compact length framing, 32 Reed–Solomon parity symbols per block, payload-plus-CRC correction, and interleaving for longer data.
- Added a real center-logo regression: an opaque 7×7 module overlay is applied to R1, and the payload is recovered byte-for-byte at PPM 1 and 4.
- Optimized automatic standard detection to use finder candidates instead of trying every codec exhaustively; module-size probes are limited to divisors of image dimensions.

The remaining entries below document historical development snapshots. The current pipe-based interface and complete standards registry are described in `README.md` and `STANDARDS.md`.

---

## Earlier development history

- Added a central registry for OI (OverImage), P1 (Panda 1), P2 (Panda 2), E1 (Elephant 1), Z1 (Zebra 1), and L1 (Lion 1).
- Encoding now requires a selector immediately after the action: `encode p2+ FILE OUTPUT.png`, `encode-text p2+ TEXT OUTPUT.png`. The trailing plus delimits the complete short name.
- Added top-level OI selectors that generate standalone barcodes without an origin image: `encode oi+ PAYLOAD OUTPUT.png` and `encode-text oi+ TEXT OUTPUT.png`. `--on-blank` selects the generated carrier color. The separate `imgmod` namespace remains the explicit legacy origin-image overlay interface.
- Added P1 encoding for the previous headerless triple-repeat barcode format.
- Decode and inspect can auto-detect P2, P1, and OI; an optional selector forces a specific decoder.
- Added `hushraster standards` and explicit not-implemented responses for E1, Z1, and L1 rather than pretending those reserved/planned formats exist.
- Added regression tests for standard selection, auto-detection, OI compatibility, required encoding selectors, and reserved/planned formats.

# HushRaster 1.0.1 — barcode-first CLI and standard

## Compact high-capacity raster update

- Replaced the new standalone barcode's three-copies-per-bit scheme with adaptive Reed–Solomon blocks (8, 16, 32, or 48 parity symbols), correcting up to 4, 8, 16, or 24 damaged byte symbols per block.
- Interleaved encoded bytes across blocks so localized runs of damage are spread between independent error-correction blocks.
- Reduced the default module footprint from 4×4 pixels to 1×1 pixel, changed to compact 4×4 corner finders and a one-module quiet zone, and optimized grid dimensions for fewer pixels.
- Added `--module-size` (1–32) to trade image size for visibility/print scale. The decoder detects supported module sizes and keeps a fallback for existing three-repeat headerless barcodes.
- Kept arbitrary bytes, no HushRaster-specific payload header, no compression, COBS framing, and CRC32 verification.
- Added tests for each RS parity strength, four-symbol short-frame recovery, beyond-capacity rejection, multi-block interleaving, alternate module sizes, and legacy raw-barcode compatibility.

## Headerless barcode transport and compression removal

- Top-level `encode` and `encode-text` now produce a high-contrast black-and-white raster barcode that carries raw payload bytes without a HushRaster metadata header.
- The new transport uses reversible COBS framing and a trailing CRC32; it does not store a filename, declared length, compression mode, or HushRaster magic/version field.
- Removed zlib compression from all new CLI/API encoding. Legacy decoding remains for existing IMGMod images, including old compressed payloads when their legacy header declares it.
- Previously added three-vote module decoding and three finder patterns; the custom raster remains HushRaster-specific and is not a QR Code.
- Added direct round-trip, binary/NUL, COBS framing, and corruption-detection tests.


## Historical development notes (prior to the headerless transport)

The notes below describe earlier development snapshots and are superseded for new standalone barcode generation by the headerless, uncompressed transport at the top of this file. The old codec remains only for legacy IMGMod decoding.

## Barcode-first changes

- HushRaster is now documented primarily as a self-contained, error-correcting raster barcode. The CC0 standard describes the barcode raster itself rather than treating every output as data hidden over a host image.
- Top-level `encode` and `encode-text` generate a solid-canvas barcode by default; the grid is sized automatically and `--color` selects its background (default `80`, mid-gray).
- Top-level `decode` / `decode-text` remain the scanner commands, with `scan` / `scan-text` aliases.
- Moved existing-image overlay commands to `imgmod encode`, `imgmod encode-text`, and `imgmod compare`. The IMGMod extension is documented in `IMGMOD.md` and is planned for removal in HushRaster 2.0.
- Application/package version is now `1.0.1`. The on-wire format revision remains `3`; revision-3 barcode images and legacy revision-2 development files remain on the same decode paths.
- Added smoke tests for standalone text and binary barcode generation/scanning and retained explicit IMGMod regression coverage.


## Current update

- Compression is opt-in only: `-z` / `--zlib` stores a fast zlib-level-1 stream. Default encoding stores the input bytes raw. No file-type or compression-usefulness detection is performed.
- The hidden header records compression method (`0` raw, `1` `z`), pre-error-correction body length, raw length, and a SHA-256 integrity tag over the uncompressed payload. The format revision is now `3`; the application version remains `1.0` during development. Revision-2 development files remain readable.
- Decoding follows the header by default. `--force-zlib` and `--force-no-zlib` are explicit, mutually exclusive overrides.
- Added `--mode best|depends|default|strict|fast|reconstruct`. `best` is the adaptive default; strict refuses unverified body output; fast prioritizes speed over crop/header search; reconstruct performs deeper candidate-bit repair and may salvage a partial zlib prefix.
- `best` and `reconstruct` use weak vote margins to test candidate body-bit flips, accepting exact repairs only when zlib's checksum and the hidden SHA-256 integrity tag validate. If only uncertain data can be recovered, the tool warns on standard error; `--focus` suppresses that warning but does not certify the bytes.
- Revision 3 adds an extended Hamming (13,8) SECDED body code, spatially stratified prefix replicas, strict encoder self-checks, and atomic save/read-back verification. A failed verification leaves the requested destination untouched.
- Fixed the decoder fallback so an intact-size center header is tried when the top-left header copy is damaged; improved original-grid height estimates for center-cropped images.
- Added regression coverage for explicit-vs-automatic compression, revision-2 compatibility, force overrides, mode aliases, SECDED single-bit correction, checksum-guided multi-bit recovery, center crop recovery, loss of the top-left header, and integrity enforcement. The RGB per-channel modulation remains capped at ±2 on same-size carriers.


- Added exact-size combined bootstrap voting: if top-left and center header copies each have different majority-vote errors, their pooled evidence can recover the prefix before crop geometry guesses. Impossible center-grid dimensions are rejected before tile scans, and the RGB array is reused during search.
- CLI `decode`/`decode-text` now refuse to print or save unverified bytes unless `--allow-unverified` is supplied. `--focus` cannot bypass the integrity guard.
- Decoded output now uses temporary-file writes and no-clobber installation; filesystems that disallow hard links use an exclusive-create/copy fallback with read-back verification.
- Added image-size preflight limits (40 million pixels) to avoid allocating/processing images the decoder cannot safely accept.
- Extended center-anchor geometry search to cover right/bottom-aligned and mixed crop offsets; the previously failing off-center crop regression now passes via the center header copy.


## Encoder / package hardening (HushRaster 1.0 development)

- Fixed decoded-output no-clobber behavior on Android Python builds where `os.link` is missing entirely; the exclusive-create fallback remains in effect and protects existing files.
- Exported the codec and encoder convenience helpers from the importable `hushraster` package.
- Added encoder-only `--redo N` through `encode_repeated()`. Cumulative clipped modulation is computed in a mathematically equivalent single pass; final strict decoding must pass. The on-image format and decoder remain unchanged.
- Added `--on-blank COLOR` to `encode` and `encode-text`, with a generated near-square canvas sized for the payload and both bootstrap anchors.
- Added grayscale, RGB hex, and named-color parsing.
- Added package metadata, GitHub Actions CI, source manifest, ignore rules, and regression tests for library imports, blank canvases, redo=128, pixel-equivalent repeated modulation, and missing `os.link`.


## Licensing and repository preparation

- Licensed the Python implementation and CLI under GNU GPL v3.0-only (`GPL-3.0-only`).
- Dedicated the HushRaster format specification (`FORMAT.md`) to the public domain under CC0 1.0 Universal.
- Added the canonical `gioyous-it/hushraster-python` repository URLs and documented pip installation from GitHub's `main.zip` source archive.


## 1.0.1 — output-quality and standalone OI correction

- Added `--out-qual hd|min` to standalone `encode` and `encode-text` (default `hd`).
- P1 now supports compact one-pixel modules as well as its larger default raster, and its decoder detects both scales.
- P2 uses 4-pixel modules in `hd` mode and 1-pixel modules in `min` mode.
- Standalone OI now contrast-enhances its generated blank carrier so the OI pattern is visible, then verifies the saved image still decodes. Existing-image `imgmod` encoding remains unchanged.
- Updated the all-standards Termux test script to generate standalone OI without forcing a cyan canvas and use `--out-qual min` for the OI sample.


## 1.1.1 — pipe CLI and barcode registry

- Replaced `--out-qual` with `--ppm N` (default 4; valid range 1–32).
- Normal `encode` reads raw bytes from stdin and writes a verified PNG to stdout; `decode IMAGE.png` writes exact raw bytes to stdout.
- Removed text-only encode/decode commands in favor of one byte-preserving interface.
- Renamed legacy OI to OI1 and implemented/registered P3, OI2 and CE1; retained Z1 as an additional striped barcode standard.
- Updated the standards gallery script and added pipe-interface regression tests.
- Added SPDX license headers to source code and scripts.
