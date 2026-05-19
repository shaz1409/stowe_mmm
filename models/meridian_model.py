# meridian_model.py
# Meridian model configuration and execution.
# Called from 03_model.py
#
# Outputs: outputs/meridian/

import pandas as pd

def configure(df: pd.DataFrame, features: list[str]) -> dict:
    """Build the Meridian input config (priors, geo settings, time grain, etc.)."""
    raise NotImplementedError

def run(df: pd.DataFrame, features: list[str]):
    """Fit Meridian model and save posterior + diagnostics to outputs/meridian/."""
    config = configure(df, features)
    raise NotImplementedError
