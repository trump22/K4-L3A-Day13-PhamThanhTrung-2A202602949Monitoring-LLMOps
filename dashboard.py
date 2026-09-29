from __future__ import annotations

import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from app.langfuse_dashboard import fetch_langfuse_dashboard_metrics


LOG_PATH = Path("data/logs.jsonl")


@st.cache_data(ttl=30, show_spinner="Loading structured logs...")
def load_logs(path: str, modified_ns: int) -> pd.DataFrame:
    """Load only structured fields needed by the six dashboard panels."""

    records: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))

    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="coerce")
    return frame.dropna(subset=["ts"])


def percentile(values: pd.Series, q: float) -> float:
    clean = values.dropna()
    return float(clean.quantile(q)) if not clean.empty else 0.0


def time_series(frame: pd.DataFrame, value: str, aggregation: str = "sum") -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["minute", value])
    series = frame.set_index("ts")[value]
    result = series.resample("1min").sum() if aggregation == "sum" else series.resample("1min").mean()
    return result.reset_index().rename(columns={"ts": "minute"})


def latency_time_series(responses: pd.DataFrame) -> pd.DataFrame:
    """Return per-minute latency and TTFT percentiles for the trend chart."""
    if responses.empty:
        return pd.DataFrame(columns=["minute", "measure", "latency_ms"])

    per_minute = responses.set_index("ts").resample("1min").agg(
        p50=("latency_ms", lambda values: values.quantile(0.50)),
        p95=("latency_ms", lambda values: values.quantile(0.95)),
        p99=("latency_ms", lambda values: values.quantile(0.99)),
        ttft_p95=("ttft_ms", lambda values: values.quantile(0.95)),
    )
    per_minute.index.name = "minute"
    return (
        per_minute.dropna(how="all")
        .reset_index()
        .melt(id_vars="minute", var_name="measure", value_name="latency_ms")
        .dropna(subset=["latency_ms"])
    )


def chart_with_threshold(
    data: pd.DataFrame,
    y: str,
    threshold: float | None,
    title: str,
) -> None:
    if data.empty:
        st.info("No data in the available history.")
        return
    line = alt.Chart(data).mark_line(point=True).encode(
        x=alt.X("minute:T", title="Time"),
        y=alt.Y(f"{y}:Q", title=title),
        tooltip=[alt.Tooltip("minute:T", title="Time"), alt.Tooltip(f"{y}:Q", title=title)],
    )
    if threshold is None:
        st.altair_chart(line)
        return
    rule = alt.Chart(pd.DataFrame({"threshold": [threshold]})).mark_rule(color="#d9534f").encode(
        y=alt.Y("threshold:Q", title=title),
        tooltip=[alt.Tooltip("threshold:Q", title="Threshold")],
    )
    st.altair_chart(line + rule)


def latency_chart(data: pd.DataFrame) -> None:
    if data.empty:
        st.info("No data in the available history.")
        return
    latency_data = data[data["measure"].isin(["p50", "p95", "p99"])]
    ttft_data = data[data["measure"] == "ttft_p95"]
    latency_lines = alt.Chart(latency_data).mark_line(point=True).encode(
        x=alt.X("minute:T", title="Time"),
        y=alt.Y("latency_ms:Q", title="Latency (ms)"),
        color=alt.Color("measure:N", title="Measure"),
        tooltip=[
            alt.Tooltip("minute:T", title="Time"),
            alt.Tooltip("measure:N", title="Measure"),
            alt.Tooltip("latency_ms:Q", title="Latency (ms)", format=".1f"),
        ],
    )
    rule = alt.Chart(pd.DataFrame({"threshold": [3000]})).mark_rule(
        color="#d9534f"
    ).encode(
        y=alt.Y("threshold:Q", title="Latency (ms)"),
        tooltip=[alt.Tooltip("threshold:Q", title="P95 SLO threshold")],
    )
    ttft_line = alt.Chart(ttft_data).mark_line(point=True, color="#8c6bb1").encode(
        x=alt.X("minute:T", title="Time"),
        y=alt.Y("latency_ms:Q", title="TTFT P95 (ms)"),
        tooltip=[
            alt.Tooltip("minute:T", title="Time"),
            alt.Tooltip("latency_ms:Q", title="TTFT P95 (ms)", format=".1f"),
        ],
    )
    st.altair_chart(
        alt.vconcat((latency_lines + rule).properties(height=180), ttft_line.properties(height=90))
        .resolve_scale(x="shared")
    )


def main() -> None:
    st.set_page_config(
        page_title="LLMOps monitoring dashboard",
        page_icon=":material/monitoring:",
        layout="wide",
    )
    st.title("LLMOps monitoring dashboard")
    st.caption("Source: `data/logs.jsonl` + Langfuse Cloud · all available history · refresh: every 30 seconds")

    render_dashboard()


@st.fragment(run_every=30)
def render_dashboard() -> None:

    if not LOG_PATH.exists():
        st.error("`data/logs.jsonl` does not exist. Start the API and send requests first.")
        return

    logs = load_logs(str(LOG_PATH), LOG_PATH.stat().st_mtime_ns)
    if logs.empty:
        st.warning("No valid JSON log records are available.")
        return

    langfuse_metrics = cached_langfuse_metrics()
    if langfuse_metrics["available"]:
        st.caption("Cloud aggregates: Langfuse Metrics API · request details and fallback: data/logs.jsonl · all available history")
    else:
        st.caption(f"Langfuse Cloud metrics unavailable; showing local runtime logs. {langfuse_metrics['reason']}")

    responses = logs[logs["event"] == "response_sent"].copy()
    requests = logs[logs["event"] == "request_received"].copy()
    failures = logs[logs["event"] == "request_failed"].copy()

    latency = latency_time_series(responses)
    traffic = requests.set_index("ts").resample("1min").size().reset_index(name="requests") if not requests.empty else pd.DataFrame(columns=["ts", "requests"])
    traffic = traffic.rename(columns={"ts": "minute"})
    costs = time_series(responses, "cost_usd")
    tokens = responses.set_index("ts")[["tokens_in", "tokens_out"]].resample("1min").sum().reset_index().rename(columns={"ts": "minute"}) if not responses.empty else pd.DataFrame(columns=["minute", "tokens_in", "tokens_out"])
    quality = time_series(responses, "quality_score", aggregation="mean")

    retrieval_rows = logs[logs["tool_success"].notna()].copy() if "tool_success" in logs else pd.DataFrame()
    retrieval_success = (
        float(retrieval_rows["tool_success"].mean() * 100)
        if not retrieval_rows.empty
        else None
    )
    error_rate = len(failures) / len(requests) * 100 if len(requests) else None

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.subheader("1. Latency percentiles and TTFT")
            if responses.empty:
                st.metric("Latency P50 / P95 / P99", "N/A")
                st.metric("TTFT P95", "N/A")
            else:
                p50, p95, p99 = (percentile(responses["latency_ms"], value) for value in (0.50, 0.95, 0.99))
                ttft_p95 = percentile(responses["ttft_ms"], 0.95)
                st.metric("Latency P50 / P95 / P99", f"{p50:.0f} / {p95:.0f} / {p99:.0f} ms")
                st.metric("TTFT P95", f"{ttft_p95:.0f} ms")
            if langfuse_metrics["available"]:
                cloud_latency = [langfuse_metrics.get(f"latency_p{p}") for p in (50, 95, 99)]
                if all(value is not None for value in cloud_latency):
                    st.caption("Langfuse root latency P50 / P95 / P99: " + " / ".join(f"{value:.0f}" for value in cloud_latency) + " ms")
                cloud_ttft = langfuse_metrics.get("ttft_p95")
                st.caption(f"Langfuse generation TTFT P95: {cloud_ttft:.0f} ms" if cloud_ttft is not None else "Langfuse generation TTFT P95: N/A")
            st.caption("SLO line: latency P95 ≤ 3000 ms")
            latency_chart(latency)

    with right:
        with st.container(border=True):
            st.subheader("2. Request traffic")
            st.metric("Requests in logs", len(requests))
            if langfuse_metrics["available"]:
                cloud_count = langfuse_metrics.get("trace_count")
                st.caption(f"Langfuse root traces: {cloud_count:.0f}" if cloud_count is not None else "Langfuse root traces: N/A")
            st.caption("Threshold: at least 1 request per minute during a load test")
            chart_with_threshold(traffic, "requests", 1, "Requests per minute")

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.subheader("3. Error rate and retrieval success")
            st.metric("Error rate", f"{error_rate:.2f}%" if error_rate is not None else "N/A")
            st.metric(
                "Retrieval success",
                f"{retrieval_success:.2f}%" if retrieval_success is not None else "N/A",
            )
            if langfuse_metrics["available"]:
                cloud_error_rate = langfuse_metrics.get("error_rate_pct")
                cloud_retrieval_success = langfuse_metrics.get("retrieval_success_pct")
                st.caption(
                    f"Langfuse root error rate: {cloud_error_rate:.2f}%"
                    if cloud_error_rate is not None
                    else "Langfuse root error rate: N/A"
                )
                st.caption(
                    f"Langfuse retrieval success: {cloud_retrieval_success:.2f}% ({langfuse_metrics.get('retrieval_count') or 0:.0f} spans)"
                    if cloud_retrieval_success is not None
                    else "Langfuse retrieval success: N/A"
                )
            st.caption("Thresholds: error rate ≤ 2% · retrieval success ≥ 90%")
            if requests.empty:
                st.info("No request data in the available history.")
            elif failures.empty:
                st.success("No failed requests in the available history.")
            else:
                st.bar_chart(failures["error_type"].fillna("unknown").value_counts())

    with right:
        with st.container(border=True):
            st.subheader("4. Cost over time")
            total_cost = float(responses["cost_usd"].fillna(0).sum()) if not responses.empty else 0.0
            st.metric("Total cost", f"${total_cost:.4f}")
            if langfuse_metrics["available"]:
                cloud_cost = langfuse_metrics.get("cost_usd")
                st.caption(f"Langfuse generation cost: ${cloud_cost:.4f}" if cloud_cost is not None else "Langfuse generation cost: N/A")
            st.caption("Threshold: total cost ≤ $2.50 across available history")
            # Drawing the all-history total threshold against a per-minute
            # series creates a misleading scale and comparison.
            chart_with_threshold(costs, "cost_usd", None, "Cost per minute (USD)")

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.subheader("5. Input and output tokens")
            total_in = int(responses["tokens_in"].fillna(0).sum()) if not responses.empty else 0
            total_out = int(responses["tokens_out"].fillna(0).sum()) if not responses.empty else 0
            st.metric("Input / output tokens", f"{total_in:,} / {total_out:,}")
            if langfuse_metrics["available"]:
                cloud_in, cloud_out = langfuse_metrics.get("tokens_in"), langfuse_metrics.get("tokens_out")
                if cloud_in is not None and cloud_out is not None:
                    st.caption(f"Langfuse generation tokens in / out: {cloud_in:,.0f} / {cloud_out:,.0f}")
                else:
                    st.caption("Langfuse generation token usage: N/A")
            st.caption("Threshold: total tokens ≤ 50,000 across available history")
            if not tokens.empty:
                st.area_chart(tokens, x="minute", y=["tokens_in", "tokens_out"], stack=False)

    with right:
        with st.container(border=True):
            st.subheader("6. Quality proxy")
            quality_values = responses["quality_score"].dropna() if not responses.empty else pd.Series(dtype=float)
            average_quality = float(quality_values.mean()) if not quality_values.empty else None
            st.metric("Average quality", f"{average_quality:.2f}" if average_quality is not None else "N/A")
            if langfuse_metrics["available"]:
                cloud_quality = langfuse_metrics.get("quality_avg")
                score_count = langfuse_metrics.get("quality_score_count") or 0
                st.caption(
                    f"Langfuse numeric score average: {cloud_quality:.2f} ({score_count:.0f} scores)"
                    if cloud_quality is not None
                    else "Langfuse numeric scores: no score data in the available history"
                )
            st.caption("Threshold: average quality ≥ 0.75")
            chart_with_threshold(quality, "quality_score", 0.75, "Average quality")


@st.cache_data(ttl=30, show_spinner=False)
def cached_langfuse_metrics() -> dict:
    return fetch_langfuse_dashboard_metrics()


if __name__ == "__main__":
    main()
