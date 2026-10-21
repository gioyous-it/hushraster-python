# IMGMod: legacy image-modulation extension

**Status in HushRaster 1.0.1:** compatibility extension. **Planned status in HushRaster 2.0:** removed.

IMGMod is the optional image-overlay workflow that existed before HushRaster was treated primarily as a standalone barcode. It applies the HushRaster module signal over an existing RGB image (a “cover”) instead of generating the barcode on a solid canvas. It uses the same revision-3 HushRaster header, bit order, module patterns, repetition, body SECDED, integrity tag, and decoder. The normal `decode` command can recover payload bytes from IMGMod outputs when the signal survives the source image and any later processing. `inspect` reports format and integrity information.

IMGMod is **not part of the HushRaster Barcode Standard** in [`FORMAT.md`](FORMAT.md). It does not define a different barcode format or encryption scheme; it is simply an alternate renderer that overlays the same HushRaster bit pattern on a user-provided raster. Because the source image affects the visual signal and the encoder may need to resize an image with insufficient capacity, recovery remains dependent on the image and processing path. The encoder performs a strict self-check before saving.

## Commands

Overlay arbitrary file bytes on an existing image:

```bash
cat secret.zip | hushraster imgmod encode photo.png image-with-data.png
```

Overlay text on an existing image:

```bash
printf '%s' 'Hello from HushRaster' | hushraster imgmod encode photo.png image-with-text.png
```

If the image does not have enough capacity, encoding fails unless resizing is explicitly allowed:

```bash
cat secret.zip | hushraster imgmod encode photo.png image-with-data.png --resize
```

Increase the modulation signal while retaining the same revision-3 on-image representation:

```bash
printf '%s' 'Hello from HushRaster' | hushraster imgmod encode photo.png image-with-text.png --redo 8
```

Compare the original and the IMGMod result:

```bash
hushraster imgmod compare photo.png image-with-data.png
```

IMGMod retains `--force` / `-f`, `--max-pixels`, and `--no-filename` options where applicable. New IMGMod encoding is always uncompressed; historical compressed IMGMod files can still be decoded if their header declares the old compression method. Do not rely on invisibility or recovery after arbitrary transforms: a low-amplitude signal is not mathematically invisible, and no image-processing pipeline can be guaranteed.

## Historical IMGMod test results

The regression harness contains a 1536×1536 generated landscape cover with a 95-byte payload and a separate 176×297 cover that exercises explicit resizing. These tests measure the **legacy image-overlay path** only; they are not blanket promises for all standalone barcode images or image-processing software.

On the included fixtures and Pillow encoders, the previous regression suite reported:

- Strict lossless PNG round-trip and the tested JPEG/WebP Q75/Q90 round-trips succeeded.
- JPEG Q50 and WebP Q50 succeeded on the tested fixture; different images, encoder versions, and processing settings may behave differently.
- Tested 10% right/bottom edge crops, a center crop removing about 10% from each edge, JPEG Q75 followed by that center crop, and JPEG Q85 → WebP Q85 → a 10% right crop succeeded on the recorded fixture.
- A dedicated forced-resize case started from 176×297 and successfully decoded PNG, JPEG Q75, and WebP Q75 results. The 95-byte fixture's current final dimensions were 1328×2232.
- The measured same-size difference from the base image had a maximum RGB-channel delta of 2 in that one-pass test; repeated `--redo` intentionally increases the signal and can make changes more visible.

The tests are reproducible on the included fixtures, not universal guarantees. Arbitrary crops that remove both header regions, correlated errors across many repeated modules, scaling, rotation, blur, or different lossy pipelines can still prevent exact recovery. HushRaster has an integrity digest so a damaged result is not silently declared valid.

## Command migration

In HushRaster 1.0.1, image-overlay command forms moved under `imgmod`:

```text
hushraster encode cover.png secret.zip output.png
    -> hushraster imgmod encode cover.png secret.zip output.png

hushraster encode-text cover.png "text" output.png
    -> hushraster imgmod encode-text cover.png "text" output.png

hushraster compare cover.png output.png
    -> hushraster imgmod compare cover.png output.png
```

Use top-level `encode` and `decode` for **standalone barcode generation and scanning**; payload bytes always travel through stdin/stdout. The `imgmod` commands are the explicit file-path exception. IMGMod is planned for removal in 2.0, so new integrations should generate self-contained barcodes directly.


## Standard-family CLI alias

OI has a standalone selector. For example, `printf 'hello' | hushraster encode oi+ --ppm 4 > oi.png` creates an OI image on a generated neutral-gray carrier (custom carriers can be set with `--on-blank`). For legacy overlays, use `cat payload.bin | hushraster imgmod encode cover.png output.png`; the `imgmod` command requires an origin image and an output path. Normal decoding reads the PNG from stdin, for example `hushraster decode oi+ < oi.png > payload.bin`; `inspect` also accepts an optional standard selector.
