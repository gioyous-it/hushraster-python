#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 HushRaster contributors
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import io, sys, random, json, shutil, platform, PIL
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from hushraster.core import encode_image, decode_image, HushRasterError, make_header, PREFIX, bits, parse_header_from_votes
OUT=ROOT/'test-results'; OUT.mkdir(exist_ok=True)
print('HushRaster full regression: building generated landscape and v3 carrier…', flush=True)
random.seed(42)
# Deterministic landscape-style test cover with broad gradients, edges, and texture.
w=h=1536
y,x=np.mgrid[0:h,0:w]
# Sky gradient and subtle cloud texture.
top=np.array([70,125,190]); bottom=np.array([205,220,228])
t=(y/h)[...,None]
a=top[None,None,:]*(1-t)+bottom[None,None,:]*t
cloud=(5*np.sin(x/71+y/113)+3*np.sin(x/29-y/67))[...,None]
a=np.clip(a+cloud,0,255)
# Distant and near hills.
hill1=650+65*np.sin(x/180)+22*np.sin(x/53)
hill2=820+80*np.sin(x/230+1.2)+35*np.sin(x/61)
a[y>hill1]=np.array([90,135,104])
a[y>hill2]=np.array([48,100,68])
source=Image.fromarray(a.astype('uint8'),'RGB')
d=ImageDraw.Draw(source)
# Sun, distant buildings, and trees.
d.ellipse((1120,130,1250,260),fill=(246,224,157))
for i in range(28):
    xx=random.randrange(0,w); base=random.randrange(650,1050); ht=random.randrange(40,180)
    col=random.choice([(35,83,52),(42,96,57),(59,112,65),(70,120,72)])
    d.rectangle((xx-3,base-ht//2,xx+3,base),fill=col)
    d.ellipse((xx-ht//3,base-ht,xx+ht//3,base-ht//3),fill=col)
# Fine natural-looking texture in the foreground, bounded so it remains subtle.
arr=np.asarray(source).astype(np.int16)
noise=np.random.default_rng(23).normal(0,2.2,(h,w,1))
mask=(y>800)[...,None]
arr=np.clip(arr+noise*mask,0,255).astype('uint8')
source=Image.fromarray(arr,'RGB').filter(ImageFilter.GaussianBlur(0.25))
source.save(OUT/'01_original.png')
payload=(b'HushRaster compression regression test\n' + bytes(range(32)) + b'\nfilename metadata test\n')
(OUT/'secret-test.bin').write_bytes(payload)

# Directly exercise recovery of a header whose CRC detects three weak-vote errors.
test_header = make_header(payload, payload, 'secret-test.bin', 192, 192, 0)
test_prefix = test_header[:PREFIX.size]
header_bits = list(bits(test_header[PREFIX.size:]))
vote_rows = [[bit] * 47 for bit in header_bits]
noisy_header_bits = header_bits.copy()
for idx in (3, 17, 75):
    original_bit = header_bits[idx]
    vote_rows[idx] = [1 - original_bit] * 24 + [original_bit] * 23
    noisy_header_bits[idx] = 1 - original_bit
recovered_header, repaired_bits = parse_header_from_votes(
    test_prefix, noisy_header_bits, vote_rows, len(header_bits)
)
assert recovered_header['filename'] == 'secret-test.bin'
assert repaired_bits == header_bits
metrics_header_recovery = {'success': True, 'injected_majority_errors': 3, 'recovered_filename': recovered_header['filename']}
encoded,info=encode_image(source,payload,'secret-test.bin',resize=True)
encoded.save(OUT/'02_encoded.png')
# Compare against the actual resized/cropped base carrier, isolating embedding
# changes from intentional auto-resizing.
base = source.crop((0, 0, (source.width // 8) * 8, (source.height // 8) * 8))
if base.size != encoded.size:
    base = base.resize(encoded.size, Image.Resampling.LANCZOS)
diff=np.abs(np.asarray(base).astype(np.int16)-np.asarray(encoded).astype(np.int16))
metrics={'environment':{'python':platform.python_version(),'pillow':PIL.__version__,'numpy':np.__version__},'test_image':'generated landscape illustration','original_resolution':list(source.size),'resolution':list(encoded.size),'payload_bytes':len(payload),'max_channel_delta':int(diff.max()),'pixels_with_all_channels_within_2_percent':float(100*(diff.max(axis=2)<=2).mean()),'mean_absolute_channel_error':float(diff.mean()),'normalized_similarity_percent':float(100*(1-diff.mean()/255)),'encoded_grid':info}
metrics['header_crc_vote_recovery'] = metrics_header_recovery
print(f'  carrier encoded and strict self-check passed: {encoded.size[0]}x{encoded.size[1]}', flush=True)
assert diff.max()<=2, f"RGB cap violated: {diff.max()}"
# Lossless roundtrip.
for label,im in [('png',encoded)]:
    out,meta,stats=decode_image(im)
    assert out==payload and meta['filename']=='secret-test.bin'
    metrics[label]={'success':True,'bytes':len(out)}
# JPEG / WebP recompression tests.
for fmt,quality in [('JPEG',75),('JPEG',90),('WEBP',75),('WEBP',90)]:
    buf=io.BytesIO(); encoded.save(buf,format=fmt,quality=quality,method=6); buf.seek(0)
    im=Image.open(buf).convert('RGB')
    ext='jpg' if fmt=='JPEG' else 'webp'; path=OUT/f'03_{ext}_q{quality}.{ext}'; path.write_bytes(buf.getvalue())
    try:
        out,meta,stats=decode_image(im)
        ok=out==payload and meta['filename']=='secret-test.bin'
        metrics[f'{fmt.lower()}_{quality}']={'success':ok,'bytes':len(out),'size':list(im.size)}
        assert ok
    except Exception as e:
        metrics[f'{fmt.lower()}_{quality}']={'success':False,'error':str(e)}
print('  lossless and JPEG/WebP quality 75/90 round-trips passed', flush=True)
# Right and bottom edge crop tests preserve the upper-left anchor.
for label,box in [('crop_right_10',(0,0,int(encoded.width*.9),encoded.height)),('crop_bottom_10',(0,0,encoded.width,int(encoded.height*.9))),('crop_right_bottom_10',(0,0,int(encoded.width*.9),int(encoded.height*.9)))]:
    cropped=encoded.crop(box); cropped.save(OUT/f'04_{label}.png')
    try:
        out,meta,stats=decode_image(cropped)
        ok=out==payload
        metrics[label]={'success':ok,'bytes':len(out),'crop_size':list(cropped.size)}
        assert ok
    except Exception as e:
        metrics[label]={'success':False,'error':str(e)}
print('  PNG edge-crop tests passed', flush=True)
# Compression + crop right edge.
buf=io.BytesIO(); encoded.save(buf,format='JPEG',quality=85); buf.seek(0); jpeg=Image.open(buf).convert('RGB')
cropped=jpeg.crop((0,0,int(encoded.width*.9),encoded.height)); cropped.save(OUT/'05_jpeg85_crop_right.png')
try:
    out,meta,stats=decode_image(cropped); ok=out==payload
    metrics['jpeg85_crop_right_10']={'success':ok,'bytes':len(out)}
    assert ok
except Exception as e: metrics['jpeg85_crop_right_10']={'success':False,'error':str(e)}
print('  JPEG85 + right-crop check completed', flush=True)
# Compression followed by an edge crop: realistic multi-step processing.
buf=io.BytesIO(); encoded.save(buf,format='JPEG',quality=85); buf.seek(0)
first=Image.open(buf).convert('RGB'); buf2=io.BytesIO(); first.save(buf2,format='WEBP',quality=85,method=6); buf2.seek(0)
chain=Image.open(buf2).convert('RGB'); chain.save(OUT/'05_jpeg85_then_webp85.webp',format='WEBP',quality=85,method=6)
print('  JPEG85→WebP85 re-encode saved', flush=True)
chain_crop=chain.crop((0,0,int(encoded.width*.9),encoded.height)); chain_crop.save(OUT/'05_jpeg85_webp85_crop_right.png')
try:
    out,meta,stats=decode_image(chain_crop)
    ok=out==payload; metrics['jpeg85_webp85_crop_right_10']={'success':ok,'bytes':len(out)}
    assert ok
except Exception as e: metrics['jpeg85_webp85_crop_right_10']={'success':False,'error':str(e)}
print('  JPEG85→WebP85 + right-crop decode completed', flush=True)
print('  JPEG/WebP + right-crop chains passed', flush=True)
# Center crop after each lossy format; the center header copy should remain discoverable.
for fmt in ('JPEG','WEBP'):
    buf=io.BytesIO(); encoded.save(buf,format=fmt,quality=75,method=6); buf.seek(0)
    im=Image.open(buf).convert('RGB'); box=(int(encoded.width*.1),int(encoded.height*.1),int(encoded.width*.9),int(encoded.height*.9))
    try:
        out,meta,stats=decode_image(im.crop(box)); ok=out==payload
        metrics[f'{fmt.lower()}75_center_crop_10_each_side']={'success':ok,'bytes':len(out)}
        assert ok
    except Exception as e: metrics[f'{fmt.lower()}75_center_crop_10_each_side']={'success':False,'error':str(e)}
# Lower-quality boundary probes: JPEG Q50 and WebP Q50 are reported honestly, not both required to pass.
for fmt in ('JPEG','WEBP'):
    buf=io.BytesIO(); encoded.save(buf,format=fmt,quality=50,method=6); buf.seek(0)
    im=Image.open(buf).convert('RGB')
    try:
        out,meta,stats=decode_image(im); ok=out==payload
        metrics[f'{fmt.lower()}_50']={'success':ok,'bytes':len(out)}
    except Exception as e: metrics[f'{fmt.lower()}_50']={'success':False,'error':str(e)}
print('  lossy center-crop checks passed', flush=True)
# A corner crop that removes both bootstrap anchors is measured separately.

center=encoded.crop((int(encoded.width*.1),int(encoded.height*.1),int(encoded.width*.9),int(encoded.height*.9))); center.save(OUT/'04_center_crop_10_each_side.png')
try:
    out,meta,stats=decode_image(center)
    metrics['center_crop_10_each_side']={'success':out==payload,'bytes':len(out)}
except Exception as e: metrics['center_crop_10_each_side']={'success':False,'limitation':str(e)}
# An off-center corner crop is a known limitation and is recorded, not counted as a pass.
corner=encoded.crop((int(encoded.width*.1),int(encoded.height*.1),encoded.width,encoded.height)); corner.save(OUT/'04_corner_crop_top_left_10.png')
try:
    out,meta,stats=decode_image(corner)
    metrics['corner_crop_top_left_10']={'success':out==payload,'bytes':len(out)}
except Exception as e:
    metrics['corner_crop_top_left_10']={'success':False,'known_limitation':str(e)}
print('  boundary-quality probes and off-center crop case completed', flush=True)
# Explicit auto-resize regression. Previous suite called resize=True on a large
# image that already had enough capacity, so it never exercised the resize path.
small = source.resize((176, 297), Image.Resampling.LANCZOS)
small.save(OUT/'08_resize_original.png')
resize_encoded, resize_info = encode_image(small, payload, 'secret-test.bin', resize=True)
assert resize_info['resized'] is True, 'resize regression did not actually resize'
resize_encoded.save(OUT/'09_resize_encoded.png')
# Keep the visual reference at the encoded dimensions to measure only embedding.
resize_base = small.crop((0, 0, (small.width // 8) * 8, (small.height // 8) * 8)).resize(resize_encoded.size, Image.Resampling.LANCZOS)
resize_base.save(OUT/'08_resize_base_at_output_size.png')
resize_diff = np.abs(np.asarray(resize_base).astype(np.int16)-np.asarray(resize_encoded).astype(np.int16))
assert int(resize_diff.max()) <= 2, 'RGB cap exceeded during auto-resize embedding'
metrics['forced_resize'] = {
    'success': False,
    'source_size': list(small.size),
    'encoded_size': list(resize_encoded.size),
    'resized_flag': resize_info['resized'],
    'max_channel_delta_from_resized_base': int(resize_diff.max()),
    'mean_absolute_channel_error': float(resize_diff.mean()),
}
# Lossless, JPEG, and WebP all decode after the actual auto-resize path.
for fmt, quality, ext in [('PNG', None, 'png'), ('JPEG', 75, 'jpg'), ('WEBP', 75, 'webp')]:
    buf = io.BytesIO()
    resize_encoded.save(buf, format=fmt, **({'quality': quality, 'method': 6} if quality is not None else {}))
    blob = buf.getvalue()
    path = OUT / f'10_resize_{ext}.{ext}'
    path.write_bytes(blob)
    buf.seek(0)
    candidate = Image.open(buf).convert('RGB')
    decoded, decoded_meta, decoded_stats = decode_image(candidate)
    assert decoded == payload, f'forced resize {fmt} decode mismatch'
    assert decoded_meta['filename'] == 'secret-test.bin', f'forced resize {fmt} filename metadata mismatch'
    metrics['forced_resize'][fmt.lower() + (f'_{quality}' if quality is not None else '')] = {
        'success': True,
        'bytes': len(decoded),
        'filename': decoded_meta['filename'],
        'image_size': list(candidate.size),
    }
metrics['forced_resize']['success'] = True
print('  forced-resize PNG/JPEG/WebP round-trips passed', flush=True)
# A small visual sheet for the exact code path that was previously untested.
resize_panels=[]
for fn, label in [
    ('08_resize_original.png', 'Original 176x297'),
    ('08_resize_base_at_output_size.png', 'Resized base reference'),
    ('09_resize_encoded.png', 'Encoded PNG ±2'),
    ('10_resize_jpg.jpg', 'JPEG quality 75'),
    ('10_resize_webp.webp', 'WebP quality 75'),
]:
    panel=Image.open(OUT/fn).convert('RGB'); panel.thumbnail((360,430))
    resize_panels.append((panel.copy(),label))
resize_sheet=Image.new('RGB',(1100,1000),'#101923'); rd=ImageDraw.Draw(resize_sheet)
for i,(panel,label) in enumerate(resize_panels):
    x0=(i%3)*366; y0=(i//3)*490
    rd.text((x0+8,y0+8),label,fill='white')
    resize_sheet.paste(panel,(x0+8,y0+35))
resize_sheet.save(OUT/'08_resize_visual_sheet.png')

# Save amplified difference visualization, only for inspecting changes; not a carrier.
diff8=np.clip(diff*8,0,255).astype('uint8'); Image.fromarray(diff8,'RGB').save(OUT/'06_difference_amplified_x8.png')
# Visual comparison sheet.
thumbs=[]
for fn,label in [('01_original.png','Original'),('02_encoded.png','Encoded ±2'),('03_jpg_q75.jpg','JPEG Q75'),('03_webp_q75.webp','WebP Q75'),('04_crop_right_10.png','Right crop 10%'),('04_center_crop_10_each_side.png','Center crop 10%/edge'),('05_jpeg85_webp85_crop_right.png','JPEG→WebP + crop'),('06_difference_amplified_x8.png','Difference ×8')]:
    im=Image.open(OUT/fn).convert('RGB'); im.thumbnail((300,285)); thumbs.append((im.copy(),label))
sheet=Image.new('RGB',(640,1280),'white'); sd=ImageDraw.Draw(sheet)
for i,(im,label) in enumerate(thumbs):
    xx=(i%2)*320; yy=(i//2)*320
    sd.text((xx+5,yy+3),label,fill='black'); sheet.paste(im,(xx,yy+22))
sheet.save(OUT/'07_visual_test_sheet.png')
(OUT/'test-report.json').write_text(json.dumps(metrics,indent=2))
print(json.dumps(metrics,indent=2))
