# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
"""HushRaster 1.0.1 high-redundancy barcode codec.

The embedding changes each RGB channel by no more than two integer levels.
It uses a differential pattern inside 8x8 blocks, repeated voting, and a
position-interleaved stream to tolerate common lossy re-encoding and some crops.
"""
from __future__ import annotations
import hashlib, math, struct, zlib
from itertools import combinations
from functools import lru_cache
from pathlib import Path
from PIL import Image

VERSION = "1.0.1"
MAGIC = b"HRS1"
# App version is independent of the on-wire revision; format revision 2 introduced
# explicit body-compression metadata and is intentionally incompatible with drafts.
FORMAT_VERSION = 3
SUPPORTED_FORMAT_VERSIONS = (3, 2)  # v2 retained only as a legacy decode path
COMPRESSION_NONE = 0
COMPRESSION_ZLIB = 1
COMPRESSION_NAMES = {COMPRESSION_NONE: "none", COMPRESSION_ZLIB: "z"}
REPEAT = 19
HEADER_DATA_REPEAT = 47
HEADER_REPEAT = 26
BLOCK = 8
PREFIX = struct.Struct(">4sBBIIHHB")  # magic, fmt version, compression id, stored len, raw len, grid w/h, filename length
DIGEST_LEN = 16
CRC_LEN = 4
MAX_NAME = 120
MAX_PIXELS = 40_000_000
PREFIX_REGION = 4096
PREFIX_SEED = 0x48525331  # fixed bootstrap permutation seed

class HushRasterError(Exception): pass

def read_image(path):
    try:
        with Image.open(path) as im:
            if im.width <= 0 or im.height <= 0:
                raise HushRasterError(f"Image has invalid dimensions: {im.width}x{im.height}")
            if im.width * im.height > MAX_PIXELS:
                raise HushRasterError(
                    f"Image dimensions {im.width}x{im.height} exceed the {MAX_PIXELS:,}-pixel safety limit. "
                    "Use a smaller image; this codec cannot decode carriers above that limit."
                )
            im.load()
            return im.convert("RGB")
    except Exception as e:
        raise HushRasterError(f"Cannot read image {path}: {e}") from e

def bits(data):
    for b in data:
        for shift in range(7,-1,-1): yield (b >> shift) & 1

def bits_to_bytes(values):
    out=bytearray(); acc=0; n=0
    for bit in values:
        acc=(acc<<1)|int(bit); n+=1
        if n==8: out.append(acc); acc=0; n=0
    if n: raise HushRasterError("Incomplete byte while decoding stream")
    return bytes(out)

# Format revision 3 uses an extended Hamming (13,8) SECDED code per stored
# body byte: eight data bits, four Hamming parity bits, and one overall parity
# bit. It corrects any single flipped bit per codeword and detects any double
# flipped bits. The payload SHA-256 tag still guards against multi-bit patterns
# that an SECDED code cannot uniquely repair.
_HAMMING_DATA_POSITIONS = (3, 5, 6, 7, 9, 10, 11, 12)
_HAMMING_PARITY_POSITIONS = (1, 2, 4, 8)


def _ecc_wire_bits(stored_len, format_version=FORMAT_VERSION):
    return stored_len * 13 if format_version >= 3 else stored_len * 8


def _ecc_wire_len(stored_len, format_version=FORMAT_VERSION):
    return (_ecc_wire_bits(stored_len, format_version) + 7) // 8


def _hamming13_encode(data):
    total_bits = len(data) * 13
    encoded = bytearray((total_bits + 7) // 8)
    bit_offset = 0
    for value in data:
        code = [0] * 13  # positions 1..13; position 13 is overall parity
        for bit_index, position in enumerate(_HAMMING_DATA_POSITIONS):
            code[position - 1] = (value >> (7 - bit_index)) & 1
        for parity_position in _HAMMING_PARITY_POSITIONS:
            parity = 0
            for position in range(1, 13):
                if position & parity_position:
                    parity ^= code[position - 1]
            code[parity_position - 1] = parity
        code[12] = sum(code[:12]) & 1
        for bit in code:
            if bit:
                encoded[bit_offset // 8] |= 1 << (7 - bit_offset % 8)
            bit_offset += 1
    return bytes(encoded)


def _hamming13_decode(wire_data, expected_length):
    expected_wire_length = _ecc_wire_len(expected_length, 3)
    if len(wire_data) != expected_wire_length:
        raise HushRasterError(
            f"Error-correction body length mismatch (expected {expected_wire_length}, got {len(wire_data)})"
        )
    needed_bits = expected_length * 13
    def get_bit(index):
        return (wire_data[index // 8] >> (7 - index % 8)) & 1
    recovered = bytearray()
    corrected_symbols = 0
    for offset in range(0, needed_bits, 13):
        code = [get_bit(offset + index) for index in range(13)]
        syndrome = 0
        for parity_position in _HAMMING_PARITY_POSITIONS:
            parity = 0
            for position in range(1, 13):
                if position & parity_position:
                    parity ^= code[position - 1]
            if parity:
                syndrome |= parity_position
        overall_parity = sum(code) & 1
        if syndrome and overall_parity:
            if syndrome > 12:
                raise HushRasterError("Hamming SECDED found an invalid single-bit syndrome")
            code[syndrome - 1] ^= 1
            corrected_symbols += 1
        elif syndrome and not overall_parity:
            raise HushRasterError("Hamming SECDED detected a double-bit error")
        elif not syndrome and overall_parity:
            code[12] ^= 1
            corrected_symbols += 1
        value = 0
        for position in _HAMMING_DATA_POSITIONS:
            value = (value << 1) | code[position - 1]
        recovered.append(value)
    return bytes(recovered), corrected_symbols


def _decode_wire_body(wire_data, stored_len, format_version):
    if format_version >= 3:
        return _hamming13_decode(wire_data, stored_len)
    if len(wire_data) != stored_len:
        raise HushRasterError("Legacy body length mismatch")
    return wire_data, 0


def stride_for(n):
    if n <= 1: return 1
    candidate = max(1, n//2 + 1)
    if candidate % 2 == 0: candidate += 1
    while math.gcd(candidate,n) != 1:
        candidate += 2
        if candidate >= n: candidate = 1
    return candidate

def _shuffle(values, seed):
    # The legacy revision-2 format specifies Fisher-Yates driven by xorshift32 so the slot
    # permutation is deterministic across Python versions and implementations.
    state=seed & 0xffffffff
    if state == 0: state=0xA341316C
    for i in range(len(values)-1,0,-1):
        state ^= (state << 13) & 0xffffffff
        state ^= state >> 17
        state ^= (state << 5) & 0xffffffff
        state &= 0xffffffff
        j=state % (i+1)
        values[i],values[j]=values[j],values[i]

@lru_cache(maxsize=4)
def _permutation(count, seed):
    order=list(range(count)); _shuffle(order,seed)
    inverse=[0]*count
    for logical,physical in enumerate(order): inverse[physical]=logical
    return tuple(order),tuple(inverse)

@lru_cache(maxsize=4)
def _prefix_permutation(version=FORMAT_VERSION):
    """Return logical-to-physical prefix slots and the inverse map.

    v2 used a pseudorandom shuffle. v3 spatially stratifies the 26 copies of
    each bootstrap bit over the whole 4096-tile region. This avoids the unlucky
    case where all copies of one header bit fall inside a crop. Unassigned v3
    slots are mapped after active logical entries so decoders skip them.
    """
    if version == 2:
        return _permutation(PREFIX_REGION, PREFIX_SEED)
    if version != 3:
        raise HushRasterError(f"Unsupported prefix layout revision: {version}")
    active = PREFIX.size * 8 * HEADER_REPEAT
    stride = PREFIX_REGION // HEADER_REPEAT
    order = [-1] * PREFIX_REGION
    occupied = set()
    for bit_index in range(PREFIX.size * 8):
        for copy_index in range(HEADER_REPEAT):
            logical = bit_index * HEADER_REPEAT + copy_index
            physical = copy_index * stride + bit_index
            if physical >= PREFIX_REGION or physical in occupied:
                raise HushRasterError("Internal error constructing balanced prefix layout")
            order[logical] = physical
            occupied.add(physical)
    remainder = (slot for slot in range(PREFIX_REGION) if slot not in occupied)
    for logical in range(active, PREFIX_REGION):
        order[logical] = next(remainder)
    inverse = [0] * PREFIX_REGION
    for logical, physical in enumerate(order):
        inverse[physical] = logical
    return tuple(order), tuple(inverse)

@lru_cache(maxsize=4)
def _data_permutation(gw, gh):
    total=gw*gh
    region_h=(PREFIX_REGION+gw-1)//gw
    center_y0=(gh-region_h)//2
    center_start=center_y0*gw
    center_end=center_start+PREFIX_REGION
    if center_start < PREFIX_REGION or center_end > total:
        raise HushRasterError("Image is too small for spatially duplicated headers")
    physical=[i for i in range(total) if not (i < PREFIX_REGION or center_start <= i < center_end)]
    seed=((gw*0x9E3779B1) ^ (gh*0x85EBCA77) ^ 0x48525331) & 0xffffffff
    _shuffle(physical,seed)
    inverse=[-1]*total
    for logical,slot in enumerate(physical): inverse[slot]=logical
    return tuple(physical),tuple(inverse)

def make_header(stored_payload, raw_payload, filename, gw, gh, compression):
    if not (1 <= gw <= 65535 and 1 <= gh <= 65535):
        raise HushRasterError('Carrier grid dimensions exceed the 16-bit format limit')
    if compression not in (COMPRESSION_NONE, COMPRESSION_ZLIB):
        raise HushRasterError(f"Unsupported compression method ID: {compression}")
    if len(stored_payload) > 0xffffffff or len(raw_payload) > 0xffffffff:
        raise HushRasterError('Payload exceeds the 4 GiB format limit')
    name = filename.encode('utf-8')
    if len(name) > MAX_NAME: raise HushRasterError(f"Filename metadata exceeds {MAX_NAME} UTF-8 bytes")
    prefix = PREFIX.pack(MAGIC, FORMAT_VERSION, compression, len(stored_payload), len(raw_payload), gw, gh, len(name))
    # The integrity tag covers the original, uncompressed payload.
    body = prefix + name + hashlib.sha256(raw_payload).digest()[:DIGEST_LEN]
    return body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)


def parse_header(raw):
    if len(raw) < PREFIX.size + DIGEST_LEN + CRC_LEN:
        raise HushRasterError("Incomplete header")
    prefix = raw[:PREFIX.size]
    magic, version, compression, stored_len, raw_len, gw, gh, name_len = PREFIX.unpack(prefix)
    if magic != MAGIC:
        raise HushRasterError("No HushRaster payload signature found")
    if version not in SUPPORTED_FORMAT_VERSIONS:
        raise HushRasterError(
            f"Unsupported format revision {version}; supported revisions: "
            + ", ".join(map(str, SUPPORTED_FORMAT_VERSIONS))
        )
    if compression not in COMPRESSION_NAMES:
        raise HushRasterError(f"Unsupported compression method ID {compression}")
    if not gw or not gh:
        raise HushRasterError("Invalid zero-sized carrier grid in header")
    if name_len > MAX_NAME:
        raise HushRasterError("Invalid filename length in header")
    if raw_len > MAX_DECODE_BYTES:
        raise HushRasterError(f"Decoded payload exceeds the {MAX_DECODE_BYTES:,}-byte safety limit")
    if compression == COMPRESSION_NONE and stored_len != raw_len:
        raise HushRasterError("Invalid raw-body length in header")
    if stored_len > MAX_DECODE_BYTES:
        raise HushRasterError(f"Stored payload exceeds the {MAX_DECODE_BYTES:,}-byte safety limit")
    header_len = PREFIX.size + name_len + DIGEST_LEN + CRC_LEN
    if len(raw) < header_len:
        raise HushRasterError("Incomplete header")
    body, crc = raw[:header_len-4], struct.unpack('>I', raw[header_len-4:header_len])[0]
    if zlib.crc32(body) & 0xffffffff != crc:
        raise HushRasterError("Header CRC failed")
    try:
        filename = raw[PREFIX.size:PREFIX.size+name_len].decode('utf-8')
    except UnicodeDecodeError as e:
        raise HushRasterError("Invalid filename encoding") from e
    digest = raw[PREFIX.size+name_len:PREFIX.size+name_len+DIGEST_LEN]
    return {'stored_len': stored_len, 'raw_len': raw_len,
            'format_version': version,
            'compression_id': compression, 'compression': COMPRESSION_NAMES[compression],
            'grid_w': gw, 'grid_h': gh, 'filename': filename, 'digest': digest,
            'header_len': header_len, 'raw': raw[:header_len]}

def parse_header_from_votes(prefix, decoded_bits, votes, header_rest_bits, max_flips=4, candidate_pool=24):
    """Parse the repeated header; use its CRC to repair a few weak-vote bits.

    The CRC is not encryption or authentication. It is useful as a decoding
    oracle: if a handful of repeated header bits narrowly lost their majority,
    test the least-confident votes first and accept only a CRC-valid header.
    """
    base_bits = list(decoded_bits[:header_rest_bits])
    if header_rest_bits % 8:
        raise HushRasterError("Internal header bit count is not byte-aligned")
    base_bytes = bits_to_bytes(base_bits)
    try:
        return parse_header(prefix + base_bytes), base_bits
    except HushRasterError as first_error:
        if "Header CRC failed" not in str(first_error):
            raise

    ranked = []
    for i in range(header_rest_bits):
        v = votes[i]
        if not v:
            continue
        # Lower normalized majority margin is a weaker bit decision. Prefer
        # fewer observed votes when margins are otherwise equal.
        margin = abs(2 * sum(v) - len(v)) / len(v)
        ranked.append((margin, len(v), i))
    ranked.sort(key=lambda item: (item[0], item[1]))
    candidate_positions = [item[2] for item in ranked[:candidate_pool]]
    for flip_count in range(1, min(max_flips, len(candidate_positions)) + 1):
        for positions in combinations(candidate_positions, flip_count):
            candidate_bits = base_bits.copy()
            for pos in positions:
                candidate_bits[pos] ^= 1
            try:
                parsed = parse_header(prefix + bits_to_bytes(candidate_bits))
            except HushRasterError:
                continue
            return parsed, candidate_bits
    raise HushRasterError(
        "Hidden header CRC failed after recovery attempts; compression, cropping, "
        "or image texture may have corrupted too many header votes."
    )

@lru_cache(maxsize=1)
def _patterns():
    import numpy as np
    return (
        np.tile(np.array([1,1,1,1,-1,-1,-1,-1],dtype=np.int16),(8,1)),
        np.tile(np.array([1]*4+[-1]*4,dtype=np.int16)[:,None],(1,8)),
        np.array([[1 if (x<4)==(y<4) else -1 for x in range(8)] for y in range(8)],dtype=np.int16),
        np.array([[1 if x+y < 7 else -1 for x in range(8)] for y in range(8)],dtype=np.int16),
    )

@lru_cache(maxsize=8192)
def _pattern_for_slot(slot):
    # Stable 32-bit mixer gives each tile a pseudo-random low-frequency pattern
    # and polarity, avoiding systematic correlation with sky/landscape gradients.
    v=slot & 0xffffffff
    v ^= v >> 16; v=(v*0x7feb352d)&0xffffffff
    v ^= v >> 15; v=(v*0x846ca68b)&0xffffffff
    v ^= v >> 16
    polarity=1 if (v & 1) else -1
    return _patterns()[(v >> 1) % 4] * polarity

def _modulate_tile(arr, x, y, bit, slot):
    # Four low-frequency, zero-mean patterns reduce correlation with natural edges.
    # Every RGB channel changes by at most two integer levels.
    import numpy as np
    pat=_pattern_for_slot(slot)
    sign=1 if bit else -1
    tile=arr[y:y+8,x:x+8,:].astype('int16')
    arr[y:y+8,x:x+8,:]=np.clip(tile + sign*2*pat[:,:,None],0,255).astype('uint8')

def _read_tile_bit(arr, x, y, slot):
    pat=_pattern_for_slot(slot)
    tile=arr[y:y+8,x:x+8,:].astype('float32')
    score=((tile-127.5)*pat[:,:,None]).sum()
    return 1 if score > 0 else 0

def _tile_values(image, xoff=0, yoff=0):
    import numpy as np
    arr=np.asarray(image.convert('RGB'))
    gw=max(0,(image.width-xoff)//8); gh=max(0,(image.height-yoff)//8)
    for y in range(gh):
        for x in range(gw): yield (x,y,_read_tile_bit(arr,xoff+x*8,yoff+y*8,y*gw+x))

def required_tiles(stored_len, filename, format_version=FORMAT_VERSION):
    name_len=len(filename.encode('utf-8'))
    header_len=PREFIX.size+name_len+DIGEST_LEN+CRC_LEN
    header_rest_bits=(header_len-PREFIX.size)*8
    payload_bits=_ecc_wire_len(stored_len, format_version)*8
    rest_tiles=header_rest_bits*HEADER_DATA_REPEAT + payload_bits*REPEAT
    return 2*PREFIX_REGION+rest_tiles

def _ensure_capacity(image, needed, resize, max_pixels):
    # The decoder has a hard image-size limit. Apply it before allocating an
    # enlarged image or embedding anything, including when the cover already
    # has enough blocks and therefore would not enter the resize branch.
    hard_limit = MAX_PIXELS
    requested_limit = hard_limit if not max_pixels else min(int(max_pixels), hard_limit)
    used_pixels = image.width * image.height
    if used_pixels > requested_limit:
        raise HushRasterError(
            f"Input cover {image.width}x{image.height} ({used_pixels:,} pixels) exceeds the "
            f"effective {requested_limit:,}-pixel limit; use a smaller cover."
        )
    gw=image.width//8; gh=image.height//8
    if gw*gh >= needed: return image, False
    if not resize: raise HushRasterError(f"Image capacity too small: need {needed:,} 8x8 blocks, have {gw*gh:,}. Use --resize or a larger image.")
    # Grow by the square root of the needed ratio, preserving aspect ratio.
    scale=math.sqrt(needed/max(1,gw*gh))*1.015
    w=max(8, math.ceil(image.width*scale/8)*8); h=max(8, math.ceil(image.height*scale/8)*8)
    while (w//8)*(h//8) < needed:
        if w/image.width <= h/image.height: w += 8
        else: h += 8
    if w*h > requested_limit:
        raise HushRasterError(
            f"Auto-resize needs {w}x{h} ({w*h:,} pixels), over the effective {requested_limit:,}-pixel limit"
        )
    return image.resize((w,h), Image.Resampling.LANCZOS), True

def encode_image(image, payload, filename, resize=False, max_pixels=MAX_PIXELS, compression="none", verify=True):
    """Legacy IMGMod encoder. New releases never create compressed payloads."""
    import numpy as np
    if image.width <= 0 or image.height <= 0:
        raise HushRasterError("Carrier image has invalid zero-sized dimensions")
    if image.width * image.height > MAX_PIXELS:
        raise HushRasterError(
            f"Input cover {image.width}x{image.height} exceeds the {MAX_PIXELS:,}-pixel codec safety limit."
        )
    if compression != "none":
        raise HushRasterError("Payload compression is no longer supported; pass compression='none'")
    if len(payload) > 0xffffffff: raise HushRasterError("Payload exceeds the 4 GiB format limit")
    if len(payload) > MAX_DECODE_BYTES:
        raise HushRasterError(f"Payload exceeds the {MAX_DECODE_BYTES:,}-byte decoded-size safety limit")
    stored_payload = payload
    compression_id = COMPRESSION_NONE
    if len(stored_payload) > 0xffffffff: raise HushRasterError("Stored payload exceeds the 4 GiB format limit")
    # Round dimensions to block boundaries without changing image content except for edge padding.
    w=max(8,(image.width//8)*8); h=max(8,(image.height//8)*8)
    if (w,h) != image.size: image=image.crop((0,0,w,h))
    needed=required_tiles(len(stored_payload), filename, FORMAT_VERSION)
    image, resized=_ensure_capacity(image,needed,resize,max_pixels)
    # Do not allocate the ECC-expanded body until capacity has been validated;
    # huge requests should fail on the pixel cap without a huge temporary buffer.
    wire_payload = _hamming13_encode(stored_payload) if FORMAT_VERSION >= 3 else stored_payload
    if len(wire_payload) != _ecc_wire_len(len(stored_payload), FORMAT_VERSION):
        raise HushRasterError("Internal error: error-correction wire length mismatch")
    w,h=image.size; gw=w//8; gh=h//8
    header=make_header(stored_payload,payload,filename,gw,gh,compression_id)
    stream=header+stored_payload
    prefix=stream[:PREFIX.size]
    arr=np.array(image.convert('RGB'),copy=True)
    total=gw*gh
    region_h=(PREFIX_REGION+gw-1)//gw; center_y0=(gh-region_h)//2; center_start=center_y0*gw
    center_end=center_start+PREFIX_REGION
    avail=total-2*PREFIX_REGION
    header_rest_bits=(len(header)-PREFIX.size)*8
    body_bits=len(wire_payload)*8
    rest_slots=header_rest_bits*HEADER_DATA_REPEAT + body_bits*REPEAT
    if center_start < PREFIX_REGION or center_end > total or rest_slots > avail:
        raise HushRasterError("Internal capacity calculation mismatch")
    # Bootstrap prefix duplicated at top-left and center, for crop resilience.
    prefix_bits=list(bits(prefix)); prefix_order,_=_prefix_permutation(FORMAT_VERSION)
    for i,b in enumerate(prefix_bits):
        for c in range(HEADER_REPEAT):
            logical=i*HEADER_REPEAT+c; local_slot=prefix_order[logical]
            x=local_slot%gw; y=local_slot//gw
            _modulate_tile(arr,x*8,y*8,b,local_slot)
            center_slot=center_start+local_slot
            cx=center_slot%gw; cy=center_slot//gw
            _modulate_tile(arr,cx*8,cy*8,b,local_slot)
    data_order,_=_data_permutation(gw,gh)
    header_rest=list(bits(header[PREFIX.size:]))
    payload_stream=list(bits(wire_payload))
    for i,b in enumerate(header_rest):
        for c in range(HEADER_DATA_REPEAT):
            logical=i*HEADER_DATA_REPEAT+c; slot=data_order[logical]
            x=slot%gw; y=slot//gw
            _modulate_tile(arr,x*8,y*8,b,slot)
    payload_base=len(header_rest)*HEADER_DATA_REPEAT
    for i,b in enumerate(payload_stream):
        for c in range(REPEAT):
            logical=payload_base+i*REPEAT+c; slot=data_order[logical]
            x=slot%gw; y=slot//gw
            _modulate_tile(arr,x*8,y*8,b,slot)
    encoded_image = Image.fromarray(arr, 'RGB')
    # Fail closed by default: never report a successful encoding unless this
    # exact in-memory PNG pixel array can be decoded in strict, checksum-verified
    # mode. This catches carrier-texture interference before a file is written.
    if verify:
        try:
            recovered, _verify_header, verify_stats = decode_image(encoded_image, mode="strict")
        except HushRasterError as exc:
            raise HushRasterError(
                "Encoder self-check failed: the generated image could not be "
                "decoded in strict mode. The output has NOT been accepted as "
                "safe to use; try a different cover image or a larger resize. "
                f"Underlying decoder error: {exc}"
            ) from exc
        if recovered != payload or not verify_stats.get("integrity_verified"):
            raise HushRasterError(
                "Encoder self-check failed: decoded bytes did not exactly match "
                "the input payload and its integrity tag. The output has NOT "
                "been accepted as safe to use."
            )
    return encoded_image, {
        'resized':resized,'grid_w':gw,'grid_h':gh,'header_len':len(header),
        'required_tiles':needed,'total_tiles':total,'compression':compression,
        'raw_len':len(payload),'stored_len':len(stored_payload),
        'wire_body_len':len(wire_payload),
        'error_correction': 'Hamming(13,8) SECDED' if FORMAT_VERSION >= 3 else 'none (legacy)',
        'compression_ratio': (len(stored_payload)/len(payload)) if payload else 1.0,
    }

def _decode_prefix_for_width(image, original_gw, xoff=0, yoff=0, arr=None):
    import numpy as np
    if arr is None:
        arr=np.asarray(image.convert('RGB'))
    cw=(image.width-xoff)//8; ch=(image.height-yoff)//8
    max_rows=min(ch, (PREFIX_REGION + original_gw - 1)//original_gw)
    active_bits=PREFIX.size*8
    for layout_version in SUPPORTED_FORMAT_VERSIONS:
        votes=[[] for _ in range(active_bits)]
        _,prefix_inverse=_prefix_permutation(layout_version)
        for y in range(max_rows):
            xlimit=min(cw, max(0, PREFIX_REGION-y*original_gw))
            for x in range(xlimit):
                slot=y*original_gw+x
                logical=prefix_inverse[slot]
                if logical < 0 or logical >= active_bits*HEADER_REPEAT:
                    continue
                bit=_read_tile_bit(arr,xoff+x*8,yoff+y*8,slot)
                votes[logical//HEADER_REPEAT].append(bit)
        if any(not v for v in votes):
            continue
        prefix_bits=[1 if sum(v)>len(v)/2 else 0 for v in votes]
        try:
            prefix=bits_to_bytes(prefix_bits)
            magic,version,compression,stored_len,raw_len,gw,gh,name_len=PREFIX.unpack(prefix)
        except (HushRasterError, struct.error):
            continue
        if (magic != MAGIC or version != layout_version or version not in SUPPORTED_FORMAT_VERSIONS
                or compression not in COMPRESSION_NAMES or gw != original_gw
                or name_len > MAX_NAME or gh < 1):
            continue
        if compression == COMPRESSION_NONE and stored_len != raw_len:
            continue
        if raw_len > MAX_DECODE_BYTES or stored_len > MAX_DECODE_BYTES:
            continue
        if gw*gh > MAX_PIXELS//64:
            continue
        return {'stored_len':stored_len,'raw_len':raw_len,'compression_id':compression,
                'compression':COMPRESSION_NAMES[compression], 'format_version':version,
                'grid_w':gw,'grid_h':gh,'name_len':name_len,'prefix':prefix}
    return None

def _decode_combined_exact_prefix(image, original_gw, original_gh, arr=None):
    """Decode an un-cropped carrier by pooling both full bootstrap copies.

    A lossy encoder can make a few bit decisions wrong in each anchor, even
    when the combined evidence is sufficient.  Trying either anchor in
    isolation throws that evidence away, so this path pools their votes before
    considering expensive dimension/crop guesses.  The normal full-header CRC
    and payload digest still have to pass later; this is only a locator.
    """
    import numpy as np
    if image.width % 8 or image.height % 8:
        return None
    if original_gw * 8 != image.width or original_gh * 8 != image.height:
        return None
    region_h = (PREFIX_REGION + original_gw - 1) // original_gw
    center_y0 = (original_gh - region_h) // 2
    center_start = center_y0 * original_gw
    if center_start < PREFIX_REGION or center_start + PREFIX_REGION > original_gw * original_gh:
        return None
    if arr is None:
        arr = np.asarray(image.convert('RGB'))
    active_bits = PREFIX.size * 8
    for layout_version in SUPPORTED_FORMAT_VERSIONS:
        votes = [[] for _ in range(active_bits)]
        _, inverse = _prefix_permutation(layout_version)
        for local_slot in range(PREFIX_REGION):
            logical = inverse[local_slot]
            if logical >= active_bits * HEADER_REPEAT:
                continue
            # Same local prefix slot is duplicated at top-left and center.
            x = (local_slot % original_gw) * 8
            y = (local_slot // original_gw) * 8
            bit = _read_tile_bit(arr, x, y, local_slot)
            votes[logical // HEADER_REPEAT].append(bit)
            center_slot = center_start + local_slot
            cx = (center_slot % original_gw) * 8
            cy = (center_slot // original_gw) * 8
            bit = _read_tile_bit(arr, cx, cy, local_slot)
            votes[logical // HEADER_REPEAT].append(bit)
        if any(not v for v in votes):
            continue
        prefix = bits_to_bytes([1 if sum(v) > len(v) / 2 else 0 for v in votes])
        try:
            magic, version, compression, stored_len, raw_len, gw, gh, name_len = PREFIX.unpack(prefix)
        except struct.error:
            continue
        if (magic != MAGIC or version != layout_version or version not in SUPPORTED_FORMAT_VERSIONS
                or compression not in COMPRESSION_NAMES or gw != original_gw or gh != original_gh
                or name_len > MAX_NAME):
            continue
        if compression == COMPRESSION_NONE and stored_len != raw_len:
            continue
        if raw_len > MAX_DECODE_BYTES or stored_len > MAX_DECODE_BYTES or gw * gh > MAX_PIXELS // 64:
            continue
        return {'stored_len': stored_len, 'raw_len': raw_len,
                'compression_id': compression, 'compression': COMPRESSION_NAMES[compression],
                'format_version': version, 'grid_w': gw, 'grid_h': gh,
                'name_len': name_len, 'prefix': prefix,
                'xoff': 0, 'yoff': 0, 'x_tile0': 0, 'y_tile0': 0,
                'anchor': 'combined-exact (top-left+center)'}
    return None


def _decode_center_prefix(image, original_gw, original_gh, mode_x="center", mode_y="center", arr=None):
    import numpy as np
    if original_gw <= 0 or original_gh <= 0:
        return None
    region_h=(PREFIX_REGION+original_gw-1)//original_gw
    center_y0=(original_gh-region_h)//2
    center_start=center_y0*original_gw
    # A valid encoder never permits its two bootstrap regions to overlap or
    # extend outside the carrier. Reject impossible guessed dimensions before
    # sampling thousands of tiles (especially on tiny/no-header images).
    if center_start < PREFIX_REGION or center_start + PREFIX_REGION > original_gw * original_gh:
        return None
    delta_x=max(0,original_gw*8-image.width)
    delta_y=max(0,original_gh*8-image.height)
    left=0 if mode_x=="left" else (delta_x if mode_x=="right" else delta_x//2)
    top=0 if mode_y=="top" else (delta_y if mode_y=="bottom" else delta_y//2)
    xoff=(8-left%8)%8; yoff=(8-top%8)%8
    x_tile0=(left+xoff)//8; y_tile0=(top+yoff)//8
    cw=(image.width-xoff)//8; ch=(image.height-yoff)//8
    local_y_start=max(0,center_y0-y_tile0)
    local_y_end=min(ch,center_y0+region_h-y_tile0)
    local_x_start=max(0,-x_tile0); local_x_end=min(cw,original_gw-x_tile0)
    if arr is None:
        arr=np.asarray(image.convert('RGB'))
    for layout_version in SUPPORTED_FORMAT_VERSIONS:
        votes=[[] for _ in range(PREFIX.size*8)]
        _,prefix_inverse=_prefix_permutation(layout_version)
        for y in range(local_y_start,local_y_end):
            for x in range(local_x_start,local_x_end):
                local_x=x+x_tile0; local_y=y+y_tile0-center_y0
                local_slot=local_y*original_gw+local_x
                if local_slot < 0 or local_slot >= PREFIX_REGION:
                    continue
                logical=prefix_inverse[local_slot]
                if logical < 0 or logical >= PREFIX.size*8*HEADER_REPEAT:
                    continue
                bit=_read_tile_bit(arr,xoff+x*8,yoff+y*8,local_slot)
                votes[logical//HEADER_REPEAT].append(bit)
        # Cropping can erase some replicas. An empty bit is unrecoverable, but
        # having fewer than all 26 replicas is explicitly expected in v3.
        if any(not v for v in votes):
            continue
        prefix=bits_to_bytes([1 if sum(v)>len(v)/2 else 0 for v in votes])
        try:
            magic,version,compression,stored_len,raw_len,gw,gh,name_len=PREFIX.unpack(prefix)
        except struct.error:
            continue
        if (magic!=MAGIC or version!=layout_version or version not in SUPPORTED_FORMAT_VERSIONS
                or compression not in COMPRESSION_NAMES or gw!=original_gw or gh!=original_gh
                or name_len>MAX_NAME):
            continue
        if compression == COMPRESSION_NONE and stored_len != raw_len:
            continue
        if raw_len > MAX_DECODE_BYTES or stored_len > MAX_DECODE_BYTES or gw*gh > MAX_PIXELS//64:
            continue
        return {'stored_len':stored_len,'raw_len':raw_len,'compression_id':compression,
                'compression':COMPRESSION_NAMES[compression], 'format_version':version,
                'grid_w':gw,'grid_h':gh,'name_len':name_len,'prefix':prefix,
                'xoff':xoff,'yoff':yoff,'x_tile0':x_tile0,'y_tile0':y_tile0,
                'anchor':f'center-copy ({mode_x}/{mode_y})'}
    return None


MAX_DECODE_BYTES = 256 * 1024 * 1024


def _inflate_zlib(data, expected_len, exact_length=True):
    """Inflate one complete zlib stream under explicit output-size limits."""
    if exact_length and expected_len > MAX_DECODE_BYTES:
        raise HushRasterError(
            f"Decoded size in header ({expected_len:,} bytes) exceeds the safety limit "
            f"({MAX_DECODE_BYTES:,}); raise MAX_DECODE_BYTES in core.py only if trusted."
        )
    obj = zlib.decompressobj()
    try:
        limit = min(MAX_DECODE_BYTES, expected_len + 1) if exact_length else MAX_DECODE_BYTES + 1
        output = obj.decompress(data, limit)
        if len(output) > MAX_DECODE_BYTES or (exact_length and len(output) > expected_len) or obj.unconsumed_tail:
            raise HushRasterError("zlib output exceeds the configured safety/length limit")
        if not obj.eof:
            raise HushRasterError("incomplete zlib stream")
        if obj.unused_data:
            raise HushRasterError("unexpected bytes after the zlib stream")
        extra = obj.flush()
        output += extra
    except zlib.error as e:
        raise HushRasterError(f"zlib decompression failed: {e}") from e
    if len(output) > MAX_DECODE_BYTES or (exact_length and len(output) != expected_len):
        raise HushRasterError(
            f"zlib output length mismatch (header says {expected_len:,}, got {len(output):,})"
        )
    return output


def _try_body_bit_repair(body_bits, body_votes, mode, valid_candidate):
    """Try flipping low-confidence voted bits; accept only candidate passing validator."""
    if mode not in ("best", "reconstruct"):
        return None
    pool_size, max_flips = (16, 2) if mode == "best" else (20, 3)
    ranked=[]
    for i, vv in enumerate(body_votes):
        if not vv:
            continue
        margin=abs(2*sum(vv)-len(vv))/len(vv)
        ranked.append((margin, len(vv), i))
    ranked.sort(key=lambda x:(x[0],x[1]))
    positions=[x[2] for x in ranked[:pool_size]]
    original = list(body_bits)
    # Try fewest changed decisions first. Compression checksum + stored SHA tag
    # act as validation oracles; no filetype heuristics are used.
    for n in range(1, min(max_flips, len(positions))+1):
        for changes in combinations(positions,n):
            candidate=original.copy()
            for i in changes:
                candidate[i] ^= 1
            try:
                result=valid_candidate(bits_to_bytes(candidate))
            except (HushRasterError, ValueError, zlib.error):
                continue
            if result is not None:
                return result, n
    return None


def _salvage_zlib_prefix(data, max_output):
    """Recover the longest safely-decompressed prefix when a zlib stream is damaged."""
    if max_output <= 0 or max_output > MAX_DECODE_BYTES:
        max_output = min(MAX_DECODE_BYTES, max(0, max_output))
    obj=zlib.decompressobj()
    out=bytearray()
    for index in range(len(data)):
        try:
            piece=obj.decompress(data[index:index+1], max_output-len(out)+1)
            out.extend(piece)
            if len(out) > max_output:
                return bytes(out[:max_output])
        except zlib.error:
            break
    return bytes(out)


def decode_image(image, max_search_width=8192, mode="best", force_compression=None):
    """Decode a carrier.

    Modes: best (adaptive), strict (verified output only), fast (top-left only,
    no body repair), and reconstruct (more candidate repairs + partial zlib salvage).
    force_compression is None, "z", or "none" and overrides the header method.
    """
    import numpy as np
    if image.width <= 0 or image.height <= 0:
        raise HushRasterError("Carrier image has invalid zero-sized dimensions")
    if image.width * image.height > MAX_PIXELS:
        raise HushRasterError(
            f"Carrier dimensions {image.width}x{image.height} exceed the {MAX_PIXELS:,}-pixel safety limit."
        )
    aliases={"depends":"best", "default":"best"}
    mode=aliases.get(mode,mode)
    if mode not in ("best","strict","fast","reconstruct"):
        raise HushRasterError(f"Unknown decode mode: {mode}")
    if force_compression not in (None,"z","none"):
        raise HushRasterError("force_compression must be None, 'z', or 'none'")
    # Convert the carrier only once. Header-location recovery may test dozens
    # of candidate grid widths; rebuilding a full RGB array for every candidate
    # made large/no-header images unnecessarily expensive.
    arr=np.asarray(image.convert('RGB'))
    cw=image.width//8; ch=image.height//8
    found=None
    # Exact-size anchors are much cheaper and more reliable than guessing a
    # crop/resize geometry. Try both independently, then pool their evidence,
    # before entering the expensive dimension search lattice.
    meta = _decode_prefix_for_width(image, cw, arr=arr) if cw > 0 else None
    if meta:
        found=(cw,meta,{'xoff':0,'yoff':0,'x_tile0':0,'y_tile0':0,'anchor':'top-left'})
    if not found and mode != "fast" and cw > 0 and ch > 0:
        try:
            center_meta = _decode_center_prefix(image, cw, ch, "center", "center", arr=arr)
        except HushRasterError:
            center_meta = None
        if center_meta:
            found=(cw,center_meta,{k:center_meta[k] for k in ('xoff','yoff','x_tile0','y_tile0','anchor')})
    if not found and mode != "fast" and cw > 0 and ch > 0:
        combined_meta = _decode_combined_exact_prefix(image, cw, ch, arr=arr)
        if combined_meta:
            found=(cw,combined_meta,{k:combined_meta[k] for k in ('xoff','yoff','x_tile0','y_tile0','anchor')})
    # Only try top-left prefix reads at guessed widths after all exact-size
    # anchors are exhausted. Re-running a 4096-tile scan for dozens of width
    # candidates before checking center geometry was a severe worst-case stall.
    if not found and mode != "fast" and cw < max_search_width:
        for gw in range(cw + 1, min(max_search_width, cw + max(32, cw // 4)) + 1):
            meta = _decode_prefix_for_width(image, gw, arr=arr)
            if meta:
                found=(gw,meta,{'xoff':0,'yoff':0,'x_tile0':0,'y_tile0':0,'anchor':'top-left'})
                break
    # Center-header search helps survive crops; fast deliberately skips it.
    if not found and mode != "fast" and cw > 0 and ch > 0:
        max_gw=min(max_search_width,cw+max(48,cw//4))
        max_gh=min(8192,ch+max(48,ch//4))
        centered=[]; horizontal=[]; vertical=[]
        for gw0 in range(cw,max_gw+1):
            # Use the actual pixel aspect ratio rather than tile counts. Tile
            # counts lose up to one block at every cropped edge, which can make
            # the estimated original height miss by two or more blocks.
            estimate=max(ch,round(gw0*image.height/max(1,image.width)))
            for gh0 in range(max(ch,estimate-3),min(max_gh,estimate+3)+1):
                if gw0>cw and gh0>ch: centered.append((gw0,gh0))
            if gw0>cw: horizontal.append((gw0,ch))
        for gh0 in range(ch+1,max_gh+1): vertical.append((cw,gh0))
        def try_centered_pairs(pairs, modes):
            nonlocal found
            for gw0,gh0 in pairs:
                for mx,my in modes:
                    try: meta=_decode_center_prefix(image,gw0,gh0,mx,my,arr=arr)
                    except HushRasterError: continue
                    if meta:
                        found=(gw0,meta,{k:meta[k] for k in ('xoff','yoff','x_tile0','y_tile0','anchor')})
                        return
        if cw > ch:
            try_centered_pairs(vertical, [('left','top'),('left','center'),('left','bottom')])
        elif ch > cw:
            try_centered_pairs(horizontal, [('left','top'),('center','top'),('right','top')])
        # Center-copy geometry can be centered, left/top aligned, right/bottom
        # aligned, or mixed. The right/bottom case matters for a crop that
        # trims the original top-left corner but retains the carrier's far edges.
        center_modes = [
            ('center','center'), ('right','bottom'), ('left','top'),
            ('right','center'), ('left','center'), ('center','bottom'),
            ('center','top'), ('right','top'), ('left','bottom'),
        ]
        if not found:
            # Prioritize common proportional center-crop factors before the
            # exhaustive dimension lattice. A full 10%-per-edge center crop
            # loses 20% of each axis, so original dimensions are about 1.25x
            # the observed pixel dimensions; checking this first avoids hundreds
            # of needless 4096-tile scans on images that are readily recoverable.
            common_scales = (1.25, 1.20, 1.15, 1.1111111111, 1.10, 1.05,
                             1.3333333333, 1.50, 1.6666666667, 2.0)
            common_pairs=[]
            seen=set()
            for scale in common_scales:
                base_w=round(image.width*scale/8)
                base_h=round(image.height*scale/8)
                for dw,dh in ((0,0),(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1),(1,-1),(-1,1)):
                    pair=(base_w+dw,base_h+dh)
                    if (pair not in seen and cw < pair[0] <= max_gw
                            and ch < pair[1] <= max_gh):
                        common_pairs.append(pair); seen.add(pair)
            try_centered_pairs(common_pairs, center_modes)
        if not found:
            try_centered_pairs(centered, center_modes)
        if not found and cw > ch:
            try_centered_pairs(horizontal, [('left','top'),('center','top'),('right','top')])
        if not found and ch > cw:
            try_centered_pairs(vertical, [('left','top'),('left','center'),('left','bottom')])
    if not found:
        raise HushRasterError("Could not locate a valid HushRaster header. The crop may have removed both anchors, changed the image scale, or compression was too destructive.")
    gw,meta,loc=found; gh=meta['grid_h']; total=gw*gh
    if total > MAX_PIXELS//64: raise HushRasterError("Header dimensions exceed safety limit")
    _,data_inverse=_data_permutation(gw,gh)
    header_rest_bits=(meta['name_len']+DIGEST_LEN+CRC_LEN)*8
    wire_body_len=_ecc_wire_len(meta['stored_len'], meta.get('format_version', FORMAT_VERSION))
    body_bits_count=wire_body_len*8
    rest_bits=header_rest_bits+body_bits_count
    rest_slots=header_rest_bits*HEADER_DATA_REPEAT+body_bits_count*REPEAT
    if rest_slots > sum(1 for v in data_inverse if v >= 0):
        raise HushRasterError("Header payload length exceeds encoded carrier capacity")
    votes=[[] for _ in range(rest_bits)]
    xoff,yoff,x_tile0,y_tile0=loc['xoff'],loc['yoff'],loc['x_tile0'],loc['y_tile0']
    cw=(image.width-xoff)//8; ch=(image.height-yoff)//8
    header_slots=header_rest_bits*HEADER_DATA_REPEAT
    for y in range(ch):
        for x in range(cw):
            slot=(y+y_tile0)*gw+(x+x_tile0)
            if slot < 0 or slot >= total: continue
            logical=data_inverse[slot]
            if logical < 0 or logical >= rest_slots: continue
            bit=_read_tile_bit(arr,xoff+x*8,yoff+y*8,slot)
            if logical < header_slots:
                bit_index=logical//HEADER_DATA_REPEAT
            else:
                bit_index=header_rest_bits+(logical-header_slots)//REPEAT
            votes[bit_index].append(bit)
    decoded=[]
    for i,v in enumerate(votes):
        if not v: raise HushRasterError("Crop removed all copies of part of the payload")
        decoded.append(1 if sum(v)>len(v)/2 else 0)
    rest=bits_to_bytes(decoded)
    prefix=meta['prefix']
    header_len=PREFIX.size+meta['name_len']+DIGEST_LEN+CRC_LEN
    header_rest_bits=(header_len-PREFIX.size)*8
    full_header, corrected_header_bits = parse_header_from_votes(prefix, decoded, votes, header_rest_bits)
    corrected_header_rest=bits_to_bytes(corrected_header_bits)
    rest=corrected_header_rest+rest[len(corrected_header_rest):]
    offset=header_len-PREFIX.size
    stored_body_wire=rest[offset:offset+wire_body_len]
    if len(stored_body_wire)!=wire_body_len:
        raise HushRasterError("Stored body length mismatch")
    body_start=header_rest_bits
    body_bit_list=decoded[body_start:body_start+wire_body_len*8]
    body_vote_list=votes[body_start:body_start+wire_body_len*8]
    declared=full_header['compression']
    effective=force_compression if force_compression is not None else declared
    overridden=force_compression is not None and force_compression != declared
    expected_len=full_header['raw_len']
    digest=full_header['digest']
    format_version=full_header.get('format_version', 2)
    stats={'grid_w':gw,'grid_h':gh,'observed_tiles':cw*ch,'anchor':loc['anchor'],
           'format_version':format_version,
           'wire_body_len':wire_body_len,
           'mode':mode,'compression_declared':declared,'compression_used':effective,
           'compression_overridden':overridden,'integrity_verified':False,
           'reconstructed':False,'uncertain':False,'repair_bits':0,
           'ecc_corrected_symbols':0,
           'error_correction':'Hamming(13,8) SECDED' if format_version >= 3 else 'none (legacy)',
           'warning':None}

    def mark_verified(payload, repaired=0):
        stats['integrity_verified']=True
        stats['reconstructed']=bool(repaired)
        stats['repair_bits']=repaired
        if repaired:
            stats['recovery']='checksum-guided bit repair'
        return payload

    def raw_validator(data):
        try:
            body, _corrected = _decode_wire_body(data, full_header['stored_len'], format_version)
        except HushRasterError:
            return None
        if len(body)==expected_len and hashlib.sha256(body).digest()[:DIGEST_LEN]==digest:
            return body
        return None

    def zlib_validator(data):
        try:
            body, _corrected = _decode_wire_body(data, full_header['stored_len'], format_version)
            out=_inflate_zlib(body, expected_len)
        except HushRasterError:
            return None
        if hashlib.sha256(out).digest()[:DIGEST_LEN]==digest:
            return out
        return None

    try:
        stored_body, ecc_corrected = _decode_wire_body(
            stored_body_wire, full_header['stored_len'], format_version
        )
        stats['ecc_corrected_symbols'] = ecc_corrected
    except HushRasterError as ecc_error:
        if mode in ('best','reconstruct'):
            validator = raw_validator if effective == 'none' else zlib_validator
            repaired = _try_body_bit_repair(body_bit_list, body_vote_list, mode, validator)
            if repaired:
                result, n = repaired
                return mark_verified(result, n), full_header, stats
        raise HushRasterError(
            f"Body error-correction failed: {ecc_error}. No verified reconstruction was found."
        ) from ecc_error

    if effective == "none":
        payload=stored_body
        valid=raw_validator(stored_body_wire)
        if valid is not None:
            return mark_verified(valid),full_header,stats
        if overridden:
            stats['warning']="--force-no-zlib treated the stored body as raw; the header's original-payload integrity tag does not apply to this forced interpretation."
            return payload,full_header,stats
        if mode in ('best','reconstruct'):
            repaired=_try_body_bit_repair(body_bit_list, body_vote_list, mode, raw_validator)
            if repaired:
                result,n=repaired
                return mark_verified(result,n),full_header,stats
            stats['reconstructed']=True; stats['uncertain']=True
            stats['recovery']='majority-vote raw body'
            stats['warning']="The raw payload failed its integrity check. Returned the best majority-vote bytes, but they may be incorrect."
            return payload,full_header,stats
        raise HushRasterError("Payload SHA-256 verification failed; use --mode reconstruct for best-effort recovery")

    # Effective compression is zlib; the header is the only automatic guide.
    if not overridden and expected_len > MAX_DECODE_BYTES:
        raise HushRasterError(
            f"Decoded size in header ({expected_len:,} bytes) exceeds the safety limit "
            f"({MAX_DECODE_BYTES:,})"
        )
    inflated=None
    try:
        inflated=_inflate_zlib(stored_body, expected_len, exact_length=not overridden)
    except HushRasterError as inflate_error:
        if mode in ('best','reconstruct'):
            repaired=_try_body_bit_repair(body_bit_list, body_vote_list, mode, zlib_validator)
            if repaired:
                result,n=repaired
                return mark_verified(result,n),full_header,stats
        if overridden:
            raise HushRasterError(f"Forced zlib interpretation failed: {inflate_error}") from inflate_error
        if mode in ('best','reconstruct'):
            # Keep any definitely decompressed prefix; never pretend it is complete.
            limit=min(expected_len, MAX_DECODE_BYTES)
            partial=_salvage_zlib_prefix(stored_body,limit)
            if partial:
                stats['reconstructed']=True; stats['uncertain']=True
                stats['recovery']='partial zlib prefix salvage'
                if len(partial) < expected_len:
                    stats['warning']=(f"The compressed stream is damaged. Returned only a best-effort decompressed prefix "
                                      f"({len(partial):,} of {expected_len:,} expected bytes); content is incomplete and may be incorrect.")
                else:
                    stats['warning']=(f"The compressed stream is damaged. Decompression produced {len(partial):,} bytes, "
                                      "but stream/payload integrity could not be verified; the output may contain incorrect data.")
                return partial,full_header,stats
        raise HushRasterError(f"{inflate_error}; no checksum-verified reconstruction found") from inflate_error

    # zlib's own Adler-32 passed; the embedded SHA tag independently verifies the original payload.
    if len(inflated)==expected_len and hashlib.sha256(inflated).digest()[:DIGEST_LEN]==digest:
        stats['integrity_verified']=True
        if overridden:
            stats['warning']="The forced zlib interpretation worked, but it overrides the method declared in the header."
        return inflated,full_header,stats
    if overridden:
        stats['uncertain']=True
        stats['warning']="Forced zlib decompression succeeded, but the resulting length or SHA-256 tag does not match the header."
        return inflated,full_header,stats
    if mode in ('best','reconstruct'):
        repaired=_try_body_bit_repair(body_bit_list, body_vote_list, mode, zlib_validator)
        if repaired:
            result,n=repaired
            return mark_verified(result,n),full_header,stats
        stats['reconstructed']=True; stats['uncertain']=True
        stats['recovery']='zlib stream with integrity-tag mismatch'
        stats['warning']="zlib decompression succeeded, but the recovered bytes failed HushRaster's SHA-256 integrity check. Returned them as an uncertain reconstruction."
        return inflated,full_header,stats
    raise HushRasterError("Payload SHA-256 verification failed; use --mode reconstruct for best-effort recovery")

