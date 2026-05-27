# Model Comparison Report

**Run:** 2026-05-27_1223

## Fit Metrics

| model    |   r_squared |   mape_pct |   mae |   n_obs |
|:---------|------------:|-----------:|------:|--------:|
| meridian |      0.7646 |       7.23 | 12.01 |     105 |
| robyn    |      0.474  |      10.21 | 17.02 |     105 |

### Publish gate thresholds
- R² ≥ 0.5
- MAPE ≤ 30.0%
- ROI divergence ≤ 50% per channel

## ROI Comparison (leads per £1k spend)

| channel    |   roi_meridian |   cpa_meridian |   roi_robyn |   cpa_robyn |   roi_divergence_pct |
|:-----------|---------------:|---------------:|------------:|------------:|---------------------:|
| bing_ads   |         2.4091 |         415.09 |      1.0076 |      992.46 |                 82   |
| google_ads |         2.7249 |         366.98 |      0.2466 |     4054.97 |                166.8 |
| meta       |         0.7617 |        1312.85 |      1.2983 |      770.22 |                 52.1 |
| stackadapt |         0.5722 |        1747.56 |      1.2604 |      793.37 |                 75.1 |

## Publish Gate

**Result:** ✅ PASSED
**Reason:** Force-promoted via --promote meridian
**Winner:** meridian
**Promoted to:** `outputs/meridian/accepted`

## Model Run Directories

- **meridian**: `/Users/shazahmed/stowe_mmm/outputs/meridian/2026-05-27_1221`
- **robyn**: `/Users/shazahmed/stowe_mmm/outputs/robyn/2026-05-27_1217`