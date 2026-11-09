---
name: investment-risk
description: Risk assessment, evidence freshness, and accurate guidance about the separate human-approved paper-trading workflow.
---

# Investment Risk Skill

Use this skill whenever evaluating an investment assessment or explaining the paper-trading workflow.

## Procedure

1. **Identify Uncertainty and Downside Scenarios**
   - Highlight valuation risks, margin compression, debt load, earnings volatility, macroeconomic sensitivity, and conflicting technical vs. fundamental signals.
   - Never claim that historical prices, technical indicators, or LLM analysis guarantee future returns.

2. **State Portfolio-Visibility Limits**
   - The research agent cannot inspect the paper ledger. `get_paper_portfolio` is not an available agent tool.
   - Do not infer the user's holdings, available cash, or concentration from conversation or saved preferences. If the user wants to make a paper proposal, they can inspect their portfolio in the Streamlit Paper Trading section or with the portfolio CLI commands.

3. **Check Data Freshness and Trading Constraints**
   - When discussing a possible trade, cite the retrieval date for any market price. The Paper Trading UI can explicitly refresh holding valuations, but proposal prices remain user-entered and are not verified against a quote at approval time.
   - The agent cannot create a proposal: `propose_paper_trade` is not an available agent tool. Do not say that you created, queued, or reviewed a paper trade.
   - The CLI or Streamlit UI lets the user enter a ticker, side, quantity, price, rationale, an optional saved-report ID, and an optional user-supplied transaction-cost assumption in basis points. This is a simulation input, not a brokerage or tax estimate. The deterministic ledger checks cash or held shares when a human reviews the pending proposal; it does not fetch a price at review time.
   - Portfolio valuation uses the last daily close returned by the market-data provider. Keep each source timestamp visible; if any holding lacks a valid quote, do not present a full portfolio value or total return. Dividends and corporate actions are not modeled.

4. **Enforce Mandatory Human Approval**
   - Creating a proposal in the CLI or UI creates a `PENDING` record only.
   - A human must explicitly approve or reject it: the CLI requires `proposal-review <id> --approve` or `--reject`; the UI requires an explicit review action, including confirmation before approval. Approval changes only the deterministic paper ledger. There is no broker connection or real order execution.
