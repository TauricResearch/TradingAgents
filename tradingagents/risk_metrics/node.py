"""The graph step that computes the Quantitative Risk Metrics block before the debates."""

from tradingagents.risk_metrics.service import risk_block


def create_quant_risk_node():
    """A node that writes ``quant_risk_metrics`` from the run's ticker, date and asset type.

    It makes no model call. Like the Memory Log step it runs beside the analysts, so the
    trader, the three risk debators and the portfolio manager all find the block in state.
    """

    def quant_risk_node(state) -> dict:
        return {"quant_risk_metrics": risk_block(
            state["company_of_interest"], state["trade_date"], state.get("asset_type", "stock"))}

    return quant_risk_node
