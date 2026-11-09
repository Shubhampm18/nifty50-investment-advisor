"""Local Streamlit interface for research, paper trading, and preferences."""

from __future__ import annotations

import re
from typing import Any

import streamlit as st

from nifty50_investment_advisor.database import (
    get_research_report,
    get_stock_comparison,
    initialize_database,
    list_research_reports,
    list_stock_comparisons,
    save_research_report,
    save_stock_comparison,
)
from nifty50_investment_advisor.memory import (
    PREFERENCE_CATEGORIES,
    clear_preferences,
    has_saved_preferences,
    read_preferences,
    save_preference,
)
from nifty50_investment_advisor.portfolio import (
    DEFAULT_PORTFOLIO_NAME,
    create_portfolio,
    create_trade_proposal,
    get_default_initial_cash,
    get_portfolio_summary,
    list_paper_trades,
    list_portfolios,
    list_trade_proposals,
    review_trade_proposal,
)
from nifty50_investment_advisor.portfolio_valuation import (
    build_portfolio_valuation,
    refresh_portfolio_quotes,
)

PAGES = (
    "Research & Reports",
    "Saved Reports",
    "Paper Trading",
    "Preferences",
)


def run_research(question: str) -> dict[str, Any]:
    """Load the research service only when the user submits a request."""
    from nifty50_investment_advisor.research import run_research as research

    return research(question)


def run_stock_comparison(
    tickers: str,
    research_question: str | None = None,
) -> dict[str, Any]:
    """Load comparison services only when the user submits a request."""
    from nifty50_investment_advisor.research import (
        run_stock_comparison as compare,
    )

    return compare(tickers, research_question)


def _safe_error(message: Any) -> str:
    """Return a short, single-line error without stack traces or credentials."""
    value = str(message).splitlines()[0][:400]
    value = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", value)
    value = re.sub(
        r"(?i)\b(api[_ -]?key|access[_ -]?token|token|secret|password)"
        r"\s*[:=]\s*[^\s,;]+",
        r"\1=[redacted]",
        value,
    )
    return value or "An unexpected error occurred."


def _show_report(report: dict[str, Any]) -> None:
    """Render the user-facing fields of a validated report."""
    st.subheader(report.get("ticker", "Research report"))
    if report.get("company_name"):
        st.caption(str(report["company_name"]))

    st.markdown("#### Summary")
    st.write(report.get("summary", "No summary was returned."))

    evidence = report.get("evidence") or []
    st.markdown("#### Available evidence")
    if not evidence:
        st.info("No structured evidence items were available.")
    for index, item in enumerate(evidence, start=1):
        with st.expander(
            f"{index}. {item.get('source_name', 'Source')} · "
            f"{item.get('evidence_type', 'evidence')}"
        ):
            st.write(item.get("claim", "No claim provided."))
            if item.get("published_at"):
                st.caption(f"Published: {item['published_at']}")
            if item.get("limitations"):
                st.caption(f"Limitations: {item['limitations']}")
            source_url = item.get("source_url")
            if isinstance(source_url, str) and source_url.startswith(("https://", "http://")):
                st.link_button("Open source", source_url)

    data = report.get("data") or {}
    statuses = data.get("retrieval_status") or {}
    errors = data.get("retrieval_errors") or {}
    if statuses:
        st.markdown("#### Retrieval status")
        status_columns = st.columns(len(statuses))
        for column, (name, status) in zip(status_columns, statuses.items()):
            column.metric(name.replace("_", " ").title(), status.replace("_", " "))
    for name, error in errors.items():
        st.warning(f"{name.replace('_', ' ').title()}: {_safe_error(error)}")

    missing = report.get("missing_information") or []
    if missing:
        with st.expander("Missing information"):
            for item in missing:
                st.write(f"• {_safe_error(item)}")

    uncertainty = report.get("uncertainty") or []
    risks = report.get("risks") or []
    if uncertainty or risks:
        with st.expander("Uncertainty and risks"):
            for item in uncertainty:
                st.write(f"Uncertainty: {item}")
            for item in risks:
                st.write(f"Risk: {item}")

    if report.get("conclusion"):
        st.info(report["conclusion"])
    if report.get("disclaimer"):
        st.caption(report["disclaimer"])


def _research_page() -> None:
    st.header("Research & Reports")
    workflow = st.radio(
        "Research workflow",
        options=["Single-stock research", "Stock comparison"],
        horizontal=True,
        key="research_workflow",
    )
    if workflow == "Stock comparison":
        _comparison_page()
        return

    st.write(
        "Submit a question to retrieve current market evidence and generate "
        "a research report. Results are not cached between requests."
    )

    with st.form("research_form"):
        question = st.text_area(
            "Research question",
            placeholder="For example: Review the latest evidence on RELIANCE.NS",
            max_chars=2000,
            key="research_question",
        )
        submitted = st.form_submit_button("Run research", type="primary", key="run_research_submit")

    if submitted:
        st.session_state.pop("research_result", None)
        st.session_state.pop("research_error", None)
        st.session_state.pop("saved_report_id", None)
        if not question.strip():
            st.session_state["research_error"] = "Enter a research question."
        else:
            try:
                st.session_state["research_result"] = run_research(question)
            except Exception as exc:  # noqa: BLE001 - keep provider failures in the UI
                st.session_state["research_error"] = (
                    "Research could not complete "
                    f"({type(exc).__name__}). Check your provider and data "
                    "configuration, then try again."
                )

    if error := st.session_state.get("research_error"):
        st.error(error)

    result = st.session_state.get("research_result")
    if not isinstance(result, dict):
        return

    report = result.get("report")
    if result.get("ok") is True and isinstance(report, dict):
        st.success("Research completed. Review the evidence and limitations below.")
    else:
        st.warning(
            "Research did not complete successfully. Any returned evidence "
            "is partial and should not be treated as a completed analysis."
        )

    if result.get("agent_error"):
        st.warning(f"Research agent: {_safe_error(result['agent_error'])}")
    news = result.get("news")
    if isinstance(news, dict) and news.get("ok") is False:
        st.warning(
            f"News retrieval failed: {_safe_error(news.get('error', 'No details were returned.'))}"
        )

    if isinstance(report, dict):
        _show_report(report)
    elif result.get("analysis"):
        st.write(result["analysis"])

    if result.get("ok") is True and isinstance(report, dict):
        saved_id = st.session_state.get("saved_report_id")
        if saved_id is not None:
            st.success(f"Report saved with ID {saved_id}.")
        elif st.button("Save this report", type="primary", key="save_research_report"):
            try:
                initialize_database()
                st.session_state["saved_report_id"] = save_research_report(report)
            except Exception as exc:  # noqa: BLE001 - show a safe persistence error
                st.error(f"Could not save the report ({type(exc).__name__}).")
            else:
                st.success(f"Report saved with ID {st.session_state['saved_report_id']}.")


def _show_comparison_report(report: dict[str, Any]) -> None:
    """Render the aggregate comparison and each ticker's retained evidence."""
    tickers = report.get("tickers") or []
    st.subheader("Stock comparison")
    if tickers:
        labels = {
            stock.get("ticker"): stock.get("company_name")
            for stock in report.get("stocks", [])
            if isinstance(stock, dict)
        }
        st.caption(
            "Compared tickers: "
            + ", ".join(
                f"{labels[ticker]} ({ticker})" if labels.get(ticker) else str(ticker)
                for ticker in tickers
            )
        )
    st.markdown("#### Summary")
    st.write(report.get("summary", "No comparison summary was returned."))
    if report.get("universe_checked_at"):
        freshness = " (last known list; refresh failed)" if report.get("universe_stale") else ""
        st.caption(
            "NIFTY 50 member list checked "
            f"{report['universe_checked_at']}{freshness}."
        )

    differences = report.get("differences") or []
    st.markdown("#### Returned data differences")
    if differences:
        rows = []
        for difference in differences:
            for observation in difference.get("observations", []):
                rows.append(
                    {
                        "Category": difference.get("category"),
                        "Metric": difference.get("metric"),
                        "Ticker": observation.get("ticker"),
                        "Value": observation.get("value"),
                        "As of": observation.get("as_of") or "Not provided",
                        "Source": observation.get("source_name"),
                    }
                )
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("No numeric metric was returned for at least two tickers.")

    missing = report.get("missing_information") or []
    if missing:
        with st.expander("Missing information across tickers"):
            for item in missing:
                st.write(f"• {_safe_error(item)}")

    uncertainty = report.get("uncertainty") or []
    if uncertainty:
        st.markdown("#### Uncertainty")
        for item in uncertainty:
            st.write(f"• {item}")

    for stock in report.get("stocks") or []:
        ticker = stock.get("ticker", "Unknown ticker")
        with st.expander(f"{ticker} · evidence and retrieval status"):
            individual = stock.get("report")
            if isinstance(individual, dict):
                _show_report(individual)
            news = stock.get("news")
            if isinstance(news, dict):
                st.caption(
                    f"Company-specific news retrieval: "
                    f"{'success' if news.get('ok') is True else 'failed'}"
                )

    if report.get("conclusion"):
        st.info(report["conclusion"])
    if report.get("disclaimer"):
        st.caption(report["disclaimer"])


def _comparison_page() -> None:
    """Run a comparison only on submit and save only after a separate action."""
    st.write(
        "Compare 2 to 5 distinct current NIFTY 50 constituents. Enter NSE symbols "
        "with or without the .NS suffix. The official constituent list is checked "
        "when you submit; returned values are not ranked."
    )
    with st.form("stock_comparison_form"):
        tickers = st.text_area(
            "NSE ticker symbols",
            placeholder="RELIANCE.NS, TCS.NS",
            help="Enter 2 to 5 NSE symbols, separated by commas or new lines.",
            max_chars=200,
            key="comparison_tickers",
        )
        question = st.text_area(
            "Comparison note (optional)",
            placeholder="Add context to save with this comparison.",
            help="The summary is deterministic and this note does not change its calculations.",
            max_chars=2000,
            key="comparison_question",
        )
        submitted = st.form_submit_button(
            "Run comparison", type="primary", key="compare_tickers_submit"
        )

    if submitted:
        st.session_state.pop("comparison_result", None)
        st.session_state.pop("comparison_error", None)
        st.session_state.pop("saved_comparison_id", None)
        try:
            st.session_state["comparison_result"] = run_stock_comparison(
                tickers,
                question.strip() or None,
            )
        except ValueError as exc:
            st.session_state["comparison_error"] = _safe_error(exc)
        except Exception as exc:  # noqa: BLE001 - display safe service failure
            st.session_state["comparison_error"] = _safe_error(
                f"Comparison could not complete ({type(exc).__name__}): {exc}"
            )

    if error := st.session_state.get("comparison_error"):
        st.error(error)

    result = st.session_state.get("comparison_result")
    if not isinstance(result, dict):
        return
    report = result.get("report")
    if result.get("ok") is True and isinstance(report, dict):
        st.success("Comparison completed. Review per-ticker evidence and missing fields.")
    else:
        st.warning(
            "No evidence source returned usable data. Any displayed "
            "per-ticker evidence is partial."
        )
    if result.get("error"):
        st.warning(f"Comparison status: {_safe_error(result['error'])}")
    if isinstance(report, dict):
        _show_comparison_report(report)

    if result.get("ok") is True and isinstance(report, dict):
        saved_id = st.session_state.get("saved_comparison_id")
        if saved_id is not None:
            st.success(f"Comparison saved with ID {saved_id}.")
        elif st.button(
            "Save this comparison",
            type="primary",
            key="save_stock_comparison",
        ):
            try:
                initialize_database()
                st.session_state["saved_comparison_id"] = save_stock_comparison(report)
            except Exception as exc:  # noqa: BLE001 - show safe persistence failure
                st.error(f"Could not save comparison ({type(exc).__name__}).")
            else:
                st.success(
                    f"Comparison saved with ID {st.session_state['saved_comparison_id']}."
                )


def _saved_reports_page() -> None:
    st.header("Saved Reports")
    try:
        initialize_database()
        reports = list_research_reports(limit=100)
        comparisons = list_stock_comparisons(limit=100)
    except Exception as exc:  # noqa: BLE001 - show a safe retrieval error
        st.error(f"Could not list saved reports ({type(exc).__name__}).")
        return

    entries = [
        {
            **item,
            "selection": f"research:{item['id']}",
            "report_type": "Single-stock",
            "ticker_label": item["ticker"],
            "company": item.get("company_name") or "",
        }
        for item in reports
    ] + [
        {
            **item,
            "selection": f"comparison:{item['id']}",
            "report_type": "Comparison",
            "ticker_label": ", ".join(item["tickers"]),
            "company": "",
        }
        for item in comparisons
    ]
    entries.sort(key=lambda item: item["id"], reverse=True)
    if not entries:
        st.info("No research reports or comparisons have been saved yet.")
        return

    st.dataframe(
        [
            {
                "ID": item["id"],
                "Type": item["report_type"],
                "Ticker(s)": item["ticker_label"],
                "Company": item["company"],
                "Question": item["research_question"],
                "Generated": item["generated_at"],
                "Saved": item["stored_at"],
            }
            for item in entries
        ],
        width="stretch",
        hide_index=True,
    )

    by_selection = {item["selection"]: item for item in entries}
    with st.form("open_report_form"):
        selection = st.selectbox(
            "Choose a report to open",
            options=list(by_selection),
            format_func=lambda value: (
                f"{by_selection[value]['report_type']} #{by_selection[value]['id']} · "
                f"{by_selection[value]['ticker_label']} · "
                f"{by_selection[value]['research_question']}"
            ),
            key="saved_report_choice",
        )
        open_report = st.form_submit_button("Open report", key="open_saved_report")

    if open_report:
        report_type, raw_id = selection.split(":", maxsplit=1)
        report_id = int(raw_id)
        try:
            if report_type == "comparison":
                report = get_stock_comparison(report_id)
            else:
                report = get_research_report(report_id)
        except Exception as exc:  # noqa: BLE001 - show a safe retrieval error
            st.error(f"Could not open report ({type(exc).__name__}).")
        else:
            st.session_state["opened_report"] = report
            st.session_state["opened_report_id"] = report_id
            st.session_state["opened_report_type"] = report_type

    opened_report = st.session_state.get("opened_report")
    if isinstance(opened_report, dict):
        st.divider()
        st.caption(
            f"Saved {st.session_state.get('opened_report_type', 'research')} "
            f"#{st.session_state.get('opened_report_id')}"
        )
        if st.session_state.get("opened_report_type") == "comparison":
            _show_comparison_report(opened_report)
        else:
            _show_report(opened_report)


def _format_portfolio(portfolio_id: int, portfolios: dict[int, dict[str, Any]]) -> str:
    item = portfolios[portfolio_id]
    return f"#{portfolio_id} · {item['name']} · ₹{item['cash_balance']:,.2f} cash"


def _paper_trading_page() -> None:
    st.header("Paper Trading")
    st.caption(
        "All trades are simulated in the local paper ledger. No brokerage "
        "connection or real orders are available."
    )

    with st.expander("Create portfolio"):
        with st.form("create_portfolio_form"):
            name = st.text_input(
                "Portfolio name",
                value=DEFAULT_PORTFOLIO_NAME,
                key="new_portfolio_name",
            )
            initial_cash = st.number_input(
                "Initial cash (₹)",
                min_value=0.0,
                value=get_default_initial_cash(),
                step=10000.0,
                key="new_portfolio_cash",
            )
            create = st.form_submit_button("Create portfolio", key="create_portfolio_submit")
        if create:
            try:
                create_portfolio(name=name, initial_cash=initial_cash)
            except Exception as exc:  # noqa: BLE001 - show a safe persistence error
                st.error(f"Could not create portfolio ({type(exc).__name__}).")
            else:
                st.success("Paper portfolio created.")

    try:
        portfolio_rows = list_portfolios()
    except Exception as exc:  # noqa: BLE001 - show a safe retrieval error
        st.error(f"Could not list portfolios ({type(exc).__name__}).")
        return

    if not portfolio_rows:
        st.info("Create a portfolio to view its paper-trading ledger.")
        return

    portfolios = {int(item["id"]): item for item in portfolio_rows}
    portfolio_id = st.selectbox(
        "Portfolio",
        options=list(portfolios),
        format_func=lambda value: _format_portfolio(value, portfolios),
        key="paper_portfolio_choice",
    )

    try:
        summary = get_portfolio_summary(portfolio_id)
    except Exception as exc:  # noqa: BLE001 - show a safe portfolio error
        st.error(f"Could not load portfolio summary ({type(exc).__name__}).")
        return

    metrics = st.columns(4)
    metrics[0].metric("Cash balance", f"₹{summary['cash_balance']:,.2f}")
    metrics[1].metric("Initial cash", f"₹{summary['initial_cash']:,.2f}")
    metrics[2].metric("Realized P&L", f"₹{summary['realized_pnl']:,.2f}")
    metrics[3].metric("Simulated costs paid", f"₹{summary['total_fees']:,.2f}")

    st.subheader("Portfolio valuation")
    st.caption(
        "Refresh retrieves the latest daily close returned by Yahoo Finance; it is "
        "not guaranteed live exchange data, and dates can differ by ticker. "
        "Dividends and corporate actions are not modeled. Portfolio totals are "
        "shown only when every holding has a valid returned price."
    )
    quote_state_key = f"portfolio_quotes_{portfolio_id}"
    if st.button("Refresh holding prices", key="refresh_portfolio_quotes"):
        st.session_state[quote_state_key] = refresh_portfolio_quotes(
            summary["holdings"]
        )
    quotes = st.session_state.get(quote_state_key, {})
    valuation = build_portfolio_valuation(summary, quotes)
    valuation_metrics = st.columns(4)
    total_value = valuation["total_value"]
    valuation_metrics[0].metric(
        "Portfolio value",
        f"₹{total_value:,.2f}" if total_value is not None else "Incomplete",
    )
    total_pnl = valuation["total_pnl"]
    valuation_metrics[1].metric(
        "Total P&L",
        f"₹{total_pnl:,.2f}" if total_pnl is not None else "Incomplete",
    )
    total_return = valuation["total_return_percent"]
    valuation_metrics[2].metric(
        "Total return",
        f"{total_return:.2f}%" if total_return is not None else "Unavailable",
    )
    valuation_metrics[3].metric("Holdings", summary["holdings_count"])
    if not valuation["valuation_complete"]:
        st.warning(
            "At least one holding has no valid quote. The displayed known-value "
            "subtotal is partial and is not used to calculate total P&L or return."
        )
        st.caption(
            f"Cash plus priced holdings: ₹{valuation['partial_total_value']:,.2f} "
            "(partial only)."
        )
    if valuation["holdings"]:
        st.dataframe(valuation["holdings"], hide_index=True, width="stretch")
    else:
        st.caption("No holdings in this portfolio; value equals the cash balance.")

    st.subheader("Create pending proposal")
    st.caption(
        "Proposal prices are user-entered and are not checked against refreshed "
        "quotes when you approve them."
    )
    try:
        saved_reports = list_research_reports(limit=100)
    except Exception:  # noqa: BLE001 - reports are optional for proposal creation
        saved_reports = []
        st.warning(
            "Saved reports could not be listed; proposals can still be created "
            "without a report link."
        )

    report_options: list[int | None] = [None] + [int(item["id"]) for item in saved_reports]
    report_labels: dict[int | None, str] = {None: "No linked report"}
    report_labels.update(
        {
            int(item["id"]): f"#{item['id']} · {item['ticker']} · {item['research_question']}"
            for item in saved_reports
        }
    )
    with st.form("create_proposal_form"):
        columns = st.columns(2)
        ticker = columns[0].text_input("Ticker", placeholder="RELIANCE.NS", key="proposal_ticker")
        side = columns[1].selectbox("Side", options=["BUY", "SELL"], key="proposal_side")
        quantity = st.number_input(
            "Quantity", min_value=1, value=1, step=1, key="proposal_quantity"
        )
        price = st.number_input(
            "Proposed price per share (₹)",
            min_value=0.01,
            value=100.0,
            step=1.0,
            key="proposal_price",
        )
        cost_bps = st.number_input(
            "Assumed transaction cost (basis points)",
            min_value=0.0,
            max_value=10_000.0,
            value=0.0,
            step=1.0,
            help=(
                "Simulation assumption applied to notional per trade. It is not a "
                "broker quote, statutory fee schedule, or tax estimate."
            ),
            key="proposal_transaction_cost_bps",
        )
        rationale = st.text_area("Rationale", max_chars=2000, key="proposal_rationale")
        report_id = st.selectbox(
            "Research report (optional)",
            options=report_options,
            format_func=lambda value: report_labels[value],
            key="proposal_report_id",
        )
        propose = st.form_submit_button("Create pending proposal", key="create_proposal_submit")
    if propose:
        try:
            proposal_id = create_trade_proposal(
                portfolio_id=portfolio_id,
                ticker=ticker,
                side=side,
                quantity=int(quantity),
                proposed_price=price,
                rationale=rationale,
                research_report_id=report_id,
                transaction_cost_bps=cost_bps,
            )
        except Exception as exc:  # noqa: BLE001 - show a safe validation error
            st.error(f"Could not create proposal ({type(exc).__name__}).")
        else:
            st.success(f"Proposal #{proposal_id} created with PENDING status.")
            estimated_fee = round(
                float(quantity) * float(price) * float(cost_bps) / 10_000, 2
            )
            st.caption(
                f"At the saved assumption, the estimated simulated cost is "
                f"₹{estimated_fee:,.2f} ({cost_bps:g} bps). This is not a broker "
                "quote or statutory fee estimate."
            )

    try:
        proposals = list_trade_proposals(portfolio_id=portfolio_id, limit=100)
        trades = list_paper_trades(portfolio_id=portfolio_id, limit=100)
    except Exception as exc:  # noqa: BLE001 - show a safe retrieval error
        st.error(f"Could not load proposal or trade history ({type(exc).__name__}).")
        return

    st.subheader("Proposal history")
    pending = [item for item in proposals if item["status"] == "PENDING"]
    for item in pending:
        with st.container(border=True):
            st.markdown(
                f"**Proposal #{item['id']} · {item['side']} {item['quantity']} {item['ticker']}**"
            )
            st.write(
                f"Proposed price: ₹{item['proposed_price']:,.2f} per share · "
                f"Cost assumption: {item['transaction_cost_bps']:g} bps · "
                f"Rationale: {item['rationale']}"
            )
            with st.form(f"review_proposal_form_{item['id']}"):
                confirmed = st.checkbox(
                    "I confirm: approve this proposal and execute the simulated paper trade.",
                    key=f"confirm_approval_{item['id']}",
                )
                approve = st.form_submit_button(
                    "Approve & execute paper trade",
                    key=f"approve_proposal_{item['id']}",
                )
                reject = st.form_submit_button(
                    "Reject proposal",
                    key=f"reject_proposal_{item['id']}",
                )
            if approve:
                if not confirmed:
                    st.warning("Check the confirmation box before approving.")
                else:
                    try:
                        result = review_trade_proposal(item["id"], approved=True)
                    except Exception as exc:  # noqa: BLE001 - show a safe review error
                        st.error(f"Could not approve proposal ({type(exc).__name__}).")
                    else:
                        st.session_state["paper_notice"] = (
                            f"Proposal #{item['id']} approved; simulated trade "
                            f"#{result.get('trade_id')} recorded."
                        )
                        st.rerun()
            elif reject:
                try:
                    review_trade_proposal(item["id"], approved=False)
                except Exception as exc:  # noqa: BLE001 - show a safe review error
                    st.error(f"Could not reject proposal ({type(exc).__name__}).")
                else:
                    st.session_state["paper_notice"] = (
                        f"Proposal #{item['id']} rejected. No paper trade was executed."
                    )
                    st.rerun()

    if notice := st.session_state.pop("paper_notice", None):
        st.success(notice)
    if proposals:
        st.dataframe(proposals, hide_index=True, width="stretch")
    else:
        st.info("No proposals have been created for this portfolio.")

    st.subheader("Executed paper trades")
    if trades:
        st.dataframe(trades, hide_index=True, width="stretch")
    else:
        st.caption("No simulated trades have been executed.")


def _preferences_page() -> None:
    st.header("Preferences")
    st.write(
        "Save only durable preferences you explicitly want remembered. "
        "Preferences are private and are not financial evidence or live portfolio data."
    )
    st.caption(
        "Use report style, research interests, or explicitly stated investment "
        "horizon and risk constraints. Do not save holdings, balances, income, "
        "credentials, current prices, news, or research claims."
    )
    if notice := st.session_state.pop("preferences_notice", None):
        st.success(notice)

    try:
        current = read_preferences()
    except Exception as exc:  # noqa: BLE001 - show a safe memory error
        st.error(f"Could not read preferences ({type(exc).__name__}).")
        current = None

    st.text_area(
        "Saved preferences",
        value=current or "No preferences have been saved.",
        height=180,
        disabled=True,
    )

    with st.form("save_preference_form"):
        category = st.selectbox(
            "Preference type",
            options=PREFERENCE_CATEGORIES,
            key="preference_category",
        )
        preference = st.text_input(
            "Preference to remember",
            max_chars=500,
            placeholder="For example: Use concise summaries with a short risk section.",
            key="preference_value",
        )
        save = st.form_submit_button("Save this preference", key="save_preference_submit")
    if save:
        try:
            save_preference(category, preference)
        except Exception as exc:  # noqa: BLE001 - show a safe memory error
            st.error(f"Could not save preference ({type(exc).__name__}).")
        else:
            st.session_state["preferences_notice"] = (
                "Preference saved for future research requests."
            )
            st.rerun()

    with st.form("clear_preferences_form"):
        confirmed = st.checkbox(
            "I understand this clears all saved preferences.",
            key="confirm_clear_preferences",
        )
        clear = st.form_submit_button("Clear saved preferences", key="clear_preferences_submit")
    if clear:
        if not confirmed:
            st.warning("Confirm the checkbox before clearing preferences.")
        else:
            try:
                clear_preferences()
            except Exception as exc:  # noqa: BLE001 - show a safe memory error
                st.error(f"Could not clear preferences ({type(exc).__name__}).")
            else:
                st.session_state["preferences_notice"] = "Saved preferences cleared."
                st.rerun()

    if has_saved_preferences(current):
        st.caption("Only preferences you explicitly submitted are stored.")


def main() -> None:
    """Render the local advisor interface."""
    st.set_page_config(
        page_title="NIFTY 50 Investment Advisor",
        page_icon="📈",
        layout="wide",
    )
    st.title("NIFTY 50 Investment Advisor")
    st.caption("Evidence-led research · private preferences · simulated paper trading")

    page = st.sidebar.radio("Workspace", options=PAGES, key="ui_page")
    if page == "Research & Reports":
        _research_page()
    elif page == "Saved Reports":
        _saved_reports_page()
    elif page == "Paper Trading":
        _paper_trading_page()
    else:
        _preferences_page()


if __name__ == "__main__":
    main()
