"""Plotly rendering; zone geometry is computed by the deterministic engine."""

import pandas as pd


def zone_chart(bars, zones, *, selected_id=None):
    import plotly.graph_objects as go

    figure = go.Figure(
        go.Candlestick(
            x=bars.index,
            open=bars.open,
            high=bars.high,
            low=bars.low,
            close=bars.close,
            name="Raw daily OHLC",
            increasing_line_color="#16a085",
            decreasing_line_color="#df624f",
        )
    )
    visible = [z for z in zones if selected_id is None or z.zone_id == selected_id]
    for zone in visible:
        if bars.empty or pd.Timestamp(zone.confirmed_at) > bars.index[-1]:
            continue
        color = "#16a085" if zone.side == "Demand" else "#df624f"
        figure.add_shape(
            type="rect",
            x0=zone.confirmed_at,
            x1=bars.index[-1],
            y0=min(zone.distal, zone.proximal),
            y1=max(zone.distal, zone.proximal),
            fillcolor=color,
            opacity=0.18,
            line_color=color,
        )
        figure.add_scatter(
            x=[zone.confirmed_at],
            y=[zone.proximal],
            mode="markers+text",
            text=[zone.pattern],
            textposition="top center",
            marker={"color": color, "size": 10},
            name="Confirmed " + zone.pattern,
        )
        figure.add_vrect(
            x0=zone.formation, x1=zone.confirmed_at, fillcolor="#718096", opacity=0.12, line_width=0
        )
        figure.add_scatter(
            x=[zone.leg_in],
            y=[bars.loc[pd.Timestamp(zone.leg_in), "close"]],
            mode="markers",
            marker={"symbol": "diamond", "size": 9},
            name="Leg in",
        )
    figure.update_layout(
        template="plotly_dark",
        height=620,
        xaxis_rangeslider_visible=False,
        xaxis_title="Session close (UTC)",
        yaxis_title="Raw price (USD)",
        title="Experimental Supply & Demand · historical daily bars",
        legend_orientation="h",
    )
    return figure
