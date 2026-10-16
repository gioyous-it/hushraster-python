# Development changes — HushRaster 1.0

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
