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
    raise NotImplementedError


def main():
    sources = {
        "oecd":          oecd.fetch(),
        "boe":           boe.fetch(),
        "ons":           ons.fetch(),
        "google_trends": google_trends.fetch(),
        "open_meteo":    weather.fetch_open_meteo(),
        "land_registry": land_registry.fetch(),
        "bank_holidays": bank_holidays.fetch(),
    }

    date_range = pd.date_range(DATE_START, DATE_END, freq=TIME_GRAIN)
    sources["calendar"] = calendar.build_calendar_features(date_range)

    df = align_to_grain(sources)

    df.to_csv("data/processed/control_vars.csv", index=True, index_label="date")
    print(f"Saved {len(df)} rows × {len(df.columns)} control variables to data/processed/control_vars.csv")

    lag_cols = [c for c in df.columns if df[c].isna().any()]
    if lag_cols:
        print(f"Warning: trailing NaNs in {lag_cols} — likely publication lag. Consider forward-filling.")
