# V6 signal-source provenance freeze

## TB_13_Top_R

- Classification: suspected gain mismatch.
- Evidence basis: manual experiment-context confirmation of a speed-range setting mismatch.
- The experiment-level action table records an approximate proposed factor of 59.0814196242.
- The frozen H5 does not apply one identical factor to every channel. Eight channels (`ch_05, ch_06, ch_07, ch_08, ch_09, ch_10, ch_11, ch_12`) contain `signal_adjusted`, with per-channel factors from 58.0281677246 to 61.2359542847 (median 58.5379276276).
- Each adjusted array was verified bytewise by hash and numerically as `signal_adjusted = signal * channel_factor`.
- The processing access rule reads `signal_adjusted` when it exists. Therefore those eight adjusted arrays enter signal processing unless their channel rows are removed by the separate raw-acquisition low-amplitude screen.

## CSB_07_A

- Classification: suspected gain mismatch, with a peer-group ratio of 3.07093166684.
- Evidence strength: low. No correction factor is confirmed.
- Action: mark only. No channel contains `signal_adjusted`; the raw `signal` remains the analysis input and the condition remains in calibration.
- This record must not be described as a confirmed anomaly or confirmed gain correction.

## Low-amplitude screen consistency

- The manuscript's 20 mm/s low-amplitude screen is retained as a raw-acquisition quality screen for the amplitude-dependent and NLI figure chain and is applied to `signal` before downstream use of the preferred signal.
- It does not explain the Table 4-to-parameter-summary denominator change. The latter is produced by the separate requirement `drift_valid` and `drift_R2 >= 0.05`.
- As a diagnostic only, the v6 audit also evaluated the threshold on preferred signals. The raw-acquisition screen flags 48 channel IDs, whereas a preferred-signal screen would flag 8; 40 classifications differ. The latter is not used to change manuscript populations in this round.
- V6 wording is `low-amplitude screen`, not `amplitude anomaly screen`.

## Release representation

The release package must preserve raw arrays, adjusted arrays where present, per-channel factors, experiment- and channel-level classifications, confidence, reasons, and the preferred-signal access rule. Raw data must never be overwritten by adjusted values.
