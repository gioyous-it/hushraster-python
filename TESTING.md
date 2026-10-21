# Testing HushRaster 1.0.1

Run from the repository root:

```bash
python -m compileall -q hushraster.py hushraster tests
python -m pytest -q
```

Coverage includes pipe-only CLI round trips, standalone OI, reserved-format errors, legacy IMGMod helpers, distinct marker/finder signatures across the registry, all 200 additional numbered standards, varied binary payloads, Reed–Solomon correction in D2 and R1–R5, Hamming correction, all new glyph trees, CRC verification, `d1+` selector handling, and both module and direct-script launchers.

The standard trees contain P1–P13, D1–D11, CE1–CE11, Z1–Z11, M1–M10, H1–H10 and T1–T10. No numbered variant is a compatibility profile. Each has a unique finder signature and either an in-band wire marker or its own standard-specific length/ECC framing and coding transform. M uses checkerboard-phase cells, H uses hexagonal-outline cells, and T uses up/down triangles. The pipe contract is intentional: normal encode/decode/inspect commands exchange data over stdin/stdout; `imgmod` is the explicit file-path exception.

No test can guarantee survival under arbitrary resizing, cropping, camera perspective or lossy recompression. The standalone raster scanner expects an aligned grid. Error correction varies by standard, and CRC32 is not cryptographic authentication.


## Additional 200 standards and R1 logo test

- 200 additional standards across the A/B/F/G/I/J/K/N/Q/R/S/U/V/W/X/Y/AA/BR/CP/ST trees.
- Binary-safe round trips for all 200 at PPM 1 and PPM 4.
- Unique finder templates, distinct 4×4 glyphs for all 20 additional visual trees, selector routing and auto-detection.
- R1–R5 Reed–Solomon codewords tested at their full error-correction limits (16, 24, 12, 8, and 32 unknown symbol errors, respectively).
- R1 single-finder geometry and centered 7×7 opaque logo-overlay recovery tested at PPM 1 and PPM 4.
- R1 and R2 extended payload-length framing tested with lengths at and above 255 bytes.
