"""
dashboard/app.py — Main Dash application entry point.

Run:
    python dashboard/app.py

Environment:
    HERMES_DB_PATH — path to SQLite database (default /opt/data/hermes.db)
"""

import os

import dash
from dash import Input, Output, State, dcc, html

from .queries import get_db_connection, get_stats_summary
from .simple import build_layout as simple_layout
from .advanced import build_layout as advanced_layout

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BG = "#0d1117"
CARD_BG = "#161b22"
TEXT = "#c9d1d9"
ACCENT = "#58a6ff"
BORDER = "#30363d"
MUTED = "#8b949e"

_REFRESH_INTERVAL_MS = 60_000  # 60 seconds

# ---------------------------------------------------------------------------
# App init
# ---------------------------------------------------------------------------
app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    title="Trading Dashboard",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server  # Expose WSGI server for gunicorn/fly.io


# ---------------------------------------------------------------------------
# Helper: "no data" placeholder
# ---------------------------------------------------------------------------
def _no_data_layout(message: str = "No data yet") -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        "○",
                        style={"fontSize": "48px", "color": MUTED, "marginBottom": "16px"},
                    ),
                    html.Div(
                        message,
                        style={"color": MUTED, "fontSize": "18px"},
                    ),
                    html.Div(
                        f"DB: {os.environ.get('HERMES_DB_PATH', '/opt/data/hermes.db')}",
                        style={"color": MUTED, "fontSize": "12px", "marginTop": "8px"},
                    ),
                ],
                style={"textAlign": "center", "padding": "80px 20px"},
            )
        ]
    )


# ---------------------------------------------------------------------------
# Toggle button styles
# ---------------------------------------------------------------------------
def _tab_style(active: bool) -> dict:
    return {
        "padding": "8px 24px",
        "border": f"1px solid {BORDER}",
        "borderRadius": "6px",
        "cursor": "pointer",
        "fontSize": "13px",
        "fontWeight": "600",
        "transition": "all 0.15s ease",
        "backgroundColor": ACCENT if active else CARD_BG,
        "color": "#0d1117" if active else TEXT,
        "outline": "none",
    }


# ---------------------------------------------------------------------------
# Root layout (static shell — content rendered by callback)
# ---------------------------------------------------------------------------
app.layout = html.Div(
    [
        # Refresh interval
        dcc.Interval(
            id="refresh-interval",
            interval=_REFRESH_INTERVAL_MS,
            n_intervals=0,
        ),
        # Mode store: "simple" | "advanced"
        dcc.Store(id="mode-store", data="simple"),

        # Header
        html.Div(
            [
                html.Div(
                    [
                        html.H1(
                            "Trading Dashboard",
                            style={
                                "margin": "0",
                                "fontSize": "20px",
                                "fontWeight": "700",
                                "color": TEXT,
                                "letterSpacing": "0.5px",
                            },
                        ),
                    ],
                    style={"flex": "1"},
                ),
                # Mode toggle buttons
                html.Div(
                    [
                        html.Button(
                            "Simple",
                            id="btn-simple",
                            n_clicks=0,
                            style=_tab_style(active=True),
                        ),
                        html.Button(
                            "Advanced",
                            id="btn-advanced",
                            n_clicks=0,
                            style=_tab_style(active=False),
                        ),
                    ],
                    style={"display": "flex", "gap": "8px", "alignItems": "center"},
                ),
            ],
            style={
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "space-between",
                "padding": "16px 24px",
                "backgroundColor": CARD_BG,
                "borderBottom": f"1px solid {BORDER}",
                "position": "sticky",
                "top": "0",
                "zIndex": "100",
            },
        ),

        # Main content area
        html.Div(
            id="main-content",
            style={"padding": "20px 24px", "minHeight": "calc(100vh - 64px)"},
        ),
    ],
    style={
        "backgroundColor": BG,
        "minHeight": "100vh",
        "fontFamily": (
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', "
            "Helvetica, Arial, sans-serif"
        ),
        "color": TEXT,
    },
)


# ---------------------------------------------------------------------------
# Callback: track active mode on button click
# ---------------------------------------------------------------------------
@app.callback(
    Output("mode-store", "data"),
    Input("btn-simple", "n_clicks"),
    Input("btn-advanced", "n_clicks"),
    State("mode-store", "data"),
    prevent_initial_call=False,
)
def update_mode(n_simple: int, n_advanced: int, current_mode: str) -> str:
    ctx = dash.callback_context
    if not ctx.triggered or ctx.triggered[0]["prop_id"] == ".":
        return current_mode or "simple"
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger_id == "btn-advanced":
        return "advanced"
    return "simple"


# ---------------------------------------------------------------------------
# Callback: update button styles to reflect active mode
# ---------------------------------------------------------------------------
@app.callback(
    Output("btn-simple", "style"),
    Output("btn-advanced", "style"),
    Input("mode-store", "data"),
)
def update_button_styles(mode: str):
    simple_active = mode == "simple"
    return _tab_style(simple_active), _tab_style(not simple_active)


# ---------------------------------------------------------------------------
# Callback: render content on mode change or interval tick
# ---------------------------------------------------------------------------
@app.callback(
    Output("main-content", "children"),
    Input("mode-store", "data"),
    Input("refresh-interval", "n_intervals"),
)
def render_content(mode: str, _n_intervals: int) -> html.Div:
    # Gracefully handle missing DB
    conn = get_db_connection()
    if conn is None:
        return _no_data_layout(
            "Database unavailable — waiting for data.\n"
            f"Path: {os.environ.get('HERMES_DB_PATH', '/opt/data/hermes.db')}"
        )
    conn.close()

    # Check whether we have any meaningful data
    stats = get_stats_summary()
    has_data = (
        stats["total_trades"] > 0
        or stats["open_positions_count"] > 0
        or stats["current_equity"] > 0
    )

    if not has_data:
        return _no_data_layout("No trades recorded yet. Waiting for data...")

    if mode == "advanced":
        return advanced_layout()
    return simple_layout()


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=8050, debug=False)
