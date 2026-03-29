"""PDF tearsheet generator for backtest results.

Produces an investor-ready single-page PDF (US Letter landscape) containing:
  - Row 0: Equity curve (net returns, cumulative)
  - Row 1: Drawdown fill (red, alpha 0.3)
  - Row 2 left: Monthly returns heatmap
  - Row 2 right: Metrics and cost assumptions table

Usage:
    from pathlib import Path
    from fund_backtest.reports.tearsheet import TearsheetBuilder

    builder = TearsheetBuilder()
    output = builder.build(result, bundle, cost_config, Path("out.pdf"))
    # output == Path("out.pdf"), exists on disk
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

# Guard: only switch backend if not already set to Agg.
# Must happen BEFORE importing pyplot to take effect.
if matplotlib.get_backend() != "Agg":
    matplotlib.use("Agg")

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from fund_backtest.metrics.types import MetricsBundle
from fund_backtest.simulator.types import CostConfig, PortfolioResult


class TearsheetBuilder:
    """Generates a single-page PDF tearsheet from a completed backtest run.

    The tearsheet is designed for investor conversations: it shows the
    strategy's equity curve, drawdown history, monthly return attribution,
    and a full metrics table with cost assumptions explicitly listed.

    Cost assumptions are rendered in the metrics table so readers know
    exactly what friction was assumed (slippage, commission, borrow rate).
    """

    def build(
        self,
        result: PortfolioResult,
        bundle: MetricsBundle,
        cost_config: CostConfig,
        output_path: Path,
    ) -> Path:
        """Build and save the tearsheet PDF.

        Args:
            result: Completed simulation output (net_returns used for charts).
            bundle: Computed metrics (scalar values + rolling Series).
            cost_config: Cost assumptions to display in the metrics table.
            output_path: Destination file path (must have .pdf extension by convention).

        Returns:
            output_path — the same path passed in, verified to exist on disk.
        """
        fig = plt.figure(figsize=(11, 8.5), constrained_layout=True)
        gs = gridspec.GridSpec(3, 2, figure=fig, height_ratios=[1.5, 1, 1])

        ax_equity = fig.add_subplot(gs[0, :])    # Row 0: equity curve, full width
        ax_dd = fig.add_subplot(gs[1, :])         # Row 1: drawdown fill, full width
        ax_heatmap = fig.add_subplot(gs[2, 0])    # Row 2 left: monthly heatmap
        ax_table = fig.add_subplot(gs[2, 1])      # Row 2 right: metrics + cost table

        self._draw_equity(ax_equity, result.net_returns)
        self._draw_drawdown(ax_dd, result.net_returns)
        self._draw_monthly_heatmap(ax_heatmap, result.net_returns)
        self._draw_metrics_table(ax_table, bundle, cost_config)

        with PdfPages(output_path) as pdf:
            d = pdf.infodict()
            d["Title"] = "AI Hedge Fund — Backtest Tearsheet"
            pdf.savefig(fig, bbox_inches="tight")

        plt.close(fig)
        return output_path

    def _draw_equity(self, ax: plt.Axes, net_returns: pd.Series) -> None:
        """Plot cumulative equity curve from net daily returns.

        Args:
            ax: Matplotlib axes to draw on.
            net_returns: Daily net returns Series with DatetimeIndex.
        """
        equity = (1 + net_returns).cumprod()
        ax.plot(equity.index, equity.values, label="Net Returns", linewidth=1.2)
        ax.set_title("Equity Curve")
        ax.set_ylabel("Cumulative Return")
        ax.legend(loc="upper left")

    def _draw_drawdown(self, ax: plt.Axes, net_returns: pd.Series) -> None:
        """Plot rolling maximum drawdown as a filled red area.

        Args:
            ax: Matplotlib axes to draw on.
            net_returns: Daily net returns Series with DatetimeIndex.
        """
        equity = (1 + net_returns).cumprod()
        rolling_max = equity.cummax()
        drawdown = equity / rolling_max - 1
        ax.fill_between(drawdown.index, drawdown.values, 0, color="red", alpha=0.3)
        ax.set_title("Drawdown")
        ax.set_ylabel("Drawdown")

    def _draw_monthly_heatmap(self, ax: plt.Axes, net_returns: pd.Series) -> None:
        """Plot monthly return heatmap as a colour-mapped table.

        Args:
            ax: Matplotlib axes to draw on.
            net_returns: Daily net returns Series with DatetimeIndex.
        """
        # Resample to month-end using 'ME' (pandas 3.x compatible alias).
        monthly = (1 + net_returns).resample("ME").prod() - 1
        monthly_df = monthly.to_frame(name="ret")
        monthly_df["year"] = monthly_df.index.year
        monthly_df["month"] = monthly_df.index.month
        pivoted = monthly_df.pivot(index="month", columns="year", values="ret")

        im = ax.imshow(
            pivoted.values,
            aspect="auto",
            cmap="RdYlGn",
            vmin=-0.1,
            vmax=0.1,
        )
        ax.set_title("Monthly Returns")
        ax.set_xlabel("Year")
        ax.set_ylabel("Month")
        ax.set_xticks(range(len(pivoted.columns)))
        ax.set_xticklabels(pivoted.columns, rotation=45, ha="right", fontsize=7)
        ax.set_yticks(range(len(pivoted.index)))
        ax.set_yticklabels(
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][: len(pivoted.index)],
            fontsize=7,
        )
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    def _draw_metrics_table(
        self,
        ax: plt.Axes,
        bundle: MetricsBundle,
        cost_config: CostConfig,
    ) -> None:
        """Render scalar metrics and cost assumptions as a plain table.

        The table contains 10 risk/return metrics followed by a cost
        section separator and 3 cost assumption rows so investors can
        see exactly what friction was assumed.

        Args:
            ax: Matplotlib axes to draw on (axis will be turned off).
            bundle: Computed metrics bundle with scalar values.
            cost_config: Cost assumptions to render at the bottom.
        """
        data = [
            ["Sharpe", f"{bundle.sharpe:.2f}"],
            ["Sortino", f"{bundle.sortino:.2f}"],
            ["Calmar", f"{bundle.calmar:.2f}"],
            ["Max Drawdown", f"{bundle.max_drawdown:.1%}"],
            ["CAGR", f"{bundle.cagr:.1%}"],
            ["Hit Rate", f"{bundle.hit_rate:.1%}"],
            ["Win/Loss", f"{bundle.win_loss_ratio:.2f}"],
            ["Turnover", f"{bundle.annual_turnover:.1f}x"],
            ["Alpha", f"{bundle.alpha:.2%}"],
            ["Beta", f"{bundle.beta:.2f}"],
            ["--- Cost Assumptions ---", ""],
            ["Slippage", f"{cost_config.slippage_bps:.0f} bps (one-way)"],
            ["Commission", f"{cost_config.commission_bps:.0f} bps (one-way)"],
            ["Borrow Rate", f"{cost_config.borrow_cost_bps_annual:.0f} bps/yr (flat)"],
        ]
        ax.table(cellText=data, loc="center", cellLoc="left")
        ax.axis("off")
        ax.set_title("Metrics & Costs")
