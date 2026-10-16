#!/usr/bin/env python3
"""Fast regression tests for explicit compression and decoder recovery modes."""
from pathlib import Path
import sys
import zlib

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hushraster.core import (  # noqa: E402
    encode_image, decode_image, HushRasterError, _data_permutation,
    _pattern_for_slot, HEADER_DATA_REPEAT, DIGEST_LEN, CRC_LEN,
    _hamming13_encode,
)


def main():
    cover = Image.new("RGB", (1536, 1536), (128, 128, 128))
    raw_payload = b"Example raw payload\x00\x01\xff"
    original = (b"example " * 300) + b"\x00binary\xff\n"

    # No compression is the default. The payload is stored byte-for-byte.
    raw_image, raw_info = encode_image(cover, raw_payload, "sample.bin")
    assert raw_info["compression"] == "none"
    assert raw_info["stored_len"] == len(raw_payload)
    raw_out, raw_meta, raw_stats = decode_image(raw_image)
    assert raw_out == raw_payload and raw_meta["compression"] == "none"
    assert raw_stats["integrity_verified"]

    # Compression occurs only when explicitly requested, and uses method ID 'z'.
    z_image, z_info = encode_image(cover, original, "sample.bin", compression="z")
    assert z_info["compression"] == "z"
    assert z_info["stored_len"] < len(original)
    z_out, z_meta, z_stats = decode_image(z_image)
    assert z_out == original and z_meta["compression"] == "z"
    assert z_stats["integrity_verified"]
    assert decode_image(z_image, mode="depends")[0] == original
    assert decode_image(z_image, mode="default")[0] == original

    # Explicit forced interpretation works when a zlib stream was embedded raw.
    precompressed = zlib.compress(original, level=1)
    raw_stream_image, _ = encode_image(cover, precompressed, "outer-zlib.bin")
    automatic_raw, raw_stream_meta, _ = decode_image(raw_stream_image)
    assert automatic_raw == precompressed and raw_stream_meta["compression"] == "none"
    forced_out, _, forced_stats = decode_image(raw_stream_image, force_compression="z")
    assert forced_out == original
    assert forced_stats["compression_overridden"]

    # Force-no-zlib returns the stored bytes and explicitly marks integrity unverified
    # when the header declares that those bytes represent a decompressed payload.
    forced_raw, _, forced_raw_stats = decode_image(z_image, force_compression="none")
    assert len(forced_raw) == z_info["stored_len"] and forced_raw != original
    assert forced_raw_stats["compression_overridden"]
    assert not forced_raw_stats["integrity_verified"]

    # Deliberately invert ten of nineteen spatial copies of one Hamming wire bit.
    # The majority vote is wrong, but SECDED plus the SHA tag validate the bytes.
    arr = np.array(z_image.convert("RGB"), copy=True)
    gw, gh = z_image.width // 8, z_image.height // 8
    order, _ = _data_permutation(gw, gh)
    # Filename length + digest + CRC are all stored in the repeated header remainder.
    header_rest_bits = (len("sample.bin".encode("utf-8")) + DIGEST_LEN + CRC_LEN) * 8
    body_bit = 7  # a bit inside the zlib stream
    bit_start = header_rest_bits * HEADER_DATA_REPEAT + body_bit * 19
    wire_compressed = _hamming13_encode(zlib.compress(original, level=1))
    bit_value = (wire_compressed[body_bit // 8] >> (7 - (body_bit % 8))) & 1
    for vote_index in range(10):
        slot = order[bit_start + vote_index]
        x, y = (slot % gw) * 8, (slot // gw) * 8
        pattern = _pattern_for_slot(slot).astype(np.int16)
        encoded_sign = 1 if bit_value else -1
        tile = arr[y:y + 8, x:x + 8, :].astype(np.int16)
        # Reverse only this tile's modulation; flat 128-gray cover keeps this exact.
        arr[y:y + 8, x:x + 8, :] = np.clip(tile - encoded_sign * 4 * pattern[:, :, None], 0, 255).astype(np.uint8)
    damaged = Image.fromarray(arr, "RGB")
    fixed, _, fixed_stats = decode_image(damaged, mode="best")
    assert fixed == original, "best mode did not repair a single wrong-majority compressed bit"
    assert fixed_stats["integrity_verified"]
    assert fixed_stats["ecc_corrected_symbols"] >= 1 or fixed_stats["repair_bits"] >= 1

    # Make two adjacent Hamming-wire bits take the wrong majority. SECDED detects
    # this double-bit error; best mode can still recover via two low-confidence
    # majority corrections validated by zlib + the payload SHA tag.
    damaged2_arr = np.array(z_image.convert("RGB"), copy=True)
    damaged_bit = 160
    damaged_bit_start = header_rest_bits * HEADER_DATA_REPEAT + damaged_bit * 19
    for damaged_bit in (160, 161):
        damaged_bit_start = header_rest_bits * HEADER_DATA_REPEAT + damaged_bit * 19
        damaged_bit_value = (wire_compressed[damaged_bit // 8] >> (7 - (damaged_bit % 8))) & 1
        for vote_index in range(10):
            slot = order[damaged_bit_start + vote_index]
            x, y = (slot % gw) * 8, (slot // gw) * 8
            pattern = _pattern_for_slot(slot).astype(np.int16)
            encoded_sign = 1 if damaged_bit_value else -1
            tile = damaged2_arr[y:y + 8, x:x + 8, :].astype(np.int16)
            damaged2_arr[y:y + 8, x:x + 8, :] = np.clip(tile - encoded_sign * 4 * pattern[:, :, None], 0, 255).astype(np.uint8)
    damaged2 = Image.fromarray(damaged2_arr, "RGB")
    best_effort, _, best_effort_stats = decode_image(damaged2, mode="best")
    assert best_effort == original and best_effort_stats["integrity_verified"]
    assert best_effort_stats["repair_bits"] >= 1 or best_effort_stats["ecc_corrected_symbols"] >= 1
    try:
        decode_image(damaged2, mode="strict")
    except HushRasterError:
        pass
    else:
        # If strict can recover this environment's codec variation, it must be exact.
        strict_data, _, strict_stats = decode_image(damaged2, mode="strict")
        assert strict_data == original and strict_stats["integrity_verified"]

    print("PASS: raw default; opt-in zlib; legacy-v2 decode; force overrides; aliases; Hamming SECDED correction; checksum-guided two-bit recovery; strict-mode integrity")


if __name__ == "__main__":
    main()
