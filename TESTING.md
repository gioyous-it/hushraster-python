# Testing HushRaster

Run the fast/targeted suites from the repository root:

```bash
python -m compileall -q hushraster.py hushraster tests
python tests/test_compression_recovery.py
python tests/test_failsafe.py
python tests/test_encoder_features.py
python tests/test_resize_928_regression.py
python tests/test_cli_smoke.py
```

`tests/run_tests.py` is the larger generated-image and compression/cropping matrix. It creates its files in `test-results/`; some corner-crop recovery cases are computationally expensive and may take a long time on constrained runtimes. Do not treat a timeout as a pass. In the current development environment, the focused suites above passed, while one full-matrix attempt timed out after 360 seconds during the later PNG crop boundary probes, after the lossy center-crop tests.

The test matrix includes raw and opt-in zlib payloads, legacy format-2 decoding, SECDED fault injection, CLI text/binary round-trips, safe no-overwrite behavior, `--redo` pixel equivalence, blank canvases, and the Android runtime case where `os.link` is absent.

**Latest independent run:** compilation, `test_compression_recovery.py`, `test_failsafe.py`, `test_encoder_features.py`, and `test_cli_smoke.py` passed. `test_resize_928_regression.py` did not finish within a 300-second timeout in this run, so it is not counted as passed. Building a wheel and installing from the source ZIP both succeeded with build isolation disabled; build isolation could not fetch setuptools in this network-restricted test environment. Re-run the full suite and package build in CI before tagging a release.

The Python implementation and CLI are licensed under GNU GPL v3.0-only. The format specification in `FORMAT.md` is dedicated under CC0 1.0 Universal; see `LICENSE` and `LICENSES/CC0-1.0.txt` for the distinction.
