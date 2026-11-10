"""Build a one-page HTML report straight from the marts.

The report only reads marts.* tables, never raw data: if the numbers look wrong, the bug is
in a dbt model (testable), not hidden in charting code.
"""
from datetime import datetime

import plotly.graph_objects as go
from plotly.io import to_html
from plotly.subplots import make_subplots

from .config import REPORT_DIR
from .db import connect

INK, MUTED, GRID = "#1f2937", "#6b7280", "#e5e7eb"
BLUE, ORANGE, RED = "#2563eb", "#ea580c", "#dc2626"
TYPE_COLORS = {"mainline": BLUE, "regional": "#0d9488", "ultra-low-cost": ORANGE, "unknown": "#9ca3af"}
CAUSE_COLORS = {"Late aircraft": "#ea580c", "Carrier": "#2563eb", "Air traffic (NAS)": "#0d9488",
                "Weather": "#7c3aed", "Security": "#9ca3af"}


def _q(con, sql):
    cur = con.execute(sql)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _style(fig, title, height=360):
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=height, margin=dict(l=56, r=20, t=50, b=44), paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Inter, system-ui, sans-serif", size=12, color=MUTED),
        legend=dict(orientation="h", y=-0.2, x=0), hoverlabel=dict(bgcolor="white"),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    return fig


def build_report() -> None:
    with connect() as con:
        carriers = _q(con, """
            SELECT carrier_code, carrier_name, carrier_type,
                   sum(scheduled_flights) flights,
                   sum(on_time_rate * (scheduled_flights - cancelled_flights)) / sum(scheduled_flights - cancelled_flights) otp,
                   sum(cancelled_flights)::numeric / sum(scheduled_flights) cancel_rate
            FROM marts.mart_carrier_monthly GROUP BY 1,2,3 ORDER BY otp""")
        monthly = _q(con, """
            SELECT data_month, count(*) flights,
                   avg(is_on_time::int) FILTER (WHERE NOT is_cancelled) otp,
                   avg(is_cancelled::int) cancel_rate,
                   avg(arr_delay_min) FILTER (WHERE NOT is_cancelled AND NOT is_diverted) avg_delay
            FROM marts.fct_flights GROUP BY 1 ORDER BY 1""")
        hourly = _q(con, """
            SELECT crs_dep_hour h, sum(flights) flights,
                   sum(on_time_rate * flights) / sum(flights) otp,
                   avg(late_aircraft_share) late_share
            FROM marts.mart_hourly_delay GROUP BY 1 ORDER BY 1""")
        causes = _q(con, """
            SELECT carrier_code, cause, sum(delay_minutes) mins
            FROM marts.mart_delay_causes GROUP BY 1,2""")
        airports = _q(con, """
            SELECT airport_code, city_name, sum(departures) deps,
                   sum(on_time_departure_rate * departures) / sum(departures) otd,
                   sum(avg_taxi_out_min * departures) / sum(departures) taxi
            FROM marts.mart_airport_monthly GROUP BY 1,2 HAVING sum(departures) >= 500 ORDER BY otd LIMIT 10""")
        loads = _q(con, """
            SELECT count(*) files, sum(rows_loaded) rows_loaded, sum(duration_sec) secs
            FROM (SELECT DISTINCT ON (data_month) * FROM meta.ingestion_log
                  WHERE status = 'success' ORDER BY data_month, finished_at DESC) latest""")[0]

    total = sum(m["flights"] for m in monthly)
    otp = sum(float(m["otp"]) * m["flights"] for m in monthly) / total
    cancel = sum(float(m["cancel_rate"]) * m["flights"] for m in monthly) / total
    first, last = monthly[0]["data_month"], monthly[-1]["data_month"]

    # 1. carriers
    f1 = go.Figure(go.Bar(
        y=[c["carrier_name"] for c in carriers], x=[float(c["otp"]) * 100 for c in carriers], orientation="h",
        marker_color=[TYPE_COLORS.get(c["carrier_type"], MUTED) for c in carriers],
        customdata=[[c["carrier_type"], c["flights"]] for c in carriers],
        hovertemplate="%{y}<br>%{x:.1f}% on time<br>%{customdata[0]} · %{customdata[1]:,} flights<extra></extra>",
    ))
    f1.add_vline(x=otp * 100, line_dash="dot", line_color=INK,
                 annotation_text=f"all carriers {otp:.1%}", annotation_position="bottom right", annotation_font_size=11)
    _style(f1, "On-time arrival rate by carrier", height=460)
    f1.update_xaxes(title="% of completed flights arriving < 15 min late", ticksuffix="%",
                    range=[min(float(c["otp"]) for c in carriers) * 100 - 5, 100])

    # 2. hour of day (the snowball)
    f2 = make_subplots(specs=[[{"secondary_y": True}]])
    xs = [f"{int(h['h']):02d}:00" for h in hourly]
    late_max = max(float(h["late_share"]) for h in hourly) * 100
    f2.add_bar(x=xs, y=[float(h["late_share"]) * 100 for h in hourly], name="Late-aircraft share of delay min",
               marker_color="#fed7aa", secondary_y=False)
    f2.add_scatter(x=xs, y=[float(h["otp"]) * 100 for h in hourly], name="On-time rate", mode="lines+markers",
                   line=dict(color=BLUE, width=3), secondary_y=True)
    _style(f2, "Delays snowball through the day (by scheduled departure hour)")
    f2.update_yaxes(title="Late-aircraft share", ticksuffix="%", range=[0, late_max * 1.15], dtick=10, secondary_y=False)
    f2.update_yaxes(title="On-time rate", ticksuffix="%", tickformat=".0f", secondary_y=True, showgrid=False)
    f2.update_xaxes(tickangle=0, nticks=9)

    # 3. cause mix per carrier (100% stacked)
    order = [c["carrier_code"] for c in sorted(carriers, key=lambda c: c["otp"])]
    tot = {}
    for r in causes:
        tot[r["carrier_code"]] = tot.get(r["carrier_code"], 0) + (r["mins"] or 0)
    f3 = go.Figure()
    for cause, col in CAUSE_COLORS.items():
        vals = {r["carrier_code"]: (r["mins"] or 0) / tot[r["carrier_code"]] * 100 for r in causes if r["cause"] == cause}
        f3.add_bar(x=order, y=[vals.get(c, 0) for c in order], name=cause, marker_color=col,
                   hovertemplate="%{x} · " + cause + ": %{y:.0f}%<extra></extra>")
    _style(f3, "What causes the delay minutes (worst carriers on the left)")
    f3.update_layout(barmode="stack")
    f3.update_yaxes(title="% of delay minutes", ticksuffix="%", range=[0, 100])

    # 4. worst airports
    f4 = go.Figure(go.Bar(
        x=[a["airport_code"] for a in airports], y=[float(a["otd"]) * 100 for a in airports], marker_color=RED,
        customdata=[[a["city_name"], float(a["taxi"])] for a in airports],
        hovertemplate="%{x} · %{customdata[0]}<br>%{y:.1f}% on-time departures<br>avg taxi-out %{customdata[1]:.0f} min<extra></extra>",
        text=[f"{float(a['taxi']):.0f} min taxi" for a in airports], textposition="inside", textfont=dict(color="white", size=10),
    ))
    _style(f4, "10 worst airports for on-time departure (label = avg taxi-out)")
    f4.update_yaxes(title="On-time departure rate", ticksuffix="%",
                    range=[min(float(a["otd"]) for a in airports) * 100 - 8, max(float(a["otd"]) for a in airports) * 100 + 4])

    best, worst = carriers[-1], carriers[0]
    early, late = hourly[0], hourly[-1]
    findings = [
        f"<b>{best['carrier_name']}</b> was the most punctual carrier ({float(best['otp']):.1%} on time); "
        f"<b>{worst['carrier_name']}</b> the least ({float(worst['otp']):.1%}).",
        f"On-time rate falls from <b>{float(early['otp']):.0%}</b> for {int(early['h']):02d}:00 departures to "
        f"<b>{float(late['otp']):.0%}</b> by {int(late['h']):02d}:00, and late-arriving aircraft go from "
        f"{float(early['late_share']):.0%} to {float(late['late_share']):.0%} of delay minutes. "
        "Morning flights are the safest bet.",
        f"<b>{airports[0]['airport_code']}</b> ({airports[0]['city_name']}) had the worst on-time departure rate, "
        f"with {float(airports[0]['taxi']):.0f}-minute average taxi-outs pointing to ground congestion.",
    ]

    kpis = [
        ("Flights", f"{total:,}", f"{first:%b %Y} – {last:%b %Y}"),
        ("On-time arrivals", f"{otp:.1%}", "completed flights, &lt; 15 min late"),
        ("Cancelled", f"{cancel:.2%}", "of scheduled flights"),
        ("Pipeline", f"{int(loads['rows_loaded']):,} rows", f"{loads['files']} monthly files loaded in {float(loads['secs']):.1f}s via COPY"),
    ]
    div = lambda f: to_html(f, full_html=False, include_plotlyjs=False, config={"displayModeBar": False, "responsive": True})
    kpi_html = "".join(f'<div class="kpi"><div class="kl">{a}</div><div class="kv">{b}</div><div class="ks">{c}</div></div>' for a, b, c in kpis)

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>U.S. Airline On-Time Performance</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
 body{{font-family:Inter,system-ui,sans-serif;background:#f9fafb;color:{INK};margin:0}}
 .wrap{{max-width:1180px;margin:0 auto;padding:28px 20px 48px}}
 h1{{font-size:24px;margin:0 0 4px}} .sub{{color:{MUTED};font-size:14px;margin-bottom:20px}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-bottom:16px}}
 .kpi,.card{{background:white;border:1px solid {GRID};border-radius:12px;padding:14px 16px;min-width:0;overflow:hidden}}
 .kl{{font-size:12px;color:{MUTED};text-transform:uppercase;letter-spacing:.04em}}
 .kv{{font-size:26px;font-weight:650;margin:4px 0 2px}} .ks{{font-size:12px;color:{MUTED}}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(480px,100%),1fr));gap:16px;margin-bottom:16px}}
 .findings li{{margin:6px 0;line-height:1.5}} h2{{font-size:15px;margin:0 0 8px}}
 .foot{{color:{MUTED};font-size:12px;margin-top:8px}}
</style></head><body><div class="wrap">
<h1>U.S. Airline On-Time Performance</h1>
<div class="sub">Source: BTS Reporting Carrier On-Time Performance · built {datetime.now():%Y-%m-%d %H:%M}</div>
<div class="kpis">{kpi_html}</div>
<div class="card findings" style="margin-bottom:16px"><h2>Key findings</h2><ul>{''.join(f'<li>{x}</li>' for x in findings)}</ul></div>
<div class="grid"><div class="card">{div(f1)}</div><div class="card">{div(f2)}</div></div>
<div class="grid"><div class="card">{div(f3)}</div><div class="card">{div(f4)}</div></div>
<div class="foot">Python + PostgreSQL (partitioned, COPY-loaded) → dbt (staging → incremental fact → marts, 30+ tests) → this report.</div>
</div>
<script>
  // charts render while the page is still laying out; re-measure once it's final and on resize
  const fit = () => document.querySelectorAll('.js-plotly-plot').forEach(d => Plotly.Plots.resize(d));
  window.addEventListener('load', fit); window.addEventListener('resize', fit);
</script>
</body></html>"""
    REPORT_DIR.mkdir(exist_ok=True)
    out = REPORT_DIR / "flight_delays.html"
    out.write_text(html)
    print(f"  wrote  {out}")
