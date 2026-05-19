# robyn_model.py
# Robyn model configuration and execution.
# Called from 03_model.py
#
# Outputs: outputs/robyn/

import pandas as pd

def configure(df: pd.DataFrame, features: list[str]) -> dict:
    """Build the Robyn input config (hyperparameter bounds, adstock type, etc.)."""
    raise NotImplementedError

def run(df: pd.DataFrame, features: list[str]):
    """Run Robyn trials and save all model objects to outputs/robyn/."""
    config = configure(df, features)
    raise NotImplementedError
