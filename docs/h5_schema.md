# H5 Schema

Primary release asset: `modal_db_v1.1.h5`.

## Root Attributes

| Attribute | Meaning |
|---|---|
| `schema_version` | H5 schema version, currently `1.0` |
| `created_at` | Original database creation timestamp |
| `source_dir` | Public source-data location, `data/raw_xls` |

## Group Layout

```text
/experiments/<exp_id>/
  attrs:
    exp_id
    original_filename
    current_filename
    sample_rate
    dt
    duration
    rows
    channel_count
    support_type
    component_id
    direction
  datasets:
    time
    channel_ids
    channel_brackets
    freq_peaks
    modal_freq_modes
    modal_freq_values
  /channels/<ch_id>/
    attrs:
      index
      label
    datasets:
      signal
      signal_adjusted (optional; raw signal is retained separately)
      freq_peaks
      /spectrum/freq
      /spectrum/mag
```

Damping extraction scripts may add derived damping groups or datasets to the same experiment groups when rerun locally. The optional `signal_adjusted` dataset is used only when it exists; its provenance and channel-specific factor are recorded in `data/metadata/revision_2026/signal_provenance_channels.csv`.

## Minimal Read Example

```python
from pathlib import Path
import h5py

h5_path = Path("data/derived/modal_db.h5")
with h5py.File(h5_path, "r") as h5:
    experiments = h5["experiments"]
    exp_id = sorted(experiments.keys())[0]
    group = experiments[exp_id]
    time = group["time"][:]
    signal = group["channels"]["ch_01"]["signal"][:]
    print(exp_id, group.attrs["support_type"], time.shape, signal.shape)
```

## Current Database Summary

- Experiment count: `56`
- Support counts: `CA=16`, `TB=32`, `CSB=4`, `CSBD=4`
- Direction counts: `AA=8`, `AR=8`, `RA=8`, `RR=8`, `A=12`, `R=12`
- Release SHA256: `8d14ee61df2b82514540875d09fbe8a2f969b0faf1e97a567ce6f83043ba0f82`
