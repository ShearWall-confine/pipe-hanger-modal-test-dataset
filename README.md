# Modal Test Dataset for Pipe Hanger Equivalent Parameters

This repository contains the modal-test dataset and reproducibility scripts used to calibrate and internally assess equivalent parameters for full-scale pipe hanger specimens. The public database is centred on `modal_db.h5`, with the original Excel records retained for traceability and rebuilds.

## Quick Access

- Primary database: [modal_db_v1.1.h5](https://github.com/ShearWall-confine/pipe-hanger-modal-test-dataset/releases/download/v1.1.0/modal_db_v1.1.h5)
- File size: `291567448` bytes
- SHA256: `8d14ee61df2b82514540875d09fbe8a2f969b0faf1e97a567ce6f83043ba0f82`
- Previous 55-condition release: [v1.0.0](https://github.com/ShearWall-confine/pipe-hanger-modal-test-dataset/releases/tag/v1.0.0)

The v1.1 database contains all 56 completed conditions. Raw signals remain unchanged. Where a processed signal is available, it is stored separately as `signal_adjusted` and documented by the revision evidence package.

## Repository Layout

- `data/raw_xls/`: 56 original DASP-exported Excel waveform files.
- `data/metadata/`: experiment index, renaming log, manual frequency workbook, and validation reports.
- `data/metadata/revision_2026/`: machine-readable decision, provenance, sensitivity, applicability, and mapping-audit records supporting the revised manuscript.
- `data/derived/`: compact CSV/XLSX outputs used by the paper figures and tables.
- `figures/pdf/`, `figures/png/`: paper figure exports for manuscript use and GitHub preview.
- `src/`: reproducibility code for H5 construction, frequency import, damping analysis, scaling-law analysis, and figure generation.
- `scripts/`: public command-line entry points.
- `notebooks/`: output-stripped notebook for interactive inspection.
- `docs/`: data dictionary, H5 schema, and reproducibility notes.

## Reproduce the Database

Create the H5 database from the raw Excel files:

```bash
python -m src.tools.build_h5 --origin-dir data/raw_xls --h5-path data/derived/modal_db.h5
```

Import the curated frequency-identification workbook:

```bash
python -m src.tools.freq_adapter --freq-xlsx data/metadata/COMPARE_6.xlsx --h5-path data/derived/modal_db.h5
```

Validate the dataset package:

```bash
python scripts/validate_dataset.py --h5 data/derived/modal_db.h5
```

Regenerate the paper figures:

```bash
python scripts/run_paper_figures.py --target all
```

## Revised-Manuscript Evidence

The [`data/metadata/revision_2026/`](data/metadata/revision_2026/) directory provides the 56-condition index, the complete 168-row condition--mode decision record, signal-provenance metadata, calibration-sensitivity tables, NLI window data, and the parameter-level shared-axial audit. The decision record distinguishes 139 entries supported by at least one auxiliary-rule channel from 29 entries requiring manual review. This classification makes the historical decisions auditable but does not imply that an unrecorded channel choice can be reconstructed automatically.

## Requirements

The scripts require Python 3.10+ and the scientific Python stack used by the original analysis: `numpy`, `scipy`, `h5py`, `xlrd`, `openpyxl`, `matplotlib`, and `IPython`.

## License

Code is released under the MIT License in `LICENSE-CODE`.  Data are released under CC BY 4.0 in `LICENSE-DATA`.  Please cite the paper and this dataset when reusing the records.
