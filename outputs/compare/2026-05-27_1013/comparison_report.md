# Model Comparison Report

**Run:** 2026-05-27_1013

## Fit Metrics

| model    |   r_squared |   mape_pct |   mae |   n_obs |
|:---------|------------:|-----------:|------:|--------:|
| meridian |      0.5303 |       9.22 | 15.57 |     105 |
| robyn    |      0.3527 |      10.62 | 18.17 |     105 |

### Publish gate thresholds
- R² ≥ 0.5
- MAPE ≤ 30.0%
- ROI divergence ≤ 50% per channel

## ROI Comparison (leads per £1k spend)

| channel    |   roi_meridian |   cpa_meridian |   roi_robyn |   cpa_robyn |   roi_divergence_pct |
|:-----------|---------------:|---------------:|------------:|------------:|---------------------:|
| bing_ads   |          2.02  |         495.13 |       1.247 |      801.83 |                 47.3 |
| google_ads |          0.566 |        1768.14 |       0.346 |     2892.69 |                 48.2 |
| meta       |          1.891 |         528.7  |       2.35  |      425.51 |                 21.6 |
| stackadapt |          2.129 |         469.8  |       2.644 |      378.16 |                 21.6 |

## Publish Gate

**Result:** ✅ PASSED
**Reason:** Force-promoted via --promote meridian
**Winner:** meridian
**Promoted to:** `outputs/meridian/accepted`

## Model Run Directories

- **meridian**: `/Users/shazahmed/stowe_mmm/outputs/meridian/2026-05-27_1012`
- **robyn**: `/Users/shazahmed/stowe_mmm/outputs/robyn/2026-05-27_1012`