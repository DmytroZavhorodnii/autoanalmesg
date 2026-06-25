"""
Loads and filters the MessageCenters Excel file.
Required columns: ID, Created, FullMessage (Modified optional).
"""

import pandas as pd
from typing import Optional
import app.config as cfg


def load_messages(
    file_path: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: Optional[int] = cfg.DEFAULT_LIMIT,
) -> pd.DataFrame:
    """
    Read Excel and apply date range + row-count filters.
    date_from / date_to: ISO strings 'YYYY-MM-DD' (inclusive).
    Raises ValueError on missing required columns.
    """
    df = pd.read_excel(file_path)

    required = {"ID", "Created", "FullMessage"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    cols = ["ID", "Created", "FullMessage"]
    if "Modified" in df.columns:
        cols.insert(2, "Modified")
    df = df[cols].copy()

    df["Created"] = pd.to_datetime(df["Created"], errors="coerce")
    if "Modified" in df.columns:
        df["Modified"] = pd.to_datetime(df["Modified"], errors="coerce")

    if date_from:
        try:
            df = df[df["Created"] >= pd.Timestamp(date_from)]
        except Exception:
            pass

    if date_to:
        try:
            # include the full date_to day
            df = df[df["Created"] <= pd.Timestamp(date_to) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]
        except Exception:
            pass

    df = df[df["FullMessage"].notna() & (df["FullMessage"].str.strip() != "")]
    df = df.sort_values("Created", ascending=False).reset_index(drop=True)

    if limit is not None and limit < len(df):
        df = df.head(limit)

    return df
