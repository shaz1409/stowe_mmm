import pandas as pd
from config.dates import DATE_START, DATE_END, TIME_GRAIN
from . import oecd, boe, ons, weather, land_registry, bank_holidays, google_trends, calendar


def align_to_grain(sources: dict[str, pd.DataFrame | pd.Series], grain: str = TIME_GRAIN) -> pd.DataFrame:
    """
    Resample all sources to TIME_GRAIN and join into a single wide DataFrame.

    Resampling conventions by source frequency:
      - Monthly (OECD, BoE, ONS, Land Registry): forward-fill within month
      - Daily (weather, bank holidays):           aggregate — mean for continuous,
                                                  sum for counts/flags
      - Weekly (Google Trends, calendar):         reindex to grain, forward-fill gaps

    Returns a single wide DataFrame indexed by period-start date.
    Trailing NaNs from publication lag are preserved — main() warns about them.
    """
    target_index = pd.date_range(DATE_START, DATE_END, freq=grain)
    aligned: list[pd.DataFrame] = []

    for name, src in sources.items():
        if isinstance(src, pd.Series):
            src = src.to_frame()

        if src.empty or not isinstance(src.index, pd.DatetimeIndex):
            continue

        freq = pd.infer_freq(src.index)

        if freq and freq.startswith("M"):
            # Monthly source: upsample then forward-fill so every week in a
            # calendar month gets the month's published value
            src = src.resample(grain).first().reindex(target_index).ffill()

        elif freq and (freq.startswith("D") or freq == "B"):
            # Daily source: aggregate to weekly grain
            # Flags/counts → sum; continuous measures → mean
            flag_cols = [c for c in src.columns if c.startswith("is_") or c.endswith("_count")]
            cont_cols = [c for c in src.columns if c not in flag_cols]

            parts = []
            if flag_cols:
                parts.append(src[flag_cols].resample(grain).sum())
            if cont_cols:
                parts.append(src[cont_cols].resample(grain).mean())

            src = pd.concat(parts, axis=1).reindex(target_index)

        else:
            # Weekly or unknown: reindex to target grain and forward-fill small gaps
            src = src.reindex(target_index).ffill(limit=4)

        aligned.append(src)

    if not aligned:
        return pd.DataFrame(index=target_index)

    result = pd.concat(aligned, axis=1)
    result.index.name = "date"
    return result


def main():
    _fetchers = [
        ("oecd",          oecd.fetch),
        ("boe",           boe.fetch),
        ("ons",           ons.fetch),
        ("google_trends", google_trends.fetch),
        ("open_meteo",    weather.fetch_open_meteo),
        ("land_registry", land_registry.fetch),
        ("bank_holidays", bank_holidays.fetch),
    ]
    sources = {}
    for name, fetcher in _fetchers:
        try:
            sources[name] = fetcher()
        except Exception as e:
            print(f"  [{name}] WARN  {type(e).__name__}: {e} — skipped")

    date_range = pd.date_range(DATE_START, DATE_END, freq=TIME_GRAIN)
    sources["calendar"] = calendar.build_calendar_features(date_range)

    df = align_to_grain(sources)

    df.to_csv("data/processed/control_vars.csv", index=True, index_label="date")
    print(f"Saved {len(df)} rows × {len(df.columns)} control variables to data/processed/control_vars.csv")

    lag_cols = [c for c in df.columns if df[c].isna().any()]
    if lag_cols:
        print(f"Warning: trailing NaNs in {lag_cols} — likely publication lag. Consider forward-filling.")
