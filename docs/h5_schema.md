# H5 Schema

Primary release asset: `modal_db_v1.0.h5`.

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
      freq_peaks
      /spectrum/freq
      /spectrum/mag
```

Damping extraction scripts may add derived damping groups or datasets to the same experiment groups when rerun locally.

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

- Experiment count: `55`
- Support counts: `CA=16`, `TB=31`, `CSB=4`, `CSBD=4`
- Direction counts: `AA=8`, `AR=8`, `RA=8`, `RR=8`, `A=11`, `R=12`
- Release SHA256: `1b8580ceba54795c57a9cdb8dbbbc46bb71712b151a0d7ca8a4d2d2204707e2f`
