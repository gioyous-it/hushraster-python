# HushRaster 1.0 format notes

This document describes the format implemented by HushRaster 1.0. It is intentionally incompatible with earlier drafts.

## Carrier and tile grid

- The encoded carrier is RGB PNG.
- Pixels are grouped into an 8×8 tile grid. Trailing pixels that do not complete a tile are discarded before encoding.
- Tile coordinates are zero-based. The global tile slot is `y * grid_width + x`.
- Bit streams are MSB-first within each byte.
- The decoder's pattern and slot permutations are deterministic and do not depend on a secret key.

## Tile modulation

Each tile uses one of four zero-mean patterns. For `x,y` in `[0,7]`:

1. `+1` if `x < 4`, otherwise `-1`.
2. `+1` if `y < 4`, otherwise `-1`.
3. `+1` if `(x < 4) == (y < 4)`, otherwise `-1`.
4. `+1` if `x + y < 7`, otherwise `-1`.

The pattern index and polarity are derived from the global slot for data tiles and the local slot for bootstrap-header tiles. Start with `v = slot & 0xffffffff`, then apply 32-bit unsigned arithmetic:

```text
v ^= v >> 16
v = (v * 0x7feb352d) & 0xffffffff
v ^= v >> 15
v = (v * 0x846ca68b) & 0xffffffff
v ^= v >> 16
polarity = +1 if (v & 1) else -1
pattern = patterns[(v >> 1) % 4] * polarity
```

For bit `1`, add `2 * pattern[x,y]` to each RGB channel; for bit `0`, subtract it. Values are clipped to `[0,255]`. Thus the intentional per-channel change never exceeds ±2. A decoder computes `sum((pixel - 127.5) * pattern)` across the tile and reads `1` when the score is positive, otherwise `0`.

## Header

The 19-byte bootstrap prefix is packed big-endian using `>4sBBIIHHB`:

| Field | Type | Meaning |
|---|---|---|
| Magic | 4 bytes | ASCII `HRS1` |
| Format revision | uint8 | `3` (current development format; app version remains `1.0`) |
| Compression method ID | uint8 | `0` = raw/uncompressed; `1` = `z` (zlib) |
| Stored body length | uint32 | Number of bytes after compression but before v3 error correction; v2 stored the on-wire body length |
| Original raw length | uint32 | Expected number of decoded payload bytes before compression |
| Grid width | uint16 | Original number of 8×8 tiles horizontally |
| Grid height | uint16 | Original number of 8×8 tiles vertically |
| Filename length | uint8 | UTF-8 filename length; at most 120 bytes |

The full header is:

`prefix || UTF-8 filename || SHA256(original_raw_payload)[0:16] || CRC32(prefix || filename || digest)`

The body immediately follows the header remainder in the logical data stream. Method `0` stores the caller-provided bytes unchanged before error correction. Method `1` stores a zlib stream, generated only when the encoder is explicitly given `-z` / `--zlib` (zlib compression level 1). The decoder selects decompression based only on this header field; it does not detect input file types or guess whether compression would be useful. No compression is automatic. `--force-zlib` and `--force-no-zlib` override the declaration for a single decode operation.

Format revision 3 protects the post-compression body with an extended Hamming `(13,8)` SECDED code. Each stored body byte is mapped to 13 bits (eight data bits, four Hamming parity bits, and an overall parity bit), then the bitstream is packed into bytes. The on-wire body length is `ceil(stored_body_length * 13 / 8)`. SECDED corrects any single flipped bit in a 13-bit codeword and detects any double-bit error in that codeword. It cannot correct arbitrary multi-bit damage; the independent SHA-256 payload tag remains the final check. Format revision 2 has no Hamming layer and remains readable for development files created by the previous build.

The CRC32 is a big-endian uint32. The digest is the first 16 bytes of SHA-256; it detects accidental corruption but is not encryption or authentication against an attacker.

The bootstrap prefix is duplicated in two spatial regions: the top-left region and a centered region. Each prefix bit is represented by 26 repeated tile votes. When the image dimensions are still exact but lossy processing makes each anchor fail separately, revision-3 decoding pools the 52 votes from both exact-size anchors before guessing crop geometry; the full header CRC and payload SHA tag must still pass. The rest of the header is embedded in the data-tile permutation with 47 repetitions per bit; payload bits use 19 repetitions per bit. Majority voting reconstructs each bit. If the header CRC fails, the decoder tries bounded combinations of the least-confident header votes (up to four bit flips among the 24 weakest vote margins) and accepts only a CRC-valid header. In exact decoding, the payload digest is checked before bytes are treated as verified. Best-effort modes may deliberately return unverified reconstruction bytes with a warning.

## Deterministic slot permutation

For format revision 2, the 4096-tile bootstrap region is permuted using Fisher–Yates and xorshift32 with seed `0x48525331`. For each descending index `i`, update the 32-bit state as follows, masking to 32 bits after left shifts/multiplications, then choose `j = state % (i + 1)` and swap positions `i` and `j`:

```text
state ^= (state << 13) & 0xffffffff
state ^= state >> 17
state ^= (state << 5) & 0xffffffff
state &= 0xffffffff
```

For format revision 3, the bootstrap copies use spatially stratified placement rather than the legacy random shuffle. There are 152 prefix bits and 26 copies per bit. For bit index `b` and copy index `c`, the physical tile slot is `c * 157 + b`; unused region slots are ignored. This spaces every bit's copies throughout the bootstrap region so a crop is less likely to erase all copies of any one bit. Format revision 2 uses the Fisher–Yates prefix permutation above.

For payload/header-remainder slots, reserve the first 4096 global slots and the 4096-slot region starting at `center_y * grid_width`, where `center_y = (grid_height - ceil(4096 / grid_width)) // 2`. Shuffle the remaining global slot indices in ascending initial order with Fisher–Yates/xorshift32. The seed is:

`((grid_width * 0x9E3779B1) XOR (grid_height * 0x85EBCA77) XOR 0x48525331) & 0xffffffff`.

The logical stream order is the remaining header bytes first, followed by the body bytes. For revision 3, the body bytes are Hamming-coded before placement; revision 2 places the raw or zlib bytes directly. The repetition counts above determine each logical bit's consecutive positions in the shuffled slot list.

## Security and robustness boundaries

HushRaster stores bytes; it does not encrypt them. Encrypt the input file separately if secrecy is required. Revision 3 combines 19-way spatial majority voting, Hamming SECDED error correction, CRC-guided header recovery, and the payload SHA-256 integrity tag. For method `z`, the decoder can additionally try changing low-confidence voted body bits and use zlib’s Adler-32 plus the hidden SHA-256 tag to identify an exact reconstruction. `best`/`depends`/`default` are adaptive; `strict` refuses unverified body results; `fast` limits header-location work; `reconstruct` tries more bit repairs and may return only a best-effort decompressed prefix if the stream is damaged. Unverified reconstructions are warned about unless `--focus` is set. The command-line `decode` and `decode-text` commands refuse to output unverified bytes unless `--allow-unverified` is explicitly supplied; `--focus` does not bypass that guard. The current implementation enforces a 256 MiB decoded-payload safety limit and a 40-million-pixel image limit. Compression/crop recovery is empirical, not universal: some low-quality lossy encodes, resizes, rotations, or off-center crops can exceed the recovery limit.
