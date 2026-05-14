# Data Dictionary

## Experiment Identifiers

Experiment IDs follow:

```text
<support_type>_<component_code>_<direction>
```

Examples: `CA_07_A`, `TB_07+13_Mid_RR`, `CSBD_13_R`.

## Support Types

| Code | Meaning in the test matrix |
|---|---|
| `CA` | Cross-arm pipe clamp hanger |
| `TB` | Three-bolt pipe clamp hanger |
| `CSB` | C-type steel band clamp hanger |
| `CSBD` | C-shaped steel bolt dynamic clamp hanger |

## Direction Codes

| Code | Meaning |
|---|---|
| `A` | Axial release/orientation |
| `R` | Radial release/orientation |
| `AA`, `AR`, `RA`, `RR` | Combined component-orientation cases used by multi-component layouts |

## Core Files

| Path | Description |
|---|---|
| `data/raw_xls/*.XLS` | Original waveform records exported from the modal-test acquisition workflow |
| `data/metadata/experiment_index.csv` | One row per H5 experiment with filenames, type, direction, sampling rate, duration, and channel count |
| `data/metadata/COMPARE_6.xlsx` | Curated manual frequency-identification workbook |
| `data/metadata/rename_log.csv` | Historical prefix normalization log, including `TR -> CSBD` and `CS -> CSB` |
| `data/derived/*.csv` | Compact analysis summaries used by the manuscript figures and tables |

## Waveform Conventions

- Each experiment contains `20` velocity channels.
- The H5 channel IDs are `ch_01` to `ch_20`.
- `channel_brackets` preserves the original bracket-style sensor labels parsed from the Excel header.
- Time is stored in seconds.
- Signals are stored as the numeric values exported by the acquisition workflow; amplitude-sensitive paper figures interpret retained velocity amplitudes in `mm/s`.
- Typical sampling rates in the database are approximately `10.204 Hz`; some records use the corresponding higher acquisition setting from the original tests.

## Frequency Metadata

`COMPARE_6.xlsx` is the curated source for frequency calibration.  Its modes are normalized in the scripts as:

| Workbook text | Normalized mode |
|---|---|
| `径向平动` | `radial` |
| `轴向平动` | `axial` |
| `平面转动` | `planar_rotation` |
