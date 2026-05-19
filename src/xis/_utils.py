"""Shared DataFrame and serialisation helpers."""
import math
import pandas as pd


def clean_val(v):
    """Coerce NaN/inf/numpy scalars/Timestamps to JSON-serialisable Python natives."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "item"):  # numpy scalar
        return v.item()
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v


def df_to_clean_records(df: pd.DataFrame, schema_cols: set) -> list[dict]:
    """
    Filter a DataFrame to only schema-allowed columns and coerce all values
    to JSON-safe Python natives.
    """
    cols = [c for c in schema_cols if c in df.columns]
    if not cols:
        return []
    raw = df[cols].to_dict(orient="records")
    return [{k: clean_val(v) for k, v in row.items()} for row in raw]
