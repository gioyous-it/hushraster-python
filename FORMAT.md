# HushRaster P2 (Panda 2) — Compact Reed–Solomon Barcode Standard

**Specification license: CC0 1.0 Universal.** The Python implementation is separately licensed under GPL-3.0-only.

P2 is one standard in the HushRaster family. It carries arbitrary payload bytes in a compact, high-contrast raster without a HushRaster-specific header and without compression. It is a custom format, not QR Code or Data Matrix; those scanners will not decode it. The family registry and OI/P1 compatibility details are in `STANDARDS.md`.

## Payload framing (no HushRaster header)

The logical payload frame is:

`COBS(payload) || 0x00 || CRC32(payload)`

- `COBS(payload)` is Consistent Overhead Byte Stuffing, used only to frame arbitrary bytes. It is not compression and contains no zero bytes.
- `0x00` terminates the COBS frame. A valid COBS frame is non-empty, even when the user payload itself is empty.
- `CRC32(payload)` is a four-byte unsigned big-endian CRC-32/ISO-HDLC trailer. It detects accidental corruption but is not cryptographic authentication.
- No magic number, format version, filename, declared payload length, compression flag, or HushRaster metadata header is stored.
- Data capacity remaining after the frame is filled with `0xA5` bytes before error correction. These padding bytes are ignored after CRC verification.
- The payload is recovered byte-for-byte. No filename is preserved. New standalone encoding never compresses payload bytes.

## Error correction and interleaving

Data is split into systematic Reed–Solomon blocks over GF(256), with primitive polynomial `0x11D` and roots `α^0` through `α^(n−1)`. Each codeword has at most 255 bytes; its parity symbols follow its data symbols. All blocks use the same adaptive parity level, chosen from the COBS-framed payload size:

| Framed data length | Parity symbols per block | Maximum unknown byte-symbol errors corrected per block |
|---:|---:|---:|
| 1–32 bytes | 8 | 4 |
| 33–128 bytes | 16 | 8 |
| 129–192 bytes | 32 | 16 |
| 193 bytes or more | 48 | 24 |

A full block therefore carries respectively up to 247, 239, 223, or 207 data bytes. The last block may be shortened. Codeword bytes are interleaved column-by-column across blocks so a local run of damaged raster bytes is spread among multiple RS blocks instead of concentrating entirely in one block. The decoder infers block lengths from the raster dimensions and tries the supported parity levels; it accepts a candidate only when both RS decoding and CRC32 verification succeed.

These correction limits apply to erroneous *byte symbols* within each RS block—not to arbitrary cropping, missing finder patterns, perspective distortion, or all possible lossy transformations. The CRC32 check detects most incorrect output that exceeds correction capacity.

## Raster layout

- PNG, black and white, with a one-module quiet zone.
- Three compact 4×4 asymmetric finder patterns sit at the top-left, top-right, and bottom-left corners. Their 48 modules total are reserved and excluded from data.
- Payload bits are sent most-significant-bit first through the remaining modules in row-major order. Any final modules that do not make up a complete byte remain white.
- The CLI defaults to **4 pixels per module** (`--ppm 4`). Use `--ppm 1` for the smallest raster, or `--ppm 2` through `--ppm 32` for a larger, easier-to-view or print-friendly image without changing encoded data density.
- Grid width and height are selected to minimize output pixels while maintaining a valid RS block layout. The dimensions determine the number of codeword bytes; no stored length field is required.
- The decoder expects an aligned, intact PNG raster. It samples module centers and checks the corner patterns, but it is not yet a general camera scanner and does not correct perspective, arbitrary rescaling, or rotation.
- The default encode/decode safety limit is 40,000,000 image pixels. It is an implementation resource limit, not a barcode-version limit. Larger images need both a higher configured limit and enough memory.

## Compatibility

The P2 decoder supports the compact Reed–Solomon layout described here. The P1 decoder supports the previous headerless three-copies-per-bit raster. OI is the separate legacy IMGMod image-overlay format with its own metadata header and decoder. See [`STANDARDS.md`](STANDARDS.md) and [`IMGMOD.md`](IMGMOD.md).

## Content types and scope

The transport stores bytes, not semantic types. Text, URLs, vCards, image files, archives, encrypted payloads, and other files can all be carried as bytes. It does not identify, open, or auto-launch content types. Generic QR or Data Matrix applications will not recognize this custom format.

## SL1 wire format

SL1 maps each nibble to a bar height from 5 through 20 modules. Bars are equal-width, separated by one module, and vertically centred on a shared horizontal midline in a single row. The canvas is 22 modules tall, including one-module top and bottom quiet margins. Each bar encodes four bits; each encoded byte is two bars.

The current frame is `0x10 || payload_length_u32_be || payload || crc32_u32_be`. The one-byte identifier makes the fixed opening pattern just two bars instead of eight. Older images with the original four-byte `SL1\0` identifier remain decodable. The frame is divided into chunks of at most 223 data bytes, each encoded as a shortened Reed–Solomon codeword with 32 parity bytes. Codewords are interleaved by symbol position. Decode restores the blocks, corrects symbol errors, checks the marker and length, then validates CRC32. No compression is applied.
