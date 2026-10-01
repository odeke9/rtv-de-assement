from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import config  # noqa: E402

# Colour follows the entity, never its rank. Districts: validated categorical order.
# Cycles: one-hue ordinal ramp (light = baseline, dark = latest), validated with --ordinal.
DISTRICT_COLORS = {"Kanungu": "#2a78d6", "Mitooma": "#eb6834", "Rubanda": "#1baf7a", "Rukungiri": "#eda100",
                   "Missing": "#8a8984"}
DISTRICT_ORDER = {"district": list(DISTRICT_COLORS)}
CYCLE_ORDER = [c.label for c in config.CYCLES]
CYCLE_COLORS = dict(zip(CYCLE_ORDER, ["#86b6ef", "#2a78d6", "#104281"]))
SINGLE = "#2a78d6"
# Interview status is a state, so it uses the reserved status palette (with labels, never colour alone).
STATUS_COLORS = {"Found": "#0ca30c", "Unavailable": "#fab219", "Moved away": "#ec835a", "Not found": "#d03b3b",
                 "Disability": "#8a8984", "Missing": "#c3c2b7"}
LAYOUT = dict(template="plotly_white", font=dict(size=13), margin=dict(l=10, r=10, t=80, b=10),
              title_y=0.97, legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text=""))

st.set_page_config(page_title="RTV Survey Progress", layout="wide")

if not config.WAREHOUSE_PATH.exists():
    st.error("Warehouse not found. Run `python -m pipeline.run` first.")
    st.stop()


@st.cache_data(ttl=300)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    # Short-lived read-only connection: the pipeline can rebuild the warehouse while the dashboard runs.
    with duckdb.connect(str(config.WAREHOUSE_PATH), read_only=True) as con:
        return con.execute(sql, list(params)).df()


def with_labels(df: pd.DataFrame) -> pd.DataFrame:
    labels = {c.code: c.label for c in config.CYCLES}
    df["cycle"] = pd.Categorical(df["survey_cycle"].map(labels), CYCLE_ORDER, ordered=True)
    return df.sort_values("cycle")


def chart(fig, hover: str = "closest", **overrides) -> None:
    st.plotly_chart(fig.update_layout(**{**LAYOUT, "hovermode": hover, **overrides}), width="stretch")


def table(df: pd.DataFrame, label: str = "Table view") -> None:
    with st.expander(label):
        st.dataframe(df, width="stretch", hide_index=True)


def ratio(num, den):
    return num / den if den else None


def pct(x) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:.1%}"


# ---------------------------------------------------------------- filters
st.title("RTV household survey: progress and field operations")
st.caption("2021 cohort: Baseline (2020), Year 1 (2022), Year 2 (2023). Metric definitions: docs/METRICS.md")

f1, f2 = st.columns([2, 3])
cycles = f1.multiselect("Survey cycles", CYCLE_ORDER, default=CYCLE_ORDER)
districts_all = q("SELECT DISTINCT district FROM dim_geography ORDER BY 1")["district"].tolist()
districts = f2.multiselect("Districts", districts_all, default=districts_all)
if not cycles or not districts:
    st.warning("Select at least one cycle and one district.")
    st.stop()
codes = tuple(c.code for c in config.CYCLES if c.label in cycles)
in_cycles = f"survey_cycle IN ({','.join('?' * len(codes))})"
in_districts = f"district IN ({','.join('?' * len(districts))})"
params = codes + tuple(districts)

tab_ops, tab_prog, tab_long, tab_dq = st.tabs(["Field operations", "Program summary", "Longitudinal", "Data quality"])

# ---------------------------------------------------------------- Field operations
with tab_ops:
    ops = with_labels(q(f"SELECT * FROM rpt_field_operations WHERE {in_cycles} AND ({in_districts} OR district = 'Missing')",
                        params))
    by_cycle = with_labels(q(f"SELECT * FROM rpt_field_operations_cycle WHERE {in_cycles}", codes))

    m = st.columns(5)
    m[0].metric("Raw submissions", f"{int(ops.submissions_raw.sum()):,}")
    m[1].metric("After deduplication", f"{int(ops.submissions_deduplicated.sum()):,}")
    m[2].metric("Removed as duplicates", f"{int(ops.submissions_superseded.sum()):,}")
    m[3].metric("Missing location", pct(ratio(ops.submissions_missing_location.sum(), ops.submissions_raw.sum())))
    avg_min = ratio(ops.interview_minutes_sum.sum(), ops.interview_minutes_n.sum())
    m[4].metric("Avg interview duration", "n/a" if avg_min is None else f"{avg_min:.0f} min")

    daily = ops.groupby(["cycle", "submission_date", "district"], observed=True, as_index=False).submissions_raw.sum()
    fig = px.bar(daily, x="submission_date", y="submissions_raw", color="district", facet_col="cycle",
                 color_discrete_map=DISTRICT_COLORS, category_orders=DISTRICT_ORDER, title="Submissions per day during fieldwork",
                 labels={"submissions_raw": "Submissions", "submission_date": "", "cycle": ""})
    fig.update_xaxes(matches=None, tickformat="%d %b")
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    chart(fig, margin=dict(l=10, r=10, t=120, b=10), legend={**LAYOUT["legend"], "y": 1.12})
    table(daily)

    c1, c2 = st.columns(2)
    with c1:
        dedup = by_cycle.melt(id_vars="cycle", value_vars=["submissions_raw", "submissions_deduplicated"],
                              var_name="stage", value_name="submissions")
        dedup["stage"] = dedup["stage"].map({"submissions_raw": "Raw", "submissions_deduplicated": "Deduplicated"})
        fig = px.bar(dedup, x="cycle", y="submissions", color="stage", barmode="group",
                     color_discrete_map={"Raw": "#86b6ef", "Deduplicated": "#104281"},
                     title="Deduplication impact by cycle (all districts)", labels={"cycle": "", "submissions": "Submissions"})
        chart(fig)
    with c2:
        rates = by_cycle[["cycle", "duplicate_household_rate", "missing_location_rate", "missing_gps_rate"]].melt(
            id_vars="cycle", var_name="metric", value_name="rate")
        rates["metric"] = rates["metric"].map({"duplicate_household_rate": "Duplicate household rate",
                                               "missing_location_rate": "Missing location rate",
                                               "missing_gps_rate": "Missing GPS rate"})
        fig = px.bar(rates.dropna(), x="metric", y="rate", color="cycle", barmode="group",
                     color_discrete_map=CYCLE_COLORS, title="Data-capture rates by cycle (all districts)", text_auto=".1%",
                     labels={"metric": "", "rate": "Share of submissions"})
        fig.update_yaxes(tickformat=".1%")
        fig.update_traces(textposition="outside", cliponaxis=False)
        chart(fig)
    st.caption("GPS was only collected at baseline, so its rate is not defined for Year 1 and Year 2.")
    table(by_cycle.drop(columns=["survey_cycle", "cycle_order"]), "Per-cycle table")

    status = ops.groupby(["cycle", "interview_status_label"], observed=True, as_index=False).submissions_raw.sum()
    status["share"] = status.submissions_raw / status.groupby("cycle", observed=True).submissions_raw.transform("sum")
    fig = px.bar(status, x="share", y="cycle", color="interview_status_label", orientation="h",
                 color_discrete_map=STATUS_COLORS, text_auto=".0%",
                 title="Interview status mix", labels={"share": "Share of submissions", "cycle": "",
                                                       "interview_status_label": "Status"})
    fig.update_xaxes(tickformat=".0%")
    chart(fig)
    st.caption("Every exported submission has status 'Found': the exports appear to contain completed interviews only.")
    table(status)

# ---------------------------------------------------------------- Program summary
with tab_prog:
    prog = with_labels(q(f"SELECT * FROM rpt_program_summary WHERE {in_cycles} AND {in_districts}", params))
    attempted, completed, consented = (prog[c].sum() for c in
                                       ["households_attempted", "households_completed", "households_consented"])
    m = st.columns(4)
    m[0].metric("Households attempted", f"{int(attempted):,}")
    m[1].metric("Completed", f"{int(completed):,}")
    m[2].metric("Completion rate", pct(ratio(completed, attempted)))
    m[3].metric("Consent rate", pct(ratio(consented, completed)))
    st.info("Completion and consent are 100% in every cycle because the exports only contain interviews where the "
            "household was found and consented. The rates are computed correctly but cannot vary with this data.")

    fig = px.bar(prog, x="year_month", y="households_completed", color="district", barmode="group",
                 color_discrete_map=DISTRICT_COLORS, category_orders=DISTRICT_ORDER, title="Completed interviews by district and month",
                 labels={"year_month": "", "households_completed": "Completed households"})
    fig.update_xaxes(type="category", categoryorder="category ascending")
    chart(fig)
    rate_table = prog.pivot_table(index="district", columns=["cycle", "year_month"],
                                  values=["completion_rate", "consent_rate"], observed=True).round(3)
    table(rate_table.reset_index(), "Completion and consent rate by district and month")

    demo = with_labels(q(f"SELECT * FROM rpt_program_demographics WHERE {in_cycles} AND {in_districts}", params))
    dim = st.selectbox("Demographic", sorted(demo["dimension"].unique()))
    d = demo[demo.dimension == dim].groupby(["cycle", "category"], observed=True, as_index=False).households.sum()
    d["share"] = d.households / d.groupby("cycle", observed=True).households.transform("sum")
    fig = px.bar(d, x="category", y="share", color="cycle", barmode="group", color_discrete_map=CYCLE_COLORS,
                 title=f"{dim}: completed and consented households", labels={"share": "Share of households", "category": ""},
                 category_orders={"category": sorted(d.category.unique(), key=lambda c: (c == "Unknown", c))})
    fig.update_yaxes(tickformat=".0%")
    chart(fig)
    table(d)

    summary = with_labels(q(f"SELECT * FROM rpt_program_cycle WHERE {in_cycles}", codes))
    st.subheader("Comparison across cycles (all districts)")
    st.dataframe(summary.drop(columns=["survey_cycle", "cycle_order"]).set_index("cycle"), width="stretch")

# ---------------------------------------------------------------- Longitudinal
with tab_long:
    cov = q("SELECT * FROM rpt_cohort_coverage")
    for c in config.CYCLES:
        cov["cycle_pattern"] = cov["cycle_pattern"].str.replace(c.code, c.label)
    m = st.columns(3)
    for i, n in enumerate([1, 2, 3]):
        m[i].metric(f"Households seen in {n} cycle{'s' if n > 1 else ''}", f"{int(cov[cov.n_cycles == n].households.sum()):,}")
    fig = px.bar(cov.sort_values("households"), x="households", y="cycle_pattern", orientation="h",
                 color_discrete_sequence=[SINGLE], title="Households by the cycles they were observed in",
                 labels={"households": "Households", "cycle_pattern": ""})
    chart(fig)
    table(cov)

    panel = with_labels(q(f"SELECT * FROM rpt_panel_poverty WHERE {in_cycles} AND {in_districts}", params))
    n_panel = int(panel[panel.survey_cycle == panel.survey_cycle.iloc[0]].households.sum()) if len(panel) else 0
    st.subheader(f"Balanced panel: {n_panel} households observed in all three cycles")
    fig = px.line(panel, x="cycle", y="median_hhip_usd_day", color="district", markers=True,
                  color_discrete_map=DISTRICT_COLORS, category_orders=DISTRICT_ORDER, title="Median household income + production per day (USD)",
                  labels={"median_hhip_usd_day": "USD per day", "cycle": ""})
    fig.add_hline(y=config.TARGET_USD_DAY, line_dash="dot", annotation_text=f"${config.TARGET_USD_DAY:g}/day target",
                  annotation_position="top left")
    chart(fig, hover="x unified")
    table(panel.drop(columns=["survey_cycle", "cycle_order"]))
    st.caption("The panel compares the same households over time; the full samples differ per cycle "
               "(1,414 / 3,796 / 3,852 households), so their averages mix programme change with sample change.")

# ---------------------------------------------------------------- Data quality
with tab_dq:
    dq = q('SELECT "check", severity, passed, failed, total, fail_pct, detail FROM dq_results')
    m = st.columns(3)
    m[0].metric("Checks", len(dq))
    m[1].metric("Warnings failing", int(((dq.severity == "warn") & ~dq.passed).sum()))
    m[2].metric("Errors failing", int(((dq.severity == "error") & ~dq.passed).sum()))
    st.dataframe(dq, width="stretch", hide_index=True)
    st.caption("Quarantined rows")
    st.dataframe(q("SELECT survey_cycle, reject_reason, count(*) AS rows FROM stg_quarantine GROUP BY ALL ORDER BY 1"),
                 hide_index=True)
    st.caption("Variables used in Silver and Gold, with their source column per cycle")
    st.dataframe(q("SELECT canonical_name, survey_cycle, source_column, dtype, label, null_rate, notes "
                   "FROM meta_silver_variable ORDER BY 1, 2"), width="stretch", hide_index=True)
    st.caption("Recent pipeline runs")
    st.dataframe(q("SELECT * FROM ops_pipeline_runs ORDER BY logged_at DESC LIMIT 20"), width="stretch", hide_index=True)
