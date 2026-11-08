"""Parse OpenROAD / OpenSTA-style PPA report text into flat records.

Design rules:
  * Take values straight from the tool's report. Never recompute slack/WNS/TNS.
  * Anything missing from a report becomes NaN (numbers) or None (text),
    never 0, so a run without a power report doesn't claim 0 mW.

Formats handled (verify against real files from your own runs):
  report_wns          ->  "wns -0.31"
  report_tns          ->  "tns -4.20"
  report_worst_slack  ->  "worst slack -0.41"
  report_design_area  ->  "Design area 438 u^2 7% utilization."
  yosys stat          ->  "Chip area for module '\\top': 305.368000"  (fallback)
  report_power        ->  table with a "Total" row, in Watts
  report_checks       ->  "Startpoint: ...", "Endpoint: ...", "-0.41   slack (VIOLATED)"

Note: report_wns reports the worst NEGATIVE slack and clamps at 0 when
timing is met, so a design with +0.35 ns of margin shows wns 0.00. Use
worst_slack_ns to see the real margin.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

NAN = float("nan")
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"

_RE_WNS = re.compile(rf"^\s*wns\s+(?:(?:max|min)\s+)?({_NUM})\s*$", re.M)
_RE_TNS = re.compile(rf"^\s*tns\s+(?:(?:max|min)\s+)?({_NUM})\s*$", re.M)
_RE_WORST_SLACK = re.compile(
    rf"^\s*worst slack\s+(?:(?:max|min)\s+)?({_NUM})\s*$", re.M
)
_RE_AREA = re.compile(
    rf"Design area\s+({_NUM})\s+u\^2\s+({_NUM})%\s+utilization"
)
# Yosys `stat -liberty` output: synthesized cell area (um^2 for nangate45).
_RE_YOSYS_AREA = re.compile(rf"Chip area for module\s+'[^']*':\s+({_NUM})")
_RE_SLACK_LINE = re.compile(rf"^\s*({_NUM})\s+slack\s+\((?:MET|VIOLATED)\)", re.M)
_RE_STARTPOINT = re.compile(r"^Startpoint:\s*(\S+)", re.M)
_RE_ENDPOINT = re.compile(r"^Endpoint:\s*(\S+)", re.M)
# OpenSTA report_power "Total" row: internal, switching, leakage, total (Watts)
_RE_POWER_TOTAL = re.compile(
    rf"^Total\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})", re.M
)
_RE_CLK_IN_NAME = re.compile(r"_clk(\d+(?:\.\d+)?)")

W_TO_MW = 1e3


def _first_float(pattern: "re.Pattern[str]", text: str) -> float:
    m = pattern.search(text)
    return float(m.group(1)) if m else NAN


def parse_report(
    text: str,
    run_id: str = "",
    design: str = "",
    clock_period_ns: Optional[float] = None,
) -> dict:
    """Parse one run's report text into a flat dict of metrics."""
    wns = _first_float(_RE_WNS, text)
    tns = _first_float(_RE_TNS, text)

    worst_slack = _first_float(_RE_WORST_SLACK, text)
    if math.isnan(worst_slack):
        # Fallback: smallest slack printed by report_checks.
        slacks = [float(s) for s in _RE_SLACK_LINE.findall(text)]
        worst_slack = min(slacks) if slacks else NAN

    start = _RE_STARTPOINT.search(text)
    end = _RE_ENDPOINT.search(text)

    area = NAN
    util = NAN
    area_source = None
    m = _RE_AREA.search(text)
    if m:
        area, util = float(m.group(1)), float(m.group(2))
        area_source = "design_area"  # OpenROAD report_design_area
    else:
        m = _RE_YOSYS_AREA.search(text)
        if m:
            area = float(m.group(1))
            area_source = "yosys_stat"  # synthesized cell area, no placement

    p_int = p_sw = p_leak = p_total = NAN
    m = _RE_POWER_TOTAL.search(text)
    if m:
        p_int, p_sw, p_leak, p_total = (float(g) * W_TO_MW for g in m.groups())

    return {
        "run_id": run_id,
        "design": design,
        "clock_period_ns": NAN if clock_period_ns is None else float(clock_period_ns),
        "wns_ns": wns,
        "tns_ns": tns,
        "worst_slack_ns": worst_slack,
        "worst_path_start": start.group(1) if start else None,
        "worst_path_end": end.group(1) if end else None,
        "power_total_mw": p_total,
        "power_dynamic_mw": (
            p_int + p_sw if not (math.isnan(p_int) or math.isnan(p_sw)) else NAN
        ),
        "power_leakage_mw": p_leak,
        "area_um2": area,
        "area_source": area_source,
        "utilization_pct": util,
    }


def parse_file(path: Union[str, Path], clock_period_ns: Optional[float] = None) -> dict:
    """Parse a report file. Run id is the file stem; design and clock period
    are inferred from names like 'gcd_clk1.5.rpt' unless given explicitly."""
    path = Path(path)
    text = path.read_text(errors="replace")
    stem = path.stem
    design = stem.split("_clk")[0]
    if clock_period_ns is None:
        m = _RE_CLK_IN_NAME.search(stem)
        if m:
            clock_period_ns = float(m.group(1))
    return parse_report(text, run_id=stem, design=design, clock_period_ns=clock_period_ns)


def build_dataframe(paths) -> pd.DataFrame:
    """One row per report file, plus derived columns."""
    df = pd.DataFrame([parse_file(p) for p in paths])
    if df.empty:
        return df
    # Met if the real worst slack is non-negative; else fall back to WNS.
    basis = df["worst_slack_ns"].where(df["worst_slack_ns"].notna(), df["wns_ns"])
    # A printed "-0.00" is a slightly negative value that rounded to zero, so
    # it is a failing run even though -0.0 >= 0. Check the sign bit explicitly.
    negative = pd.Series(
        np.signbit(basis.fillna(0).to_numpy(dtype=float)), index=basis.index
    )
    # Nullable boolean: unknown (no slack data at all) stays <NA>, not False.
    df["timing_met"] = ((basis >= 0) & ~negative).astype("boolean").mask(basis.isna())
    # First-order estimate: the period the design could close at is
    # (period - worst slack). Rough, since it ignores re-optimization.
    achievable = df["clock_period_ns"] - df["worst_slack_ns"]
    df["est_fmax_mhz"] = 1000.0 / achievable.where(achievable > 0)
    return df.sort_values(["design", "clock_period_ns"]).reset_index(drop=True)
