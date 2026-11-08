from pathlib import Path

import pytest

from ppa_parser import build_dataframe
from ppa_parser.views import chart_frame, is_sample, summary

SAMPLES = Path(__file__).resolve().parent.parent / "sample_reports"


def _df():
    return build_dataframe(sorted(SAMPLES.glob("*.rpt")))


def test_sample_files_are_detected_as_sample(tmp_path):
    assert is_sample(SAMPLES / "gcd_clk1.0.rpt")
    real = tmp_path / "real.rpt"
    real.write_text("wns 0.00\n")
    assert not is_sample(real)
    assert not is_sample(tmp_path / "missing.rpt")


def test_chart_frame_filters_design_and_sorts():
    d = chart_frame(_df(), "gcd")
    assert list(d["clock_period_ns"]) == [1.0, 1.2, 1.5, 2.0]
    assert chart_frame(_df(), "nope").empty


def test_summary_headline_numbers():
    s = summary(chart_frame(_df(), "gcd"))
    assert s["runs"] == 4
    assert s["runs_meeting_timing"] == 2
    assert s["fastest_passing_period_ns"] == pytest.approx(1.5)


def test_summary_with_no_passing_runs():
    d = chart_frame(_df(), "gcd")
    failing = d[d["clock_period_ns"] < 1.5]
    s = summary(failing)
    assert s["runs_meeting_timing"] == 0
    assert s["fastest_passing_period_ns"] is None
