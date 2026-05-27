# Validation Report

**Run:** 2026-05-27_1012  
**Input:** data/processed/mmm_input.csv  
**Date range:** 2020-01-06 → 2024-12-30  
**Rows:** 261 | **Columns:** 16

## Summary

| Check | Status | Message |
|---|---|---|
| DATE_COVERAGE | ✅ PASS | 261 weeks, 2020-01-01 → 2024-12-31, no gaps |
| KPI_PRESENCE | ✅ PASS | quality_leads present, 105 non-null rows |
| MEDIA_PRESENT | ✅ PASS | 4/4 spend columns have non-zero values |
| NO_FULLY_NULL_COLS | ✅ PASS | No fully-NaN columns (KPI exempted) |
| NUMERIC_TYPES | ✅ PASS | 15 metric columns all numeric |
| SCHEMA_DRIFT | ✅ PASS | Schema re-initialised at config/expected_schema.yaml |
| CHANNEL_COMPLETENESS | ✅ PASS | All channels have ≥30% active weeks |
| HIGH_MISSINGNESS | ✅ PASS | No control columns to check |
| OUTLIERS | ✅ PASS | No values > 5σ from column mean |
| TRAILING_NAN | ✅ PASS | No trailing NaN sequences |
| VIF | ⚠️  WARN | 15 column(s) VIF > 10. Top 5: stackadapt_spend=253139206754.6, stackadapt_impressions=253132092705.5, google_ads_spend=2243.9, bing_ads_spend=1866.0, meta_spend=1353.0 |
| STATIONARITY | ✅ PASS | All tested columns stationary at p ≤ 0.05 (media spend excluded) |

## Issues

### ⚠️  VIF (WARN)

15 column(s) VIF > 10. Top 5: stackadapt_spend=253139206754.6, stackadapt_impressions=253132092705.5, google_ads_spend=2243.9, bing_ads_spend=1866.0, meta_spend=1353.0
