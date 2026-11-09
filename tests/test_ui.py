"""Streamlit UI tests use only temporary databases and memory directories."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import partial

import pytest
from streamlit.testing.v1 import AppTest

from nifty50_investment_advisor import config, database, memory, portfolio, ui
from nifty50_investment_advisor.reports import (
    ComparisonTickerReport,
    ResearchReport,
    StockComparisonReport,
)


class _SocketlessEventLoop(asyncio.SelectorEventLoop):
    """Avoid loopback socketpair creation blocked in restricted Windows tests."""

    def _make_self_pipe(self) -> None:
        self._ssock = None
        self._csock = None

    def _close_self_pipe(self) -> None:
        self._ssock = None
        self._csock = None

    def _write_to_self(self) -> None:
        # AppTest's script thread is joined directly and does not run this loop.
        return


@pytest.fixture(autouse=True)
def socketless_app_test_loop(monkeypatch):
    """Keep Streamlit AppTest isolated from local TCP socket access."""
    monkeypatch.setattr(asyncio, "new_event_loop", _SocketlessEventLoop)


def _ui_script() -> None:
    """Keep module imports inside the AppTest script source."""
    from nifty50_investment_advisor import ui as app_ui

    app_ui.main()


def _valid_report() -> dict:
    return {
        "ticker": "RELIANCE.NS",
        "company_name": "Reliance Industries",
        "generated_at": datetime.now(UTC).isoformat(),
        "research_question": "Review RELIANCE.NS",
        "summary": "A test-only report at the research service boundary.",
        "data": {
            "market_data": {"ok": True, "latest_close": 100.0},
            "technical_indicators": {"ok": True, "indicators": {}},
            "fundamentals": {"ok": True, "metrics": {}},
            "retrieval_status": {"market_data": "success"},
            "retrieval_errors": {},
        },
        "evidence": [
            {
                "claim": "Test evidence only.",
                "source_name": "Example source",
                "source_url": "https://example.com/research",
                "evidence_type": "market_data",
                "limitations": "Test fixture; not live market evidence.",
            }
        ],
        "uncertainty": ["Test uncertainty."],
        "risks": ["Test risk."],
        "missing_information": [],
        "conclusion": "Test conclusion.",
        "disclaimer": "Test fixture only.",
    }


def _valid_comparison() -> dict:
    stocks = []
    for ticker, close in (("RELIANCE.NS", 100.0), ("TCS.NS", 200.0)):
        individual = ResearchReport(
            ticker=ticker,
            company_name=ticker,
            research_question="Compare test evidence.",
            summary=f"Evidence record for {ticker}.",
            data={
                "market_data": {
                    "ok": True,
                    "latest_close": close,
                    "latest_date": "2026-10-21",
                    "source": "Test data source",
                },
                "retrieval_status": {"market_data": "success"},
                "retrieval_errors": {},
            },
            uncertainty=["Test uncertainty."],
            risks=["Test risk."],
            conclusion="Test conclusion.",
        )
        stocks.append(
            ComparisonTickerReport(
                ticker=ticker,
                report=individual,
                news={"ok": True, "query": f"{ticker} news", "articles": []},
            )
        )
    return StockComparisonReport(
        research_question="Compare test evidence.",
        tickers=[stock.ticker for stock in stocks],
        stocks=stocks,
        summary="The returned values differ; neither ticker is ranked.",
        uncertainty=["Test uncertainty."],
        conclusion="No winner is selected.",
    ).model_dump(mode="json")


@pytest.fixture
def isolated_services(tmp_path, monkeypatch):
    db_path = tmp_path / "paper-ledger.sqlite3"
    memory_path = tmp_path / "private-memory"
    settings_root = tmp_path / "settings-project"
    settings_root.mkdir()
    initialize_calls: list[None] = []
    database.initialize_database(db_path)
    monkeypatch.setattr(config, "_project_root", lambda: settings_root)

    def initialize() -> None:
        initialize_calls.append(None)
        database.initialize_database(db_path)

    monkeypatch.setattr(ui, "initialize_database", initialize)
    monkeypatch.setattr(
        ui, "save_research_report", partial(database.save_research_report, db_path=db_path)
    )
    monkeypatch.setattr(
        ui, "get_research_report", partial(database.get_research_report, db_path=db_path)
    )
    monkeypatch.setattr(
        ui,
        "list_research_reports",
        partial(database.list_research_reports, db_path=db_path),
    )
    monkeypatch.setattr(
        ui,
        "save_stock_comparison",
        partial(database.save_stock_comparison, db_path=db_path),
    )
    monkeypatch.setattr(
        ui,
        "get_stock_comparison",
        partial(database.get_stock_comparison, db_path=db_path),
    )
    monkeypatch.setattr(
        ui,
        "list_stock_comparisons",
        partial(database.list_stock_comparisons, db_path=db_path),
    )
    monkeypatch.setattr(
        ui, "create_portfolio", partial(portfolio.create_portfolio, db_path=db_path)
    )
    monkeypatch.setattr(ui, "list_portfolios", partial(portfolio.list_portfolios, db_path=db_path))
    monkeypatch.setattr(
        ui,
        "get_portfolio_summary",
        partial(portfolio.get_portfolio_summary, db_path=db_path),
    )
    monkeypatch.setattr(
        ui,
        "create_trade_proposal",
        partial(portfolio.create_trade_proposal, db_path=db_path),
    )
    monkeypatch.setattr(
        ui,
        "list_trade_proposals",
        partial(portfolio.list_trade_proposals, db_path=db_path),
    )
    monkeypatch.setattr(
        ui,
        "list_paper_trades",
        partial(portfolio.list_paper_trades, db_path=db_path),
    )
    monkeypatch.setattr(
        ui,
        "review_trade_proposal",
        partial(portfolio.review_trade_proposal, db_path=db_path),
    )
    monkeypatch.setattr(ui, "read_preferences", partial(memory.read_preferences, memory_path))
    monkeypatch.setattr(
        ui,
        "save_preference",
        partial(memory.save_preference, memory_directory=memory_path),
    )
    monkeypatch.setattr(
        ui,
        "clear_preferences",
        partial(memory.clear_preferences, memory_directory=memory_path),
    )

    assert db_path.resolve() != (memory_path / memory.PREFERENCES_FILENAME).resolve()
    assert not memory_path.resolve().is_relative_to(memory.PROJECT_ROOT.resolve())
    return {
        "db_path": db_path,
        "memory_path": memory_path,
        "initialize_calls": initialize_calls,
    }


def _run_app() -> AppTest:
    app = AppTest.from_function(_ui_script, default_timeout=30).run(timeout=30)
    assert not app.exception, [item.message for item in app.exception]
    return app


def _has_header(app: AppTest, text: str) -> bool:
    return any(item.value == text for item in app.header)


def test_navigation_renders_all_five_sections(isolated_services):
    # Dashboard is the default first page.
    app = _run_app()
    assert _has_header(app, "Dashboard")

    for page in ("Research & Reports", "Saved Reports", "Paper Trading", "Preferences"):
        app.radio(key="ui_page").set_value(page).run()
        assert not app.exception, [item.message for item in app.exception]
        assert _has_header(app, page)


def test_dashboard_empty_state_shows_message(isolated_services):
    app = _run_app()
    app.radio(key="ui_page").set_value("Dashboard").run()
    assert any(
        "No portfolio yet" in item.value or "Create one" in item.value
        for item in app.info
    )


def test_research_runs_only_on_submit_and_saves_only_on_explicit_action(
    isolated_services, monkeypatch
):
    calls: list[str] = []
    report = _valid_report()

    def research_stub(question: str) -> dict:
        calls.append(question)
        return {
            "ok": True,
            "question": question,
            "ticker": report["ticker"],
            "analysis": "Test analysis at the service boundary.",
            "news": {"ok": True, "articles": []},
            "agent_error": None,
            "report": report,
        }

    monkeypatch.setattr(ui, "run_research", research_stub)
    app = _run_app()
    app.radio(key="ui_page").set_value("Research & Reports").run()
    app.text_area(key="research_question").set_value("Review RELIANCE.NS")
    assert calls == []

    app.form_submit_button(key="run_research_submit").click().run()
    assert calls == ["Review RELIANCE.NS"]
    assert any("Research completed" in item.value for item in app.success)
    assert database.list_research_reports(db_path=isolated_services["db_path"]) == []

    app.button(key="save_research_report").click().run()
    reports = database.list_research_reports(db_path=isolated_services["db_path"])
    assert len(reports) == 1
    assert reports[0]["ticker"] == "RELIANCE.NS"

    app.button(key="save_research_report").click().run()
    assert len(database.list_research_reports(db_path=isolated_services["db_path"])) == 1


def test_saved_reports_opens_the_selected_report(isolated_services):
    report_id = database.save_research_report(_valid_report(), db_path=isolated_services["db_path"])
    app = _run_app()
    app.radio(key="ui_page").set_value("Saved Reports").run()
    assert app.dataframe
    app.form_submit_button(key="open_saved_report").click().run()
    assert app.session_state["opened_report_id"] == report_id
    assert _has_header(app, "Saved Reports")
    assert any(item.value == "RELIANCE.NS" for item in app.subheader)


def test_comparison_runs_only_on_submit_and_saves_only_explicitly(
    isolated_services, monkeypatch
):
    calls: list[tuple[str, str | None]] = []
    report = _valid_comparison()

    def comparison_stub(tickers: str, question: str | None) -> dict:
        calls.append((tickers, question))
        return {
            "ok": True,
            "tickers": report["tickers"],
            "analysis": report["summary"],
            "agent_error": None,
            "report": report,
        }

    monkeypatch.setattr(ui, "run_stock_comparison", comparison_stub)
    app = _run_app()
    app.radio(key="ui_page").set_value("Research & Reports").run()
    app.radio(key="research_workflow").set_value("Stock comparison").run()
    app.text_area(key="comparison_tickers").set_value(" reliance.ns, tcs.ns ")
    app.text_area(key="comparison_question").set_value("Compare recent evidence.")
    assert calls == []
    assert database.list_stock_comparisons(db_path=isolated_services["db_path"]) == []

    app.form_submit_button(key="compare_tickers_submit").click().run()
    assert calls == [(" reliance.ns, tcs.ns ", "Compare recent evidence.")]
    assert any("Comparison completed" in item.value for item in app.success)
    assert database.list_stock_comparisons(db_path=isolated_services["db_path"]) == []

    app.button(key="save_stock_comparison").click().run()
    saved = database.list_stock_comparisons(db_path=isolated_services["db_path"])
    assert len(saved) == 1
    assert saved[0]["report_type"] == "comparison"
    assert saved[0]["tickers"] == ["RELIANCE.NS", "TCS.NS"]

    app.button(key="save_stock_comparison").click().run()
    assert len(database.list_stock_comparisons(db_path=isolated_services["db_path"])) == 1


def test_saved_reports_opens_a_comparison_as_a_distinct_type(isolated_services):
    comparison_id = database.save_stock_comparison(
        _valid_comparison(),
        db_path=isolated_services["db_path"],
    )
    app = _run_app()
    app.radio(key="ui_page").set_value("Saved Reports").run()
    assert app.dataframe
    app.selectbox(key="saved_report_choice").set_value(f"comparison:{comparison_id}")
    app.form_submit_button(key="open_saved_report").click().run()

    assert app.session_state["opened_report_id"] == comparison_id
    assert app.session_state["opened_report_type"] == "comparison"
    assert any(item.value == "Stock comparison" for item in app.subheader)


def test_paper_trading_creates_a_portfolio_from_the_form(isolated_services):
    app = _run_app()
    app.radio(key="ui_page").set_value("Paper Trading").run()
    app.text_input(key="new_portfolio_name").set_value("Created in UI")
    app.number_input(key="new_portfolio_cash").set_value(25000.0)
    app.form_submit_button(key="create_portfolio_submit").click().run()

    rows = portfolio.list_portfolios(db_path=isolated_services["db_path"])
    assert len(rows) == 1
    assert rows[0]["name"] == "Created in UI"
    assert rows[0]["cash_balance"] == 25000.0


def test_paper_trading_form_uses_configured_default_cash(
    isolated_services, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INITIAL_PAPER_CASH", "76543.25")

    app = _run_app()
    app.radio(key="ui_page").set_value("Paper Trading").run()

    assert app.number_input(key="new_portfolio_cash").value == 76543.25


def test_paper_trading_refreshes_prices_only_after_explicit_click(
    isolated_services, monkeypatch
):
    db_path = isolated_services["db_path"]
    portfolio_id = portfolio.create_portfolio(
        "Valuation UI portfolio", 10_000, db_path=db_path
    )
    proposal_id = portfolio.create_trade_proposal(
        portfolio_id,
        "RELIANCE.NS",
        "BUY",
        2,
        100,
        "Test holding",
        db_path=db_path,
    )
    portfolio.review_trade_proposal(proposal_id, approved=True, db_path=db_path)
    calls = []

    def refresh(holdings):
        calls.append(holdings)
        return {
            "RELIANCE.NS": {
                "ok": True,
                "price": 110.0,
                "as_of": "2026-10-22",
                "source": "Test quote",
            }
        }

    monkeypatch.setattr(ui, "refresh_portfolio_quotes", refresh)
    app = _run_app()
    app.radio(key="ui_page").set_value("Paper Trading").run()

    assert calls == []
    app.button(key="refresh_portfolio_quotes").click().run()

    assert len(calls) == 1
    assert calls[0][0]["ticker"] == "RELIANCE.NS"
    assert app.session_state[f"portfolio_quotes_{portfolio_id}"]["RELIANCE.NS"]["price"] == 110.0


def test_proposal_stays_pending_until_explicit_confirmed_approval(isolated_services, monkeypatch):
    db_path = isolated_services["db_path"]
    portfolio_id = portfolio.create_portfolio("UI test portfolio", 100000, db_path=db_path)
    review_calls: list[tuple[int, bool]] = []

    def review_spy(proposal_id: int, approved: bool):
        review_calls.append((proposal_id, approved))
        return portfolio.review_trade_proposal(proposal_id, approved=approved, db_path=db_path)

    monkeypatch.setattr(ui, "review_trade_proposal", review_spy)
    app = _run_app()
    app.radio(key="ui_page").set_value("Paper Trading").run()
    app.text_input(key="proposal_ticker").set_value("RELIANCE.NS")
    app.text_area(key="proposal_rationale").set_value("Test-only proposal rationale")
    app.number_input(key="proposal_transaction_cost_bps").set_value(25.0)
    app.form_submit_button(key="create_proposal_submit").click().run()

    proposals = portfolio.list_trade_proposals(portfolio_id=portfolio_id, db_path=db_path)
    assert len(proposals) == 1
    proposal_id = proposals[0]["id"]
    assert proposals[0]["status"] == "PENDING"
    assert proposals[0]["transaction_cost_bps"] == 25.0
    assert portfolio.list_paper_trades(portfolio_id, db_path=db_path) == []

    app.form_submit_button(key=f"approve_proposal_{proposal_id}").click().run()
    assert review_calls == []
    assert (
        portfolio.list_trade_proposals(portfolio_id=portfolio_id, db_path=db_path)[0]["status"]
        == "PENDING"
    )

    app.checkbox(key=f"confirm_approval_{proposal_id}").check()
    app.form_submit_button(key=f"approve_proposal_{proposal_id}").click().run()
    assert review_calls == [(proposal_id, True)]
    assert (
        portfolio.list_trade_proposals(portfolio_id=portfolio_id, db_path=db_path)[0]["status"]
        == "APPROVED"
    )
    trades = portfolio.list_paper_trades(portfolio_id, db_path=db_path)
    assert len(trades) == 1
    assert trades[0]["fee_amount"] == 0.25

    app.text_area(key="proposal_rationale").set_value("Second test proposal")
    app.form_submit_button(key="create_proposal_submit").click().run()
    proposals = portfolio.list_trade_proposals(portfolio_id=portfolio_id, db_path=db_path)
    rejected_id = next(item["id"] for item in proposals if item["status"] == "PENDING")
    assert review_calls == [(proposal_id, True)]

    app.form_submit_button(key=f"reject_proposal_{rejected_id}").click().run()
    assert review_calls == [(proposal_id, True), (rejected_id, False)]
    statuses = {
        item["id"]: item["status"]
        for item in portfolio.list_trade_proposals(portfolio_id=portfolio_id, db_path=db_path)
    }
    assert statuses[rejected_id] == "REJECTED"
    assert len(portfolio.list_paper_trades(portfolio_id, db_path=db_path)) == 1


def test_preferences_require_explicit_save_and_deliberate_clear(isolated_services):
    app = _run_app()
    app.radio(key="ui_page").set_value("Preferences").run()
    assert isolated_services["initialize_calls"] == []

    app.text_input(key="preference_value").set_value("Use concise reports.")
    assert memory.read_preferences(isolated_services["memory_path"]) is None
    app.form_submit_button(key="save_preference_submit").click().run()
    current = memory.read_preferences(isolated_services["memory_path"])
    assert current is not None and "Use concise reports." in current
    assert any("Preference saved" in item.value for item in app.success)

    app.form_submit_button(key="clear_preferences_submit").click().run()


def test_dashboard_charts_and_kpis_after_refresh(isolated_services, monkeypatch):
    """Dashboard renders KPIs + holdings charts after an explicit price refresh."""
    db_path = isolated_services["db_path"]
    portfolio_id = portfolio.create_portfolio("Dash portfolio", 10_000, db_path=db_path)
    proposal_id = portfolio.create_trade_proposal(
        portfolio_id,
        "RELIANCE.NS",
        "BUY",
        2,
        100,
        "Seed",
        db_path=db_path,
    )
    portfolio.review_trade_proposal(proposal_id, approved=True, db_path=db_path)

    calls: list = []

    def refresh(holdings):
        calls.append(holdings)
        return {
            "RELIANCE.NS": {
                "ok": True,
                "price": 110.0,
                "as_of": "2026-10-22",
                "source": "Test quote",
            }
        }

    monkeypatch.setattr(ui, "refresh_portfolio_quotes", refresh)
    app = _run_app()
    assert _has_header(app, "Dashboard")
    assert calls == []  # refresh is explicit-only

    app.button(key="refresh_portfolio_quotes").click().run()
    assert len(calls) == 1

    # KPI: portfolio value = cash 9800 + holdings 220 = 10020; P&L = 20 (0.20%).
    metric_values = [item.value for item in app.metric]
    assert "₹10,020.00" in metric_values
    assert "₹20.00" in metric_values
    assert "0.20%" in metric_values

    # Charts render behind the "Holdings charts" subheader.
    assert any("Holdings charts" in item.value for item in app.subheader)


def test_dashboard_partial_quotes_warn_and_exclude(isolated_services, monkeypatch):
    """Unpriced holdings show the incomplete warning in the KPI row."""
    db_path = isolated_services["db_path"]
    portfolio_id = portfolio.create_portfolio("Partial dash", 10_000, db_path=db_path)
    for ticker, qty in (("RELIANCE.NS", 2), ("TCS.NS", 1)):
        pid = portfolio.create_trade_proposal(
            portfolio_id, ticker, "BUY", qty, 100, "Seed", db_path=db_path
        )
        portfolio.review_trade_proposal(pid, approved=True, db_path=db_path)

    monkeypatch.setattr(
        ui,
        "refresh_portfolio_quotes",
        lambda _h: {
            "RELIANCE.NS": {
                "ok": True,
                "price": 110.0,
                "as_of": "2026-10-22",
                "source": "Test quote",
            },
            "TCS.NS": {"ok": False, "error": "No quote."},
        },
    )
    app = _run_app()
    app.button(key="refresh_portfolio_quotes").click().run()

    assert any("Incomplete" in item.value for item in app.metric)
    assert any("no valid quote" in item.value for item in app.warning)
    # The unpriced holding is excluded from the priced-holdings caption path;
    # the chart header only appears when at least one holding is priced.
    assert any("Holdings charts" in item.value for item in app.subheader)


def test_saved_report_shows_export_buttons(isolated_services):
    """After opening a saved report, Markdown/JSON download buttons appear."""
    db_path = isolated_services["db_path"]
    database.save_research_report(_valid_report(), db_path=db_path)

    app = _run_app()
    app.radio(key="ui_page").set_value("Saved Reports").run()
    app.form_submit_button(key="open_saved_report").click().run()

    downloaded = app.get("download_button")
    assert downloaded
    labels = [item.label for item in downloaded]
    assert any("Markdown" in str(l) for l in labels)
    assert any("JSON" in str(l) for l in labels)
