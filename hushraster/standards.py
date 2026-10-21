# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Stable registry of the HushRaster barcode standards."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Standard:
    code: str
    name: str
    status: str
    description: str


# New independent design families. Family membership denotes visual/code-design lineage, not
# backwards compatibility with an existing standard. Ten separately framed formats per tree.
ADDITIONAL_TREES = {
    "a": ("Arc", "arc-band modules"),
    "b": ("Braid", "interwoven-strand modules"),
    "f": ("Facet", "faceted-diamond modules"),
    "g": ("Grid", "nested-grid modules"),
    "i": ("Iris", "concentric-iris modules"),
    "j": ("Junction", "spoke-junction modules"),
    "k": ("Keystone", "trapezoid-keystone modules"),
    "n": ("Nexus", "node-cluster modules"),
    "q": ("Quick", "chevron modules"),
    "r": ("Resilient", "high-redundancy compact modules"),
    "s": ("Spiral", "spiral-track modules"),
    "u": ("Umbra", "eclipse-and-shadow modules"),
    "v": ("Vector", "directional-arrow modules"),
    "w": ("Weave", "cross-woven modules"),
    "x": ("Cross", "cross-lattice modules"),
    "y": ("Asymmetric", "asymmetric-wedge modules"),
    "aa": ("Adaptive Array", "adaptive block-array modules"),
    "br": ("Bridge", "bridge-and-rail modules"),
    "cp": ("Compact Payload", "dense microcell modules"),
    "st": ("Staggered", "staggered-column modules"),
}

_METHOD_DESCRIPTIONS = {
    "rawcrc": "literal payload plus CRC32",
    "repbyte3": "byte-triplication with majority repair",
    "repbit3": "bit-triplication with majority repair",
    "repbyte5": "fivefold byte repetition with majority repair",
    "mask": "standard-specific reversible stream mask plus CRC32",
    "bitrev": "bit-reversed bytes plus CRC32",
    "interleave": "8-byte even/odd permutation plus CRC32",
    "hamming": "Hamming(7,4) single-bit correction plus CRC32",
    "rs8": "Reed-Solomon with eight parity symbols plus CRC32",
    "parity8": "per-eight-byte parity detection plus CRC32",
    "delta": "differential XOR coding plus CRC32",
    "rs16": "Reed-Solomon with 16 parity symbols, correcting up to 8 unknown byte-symbol errors per codeword; payload and CRC32 are protected",
    "rs24": "Reed-Solomon with 24 parity symbols, correcting up to 12 unknown byte-symbol errors per codeword; payload and CRC32 are protected",
    "rs32": "Reed-Solomon with 32 parity symbols, correcting up to 16 unknown byte-symbol errors per codeword; payload and CRC32 are protected",
    "rs48": "Reed-Solomon with 48 parity symbols, correcting up to 24 unknown byte-symbol errors per codeword; payload and CRC32 are protected",
    "rs64": "Reed-Solomon with 64 parity symbols, correcting up to 32 unknown byte-symbol errors per codeword; payload and CRC32 are protected",
}

# Per-tree ten-format coding schedules. The R tree foregrounds strength/size trade-offs.
_ADDITIONAL_METHODS = {
    "a": ("rawcrc", "repbyte3", "repbit3", "repbyte5", "mask", "bitrev", "interleave", "hamming", "rs8", "parity8"),
    "b": ("repbyte3", "interleave", "repbit3", "mask", "hamming", "repbyte5", "bitrev", "rs8", "parity8", "delta"),
    "f": ("bitrev", "repbyte3", "hamming", "repbit3", "mask", "interleave", "rs8", "repbyte5", "parity8", "delta"),
    "g": ("interleave", "rawcrc", "repbit3", "repbyte3", "mask", "bitrev", "hamming", "rs8", "repbyte5", "parity8"),
    "i": ("repbit3", "repbyte3", "mask", "hamming", "interleave", "bitrev", "rs8", "repbyte5", "parity8", "delta"),
    "j": ("hamming", "repbit3", "interleave", "repbyte3", "mask", "rs8", "bitrev", "repbyte5", "parity8", "delta"),
    "k": ("mask", "bitrev", "repbyte3", "repbit3", "hamming", "interleave", "rs8", "repbyte5", "parity8", "delta"),
    "n": ("parity8", "repbyte3", "repbit3", "interleave", "mask", "hamming", "bitrev", "rs8", "repbyte5", "delta"),
    "q": ("repbyte5", "repbyte3", "repbit3", "mask", "bitrev", "interleave", "hamming", "rs8", "parity8", "delta"),
    "r": ("rs32", "rs48", "rs24", "rs16", "rs64", "rs8", "hamming", "repbyte3", "interleave", "parity8"),
    "s": ("repbit3", "interleave", "repbyte5", "mask", "bitrev", "hamming", "rs8", "repbyte3", "parity8", "delta"),
    "u": ("mask", "repbit3", "repbyte3", "bitrev", "interleave", "hamming", "rs8", "repbyte5", "parity8", "delta"),
    "v": ("bitrev", "interleave", "mask", "repbyte3", "repbit3", "hamming", "rs8", "repbyte5", "parity8", "delta"),
    "w": ("interleave", "repbyte3", "repbit3", "repbyte5", "mask", "bitrev", "hamming", "rs8", "parity8", "delta"),
    "x": ("hamming", "repbyte3", "repbit3", "interleave", "mask", "bitrev", "rs8", "repbyte5", "parity8", "delta"),
    "y": ("delta", "mask", "bitrev", "repbyte3", "repbit3", "interleave", "hamming", "rs8", "repbyte5", "parity8"),
    "aa": ("rawcrc", "interleave", "repbyte3", "repbit3", "mask", "bitrev", "hamming", "rs8", "repbyte5", "parity8"),
    "br": ("repbyte3", "hamming", "interleave", "repbit3", "mask", "bitrev", "rs8", "repbyte5", "parity8", "delta"),
    "cp": ("rawcrc", "mask", "bitrev", "interleave", "hamming", "repbyte3", "repbit3", "rs8", "parity8", "delta"),
    "st": ("interleave", "repbit3", "repbyte3", "mask", "bitrev", "hamming", "rs8", "repbyte5", "parity8", "delta"),
}

STANDARDS = {
    "p1": Standard("P1", "Panda 1", "implemented", "Monochrome triple-bit repetition with CRC32"),
    "p2": Standard("P2", "Panda 2", "implemented-default", "Monochrome interleaved Reed-Solomon correction with CRC32"),
    "p3": Standard("P3", "Panda 3", "implemented-raw", "Compact raw monochrome barcode with length prefix; no checksum or error correction"),
    **{f"p{i}": Standard(f"P{i}", f"Panda {i}", "implemented", _desc) for i, _desc in zip(range(4, 14), (
        "CRC-framed compact binary modules", "byte-wise triple repetition with majority repair",
        "bit-wise triple repetition with majority repair", "byte-wise fivefold repetition with majority repair",
        "keyed byte masking plus CRC32", "per-byte bit-reversal plus CRC32",
        "eight-byte even/odd interleaving plus CRC32", "Hamming(7,4) single-bit correction plus CRC32",
        "Reed-Solomon(8 parity symbols) correction plus CRC32", "eight-byte block parity plus CRC32",
    ))},
    "oi1": Standard("OI", "OverImage", "implemented-legacy", "Legacy OI modulation on a generated carrier; origin-image overlay remains under imgmod"),
    "d1": Standard("D1", "Diagonal 1", "implemented-raw", "Standalone diagonal-module barcode; raw framing without checksum or error correction"),
    **{f"d{i}": Standard(f"D{i}", f"Diagonal {i}", "implemented", _desc) for i, _desc in zip(range(2, 12), (
        "Reed-Solomon with eight parity symbols (up to four unknown byte-symbol errors per block) plus CRC32", "Hamming(7,4) single-bit correction plus CRC32",
        "byte-wise triple repetition with majority repair", "bit-wise triple repetition with majority repair",
        "byte-wise fivefold repetition with majority repair", "eight-byte even/odd interleaving plus CRC32",
        "keyed byte masking plus CRC32", "per-byte bit-reversal plus CRC32",
        "eight-byte block parity plus CRC32", "differential XOR chaining plus CRC32",
    ))},
    "ce1": Standard("CE1", "Colored Elephant 1", "implemented-colour", "Five-colour base-5 barcode with CRC32; no error correction"),
    **{f"ce{i}": Standard(f"CE{i}", f"Colored Elephant {i}", "implemented", _desc) for i, _desc in zip(range(2, 12), (
        "Base-5 symbols with byte-wise triple repetition and majority repair", "Base-5 symbols with bit-wise triple repetition and majority repair",
        "Base-5 symbols with byte-wise fivefold repetition and majority repair", "Base-5 symbols with keyed byte masking and CRC32",
        "Base-5 symbols with per-byte bit-reversal and CRC32", "Base-5 symbols with eight-byte even/odd interleaving and CRC32",
        "Base-5 symbols with repeated colour cells plus Hamming(7,4) correction and CRC32", "Byte-local base-5 symbols with Reed-Solomon correction and CRC32",
        "Base-5 symbols with eight-byte block parity and CRC32", "Base-5 symbols with differential XOR chaining and CRC32",
    ))},
    "z1": Standard("Z1", "Zebra 1", "implemented-lightweight", "Striped monochrome barcode with CRC32 but no error correction"),
    **{f"z{i}": Standard(f"Z{i}", f"Zebra {i}", "implemented", _desc) for i, _desc in zip(range(2, 12), (
        "Striped binary barcode with byte-wise triple repetition and majority repair", "Striped binary barcode with bit-wise triple repetition and majority repair",
        "Striped binary barcode with byte-wise fivefold repetition and majority repair", "Striped binary barcode with keyed byte masking and CRC32",
        "Striped binary barcode with per-byte bit-reversal and CRC32", "Striped binary barcode with eight-byte even/odd interleaving and CRC32",
        "Striped binary barcode with Hamming(7,4) single-bit correction and CRC32", "Striped binary barcode with Reed-Solomon correction and CRC32",
        "Striped binary barcode with eight-byte block parity and CRC32", "Striped binary barcode with differential XOR chaining and CRC32",
    ))},
    **{f"m{i}": Standard(f"M{i}", f"Mosaic {i}", "implemented", _desc) for i, _desc in zip(range(1, 11), (
        "Checkerboard-phase modules with byte-wise triple repetition and CRC32",
        "Checkerboard-phase modules with bit-wise triple repetition and CRC32",
        "Checkerboard-phase modules with byte-wise fivefold repetition and CRC32",
        "Checkerboard-phase modules with code-specific masking and CRC32",
        "Checkerboard-phase modules with bit-reversal transform and CRC32",
        "Checkerboard-phase modules with even/odd interleaving and CRC32",
        "Checkerboard-phase modules with Hamming single-bit correction and CRC32",
        "Checkerboard-phase modules with Reed-Solomon correction and CRC32",
        "Checkerboard-phase modules with block parity and CRC32",
        "Checkerboard-phase modules with differential XOR chaining and CRC32",
    ))},
    **{f"h{i}": Standard(f"H{i}", f"Hexa {i}", "implemented", _desc) for i, _desc in zip(range(1, 11), (
        "Hexagonal-outline modules with byte-wise triple repetition and CRC32",
        "Hexagonal-outline modules with bit-wise triple repetition and CRC32",
        "Hexagonal-outline modules with byte-wise fivefold repetition and CRC32",
        "Hexagonal-outline modules with code-specific masking and CRC32",
        "Hexagonal-outline modules with bit-reversal transform and CRC32",
        "Hexagonal-outline modules with even/odd interleaving and CRC32",
        "Hexagonal-outline modules with Hamming single-bit correction and CRC32",
        "Hexagonal-outline modules with Reed-Solomon correction and CRC32",
        "Hexagonal-outline modules with block parity and CRC32",
        "Hexagonal-outline modules with differential XOR chaining and CRC32",
    ))},
    **{f"t{i}": Standard(f"T{i}", f"Triangle {i}", "implemented", _desc) for i, _desc in zip(range(1, 11), (
        "Up/down triangle glyphs with byte-wise triple repetition and CRC32",
        "Up/down triangle glyphs with bit-wise triple repetition and CRC32",
        "Up/down triangle glyphs with byte-wise fivefold repetition and CRC32",
        "Up/down triangle glyphs with code-specific masking and CRC32",
        "Up/down triangle glyphs with bit-reversal transform and CRC32",
        "Up/down triangle glyphs with even/odd interleaving and CRC32",
        "Up/down triangle glyphs with Hamming single-bit correction and CRC32",
        "Up/down triangle glyphs with Reed-Solomon correction and CRC32",
        "Up/down triangle glyphs with block parity and CRC32",
        "Up/down triangle glyphs with differential XOR chaining and CRC32",
    ))},
    **{
        f"{tree}{i}": Standard(
            f"{tree.upper()}{i}", ("Resilient Compact" if tree == "r" and i == 1 else f"{tree_name} {i}"), "implemented",
            f"{visual}; {_METHOD_DESCRIPTIONS[method]}; " +
            ("single asymmetric finder identifies the format; length-prefix frame" if tree == "r" and i <= 5 else f"unique HR{tree.upper()}{i} wire marker and finder signature"),
        )
        for tree, (tree_name, visual) in ADDITIONAL_TREES.items()
        for i, method in enumerate(_ADDITIONAL_METHODS[tree], start=1)
    },
    "sl1": Standard("SL1", "Scan Lonely 1", "implemented", "Single row of equal-width vertical bars with data-bearing variable heights; CRC32 plus Reed-Solomon (32 parity symbols, correcting up to 16 byte-symbol errors per codeword)"),
    "e1": Standard("E1", "Elephant 1", "reserved", "Reserved for a future Elephant-family monochrome format"),
    "l1": Standard("L1", "Lion 1", "reserved", "Reserved for a future standard; visual and data format not yet selected"),
}

def normalize_standard(value: str | None) -> str | None:
    if value is None:
        return None
    code = value.lower().removesuffix("+")
    # OI and D1 are canonical spellings; oi2 is retained as a legacy alias.
    aliases = {"oi": "oi1", "oi1": "oi1", "oi2": "d1"}
    code = aliases.get(code, code)
    if code not in STANDARDS:
        raise ValueError(f"Unknown HushRaster standard {value!r}; choose one of: {', '.join(STANDARDS)}")
    return code


def standard_listing() -> str:
    lines = [
        "HushRaster standards:",
        "  Canonical selectors are lowercase and end in +, for example p2+ or d1+.",
        "  encode [STANDARD+] reads raw bytes from stdin and writes a PNG to stdout (default: p2).",
        "  decode [STANDARD+] reads PNG bytes from stdin and writes recovered raw bytes to stdout.",
        "  --ppm N controls pixels per module; the default is 4 and 1 is most compact.",
    ]
    order = ([f"p{i}" for i in range(1, 14)] + ["oi1"] + [f"d{i}" for i in range(1, 12)] +
             [f"ce{i}" for i in range(1, 12)] + [f"z{i}" for i in range(1, 12)] +
             [f"m{i}" for i in range(1, 11)] + [f"h{i}" for i in range(1, 11)] +
             [f"t{i}" for i in range(1, 11)] +
             [f"{tree}{i}" for tree in ADDITIONAL_TREES for i in range(1, 11)] + ["sl1", "e1", "l1"])
    for key in order:
        item = STANDARDS[key]
        selector = "oi+" if key == "oi1" else key + "+"
        lines.append(f"  {selector} — {item.code} ({item.name}) [{item.status}]: {item.description}")
    lines.extend([
        "  D1 (d1+) is the raw diagonal format. D2 (d2+) uses Reed-Solomon correction and CRC32.",
        "  P3 and D1 have no checksum or error correction; CE1 and Z1 detect corruption with CRC32.",
        "  M1–M10 use checkerboard-phase Mosaic cells; H1–H10 use hexagonal-outline cells; T1–T10 use up/down triangle glyphs.",
        "  200 additional standards span 20 trees: Arc (A), Braid (B), Facet (F), Grid (G), Iris (I), Junction (J), Keystone (K), Nexus (N), Quick (Q), Resilient (R), Spiral (S), Umbra (U), Vector (V), Weave (W), Cross (X), Asymmetric (Y), Adaptive Array (AA), Bridge (BR), Compact Payload (CP), and Staggered (ST).",
        "  R1 (r1+) uses one asymmetric finder and 32 Reed-Solomon parity symbols per block, protecting payload and CRC32; it can correct up to 16 unknown byte-symbol errors per block.",
        "  SL1 (sl1+) uses one row of equal-width vertical bars whose heights encode nibbles; it uses CRC32 and 32 Reed-Solomon parity symbols per codeword.",
        "  E1 and L1 remain reserved. imgmod is the legacy file-based OI overlay command.",
    ])
    return "\n".join(lines)
