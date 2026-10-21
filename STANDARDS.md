# HushRaster Standard Registry

HushRaster is a family of **distinct raster formats**. Use a lowercase selector followed by `+`, for example `p2+`, `d1+`, `m1+`, `aa1+`, or `r1+`. A shared family prefix describes the visual/data-design lineage; it does not mean the formats are wire-compatible aliases. Every numbered standard has a defined framing/coding scheme and a unique finder signature; formats that carry an in-band wire ID use a unique ID.

## Monochrome and legacy standards

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `p1+` | P1 — Panda 1 | Triple-bit repetition and CRC32. |
| `p2+` | P2 — Panda 2 | Interleaved Reed–Solomon error correction and CRC32; default. |
| `p3+` | P3 — Panda 3 | Length-prefixed raw bytes; no checksum or error correction. |
| `p4+` | P4 — Panda 4 | Unique framing and finder design; raw body with CRC32. |
| `p5+` | P5 — Panda 5 | Byte-wise triple repetition, majority repair and CRC32. |
| `p6+` | P6 — Panda 6 | Bit-wise triple repetition, majority repair and CRC32. |
| `p7+` | P7 — Panda 7 | Byte-wise fivefold repetition, majority repair and CRC32. |
| `p8+` | P8 — Panda 8 | Standard-specific keyed byte masking and CRC32. |
| `p9+` | P9 — Panda 9 | Per-byte bit reversal and CRC32. |
| `p10+` | P10 — Panda 10 | Even/odd byte interleaving in eight-byte blocks and CRC32. |
| `p11+` | P11 — Panda 11 | Hamming(7,4) single-bit correction and CRC32. |
| `p12+` | P12 — Panda 12 | Reed–Solomon with eight parity symbols per block and CRC32. |
| `p13+` | P13 — Panda 13 | Eight-byte block parity and CRC32. |
| `oi+` | OI — OverImage | Legacy standalone modulation on a generated carrier. `oi1+` remains accepted. `imgmod` is the origin-image overlay exception. |

## Diagonal tree

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `d1+` | D1 — Diagonal 1 | Own `HRD1` wire marker and diagonal-cell finder; raw length framing, no checksum or error correction. Legacy OI2-marked images still decode. |
| `d2+` | D2 — Diagonal 2 | Diagonal modules with Reed–Solomon (eight parity symbols; up to four unknown byte-symbol errors per block) and CRC32. |
| `d3+` | D3 — Diagonal 3 | Diagonal modules with Hamming(7,4) single-bit correction and CRC32. |
| `d4+` | D4 — Diagonal 4 | Byte-wise triple repetition and CRC32. |
| `d5+` | D5 — Diagonal 5 | Bit-wise triple repetition and CRC32. |
| `d6+` | D6 — Diagonal 6 | Byte-wise fivefold repetition and CRC32. |
| `d7+` | D7 — Diagonal 7 | Eight-byte even/odd interleaving and CRC32. |
| `d8+` | D8 — Diagonal 8 | Standard-specific keyed byte masking and CRC32. |
| `d9+` | D9 — Diagonal 9 | Per-byte bit reversal and CRC32. |
| `d10+` | D10 — Diagonal 10 | Eight-byte block parity and CRC32. |
| `d11+` | D11 — Diagonal 11 | Differential XOR chaining and CRC32. |

**Use `d1+`, not `d+`.** The old `oi2+` selector is accepted as a legacy alias for D1; it is not listed as a separate standard.

## Five-colour tree

The CE family uses black, white, red, green and blue modules.

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `ce1+` | CE1 — Colored Elephant 1 | Base-5 colour symbols and CRC32; no error correction. |
| `ce2+` | CE2 — Colored Elephant 2 | Byte-wise triple repetition and CRC32. |
| `ce3+` | CE3 — Colored Elephant 3 | Bit-wise triple repetition and CRC32. |
| `ce4+` | CE4 — Colored Elephant 4 | Byte-wise fivefold repetition and CRC32. |
| `ce5+` | CE5 — Colored Elephant 5 | Standard-specific keyed byte masking and CRC32. |
| `ce6+` | CE6 — Colored Elephant 6 | Per-byte bit reversal and CRC32. |
| `ce7+` | CE7 — Colored Elephant 7 | Eight-byte even/odd interleaving and CRC32. |
| `ce8+` | CE8 — Colored Elephant 8 | Byte-local base-5 cells, triple colour-cell repetition, Hamming(7,4) correction and CRC32. |
| `ce9+` | CE9 — Colored Elephant 9 | Byte-local base-5 cells, Reed–Solomon with eight parity symbols per block and CRC32. |
| `ce10+` | CE10 — Colored Elephant 10 | Eight-byte block parity and CRC32. |
| `ce11+` | CE11 — Colored Elephant 11 | Differential XOR chaining and CRC32. |

## Striped monochrome tree

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `z1+` | Z1 — Zebra 1 | Striped modules and CRC32; no error correction. |
| `z2+` | Z2 — Zebra 2 | Byte-wise triple repetition and CRC32. |
| `z3+` | Z3 — Zebra 3 | Bit-wise triple repetition and CRC32. |
| `z4+` | Z4 — Zebra 4 | Byte-wise fivefold repetition and CRC32. |
| `z5+` | Z5 — Zebra 5 | Standard-specific keyed byte masking and CRC32. |
| `z6+` | Z6 — Zebra 6 | Per-byte bit reversal and CRC32. |
| `z7+` | Z7 — Zebra 7 | Eight-byte even/odd interleaving and CRC32. |
| `z8+` | Z8 — Zebra 8 | Hamming(7,4) single-bit correction and CRC32. |
| `z9+` | Z9 — Zebra 9 | Reed–Solomon with eight parity symbols per block and CRC32. |
| `z10+` | Z10 — Zebra 10 | Eight-byte block parity and CRC32. |
| `z11+` | Z11 — Zebra 11 | Differential XOR chaining and CRC32. |

## Mosaic tree — checkerboard-phase modules

Each data cell encodes its bit through the phase of a checkerboard glyph at readable module sizes. Every standard has its own wire marker and finder signature.

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `m1+` | M1 — Mosaic 1 | Byte-wise triple repetition and CRC32. |
| `m2+` | M2 — Mosaic 2 | Bit-wise triple repetition and CRC32. |
| `m3+` | M3 — Mosaic 3 | Byte-wise fivefold repetition and CRC32. |
| `m4+` | M4 — Mosaic 4 | Standard-specific keyed byte masking and CRC32. |
| `m5+` | M5 — Mosaic 5 | Per-byte bit reversal and CRC32. |
| `m6+` | M6 — Mosaic 6 | Even/odd byte interleaving and CRC32. |
| `m7+` | M7 — Mosaic 7 | Hamming(7,4) single-bit correction and CRC32. |
| `m8+` | M8 — Mosaic 8 | Reed–Solomon correction with eight parity symbols and CRC32. |
| `m9+` | M9 — Mosaic 9 | Eight-byte block parity and CRC32. |
| `m10+` | M10 — Mosaic 10 | Differential XOR chaining and CRC32. |

## Hexa tree — hexagonal-outline cells

Data cells use a hexagonal outline with the centre carrying the bit. Distinct numbered standards use independent framing and data transforms.

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `h1+` | H1 — Hexa 1 | Byte-wise triple repetition and CRC32. |
| `h2+` | H2 — Hexa 2 | Bit-wise triple repetition and CRC32. |
| `h3+` | H3 — Hexa 3 | Byte-wise fivefold repetition and CRC32. |
| `h4+` | H4 — Hexa 4 | Standard-specific keyed byte masking and CRC32. |
| `h5+` | H5 — Hexa 5 | Per-byte bit reversal and CRC32. |
| `h6+` | H6 — Hexa 6 | Even/odd byte interleaving and CRC32. |
| `h7+` | H7 — Hexa 7 | Hamming(7,4) single-bit correction and CRC32. |
| `h8+` | H8 — Hexa 8 | Reed–Solomon correction with eight parity symbols and CRC32. |
| `h9+` | H9 — Hexa 9 | Eight-byte block parity and CRC32. |
| `h10+` | H10 — Hexa 10 | Differential XOR chaining and CRC32. |

## Triangle tree — up/down triangle glyphs

Data bits are represented by upward- versus downward-pointing triangular cells at readable module sizes.

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `t1+` | T1 — Triangle 1 | Byte-wise triple repetition and CRC32. |
| `t2+` | T2 — Triangle 2 | Bit-wise triple repetition and CRC32. |
| `t3+` | T3 — Triangle 3 | Byte-wise fivefold repetition and CRC32. |
| `t4+` | T4 — Triangle 4 | Standard-specific keyed byte masking and CRC32. |
| `t5+` | T5 — Triangle 5 | Per-byte bit reversal and CRC32. |
| `t6+` | T6 — Triangle 6 | Even/odd byte interleaving and CRC32. |
| `t7+` | T7 — Triangle 7 | Hamming(7,4) single-bit correction and CRC32. |
| `t8+` | T8 — Triangle 8 | Reed–Solomon correction with eight parity symbols and CRC32. |
| `t9+` | T9 — Triangle 9 | Eight-byte block parity and CRC32. |
| `t10+` | T10 — Triangle 10 | Differential XOR chaining and CRC32. |

## 20 additional trees — 200 new standards

These standards have distinct per-tree microglyphs at `--ppm 4` and above. At `--ppm 1` and `--ppm 2`, the cells collapse to solid high-contrast modules to prioritize minimum size. Each standard has a unique finder signature; all except R1–R5 also carry an in-band `HR<CODE>\0` wire marker. R1 uses one asymmetric finder; R2–R5 retain three finder corners. Each uses its unique finder signature plus its Reed–Solomon level and length framing to identify the format.

### Arc tree (`A`) — arc-band modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `a1+` | A1 — Arc 1 | literal payload plus CRC32 |
| `a2+` | A2 — Arc 2 | byte-triplication with majority repair |
| `a3+` | A3 — Arc 3 | bit-triplication with majority repair |
| `a4+` | A4 — Arc 4 | fivefold byte repetition with majority repair |
| `a5+` | A5 — Arc 5 | standard-specific reversible stream mask plus CRC32 |
| `a6+` | A6 — Arc 6 | bit-reversed bytes plus CRC32 |
| `a7+` | A7 — Arc 7 | 8-byte even/odd permutation plus CRC32 |
| `a8+` | A8 — Arc 8 | Hamming(7,4) single-bit correction plus CRC32 |
| `a9+` | A9 — Arc 9 | Reed-Solomon with eight parity symbols plus CRC32 |
| `a10+` | A10 — Arc 10 | per-eight-byte parity detection plus CRC32 |

### Braid tree (`B`) — interwoven-strand modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `b1+` | B1 — Braid 1 | byte-triplication with majority repair |
| `b2+` | B2 — Braid 2 | 8-byte even/odd permutation plus CRC32 |
| `b3+` | B3 — Braid 3 | bit-triplication with majority repair |
| `b4+` | B4 — Braid 4 | standard-specific reversible stream mask plus CRC32 |
| `b5+` | B5 — Braid 5 | Hamming(7,4) single-bit correction plus CRC32 |
| `b6+` | B6 — Braid 6 | fivefold byte repetition with majority repair |
| `b7+` | B7 — Braid 7 | bit-reversed bytes plus CRC32 |
| `b8+` | B8 — Braid 8 | Reed-Solomon with eight parity symbols plus CRC32 |
| `b9+` | B9 — Braid 9 | per-eight-byte parity detection plus CRC32 |
| `b10+` | B10 — Braid 10 | differential XOR coding plus CRC32 |

### Facet tree (`F`) — faceted-diamond modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `f1+` | F1 — Facet 1 | bit-reversed bytes plus CRC32 |
| `f2+` | F2 — Facet 2 | byte-triplication with majority repair |
| `f3+` | F3 — Facet 3 | Hamming(7,4) single-bit correction plus CRC32 |
| `f4+` | F4 — Facet 4 | bit-triplication with majority repair |
| `f5+` | F5 — Facet 5 | standard-specific reversible stream mask plus CRC32 |
| `f6+` | F6 — Facet 6 | 8-byte even/odd permutation plus CRC32 |
| `f7+` | F7 — Facet 7 | Reed-Solomon with eight parity symbols plus CRC32 |
| `f8+` | F8 — Facet 8 | fivefold byte repetition with majority repair |
| `f9+` | F9 — Facet 9 | per-eight-byte parity detection plus CRC32 |
| `f10+` | F10 — Facet 10 | differential XOR coding plus CRC32 |

### Grid tree (`G`) — nested-grid modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `g1+` | G1 — Grid 1 | 8-byte even/odd permutation plus CRC32 |
| `g2+` | G2 — Grid 2 | literal payload plus CRC32 |
| `g3+` | G3 — Grid 3 | bit-triplication with majority repair |
| `g4+` | G4 — Grid 4 | byte-triplication with majority repair |
| `g5+` | G5 — Grid 5 | standard-specific reversible stream mask plus CRC32 |
| `g6+` | G6 — Grid 6 | bit-reversed bytes plus CRC32 |
| `g7+` | G7 — Grid 7 | Hamming(7,4) single-bit correction plus CRC32 |
| `g8+` | G8 — Grid 8 | Reed-Solomon with eight parity symbols plus CRC32 |
| `g9+` | G9 — Grid 9 | fivefold byte repetition with majority repair |
| `g10+` | G10 — Grid 10 | per-eight-byte parity detection plus CRC32 |

### Iris tree (`I`) — concentric-iris modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `i1+` | I1 — Iris 1 | bit-triplication with majority repair |
| `i2+` | I2 — Iris 2 | byte-triplication with majority repair |
| `i3+` | I3 — Iris 3 | standard-specific reversible stream mask plus CRC32 |
| `i4+` | I4 — Iris 4 | Hamming(7,4) single-bit correction plus CRC32 |
| `i5+` | I5 — Iris 5 | 8-byte even/odd permutation plus CRC32 |
| `i6+` | I6 — Iris 6 | bit-reversed bytes plus CRC32 |
| `i7+` | I7 — Iris 7 | Reed-Solomon with eight parity symbols plus CRC32 |
| `i8+` | I8 — Iris 8 | fivefold byte repetition with majority repair |
| `i9+` | I9 — Iris 9 | per-eight-byte parity detection plus CRC32 |
| `i10+` | I10 — Iris 10 | differential XOR coding plus CRC32 |

### Junction tree (`J`) — spoke-junction modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `j1+` | J1 — Junction 1 | Hamming(7,4) single-bit correction plus CRC32 |
| `j2+` | J2 — Junction 2 | bit-triplication with majority repair |
| `j3+` | J3 — Junction 3 | 8-byte even/odd permutation plus CRC32 |
| `j4+` | J4 — Junction 4 | byte-triplication with majority repair |
| `j5+` | J5 — Junction 5 | standard-specific reversible stream mask plus CRC32 |
| `j6+` | J6 — Junction 6 | Reed-Solomon with eight parity symbols plus CRC32 |
| `j7+` | J7 — Junction 7 | bit-reversed bytes plus CRC32 |
| `j8+` | J8 — Junction 8 | fivefold byte repetition with majority repair |
| `j9+` | J9 — Junction 9 | per-eight-byte parity detection plus CRC32 |
| `j10+` | J10 — Junction 10 | differential XOR coding plus CRC32 |

### Keystone tree (`K`) — trapezoid-keystone modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `k1+` | K1 — Keystone 1 | standard-specific reversible stream mask plus CRC32 |
| `k2+` | K2 — Keystone 2 | bit-reversed bytes plus CRC32 |
| `k3+` | K3 — Keystone 3 | byte-triplication with majority repair |
| `k4+` | K4 — Keystone 4 | bit-triplication with majority repair |
| `k5+` | K5 — Keystone 5 | Hamming(7,4) single-bit correction plus CRC32 |
| `k6+` | K6 — Keystone 6 | 8-byte even/odd permutation plus CRC32 |
| `k7+` | K7 — Keystone 7 | Reed-Solomon with eight parity symbols plus CRC32 |
| `k8+` | K8 — Keystone 8 | fivefold byte repetition with majority repair |
| `k9+` | K9 — Keystone 9 | per-eight-byte parity detection plus CRC32 |
| `k10+` | K10 — Keystone 10 | differential XOR coding plus CRC32 |

### Nexus tree (`N`) — node-cluster modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `n1+` | N1 — Nexus 1 | per-eight-byte parity detection plus CRC32 |
| `n2+` | N2 — Nexus 2 | byte-triplication with majority repair |
| `n3+` | N3 — Nexus 3 | bit-triplication with majority repair |
| `n4+` | N4 — Nexus 4 | 8-byte even/odd permutation plus CRC32 |
| `n5+` | N5 — Nexus 5 | standard-specific reversible stream mask plus CRC32 |
| `n6+` | N6 — Nexus 6 | Hamming(7,4) single-bit correction plus CRC32 |
| `n7+` | N7 — Nexus 7 | bit-reversed bytes plus CRC32 |
| `n8+` | N8 — Nexus 8 | Reed-Solomon with eight parity symbols plus CRC32 |
| `n9+` | N9 — Nexus 9 | fivefold byte repetition with majority repair |
| `n10+` | N10 — Nexus 10 | differential XOR coding plus CRC32 |

### Quick tree (`Q`) — chevron modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `q1+` | Q1 — Quick 1 | fivefold byte repetition with majority repair |
| `q2+` | Q2 — Quick 2 | byte-triplication with majority repair |
| `q3+` | Q3 — Quick 3 | bit-triplication with majority repair |
| `q4+` | Q4 — Quick 4 | standard-specific reversible stream mask plus CRC32 |
| `q5+` | Q5 — Quick 5 | bit-reversed bytes plus CRC32 |
| `q6+` | Q6 — Quick 6 | 8-byte even/odd permutation plus CRC32 |
| `q7+` | Q7 — Quick 7 | Hamming(7,4) single-bit correction plus CRC32 |
| `q8+` | Q8 — Quick 8 | Reed-Solomon with eight parity symbols plus CRC32 |
| `q9+` | Q9 — Quick 9 | per-eight-byte parity detection plus CRC32 |
| `q10+` | Q10 — Quick 10 | differential XOR coding plus CRC32 |

### Resilient tree (`R`) — high-redundancy compact modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `r1+` | R1 — Resilient Compact | Single asymmetric finder; one-byte length prefix (extended at 255+); interleaved Reed–Solomon with 32 parity symbols protecting payload and CRC32; corrects up to 16 unknown byte-symbol errors per codeword. |
| `r2+` | R2 — Resilient 2 | Single length-prefix frame; interleaved Reed–Solomon with 48 parity symbols protecting payload and CRC32; up to 24 unknown byte-symbol errors per codeword. |
| `r3+` | R3 — Resilient 3 | Single length-prefix frame; interleaved Reed–Solomon with 24 parity symbols protecting payload and CRC32; up to 12 unknown byte-symbol errors per codeword. |
| `r4+` | R4 — Resilient 4 | Single length-prefix frame; interleaved Reed–Solomon with 16 parity symbols protecting payload and CRC32; up to 8 unknown byte-symbol errors per codeword. |
| `r5+` | R5 — Resilient 5 | Single length-prefix frame; interleaved Reed–Solomon with 64 parity symbols protecting payload and CRC32; up to 32 unknown byte-symbol errors per codeword. |
| `r6+` | R6 — Resilient 6 | Reed-Solomon with eight parity symbols plus CRC32 |
| `r7+` | R7 — Resilient 7 | Hamming(7,4) single-bit correction plus CRC32 |
| `r8+` | R8 — Resilient 8 | byte-triplication with majority repair |
| `r9+` | R9 — Resilient 9 | 8-byte even/odd permutation plus CRC32 |
| `r10+` | R10 — Resilient 10 | per-eight-byte parity detection plus CRC32 |

### Spiral tree (`S`) — spiral-track modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `s1+` | S1 — Spiral 1 | bit-triplication with majority repair |
| `s2+` | S2 — Spiral 2 | 8-byte even/odd permutation plus CRC32 |
| `s3+` | S3 — Spiral 3 | fivefold byte repetition with majority repair |
| `s4+` | S4 — Spiral 4 | standard-specific reversible stream mask plus CRC32 |
| `s5+` | S5 — Spiral 5 | bit-reversed bytes plus CRC32 |
| `s6+` | S6 — Spiral 6 | Hamming(7,4) single-bit correction plus CRC32 |
| `s7+` | S7 — Spiral 7 | Reed-Solomon with eight parity symbols plus CRC32 |
| `s8+` | S8 — Spiral 8 | byte-triplication with majority repair |
| `s9+` | S9 — Spiral 9 | per-eight-byte parity detection plus CRC32 |
| `s10+` | S10 — Spiral 10 | differential XOR coding plus CRC32 |

### Umbra tree (`U`) — eclipse-and-shadow modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `u1+` | U1 — Umbra 1 | standard-specific reversible stream mask plus CRC32 |
| `u2+` | U2 — Umbra 2 | bit-triplication with majority repair |
| `u3+` | U3 — Umbra 3 | byte-triplication with majority repair |
| `u4+` | U4 — Umbra 4 | bit-reversed bytes plus CRC32 |
| `u5+` | U5 — Umbra 5 | 8-byte even/odd permutation plus CRC32 |
| `u6+` | U6 — Umbra 6 | Hamming(7,4) single-bit correction plus CRC32 |
| `u7+` | U7 — Umbra 7 | Reed-Solomon with eight parity symbols plus CRC32 |
| `u8+` | U8 — Umbra 8 | fivefold byte repetition with majority repair |
| `u9+` | U9 — Umbra 9 | per-eight-byte parity detection plus CRC32 |
| `u10+` | U10 — Umbra 10 | differential XOR coding plus CRC32 |

### Vector tree (`V`) — directional-arrow modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `v1+` | V1 — Vector 1 | bit-reversed bytes plus CRC32 |
| `v2+` | V2 — Vector 2 | 8-byte even/odd permutation plus CRC32 |
| `v3+` | V3 — Vector 3 | standard-specific reversible stream mask plus CRC32 |
| `v4+` | V4 — Vector 4 | byte-triplication with majority repair |
| `v5+` | V5 — Vector 5 | bit-triplication with majority repair |
| `v6+` | V6 — Vector 6 | Hamming(7,4) single-bit correction plus CRC32 |
| `v7+` | V7 — Vector 7 | Reed-Solomon with eight parity symbols plus CRC32 |
| `v8+` | V8 — Vector 8 | fivefold byte repetition with majority repair |
| `v9+` | V9 — Vector 9 | per-eight-byte parity detection plus CRC32 |
| `v10+` | V10 — Vector 10 | differential XOR coding plus CRC32 |

### Weave tree (`W`) — cross-woven modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `w1+` | W1 — Weave 1 | 8-byte even/odd permutation plus CRC32 |
| `w2+` | W2 — Weave 2 | byte-triplication with majority repair |
| `w3+` | W3 — Weave 3 | bit-triplication with majority repair |
| `w4+` | W4 — Weave 4 | fivefold byte repetition with majority repair |
| `w5+` | W5 — Weave 5 | standard-specific reversible stream mask plus CRC32 |
| `w6+` | W6 — Weave 6 | bit-reversed bytes plus CRC32 |
| `w7+` | W7 — Weave 7 | Hamming(7,4) single-bit correction plus CRC32 |
| `w8+` | W8 — Weave 8 | Reed-Solomon with eight parity symbols plus CRC32 |
| `w9+` | W9 — Weave 9 | per-eight-byte parity detection plus CRC32 |
| `w10+` | W10 — Weave 10 | differential XOR coding plus CRC32 |

### Cross tree (`X`) — cross-lattice modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `x1+` | X1 — Cross 1 | Hamming(7,4) single-bit correction plus CRC32 |
| `x2+` | X2 — Cross 2 | byte-triplication with majority repair |
| `x3+` | X3 — Cross 3 | bit-triplication with majority repair |
| `x4+` | X4 — Cross 4 | 8-byte even/odd permutation plus CRC32 |
| `x5+` | X5 — Cross 5 | standard-specific reversible stream mask plus CRC32 |
| `x6+` | X6 — Cross 6 | bit-reversed bytes plus CRC32 |
| `x7+` | X7 — Cross 7 | Reed-Solomon with eight parity symbols plus CRC32 |
| `x8+` | X8 — Cross 8 | fivefold byte repetition with majority repair |
| `x9+` | X9 — Cross 9 | per-eight-byte parity detection plus CRC32 |
| `x10+` | X10 — Cross 10 | differential XOR coding plus CRC32 |

### Asymmetric tree (`Y`) — asymmetric-wedge modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `y1+` | Y1 — Asymmetric 1 | differential XOR coding plus CRC32 |
| `y2+` | Y2 — Asymmetric 2 | standard-specific reversible stream mask plus CRC32 |
| `y3+` | Y3 — Asymmetric 3 | bit-reversed bytes plus CRC32 |
| `y4+` | Y4 — Asymmetric 4 | byte-triplication with majority repair |
| `y5+` | Y5 — Asymmetric 5 | bit-triplication with majority repair |
| `y6+` | Y6 — Asymmetric 6 | 8-byte even/odd permutation plus CRC32 |
| `y7+` | Y7 — Asymmetric 7 | Hamming(7,4) single-bit correction plus CRC32 |
| `y8+` | Y8 — Asymmetric 8 | Reed-Solomon with eight parity symbols plus CRC32 |
| `y9+` | Y9 — Asymmetric 9 | fivefold byte repetition with majority repair |
| `y10+` | Y10 — Asymmetric 10 | per-eight-byte parity detection plus CRC32 |

### Adaptive Array tree (`AA`) — adaptive block-array modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `aa1+` | AA1 — Adaptive Array 1 | literal payload plus CRC32 |
| `aa2+` | AA2 — Adaptive Array 2 | 8-byte even/odd permutation plus CRC32 |
| `aa3+` | AA3 — Adaptive Array 3 | byte-triplication with majority repair |
| `aa4+` | AA4 — Adaptive Array 4 | bit-triplication with majority repair |
| `aa5+` | AA5 — Adaptive Array 5 | standard-specific reversible stream mask plus CRC32 |
| `aa6+` | AA6 — Adaptive Array 6 | bit-reversed bytes plus CRC32 |
| `aa7+` | AA7 — Adaptive Array 7 | Hamming(7,4) single-bit correction plus CRC32 |
| `aa8+` | AA8 — Adaptive Array 8 | Reed-Solomon with eight parity symbols plus CRC32 |
| `aa9+` | AA9 — Adaptive Array 9 | fivefold byte repetition with majority repair |
| `aa10+` | AA10 — Adaptive Array 10 | per-eight-byte parity detection plus CRC32 |

### Bridge tree (`BR`) — bridge-and-rail modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `br1+` | BR1 — Bridge 1 | byte-triplication with majority repair |
| `br2+` | BR2 — Bridge 2 | Hamming(7,4) single-bit correction plus CRC32 |
| `br3+` | BR3 — Bridge 3 | 8-byte even/odd permutation plus CRC32 |
| `br4+` | BR4 — Bridge 4 | bit-triplication with majority repair |
| `br5+` | BR5 — Bridge 5 | standard-specific reversible stream mask plus CRC32 |
| `br6+` | BR6 — Bridge 6 | bit-reversed bytes plus CRC32 |
| `br7+` | BR7 — Bridge 7 | Reed-Solomon with eight parity symbols plus CRC32 |
| `br8+` | BR8 — Bridge 8 | fivefold byte repetition with majority repair |
| `br9+` | BR9 — Bridge 9 | per-eight-byte parity detection plus CRC32 |
| `br10+` | BR10 — Bridge 10 | differential XOR coding plus CRC32 |

### Compact Payload tree (`CP`) — dense microcell modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `cp1+` | CP1 — Compact Payload 1 | literal payload plus CRC32 |
| `cp2+` | CP2 — Compact Payload 2 | standard-specific reversible stream mask plus CRC32 |
| `cp3+` | CP3 — Compact Payload 3 | bit-reversed bytes plus CRC32 |
| `cp4+` | CP4 — Compact Payload 4 | 8-byte even/odd permutation plus CRC32 |
| `cp5+` | CP5 — Compact Payload 5 | Hamming(7,4) single-bit correction plus CRC32 |
| `cp6+` | CP6 — Compact Payload 6 | byte-triplication with majority repair |
| `cp7+` | CP7 — Compact Payload 7 | bit-triplication with majority repair |
| `cp8+` | CP8 — Compact Payload 8 | Reed-Solomon with eight parity symbols plus CRC32 |
| `cp9+` | CP9 — Compact Payload 9 | per-eight-byte parity detection plus CRC32 |
| `cp10+` | CP10 — Compact Payload 10 | differential XOR coding plus CRC32 |

### Staggered tree (`ST`) — staggered-column modules

| Selector | Standard | Encoding and integrity |
|---|---|---|
| `st1+` | ST1 — Staggered 1 | 8-byte even/odd permutation plus CRC32 |
| `st2+` | ST2 — Staggered 2 | bit-triplication with majority repair |
| `st3+` | ST3 — Staggered 3 | byte-triplication with majority repair |
| `st4+` | ST4 — Staggered 4 | standard-specific reversible stream mask plus CRC32 |
| `st5+` | ST5 — Staggered 5 | bit-reversed bytes plus CRC32 |
| `st6+` | ST6 — Staggered 6 | Hamming(7,4) single-bit correction plus CRC32 |
| `st7+` | ST7 — Staggered 7 | Reed-Solomon with eight parity symbols plus CRC32 |
| `st8+` | ST8 — Staggered 8 | fivefold byte repetition with majority repair |
| `st9+` | ST9 — Staggered 9 | per-eight-byte parity detection plus CRC32 |
| `st10+` | ST10 — Staggered 10 | differential XOR coding plus CRC32 |

See [`R1.md`](R1.md) for the complete R1 framing, single-finder layout and error-correction specification.

## Reserved standards

| Selector | Standard | Status |
|---|---|---|
| `e1+` | E1 — Elephant 1 | Reserved; no encoder or decoder. |
| `l1+` | L1 — Lion 1 | Reserved; no encoder or decoder. |

## Pipe-based CLI

Normal encoding reads **raw bytes from stdin** and writes a PNG to **stdout**. Decoding reads PNG bytes from stdin and writes recovered raw bytes to stdout. Diagnostics go to stderr.

```bash
python3 -m hushraster encode < payload.bin > barcode.png
python3 -m hushraster encode p12+ --ppm 1 < payload.bin > barcode.png
python3 -m hushraster decode < barcode.png > recovered.bin
python3 -m hushraster decode d2+ < diagonal.png > recovered.bin
python3 -m hushraster inspect ce9+ < colour.png
python3 -m hushraster encode m8+ --ppm 4 < payload.bin > mosaic.png
python3 -m hushraster encode h8+ --ppm 4 < payload.bin > hexa.png
python3 -m hushraster encode t8+ --ppm 4 < payload.bin > triangle.png
python3 -m hushraster standards
```

`--ppm` controls pixels per module: it defaults to `4` and accepts values from `1` through `32`. Lower values produce smaller images, while higher values enlarge the modules for display/printing. The 20 new trees use distinguishable 4×4 microglyphs at PPM 4+; at PPM 1–2 they prioritize density by falling back to solid modules. CRC32 detects accidental corruption but is not cryptographic authentication. Error-correction limits depend on the selected standard, and no format guarantees survival of arbitrary cropping, perspective distortion or lossy recompression. These formats are HushRaster-specific, not QR Code or Data Matrix.

## Legacy IMGMod exception

Only `imgmod` takes explicit input/output image paths because it overlays data into an existing image:

```bash
cat payload.bin | python3 -m hushraster imgmod encode photo.png output.png
python3 -m hushraster decode < output.png > recovered.bin
```

The `oi+` standard generates a standalone OI carrier and does not require an origin image. The separate `imgmod` command remains the legacy image-overlay interface.

## SL1 — Scan Lonely

SL1 is a linear barcode made from **one horizontal row of equal-width vertical bars**. The bars share a horizontal centreline and spacing; each bar's height represents one four-bit symbol. No finder corners, logos, circles, squares, or decorative shapes are part of the code. Its one-byte in-band identifier occupies only the first two bars; earlier four-byte-marker images remain supported for decoding.

The encoded frame contains a format marker, payload length, raw payload bytes, and CRC32. The stream is split into shortened Reed–Solomon codewords with 32 parity symbols each, then interleaved. Each codeword can correct up to 16 unknown byte-symbol errors; CRC32 verifies the recovered payload. SL1 does not compress payload data.

Pipe examples (all normal encode/decode commands use stdin/stdout):

```sh
printf 'HushRaster SL1 sample' | python3 -m hushraster encode sl1+ --ppm 4 > sl1.png
python3 -m hushraster decode < sl1.png
python3 -m hushraster decode sl1+ < sl1.png > recovered.bin
```

`--ppm` controls the pixel scale. The decoder recognizes SL1 automatically from its fixed-height linear raster geometry. The current scanner expects the original module grid; perspective correction and arbitrary resizing are not claimed.
