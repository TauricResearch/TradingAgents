"""Render trading plan chart as PNG using Matplotlib + Pillow.

This module provides the draw_chart() function that renders a ChartJSON
into a PNG image. NO LLM call is made — pure local rendering.
"""

from __future__ import annotations

import logging
from pathlib import Path

# Set non-interactive backend before importing pyplot
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from PIL import Image

from tradingagents.graph.transform import ChartJSON

logger = logging.getLogger(__name__)

# Default chart styling
_DEFAULT_DPI = 150
_DEFAULT_FACECOLOR = "#0d0d1a"
_DEFAULT_AX_FACECOLOR = "#1a1a2e"
_LABEL_FONTSIZE = 9
# Minimum vertical gap between labels in data units (fraction of y-range)
_MIN_LABEL_GAP_FRACTION = 0.025


def _resolve_label_positions(
    prices: list[float],
    y_range: tuple[float, float],
) -> list[float]:
    """Nudge label y-positions so they don't overlap.

    Sorts labels by price, then pushes any pair closer than min_gap apart.
    Returns adjusted y-positions in the same order as the input list.
    """
    y_min, y_max = y_range
    min_gap = (y_max - y_min) * _MIN_LABEL_GAP_FRACTION

    # Build (original_index, price) pairs, sort by price
    indexed = sorted(enumerate(prices), key=lambda t: t[1])
    adjusted = [p for _, p in indexed]

    # Bottom-up pass: push overlapping labels upward
    for i in range(1, len(adjusted)):
        if adjusted[i] - adjusted[i - 1] < min_gap:
            adjusted[i] = adjusted[i - 1] + min_gap

    # Top-down pass: if top labels got pushed above y_max, compress downward
    if adjusted and adjusted[-1] > y_max - min_gap:
        adjusted[-1] = y_max - min_gap
        for i in range(len(adjusted) - 2, -1, -1):
            if adjusted[i + 1] - adjusted[i] < min_gap:
                adjusted[i] = adjusted[i + 1] - min_gap

    # Map back to original order
    result = [0.0] * len(prices)
    for rank, (orig_idx, _) in enumerate(indexed):
        result[orig_idx] = adjusted[rank]
    return result


def _compute_figsize(num_dates: int, num_ref_lines: int) -> tuple[float, float]:
    """Dynamic figure size based on data density."""
    width = max(14, num_dates * 1.2)
    height = max(8, 6 + num_ref_lines * 0.35)
    # Cap to reasonable bounds
    return (min(width, 24), min(height, 16))


def draw_chart(
    chart_json: ChartJSON,
    output_path: Path,
) -> Path:
    """Render trading plan chart as PNG using Matplotlib + Pillow.

    NO LLM call — pure local rendering from structured JSON.

    Renders:
    - Price history line (from chart_json.price_history)
    - Horizontal reference lines (TP, SL, Entry, Breakout, etc.)
    - Color-coded labels with collision avoidance
    - Current price marker

    Args:
        chart_json: Validated ChartJSON from transform_to_json().
        output_path: Path to save the output PNG file.

    Returns:
        Path to the saved PNG file.

    Raises:
        ValueError: If chart_json has inconsistent data (dates/prices length mismatch).
        RuntimeError: If Matplotlib fails to render.
        OSError: If output path is not writable.
    """
    dates = chart_json.price_history.dates
    prices = chart_json.price_history.prices

    if len(dates) != len(prices):
        raise ValueError(
            f"price_history mismatch: {len(dates)} dates vs {len(prices)} prices"
        )

    if len(dates) < 2:
        raise ValueError("price_history must have at least 2 data points")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Dynamic figure size based on data density
        figsize = _compute_figsize(len(dates), len(chart_json.reference_lines))
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(_DEFAULT_FACECOLOR)
        ax.set_facecolor(_DEFAULT_AX_FACECOLOR)

        # 1. Plot price history line
        ax.plot(
            dates,
            prices,
            color="white",
            linewidth=2,
            marker="o",
            markersize=4,
            label="Price",
        )

        # 2. Draw reference lines + collision-free labels
        y_min, y_max = chart_json.chart_info.y_axis_range
        ref_prices = [ref.price for ref in chart_json.reference_lines]
        label_y_positions = _resolve_label_positions(ref_prices, (y_min, y_max))

        for ref, label_y in zip(chart_json.reference_lines, label_y_positions):
            # Draw the horizontal line at the actual price
            ax.axhline(
                y=ref.price,
                color=ref.color,
                linestyle=ref.linestyle,
                linewidth=ref.linewidth,
            )

            # Position label at nudged y to avoid overlap
            x_pos = 0.98 if ref.align == "right" else 0.02
            ha = "right" if ref.align == "right" else "left"

            ax.annotate(
                f" {ref.label} ({ref.price:,.0f}) ",
                xy=(x_pos, ref.price),
                xytext=(x_pos, label_y),
                xycoords=("axes fraction", "data"),
                textcoords=("axes fraction", "data"),
                color=ref.color,
                fontsize=_LABEL_FONTSIZE,
                ha=ha,
                va="center",
                fontweight="bold",
                bbox=dict(
                    boxstyle="round,pad=0.15",
                    facecolor=_DEFAULT_AX_FACECOLOR,
                    edgecolor=ref.color,
                    alpha=0.85,
                ),
                arrowprops=dict(
                    arrowstyle="-",
                    color=ref.color,
                    alpha=0.4,
                    lw=0.8,
                )
                if abs(label_y - ref.price) > (y_max - y_min) * 0.005
                else None,
            )

        # 3. Mark current price
        current_price = chart_json.chart_info.current_price
        ax.axhline(
            y=current_price,
            color="yellow",
            linestyle="solid",
            linewidth=1.5,
            alpha=0.7,
        )
        ax.text(
            0.5,
            current_price,
            f" Current: {current_price:,.2f} ",
            transform=ax.get_yaxis_transform(),
            color="yellow",
            fontsize=10,
            ha="center",
            va="bottom",
            fontweight="bold",
            bbox=dict(
                boxstyle="round,pad=0.2",
                facecolor=_DEFAULT_AX_FACECOLOR,
                edgecolor="yellow",
                alpha=0.8,
            ),
        )

        # 4. Set axis range and labels
        ax.set_ylim(y_min, y_max)

        ax.set_title(
            chart_json.chart_info.title,
            fontsize=14,
            color="white",
            fontweight="bold",
            pad=20,
        )
        ax.set_xlabel(chart_json.chart_info.x_label, color="white", fontsize=11)
        ax.set_ylabel(chart_json.chart_info.y_label, color="white", fontsize=11)

        # 5. Style axes
        ax.tick_params(axis="x", colors="white", rotation=45)
        ax.tick_params(axis="y", colors="white")
        ax.grid(True, alpha=0.2, color="white", linestyle="--")

        for spine in ax.spines.values():
            spine.set_color("white")
            spine.set_alpha(0.3)

        # 6. Tight layout + save
        fig.tight_layout()
        fig.savefig(
            output_path,
            dpi=_DEFAULT_DPI,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
            edgecolor="none",
        )
        plt.close(fig)

        logger.info("Chart rendered successfully: %s", output_path)
        return output_path

    except Exception as e:
        plt.close("all")
        raise RuntimeError(f"Failed to render chart: {e}") from e


def validate_chart_image(image_path: Path) -> bool:
    """Validate that a PNG file is a valid image.

    Args:
        image_path: Path to the PNG file.

    Returns:
        True if the image is valid, False otherwise.
    """
    try:
        with Image.open(image_path) as img:
            img.verify()
        return True
    except Exception as e:
        logger.warning("Invalid image at %s: %s", image_path, e)
        return False
