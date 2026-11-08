"""Pure-pandas helpers for the dashboard (no streamlit/plotly imports, so
they can be unit tested anywhere)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def is_sample(path) -> bool:
    """True if a report file declares itself hand-written sample data."""
    try:
        return "SAMPLE DATA" in Path(path).read_text(errors="replace")[:300]
    except OSError:
        return False


def chart_frame(df: pd.DataFrame, design: str) -> pd.DataFrame:
    """Rows for one design with a known clock period, sorted by period."""
    if df.empty:
        return df
    d = df[df["design"] == design]
    return d.dropna(subset=["clock_period_ns"]).sort_values("clock_period_ns")


def summary(d: pd.DataFrame) -> dict:
    """Headline numbers for a single design's sweep."""
    met = d[d["timing_met"].fillna(False).astype(bool)]
    return {
        "runs": int(len(d)),
        "runs_meeting_timing": int(len(met)),
        # Shortest clock period that still met timing in the data we have.
        "fastest_passing_period_ns": (
            float(met["clock_period_ns"].min()) if len(met) else None
        ),
    }
