#!/data/data/com.termux/files/usr/bin/bash
# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
ROOT="${1:-$HOME/Poopy/new2}"
OUT="${2:-/storage/emulated/0/Pictures/HushRaster-standards}"
mkdir -p "$OUT"
cd "$ROOT"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
printf 'HushRaster byte-exact test\000\377\n' > "$TMP/payload.bin"
standards=(p1 p2 p3 p4 p5 p6 p7 p8 p9 p10 p11 p12 p13 oi d1 d2 d3 d4 d5 d6 d7 d8 d9 d10 d11 ce1 ce2 ce3 ce4 ce5 ce6 ce7 ce8 ce9 ce10 ce11 z1 z2 z3 z4 z5 z6 z7 z8 z9 z10 z11 m1 m2 m3 m4 m5 m6 m7 m8 m9 m10 h1 h2 h3 h4 h5 h6 h7 h8 h9 h10 t1 t2 t3 t4 t5 t6 t7 t8 t9 t10 a1 b1 f1 g1 i1 j1 k1 n1 q1 r1 r2 r3 r4 r5 s1 u1 v1 w1 x1 y1 aa1 br1 cp1 st1)
for standard in "${standards[@]}"; do
  echo "Testing $standard..."
  python3 -m hushraster encode "$standard+" --ppm 1 < "$TMP/payload.bin" > "$TMP/$standard.png"
  python3 -m hushraster decode "$standard+" < "$TMP/$standard.png" > "$TMP/$standard.out"
  cmp "$TMP/payload.bin" "$TMP/$standard.out"
  cp "$TMP/$standard.png" "$OUT/$standard.png"
  echo "  PASS: $standard round-trip; $(wc -c < "$TMP/$standard.png") PNG bytes"
done
for standard in e1 l1; do
  if python3 -m hushraster encode "$standard+" < "$TMP/payload.bin" > "$TMP/$standard.png" 2>"$TMP/$standard.err"; then
    echo "FAIL: reserved $standard unexpectedly encoded" >&2; exit 1
  fi
  echo "  PASS: $standard reports reserved/unimplemented"
done
# Exact stdin/stdout shell examples; binary-safe compare includes NUL and 0xff.
printf 'o algo\n' | python3 -m hushraster encode > "$TMP/example.png"
python3 -m hushraster decode < "$TMP/example.png" > "$TMP/example.txt"
printf 'o algo\n' > "$TMP/expected.txt"
cmp "$TMP/expected.txt" "$TMP/example.txt"
cp "$TMP/example.png" "$OUT/stdin-stdout-example.png"
echo "All implemented standards passed. Images saved under: $OUT"
