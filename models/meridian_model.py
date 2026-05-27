# models/meridian_model.py
# Real Google Meridian Bayesian MMM.
#
# Requires the project venv:
#   source .venv/bin/activate
#   pip install "jax[cpu]" google-meridian   (already done)
#
# MCMC runtime: ~10-25 min on CPU for default settings.
# Pass --quick to 03_model.py to use fast low-sample settings for testing.

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import yaml

MODEL_NAME = "meridian"
SEED       = 42

MEDIA_CHANNELS = ["google_ads", "bing_ads", "meta", "stackadapt"]

# Exposure metric per channel: PPC → clicks (intent proxy), display → impressions
EXPOSURE_COL = {
    "google_ads": "google_ads_clicks",
    "bing_ads":   "bing_ads_clicks",
    "meta":       "meta_impressions",
    "stackadapt": "stackadapt_impressions",
}


# ── Config ────────────────────────────────────────────────────────────────────

def configure(quick: bool = False) -> dict:
    if quick:
        return {"n_chains": 1, "n_adapt": 100, "n_burnin": 100, "n_keep": 100, "max_lag": 8}
    return     {"n_chains": 2, "n_adapt": 500, "n_burnin": 500, "n_keep": 1000, "max_lag": 8}


# ── InputData ─────────────────────────────────────────────────────────────────

def _build_input_data(df: pd.DataFrame, features: dict):
    from meridian.data import nd_array_input_data_builder as idb_mod

    kpi_col = features.get("kpi", "quality_leads")
    if kpi_col not in df.columns or df[kpi_col].isna().all():
        sys.exit(f"ERROR [meridian]: '{kpi_col}' missing or all-NaN. Run 01_data_prep.py first.")

    df_fit = df[df[kpi_col].notna()].copy()
    time_coords = [str(d.date()) for d in df_fit.index]

    # ── KPI ──
    y = df_fit[kpi_col].values.astype(float)

    # ── Media ──
    active = [m for m in features.get("media", []) if m["col"] in df_fit.columns]
    if not active:
        sys.exit("ERROR [meridian]: No media spend columns found in input data.")

    channel_names = [m["col"].replace("_spend", "") for m in active]

    spend_arr = np.column_stack([
        df_fit[m["col"]].fillna(0).values.astype(float)
        for m in active
    ])  # (n_times, n_channels)

    exposure_arr = np.column_stack([
        df_fit.get(EXPOSURE_COL.get(ch, m["col"]), df_fit[m["col"]])
              .fillna(0).values.astype(float)
        for ch, m in zip(channel_names, active)
    ])  # (n_times, n_channels)

    # ── Builder ──
    # Meridian national model: pass (1, n_times) shaped arrays — let the builder
    # auto-discover the geo name from the shape; don't set geos manually.
    builder = idb_mod.NDArrayInputDataBuilder(kpi_type="non_revenue")
    builder.time_coords       = time_coords
    builder.media_time_coords = time_coords
    builder.with_kpi(y.reshape(1, -1))                            # (1, n_times)
    builder.with_media(
        exposure_arr[np.newaxis],   # (n_times, n_ch) → (1, n_times, n_ch)
        spend_arr[np.newaxis],      # (n_times, n_ch) → (1, n_times, n_ch)
        channel_names,
    )

    # ── Controls (optional) ──
    ctrl_cols = [c for c in features.get("controls", []) if c in df_fit.columns]
    if ctrl_cols:
        ctrl_arr = df_fit[ctrl_cols].fillna(df_fit[ctrl_cols].median()).values.astype(float)
        builder.with_controls(ctrl_arr[np.newaxis], ctrl_cols)  # (1, n_times, n_ctrl)

    return builder.build(), df_fit, channel_names, active


# ── Outputs ───────────────────────────────────────────────────────────────────

def _extract_and_write(mmm, df_fit: pd.DataFrame, channel_names: list, active: list,
                       features: dict, outdir: str, cfg: dict) -> None:
    import arviz as az
    from meridian.analysis import analyzer as ana_lib

    kpi_col = features.get("kpi", "quality_leads")
    y       = df_fit[kpi_col].values.astype(float)

    analyzer = ana_lib.Analyzer(mmm)

    # ── Predictive accuracy ──
    acc = analyzer.predictive_accuracy()   # xarray Dataset

    # ── Expected outcome (posterior mean) ──
    # Shape: (n_samples, 1, n_times) → squeeze → (n_times,)
    expected_raw = np.array(analyzer.expected_outcome(aggregate_times=False))
    expected     = expected_raw.reshape(-1, len(y)).mean(axis=0)

    resid = y - expected
    r2    = float(1 - np.sum(resid**2) / np.sum((y - y.mean())**2))
    mape  = float(np.mean(np.abs(resid / np.where(y == 0, 1, y))) * 100)
    mae   = float(np.mean(np.abs(resid)))

    # ── ROI posterior ──
    # Shape varies: (n_samples,) or (n_samples, n_channels) or (n_samples, 1, n_channels)
    roi_raw  = np.array(analyzer.roi()).squeeze()   # remove any singleton geo dim
    if roi_raw.ndim == 1:
        roi_raw = roi_raw[:, np.newaxis]            # ensure (n_samples, n_channels)
    roi_mean = roi_raw.mean(axis=0).flatten()
    roi_p5   = np.percentile(roi_raw, 5,  axis=0).flatten()
    roi_p95  = np.percentile(roi_raw, 95, axis=0).flatten()

    # ── ROI table ──
    roi_rows = []
    for i, (ch, m) in enumerate(zip(channel_names, active)):
        total_spend = df_fit[m["col"]].fillna(0).sum()
        incr        = float(roi_mean[i] * total_spend / 1_000)
        cpa         = total_spend / incr if incr > 0 else None
        roi_rows.append({
            "channel":              ch,
            "total_spend_gbp":      round(total_spend, 2),
            "incremental_leads":    round(incr, 1),
            "roi_leads_per_kgbp":   round(float(roi_mean[i]), 4),
            "cpa_gbp":              round(cpa, 2) if cpa else None,
            "coef_p5":              round(float(roi_p5[i]), 6),
            "coef_p95":             round(float(roi_p95[i]), 6),
        })

    # ── Contributions (spend-weighted decomposition) ──
    # Approximates weekly attribution as roi_mean × weekly_spend / 1000.
    # Proper counterfactual decomposition requires one posterior pass per channel;
    # use this for Power BI visualisation and replace with full decomp if needed.
    contrib = pd.DataFrame(index=df_fit.index)
    contrib["actual"]    = y
    contrib["predicted"] = expected
    total_media_contrib  = np.zeros(len(y))
    for i, (ch, m) in enumerate(zip(channel_names, active)):
        weekly_spend   = df_fit[m["col"]].fillna(0).values
        ch_contrib     = roi_mean[i] * weekly_spend / 1_000
        contrib[f"{ch}_contrib"] = ch_contrib
        total_media_contrib += ch_contrib
    contrib["baseline"] = expected - total_media_contrib
    if ctrl_cols := [c for c in features.get("controls", []) if c in df_fit.columns]:
        contrib["controls_contrib"] = 0.0  # absorbed into baseline for now

    # ── Response curves ──
    rc_mults = [i / 10 for i in range(0, 21)]  # 0.0 to 2.0
    try:
        rc_ds = analyzer.response_curves(
            spend_multipliers=rc_mults,
            by_reach=False,
            confidence_level=0.9,
        )
        # xarray Dataset with dims (metric, channel, spend_multiplier)
        # Variable name varies across Meridian versions: try both
        outcome_var = "incremental_outcome" if "incremental_outcome" in rc_ds else "mean"
        rc_mean = rc_ds[outcome_var].to_dataframe().reset_index()
        rc_rows = []
        for _, row in rc_mean.iterrows():
            ch = row.get("channel", row.get("media_channel", ""))
            mult = float(row.get("spend_multiplier", 0))
            spend_col = f"{ch}_spend"
            mean_weekly = df_fit[spend_col].fillna(0).mean() if spend_col in df_fit.columns else 0
            rc_rows.append({
                "channel":           ch,
                "spend_pct_of_mean": int(mult * 100),
                "weekly_spend_gbp":  round(mean_weekly * mult, 2),
                "incremental_leads": round(float(row.get(outcome_var, 0)), 4),
            })
        response_curves_df = pd.DataFrame(rc_rows)
    except Exception as e:
        print(f"  [meridian] response_curves failed ({e}) — using spend-based approx")
        response_curves_df = _response_curves_approx(channel_names, active, df_fit, roi_mean)

    # ── Write ──
    os.makedirs(outdir, exist_ok=True)

    # Save posterior samples for reloading / scoring without refit
    mmm.inference_data.to_netcdf(os.path.join(outdir, "inference_data.nc"))

    contrib.to_csv(os.path.join(outdir, "contributions.csv"))
    pd.DataFrame(roi_rows).to_csv(os.path.join(outdir, "roi_table.csv"), index=False)
    response_curves_df.to_csv(os.path.join(outdir, "response_curves.csv"), index=False)
    pd.DataFrame({
        "date":      df_fit.index,
        "actual":    y,
        "predicted": expected,
        "residual":  resid,
    }).to_csv(os.path.join(outdir, "diagnostics.csv"), index=False)

    card = {
        "model":       MODEL_NAME,
        "run_date":    datetime.now().isoformat(),
        "kpi":         kpi_col,
        "n_obs":       int(len(y)),
        "r_squared":   round(r2, 4),
        "mape_pct":    round(mape, 2),
        "mae":         round(mae, 2),
        "n_chains":    cfg["n_chains"],
        "n_keep":      cfg["n_keep"],
        "max_lag":     cfg["max_lag"],
        "media_cols":  [m["col"] for m in active],
        "note":        "Real Google Meridian — Bayesian hierarchical MMM with HMC-NUTS.",
    }
    with open(os.path.join(outdir, "model_card.yaml"), "w") as fh:
        yaml.dump(card, fh, default_flow_style=False, sort_keys=False)

    print(f"  [meridian]  R²={r2:.3f}  MAPE={mape:.1f}%  MAE={mae:.1f}")
    print(f"  [meridian]  outputs → {outdir}/")


def _response_curves_approx(channel_names, active, df_fit, roi_mean) -> pd.DataFrame:
    """Spend-based response curve fallback if Meridian's API call fails."""
    rows = []
    for i, (ch, m) in enumerate(zip(channel_names, active)):
        mean_spend = df_fit[m["col"]].fillna(0).mean()
        for pct in range(0, 201, 10):
            w = mean_spend * pct / 100
            rows.append({
                "channel":           ch,
                "spend_pct_of_mean": pct,
                "weekly_spend_gbp":  round(w, 2),
                "incremental_leads": round(roi_mean[i] * w / 1_000, 4),
            })
    return pd.DataFrame(rows)


# ── Main entry ────────────────────────────────────────────────────────────────

def run(df: pd.DataFrame, features: dict, outdir: str, quick: bool = False) -> str:
    """
    Fit Meridian, write output files, return outdir.
    Set quick=True for fast low-sample test run (~2 min vs ~20 min).
    """
    try:
        from meridian.model import model as mmm_lib
        from meridian.model import spec as mspec
    except ImportError:
        sys.exit(
            "ERROR: google-meridian not importable. "
            "Activate the project venv:  source .venv/bin/activate"
        )

    cfg = configure(quick=quick)

    print(f"  [meridian] Building InputData ...")
    input_data, df_fit, channel_names, active = _build_input_data(df, features)

    model_spec = mspec.ModelSpec(
        max_lag=cfg["max_lag"],
        adstock_decay_spec="geometric",
        saturation_spec="hill",
    )

    mmm = mmm_lib.Meridian(input_data=input_data, model_spec=model_spec)

    n_total = cfg["n_chains"] * (cfg["n_adapt"] + cfg["n_burnin"] + cfg["n_keep"])
    print(f"  [meridian] Sampling posterior — "
          f"{cfg['n_chains']} chains × (adapt={cfg['n_adapt']} burnin={cfg['n_burnin']} "
          f"keep={cfg['n_keep']})  total={n_total:,} steps ...")
    print(f"  [meridian] Estimated time: {'~2 min' if quick else '~15-25 min'} on CPU")

    mmm.sample_posterior(
        n_chains=cfg["n_chains"],
        n_adapt=cfg["n_adapt"],
        n_burnin=cfg["n_burnin"],
        n_keep=cfg["n_keep"],
        seed=SEED,
    )

    print(f"  [meridian] Sampling complete. Extracting outputs ...")
    _extract_and_write(mmm, df_fit, channel_names, active, features, outdir, cfg)

    return outdir
