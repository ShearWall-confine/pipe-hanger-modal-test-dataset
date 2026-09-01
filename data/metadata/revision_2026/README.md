# Revised-Manuscript Evidence Package

This directory contains the machine-readable evidence used in the revised manuscript. It complements the waveform H5 database and does not replace the raw records.

## File Guide

- `condition_index_56.csv`: one row for each completed test condition.
- `condition_mode_decisions_168.csv`: candidate estimates, rule flags, adopted condition-level frequencies, and analysis-inclusion decisions for 168 condition--mode entries. Of these entries, 139 are supported by at least one channel passing the auxiliary checks and 29 require manual review. The classification is an audit record, not an automatic reconstruction of undocumented historical channel choices.
- `data_flow_by_type_direction.csv`: frequency, damping, and NLI population counts by hanger type and direction.
- `stiffness_manual_review_sensitivity.csv`, `damping_manual_review_sensitivity.csv`, and `nli_manual_review_sensitivity.csv`: analyses with the 29 manual-review frequency entries excluded.
- `nli_windows_detail.csv` and `nli_amplitude_bins_summary.csv`: window-level and binned evidence for the reported NLI--amplitude relationship.
- `signal_provenance_channels.csv` and `signal_provenance_notes.md`: raw/adjusted signal lineage, hashes, factors, confidence, and downstream selection. Raw arrays are never overwritten.
- `damping_input_lineage.csv`: comparison between current experimental summaries and the frozen group-level inputs used in the existing seismic analyses.
- `shared_axial_counterfactual_detail.csv` and `shared_axial_counterfactual_summary.csv`: parameter-level comparison of the intentional shared-axial engineering assignment with a direction-specific counterfactual. These files do not constitute a system-response validation.
- `applicability_domain_106_active_directions.csv`: calibrated-domain audit for active swing directions in the system model.

## Interpretation Boundaries

The manual-review exclusion is a structured subset check rather than a missing-at-random reanalysis. The shared-axial files quantify a parameter-mapping approximation without claiming that one mapping is uniformly conservative. The fixed system damping inputs remain separate from the current H5-recomputed experimental summaries, as documented in `damping_input_lineage.csv`.

The H5 release associated with this package is `modal_db_v1.1.h5` (56 conditions; SHA256 `8d14ee61df2b82514540875d09fbe8a2f969b0faf1e97a567ce6f83043ba0f82`).
