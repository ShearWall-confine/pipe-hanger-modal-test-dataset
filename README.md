# Modal Test Dataset for Pipe Hanger Equivalent Parameters

This repository contains the modal-test dataset and reproducibility scripts used to calibrate and validate equivalent parameters for full-scale pipe hanger specimens.  The public database is centred on `modal_db.h5`, with the original Excel records retained for traceability and rebuilds.

## Quick Access

- Primary database: `modal_db_v1.0.h5`
- Release asset path before publishing: `release_assets/modal_db_v1.0.h5`
- File size: `88191071` bytes
- SHA256: `1b8580ceba54795c57a9cdb8dbbbc46bb71712b151a0d7ca8a4d2d2204707e2f`

After creating a GitHub release, upload `release_assets/modal_db_v1.0.h5` as the release asset and replace this paragraph with the release download URL.  The H5 file is intentionally ignored by Git so the repository stays lightweight.

## Repository Layout

- `data/raw_xls/`: 55 original DASP-exported Excel waveform files.
- `data/metadata/`: experiment index, renaming log, manual frequency workbook, and validation reports.
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

## Requirements

The scripts require Python 3.10+ and the scientific Python stack used by the original analysis: `numpy`, `scipy`, `h5py`, `xlrd`, `openpyxl`, `matplotlib`, and `IPython`.

## License

Code is released under the MIT License in `LICENSE-CODE`.  Data are released under CC BY 4.0 in `LICENSE-DATA`.  Please cite the paper and this dataset when reusing the records.
