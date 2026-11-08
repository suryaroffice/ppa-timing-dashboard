"""PPA / Timing dashboard.  Run with:  streamlit run app.py"""
from pathlib import Path

import plotly.express as px
import streamlit as st

from ppa_parser import build_dataframe
from ppa_parser.views import chart_frame, is_sample, summary

st.set_page_config(page_title="PPA Timing Dashboard", layout="wide")
st.title("PPA / Timing Dashboard")
st.caption("Power, performance (timing) and area across runs, parsed from OpenROAD/OpenSTA-style reports.")

folder = st.sidebar.text_input("Reports folder", "sample_reports")
files = sorted(Path(folder).glob("*.rpt"))
if not files:
    st.warning(f"No *.rpt files found in '{folder}'.")
    st.stop()

if any(is_sample(f) for f in files):
    st.info("Some or all of these reports are hand-written sample data, not real tool output.")

df = build_dataframe(files)
design = st.sidebar.selectbox("Design", sorted(df["design"].unique()))
d = chart_frame(df, design)
if d.empty:
    st.warning("No runs with a known clock period for this design.")
    st.stop()

s = summary(d)
c1, c2, c3 = st.columns(3)
c1.metric("Runs", s["runs"])
c2.metric("Runs meeting timing", s["runs_meeting_timing"])
c3.metric(
    "Fastest passing period (ns)",
    "none" if s["fastest_passing_period_ns"] is None else f"{s['fastest_passing_period_ns']:.2f}",
)

st.subheader("Timing vs clock period")
st.caption(
    "Worst slack shows the real margin. WNS is clamped at 0 when timing is met, "
    "so it only goes negative on failing runs. TNS sums every failing path."
)
fig = px.line(
    d,
    x="clock_period_ns",
    y=["worst_slack_ns", "wns_ns", "tns_ns"],
    markers=True,
    labels={"clock_period_ns": "Clock period (ns)", "value": "Slack (ns)", "variable": "Metric"},
)
fig.add_hline(y=0, line_dash="dash", line_color="gray")
st.plotly_chart(fig, use_container_width=True)

left, right = st.columns(2)
with left:
    st.subheader("Power vs clock period")
    fig_p = px.line(
        d,
        x="clock_period_ns",
        y=["power_total_mw", "power_dynamic_mw", "power_leakage_mw"],
        markers=True,
        labels={"clock_period_ns": "Clock period (ns)", "value": "Power (mW)", "variable": ""},
    )
    st.plotly_chart(fig_p, use_container_width=True)
with right:
    st.subheader("Area vs clock period")
    fig_a = px.line(
        d,
        x="clock_period_ns",
        y="area_um2",
        markers=True,
        labels={"clock_period_ns": "Clock period (ns)", "area_um2": "Design area (um^2)"},
    )
    st.plotly_chart(fig_a, use_container_width=True)

st.subheader("All runs")
st.dataframe(d, use_container_width=True)
