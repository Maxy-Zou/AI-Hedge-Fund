"""CSV and JSON export builder for backtest results.

Produces structured file exports from a completed backtest run:
  - daily_returns.csv: net daily returns with ISO 8601 dates
  - positions.csv: date x ticker weight matrix
  - trade_log.csv: per-trade cost detail
  - metrics.json: scalar metrics with cost assumptions embedded

All CSV files start with a `# cost_assumptions:` comment line so
downstream consumers can identify the cost model without reading
a separate metadata file.

Usage:
    from pathlib import Path
    from fund_backtest.reports.exporter import ExportBuilder

    builder = ExportBuilder()
    csv_paths = builder.export_csv(result, cost_config, Path("outputs/"))
    json_path = builder.export_json(bundle, cost_config, Path("outputs/"))
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from fund_backtest.metrics.types import MetricsBundle
from fund_backtest.simulator.types import CostConfig, PortfolioResult


def _prepend_cost_header(path: Path, cost: CostConfig) -> None:
    """Prepend a cost assumptions comment line to a CSV file.

    The comment uses the format:
      # cost_assumptions: slippage=10.0bps, commission=5.0bps, borrow=50.0bps/yr

    Args:
        path: Path to the CSV file to modify in-place.
        cost: CostConfig holding slippage, commission, and borrow rate.
    """
    comment = (
        f"# cost_assumptions: slippage={cost.slippage_bps}bps,"
        f" commission={cost.commission_bps}bps,"
        f" borrow={cost.borrow_cost_bps_annual}bps/yr\n"
    )
    original = path.read_text()
    path.write_text(comment + original)


class ExportBuilder:
    """Writes structured CSV and JSON exports from a completed backtest run.

    Each export method embeds cost assumptions directly in the output file
    so downstream consumers (portfolio management, investor reports) do not
    need a separate metadata lookup to understand what friction was assumed.
    """

    def export_csv(
        self,
        result: PortfolioResult,
        cost_config: CostConfig,
        output_dir: Path,
    ) -> list[Path]:
        """Write daily_returns.csv, positions.csv, and trade_log.csv.

        All three files start with a `# cost_assumptions:` comment line
        and use ISO 8601 date format (YYYY-MM-DD) in the index column.

        Args:
            result: Completed simulation output with returns, positions, trade log.
            cost_config: Cost assumptions to embed as a comment header.
            output_dir: Directory to write CSV files into (created if missing).

        Returns:
            List of 3 Path objects: [daily_returns.csv, positions.csv, trade_log.csv].
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        returns_path = output_dir / "daily_returns.csv"
        result.net_returns.to_csv(
            returns_path, index=True, header=True, date_format="%Y-%m-%d"
        )
        _prepend_cost_header(returns_path, cost_config)

        positions_path = output_dir / "positions.csv"
        result.positions.to_csv(positions_path, index=True, date_format="%Y-%m-%d")
        _prepend_cost_header(positions_path, cost_config)

        trade_path = output_dir / "trade_log.csv"
        result.trade_log.to_csv(trade_path, index=False)
        _prepend_cost_header(trade_path, cost_config)

        return [returns_path, positions_path, trade_path]

    def export_json(
        self,
        bundle: MetricsBundle,
        cost_config: CostConfig,
        output_dir: Path,
    ) -> Path:
        """Write metrics.json with all scalar metrics and cost assumptions.

        Rolling pd.Series fields (rolling_sharpe, rolling_drawdown) are
        intentionally excluded — they are not JSON-serializable and are
        not useful in a scalar metrics export.

        Args:
            bundle: Computed metrics bundle (scalar + rolling Series).
            cost_config: Cost assumptions to embed under the 'cost_assumptions' key.
            output_dir: Directory to write metrics.json into (created if missing).

        Returns:
            Path to the written metrics.json file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "sharpe": bundle.sharpe,
            "sortino": bundle.sortino,
            "calmar": bundle.calmar,
            "max_drawdown": bundle.max_drawdown,
            "cagr": bundle.cagr,
            "hit_rate": bundle.hit_rate,
            "win_loss_ratio": bundle.win_loss_ratio,
            "annual_turnover": bundle.annual_turnover,
            "alpha": bundle.alpha,
            "beta": bundle.beta,
            "cost_assumptions": {
                "slippage_bps": cost_config.slippage_bps,
                "commission_bps": cost_config.commission_bps,
                "borrow_cost_bps_annual": cost_config.borrow_cost_bps_annual,
            },
        }

        path = output_dir / "metrics.json"
        path.write_text(json.dumps(data, indent=2))
        return path
