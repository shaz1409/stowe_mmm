# stowe_mmm

## Project
Marketing Mix Model for Stowe, a UK divorce law firm. Goal: attribute `quality_leads` to paid media spend across Meta, Google Ads, Microsoft Advertising (Bing), and StackAdapt, while controlling for macro and seasonal factors.

## KPI
`quality_leads` — daily count from Stowe's Azure DW (Clef-defined lead quality). Aggregated to weekly Monday for modelling. Never substitute raw form fills.

## Grain & Geography
- Time grain: weekly Monday-anchored (`W-MON`)
- v1: UK national only
- Stretch goal: England regions — Meridian supports natively, Robyn does not

## Modelling Framework
Run both in parallel:
- **Meta Robyn** — Ridge regression with adstock + Hill saturation, via `rpy2` bridge
- **Google Meridian** — Bayesian hierarchical, native Python

Compare results via `05_compare.py`, then publish one or both.

## Date Window
`2020-01-01` → `2024-12-31`. COVID confounding in 2020-Q2 through 2021-Q1 — leave in for v1; controls and Prophet seasonality should absorb it.

## Pipeline
Scripts run in order. Refit cadence: monthly/quarterly. Scoring: weekly (no refit).

| Script | Input | Output |
|---|---|---|
| `pipeline/01_data_prep.py` | APIs + DW | `data/processed/mmm_input.csv` |
| `pipeline/02_validate.py` | mmm_input.csv | `outputs/validate/{ts}/` — fails loud |
| `pipeline/03_explore.py` | mmm_input.csv | `outputs/explore/{ts}/` + `config/features.yaml` |
| `pipeline/04_model.py` | features.yaml | `outputs/{robyn,meridian}/{ts}/` |
| `pipeline/05_compare.py` | model outputs | `outputs/compare/{ts}/` + publish gate |
| `pipeline/06_optimise.py` | accepted model | `outputs/scenarios/{ts}/` |
| `pipeline/07_export.py` | accepted model | DW tables (`mmm_*`), `outputs/export/{ts}/` |
| `score.py` | accepted artefact | weekly scores, no refit |

## Domain Notes
- **Divorce Day**: inquiries spike on first Monday of January every year. Calendar features must include this explicitly.
- **Adstock**: long consideration cycle — allow wide geometric decay (theta up to ~0.5).
- **Lead quality**: optimise for `quality_leads` only, never raw form fills or click volume.
- **Channel intent**: paid search (PPC) captures intent; social/display (Meta, StackAdapt) drives consideration. Interpret coefficients accordingly.
- **Land Registry**: housing transaction volume is a meaningful macro control — property transactions correlate with financial proceedings in divorce.

## Spend Scale & Channel Mix
Total monthly paid spend ≈ £330–450k. Weekly ≈ £80–110k.

| Channel | Monthly spend | Share |
|---|---|---|
| Google Ads + Bing (PPC) | £300–400k | ~85–90% |
| Meta + StackAdapt (social/display) | £30–50k | ~10–15% |

**Implications for modelling:**
- Google Ads ROI estimates will have tight CIs; Meta and StackAdapt will have wide CIs and unstable coefficients in v1 — flag this in any client-facing output.
- Brand vs non-brand split inside Google Ads is HIGH PRIORITY for v2. At this PPC volume, brand campaigns mostly capture existing demand and inflate Google's apparent ROI. Do not ship channel recommendations based on a combined Google coefficient without a prominent caveat.
- Meta and StackAdapt are historically run by a separate agency — verify data access before promising coverage.

## Code Conventions
Mirror `sources/media/meta.py` and `sources/media/google_ads.py`.

- Source modules expose `fetch(start, end) -> pd.DataFrame` with a normalised schema
- Credentials from `.env` via `os.environ[...]` — never hardcode
- Chunk API calls monthly where limits apply
- Progress: `print(f"  Fetching {start} -> {end}")`
- Standard media schema: `date | channel | region | city | campaign | spend | impressions | clicks | conversions` plus channel extras
- Seeds: set for all stochastic operations. Default seed: `42` (Robyn uses Nevergrad, Meridian uses MCMC)
- Versioned outputs: write to `outputs/{stage}/{YYYY-MM-DD_HHMM}/`; maintain `outputs/{stage}/latest` symlink and `outputs/{stage}/accepted` symlink for promoted models

## Output Locations
- Raw API pulls: `data/raw/{source}_raw.csv`
- Modelling input: `data/processed/mmm_input.csv`
- Validation: `outputs/validate/{ts}/`
- EDA + feature suggestions: `outputs/explore/{ts}/` and `config/features.yaml`
- Model runs: `outputs/{robyn,meridian}/{ts}/` — must include model card, hyperparams, metrics
- Comparisons + publish gate: `outputs/compare/{ts}/`
- Scenarios: `outputs/scenarios/{ts}/`
- DW export staging: `outputs/export/{ts}/`

## What NOT To Do
- Don't add dependencies without updating `requirements.txt`
- Don't refactor working connectors unless explicitly asked
- Don't add async or parallelism — sequential is fine
- Don't write tests unless asked
- Don't refit inside `score.py` — score only against the accepted artefact
- Don't promote a model to `accepted` without running `05_compare.py`'s publish gate
