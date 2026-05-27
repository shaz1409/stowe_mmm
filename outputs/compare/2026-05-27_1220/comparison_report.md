# Model Comparison Report

**Run:** 2026-05-27_1220

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

| channel    |   roi_meridian |     cpa_meridian |   roi_robyn |   cpa_robyn |   roi_divergence_pct |
|:-----------|---------------:|-----------------:|------------:|------------:|---------------------:|
| bing_ads   |         0.0024 | 415093           |      1.0076 |      992.46 |                199   |
| google_ads |         0.0027 | 366984           |      0.2466 |     4054.97 |                195.7 |
| meta       |         0.0008 |      1.31285e+06 |      1.2983 |      770.22 |                199.8 |
| stackadapt |         0.0006 |      1.74756e+06 |      1.2604 |      793.37 |                199.8 |

## Publish Gate

**Result:** ❌ FAILED
**Reason:** robyn R²=0.474 < 0.5; ROI diverges >50% for channels: ['bing_ads', 'google_ads', 'meta', 'stackadapt'] — manual review needed before client presentation

## Model Run Directories

- **meridian**: `/Users/shazahmed/stowe_mmm/outputs/meridian/2026-05-27_1115`
- **robyn**: `/Users/shazahmed/stowe_mmm/outputs/robyn/2026-05-27_1217`