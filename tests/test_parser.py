import math
from pathlib import Path

import pandas as pd
import pytest

from ppa_parser import build_dataframe, parse_file, parse_report

SAMPLES = Path(__file__).resolve().parent.parent / "sample_reports"

MET_SNIPPET = """
tns 0.00
wns 0.00
worst slack 0.35
Design area 438 u^2 7% utilization.
"""

VIOLATED_SNIPPET = """
tns -2.90
wns -0.18
worst slack -0.18
"""

POWER_SNIPPET = """
Group                  Internal  Switching    Leakage      Total
                          Power      Power      Power      Power (Watts)
----------------------------------------------------------------
Sequential             2.10e-04   1.56e-05   6.50e-07   2.26e-04
----------------------------------------------------------------
Total                  3.50e-04   5.20e-05   1.30e-06   4.03e-04 100.0%
"""

CHECKS_ONLY_SNIPPET = """
Startpoint: _412_ (rising edge-triggered flip-flop clocked by core_clock)
Endpoint: _455_ (rising edge-triggered flip-flop clocked by core_clock)
        -0.18   slack (VIOLATED)

Startpoint: _500_ (rising edge-triggered flip-flop clocked by core_clock)
Endpoint: _501_ (rising edge-triggered flip-flop clocked by core_clock)
         0.40   slack (MET)
"""


def test_wns_tns_worst_slack_parsed_from_violated_run():
    r = parse_report(VIOLATED_SNIPPET)
    assert r["wns_ns"] == pytest.approx(-0.18)
    assert r["tns_ns"] == pytest.approx(-2.90)
    assert r["worst_slack_ns"] == pytest.approx(-0.18)


def test_wns_is_clamped_but_worst_slack_keeps_real_margin():
    # report_wns prints 0.00 when timing is met; worst slack shows the margin.
    r = parse_report(MET_SNIPPET)
    assert r["wns_ns"] == 0.0
    assert r["worst_slack_ns"] == pytest.approx(0.35)


def test_area_and_utilization():
    r = parse_report(MET_SNIPPET)
    assert r["area_um2"] == pytest.approx(438)
    assert r["utilization_pct"] == pytest.approx(7)


def test_power_converted_from_watts_to_mw():
    r = parse_report(POWER_SNIPPET)
    assert r["power_total_mw"] == pytest.approx(0.403)
    assert r["power_leakage_mw"] == pytest.approx(0.0013)
    assert r["power_dynamic_mw"] == pytest.approx(0.402)  # internal + switching


def test_missing_power_is_nan_not_zero():
    r = parse_report(MET_SNIPPET)
    assert math.isnan(r["power_total_mw"])
    assert math.isnan(r["power_dynamic_mw"])


def test_empty_text_gives_nans_and_no_crash():
    r = parse_report("")
    assert math.isnan(r["wns_ns"])
    assert math.isnan(r["area_um2"])
    assert r["worst_path_start"] is None


def test_worst_slack_falls_back_to_report_checks_and_captures_path():
    r = parse_report(CHECKS_ONLY_SNIPPET)
    assert r["worst_slack_ns"] == pytest.approx(-0.18)
    assert r["worst_path_start"] == "_412_"
    assert r["worst_path_end"] == "_455_"


def test_run_id_design_and_clock_period_inferred_from_filename():
    r = parse_file(SAMPLES / "gcd_clk1.5.rpt")
    assert r["run_id"] == "gcd_clk1.5"
    assert r["design"] == "gcd"
    assert r["clock_period_ns"] == pytest.approx(1.5)


def test_explicit_clock_period_overrides_filename():
    r = parse_file(SAMPLES / "gcd_clk1.5.rpt", clock_period_ns=9.9)
    assert r["clock_period_ns"] == pytest.approx(9.9)


def test_dataframe_sorted_and_timing_met_flag():
    df = build_dataframe(sorted(SAMPLES.glob("*.rpt")))
    assert list(df["clock_period_ns"]) == [1.0, 1.2, 1.5, 2.0]
    assert list(df["timing_met"]) == [False, False, True, True]


def test_dataframe_derived_fmax_and_columns():
    df = build_dataframe(sorted(SAMPLES.glob("*.rpt")))
    row = df[df["clock_period_ns"] == 2.0].iloc[0]
    # period 2.0, worst slack 0.35 -> ~1.65 ns achievable -> ~606 MHz
    assert row["est_fmax_mhz"] == pytest.approx(1000 / 1.65)
    for col in ("wns_ns", "tns_ns", "power_total_mw", "area_um2", "timing_met"):
        assert col in df.columns


def test_wns_gets_worse_as_clock_period_shrinks():
    df = build_dataframe(sorted(SAMPLES.glob("*.rpt")))
    slacks = df.sort_values("clock_period_ns")["worst_slack_ns"].tolist()
    assert slacks == sorted(slacks)  # smaller period -> smaller (worse) slack


def test_empty_input_returns_empty_dataframe():
    assert isinstance(build_dataframe([]), pd.DataFrame)
    assert build_dataframe([]).empty


FIXTURES = Path(__file__).resolve().parent / "fixtures"
YOSYS_STAT = "=== top ===\n   Chip area for module '\\top': 305.368000\n"


def test_real_opensta_output_format():
    # Fixture is output captured from a real OpenSTA run (adder16 @ 1.0 ns).
    text = (FIXTURES / "opensta_adder16_clk1.0.txt").read_text()
    r = parse_report(text, clock_period_ns=1.0)
    assert r["wns_ns"] == 0.0
    assert r["tns_ns"] == 0.0
    assert r["worst_slack_ns"] == pytest.approx(0.30)
    assert r["worst_path_start"] == "_202_"
    assert r["worst_path_end"] == "_200_"
    assert r["power_total_mw"] == pytest.approx(0.307)
    assert r["power_dynamic_mw"] == pytest.approx(0.3009)
    assert r["power_leakage_mw"] == pytest.approx(0.00589)
    assert math.isnan(r["area_um2"])  # OpenSTA reports no area
    assert r["area_source"] is None


def test_area_from_yosys_stat_when_no_design_area():
    r = parse_report("wns max 0.00\n" + YOSYS_STAT)
    assert r["area_um2"] == pytest.approx(305.368)
    assert r["area_source"] == "yosys_stat"
    assert math.isnan(r["utilization_pct"])


def test_design_area_line_takes_precedence_over_yosys():
    r = parse_report(MET_SNIPPET + YOSYS_STAT)
    assert r["area_um2"] == pytest.approx(438)
    assert r["area_source"] == "design_area"


def test_negative_zero_slack_counts_as_failing(tmp_path):
    # OpenSTA prints "-0.00" for a slightly negative value that rounds to zero.
    f = tmp_path / "d_clk0.7.rpt"
    f.write_text("tns max -0.00\nwns max -0.00\nworst slack max -0.00\n")
    df = build_dataframe([f])
    assert bool(df.loc[0, "timing_met"]) is False


def test_positive_zero_slack_counts_as_met(tmp_path):
    f = tmp_path / "d_clk0.7.rpt"
    f.write_text("tns max 0.00\nwns max 0.00\nworst slack max 0.00\n")
    df = build_dataframe([f])
    assert bool(df.loc[0, "timing_met"]) is True


def test_no_slack_data_leaves_timing_met_unknown(tmp_path):
    f = tmp_path / "d_clk1.0.rpt"
    f.write_text("nothing useful here\n")
    df = build_dataframe([f])
    assert pd.isna(df.loc[0, "timing_met"])
