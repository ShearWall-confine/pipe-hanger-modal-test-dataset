# Reproducibility Notes

## Workflow

1. Start from the 56 Excel files in `data/raw_xls/`.
2. Build the waveform H5 database.
3. Import curated modal frequencies from `data/metadata/COMPARE_6.xlsx`.
4. Validate workbook consistency and H5 completeness.
5. Regenerate compact result tables and paper figures.

## Commands

```bash
python -m src.tools.build_h5 --origin-dir data/raw_xls --h5-path data/derived/modal_db.h5
python -m src.tools.freq_adapter --freq-xlsx data/metadata/COMPARE_6.xlsx --h5-path data/derived/modal_db.h5
python -m src.tools.validate_compare6 --compare-xlsx data/metadata/COMPARE_6.xlsx --out data/metadata/compare6_validation_report.json
python scripts/validate_dataset.py --h5 data/derived/modal_db.h5
python scripts/run_paper_figures.py --target all
```

If the release H5 is downloaded instead of rebuilt, place it at:

```text
data/derived/modal_db.h5
```

and then run the validation and figure commands.

The v1.1 release H5 is the authoritative database for reproducing the revised-manuscript analyses because it preserves curated modal results and optional adjusted-signal arrays alongside the unchanged raw signals. A rebuild from the public Excel files recreates the raw waveform structure, but the curated imports and provenance-governed adjusted arrays require their corresponding processing steps.

## Output Policy

- `modal_db.h5` is the main structured database but is distributed as a GitHub Release asset, not as a Git-tracked file.
- PDF and PNG figure exports are included for paper reproduction and visual checking.
- TIFF exports are intentionally excluded from the public repository to keep the Git checkout small.
- Local reruns may create `.mplconfig/`, `_generated_tiff/`, and `data/derived/modal_db.h5`; these are ignored by Git.

## Provenance Notes

- The public naming has already normalized historical prefixes: `TR` records are represented as `CSBD`, and `CS` records are represented as `CSB`.
- `COMPARE_6.xlsx` is the curated frequency source used for stiffness calibration.
- H5 waveform records are retained to support damping, frequency-drift, and equivalent-linear applicability checks.
- Revision-specific machine-readable evidence is stored in `data/metadata/revision_2026/`; these files document analysis decisions and sensitivity checks without overwriting the source waveforms.
