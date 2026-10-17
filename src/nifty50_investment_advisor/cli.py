
"""Command-line interface for the NIFTY 50 Investment Advisor."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


from nifty50_investment_advisor.database import (
    get_research_report,
    initialize_database,
    list_research_reports,
    save_research_report,
)


from nifty50_investment_advisor.portfolio import (
    DEFAULT_INITIAL_CASH,
    DEFAULT_PORTFOLIO_NAME,
    create_portfolio,
    create_trade_proposal,
    get_portfolio_summary,
    list_paper_trades,
    list_portfolios,
    list_trade_proposals,
    review_trade_proposal,
)

from nifty50_investment_advisor.research import run_research


def _print_json(data: Any) -> None:
    """Print structured results in a readable format."""
    print(json.dumps(data, indent=2, default=str))


def _add_portfolio_commands(subparsers: Any) -> None:
    """Register portfolio-related commands."""

    create_parser = subparsers.add_parser(
        "portfolio-create",
        help="Create a paper-trading portfolio.",
    )
    create_parser.add_argument(
        "--name",
        default=DEFAULT_PORTFOLIO_NAME,
        help="Portfolio name.",
    )
    create_parser.add_argument(
        "--cash",
        type=float,
        default=DEFAULT_INITIAL_CASH,
        help="Initial cash balance in INR.",
    )

    subparsers.add_parser(
        "portfolio-list",
        help="List paper-trading portfolios.",
    )

    show_parser = subparsers.add_parser(
        "portfolio-show",
        help="Show a portfolio's cash and holdings.",
    )
    show_parser.add_argument(
        "portfolio_id",
        type=int,
        help="ID of the portfolio to display.",
    )

    research_parser = subparsers.add_parser(
        "research",
        help="Research a stock using real data and the configured LLM.",
    )
    research_parser.add_argument(
        "question",
        help="Research question or stock-analysis request.",
    )
    research_parser.add_argument(
        "--save",
        action="store_true",
        help="Save the generated report to the local database.",
    )
    
    research_list_parser = subparsers.add_parser(
        "research-list",
        help="List saved research reports.",
    )
    research_list_parser.add_argument(
        "--ticker",
        help="Filter reports by ticker, e.g. RELIANCE.NS.",
    )
    research_list_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of reports to display (1-500).",
    )

    research_show_parser = subparsers.add_parser(
        "research-show",
        help="Display a saved research report.",
    )
    research_show_parser.add_argument(
        "report_id",
        type=int,
        help="ID of the saved research report.",
    )
    
    # Create a paper-trade proposal (does not execute a trade).
    proposal_create_parser = subparsers.add_parser(
        "proposal-create",
        help="Create a paper-trade proposal for human review.",
    )
    proposal_create_parser.add_argument(
        "--portfolio-id",
        type=int,
        required=True,
        help="ID of the target portfolio.",
    )
    proposal_create_parser.add_argument(
        "--ticker",
        required=True,
        help="Stock ticker, e.g. RELIANCE.NS.",
    )
    proposal_create_parser.add_argument(
        "--side",
        choices=["BUY", "SELL"],
        required=True,
        help="Proposed trade direction.",
    )
    proposal_create_parser.add_argument(
        "--quantity",
        type=int,
        required=True,
        help="Number of shares.",
    )
    proposal_create_parser.add_argument(
        "--price",
        type=float,
        required=True,
        help="Proposed price per share in INR.",
    )
    proposal_create_parser.add_argument(
        "--rationale",
        required=True,
        help="Reason for proposing the trade.",
    )
    proposal_create_parser.add_argument(
        "--report-id",
        type=int,
        help="Optional ID of a saved research report.",
    )

    # List proposals, optionally filtered by portfolio and status.
    proposal_list_parser = subparsers.add_parser(
        "proposal-list",
        help="List paper-trade proposals.",
    )
    proposal_list_parser.add_argument(
        "--portfolio-id",
        type=int,
        help="Filter by portfolio ID.",
    )
    proposal_list_parser.add_argument(
        "--status",
        choices=["PENDING", "APPROVED", "REJECTED"],
        help="Filter by proposal status.",
    )
    proposal_list_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum proposals to display.",
    )

    # Require an explicit human decision before applying a paper trade.
    proposal_review_parser = subparsers.add_parser(
        "proposal-review",
        help="Approve or reject a pending paper-trade proposal.",
    )
    proposal_review_parser.add_argument(
        "proposal_id",
        type=int,
        help="ID of the proposal to review.",
    )
    review_decision = proposal_review_parser.add_mutually_exclusive_group(
        required=True,
    )
    review_decision.add_argument(
        "--approve",
        action="store_true",
        help="Approve and apply the paper trade.",
    )
    review_decision.add_argument(
        "--reject",
        action="store_true",
        help="Reject the proposal without executing a trade.",
    )

    # Show the history of paper trades.
    trade_list_parser = subparsers.add_parser(
        "trade-list",
        help="List executed paper trades.",
    )
    trade_list_parser.add_argument(
        "--portfolio-id",
        type=int,
        help="Filter by portfolio ID.",
    )
    trade_list_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum trades to display.",
    )




def main() -> None:
    """Initialize the database and execute a CLI command."""

    parser = argparse.ArgumentParser(
        prog="nifty50-advisor",
        description=(
            "Research NIFTY 50 stocks and manage a human-approved "
            "paper-trading portfolio."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version="nifty50-advisor 0.1.0",
    )

    subparsers = parser.add_subparsers(dest="command")
    _add_portfolio_commands(subparsers)
    args = parser.parse_args()

    try:
        initialize_database()
    except Exception as exc:
        print(f"Database initialization failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.command == "portfolio-create":
        try:
            portfolio_id = create_portfolio(
                name=args.name,
                initial_cash=args.cash,
            )
            print(f"Created portfolio with ID: {portfolio_id}")
            _print_json(get_portfolio_summary(portfolio_id))
        except (ValueError, TypeError) as exc:
            parser.error(str(exc))

    elif args.command == "portfolio-list":
        try:
            _print_json(list_portfolios())
        except Exception as exc:
            parser.error(f"Could not list portfolios: {exc}")

    elif args.command == "portfolio-show":
        try:
            summary = get_portfolio_summary(args.portfolio_id)
            if summary is None:
                parser.error(f"Portfolio {args.portfolio_id} was not found.")
            _print_json(summary)
        except (ValueError, TypeError) as exc:
            parser.error(str(exc))

    
    elif args.command == "research-list":
        try:
            reports = list_research_reports(
                limit=args.limit,
                ticker=args.ticker,
            )
            _print_json(reports)
        except (ValueError, TypeError) as exc:
            parser.error(str(exc))
        except Exception as exc:
            parser.error(f"Could not list research reports: {exc}")

    elif args.command == "research-show":
        try:
            report = get_research_report(args.report_id)
            if report is None:
                parser.error(
                    f"Research report {args.report_id} was not found."
                )
            _print_json(report)
        except (ValueError, TypeError) as exc:
            parser.error(str(exc))
        except Exception as exc:
            parser.error(f"Could not retrieve research report: {exc}")
            

    elif args.command == "research":
        try:
            result = run_research(args.question)
        except Exception as exc:
            parser.error(f"Research failed: {exc}")

        # Always show the retrieval results and errors for transparency.
        print("\nResearch result:")
        _print_json(result)

        if not result.get("ok", False):
            print(
                "\nWARNING: Research did not complete successfully. "
                "Do not treat this as a completed investment analysis.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        if args.save:
            report = result.get("report")
            if not isinstance(report, dict):
                parser.error("Research returned no valid report to save.")

            try:
                report_id = save_research_report(report)
            except Exception as exc:
                parser.error(f"Could not save research report: {exc}")

            print(f"\nResearch report saved with ID: {report_id}")

    
    elif args.command == "proposal-create":
        try:
            proposal_id = create_trade_proposal(
                portfolio_id=args.portfolio_id,
                ticker=args.ticker,
                side=args.side,
                quantity=args.quantity,
                proposed_price=args.price,
                rationale=args.rationale,
                research_report_id=args.report_id,
            )
            print(f"Created trade proposal with ID: {proposal_id}")
            _print_json(
                list_trade_proposals(
                    limit=50,
                    status="PENDING",
                )
            )
        except (ValueError, TypeError) as exc:
            parser.error(str(exc))
        except Exception as exc:
            parser.error(f"Could not create proposal: {exc}")

    elif args.command == "proposal-list":
        try:
            proposals = list_trade_proposals(
                portfolio_id=args.portfolio_id,
                status=args.status,
                limit=args.limit,
            )
            _print_json(proposals)
        except (ValueError, TypeError) as exc:
            parser.error(str(exc))
        except Exception as exc:
            parser.error(f"Could not list proposals: {exc}")

    elif args.command == "proposal-review":
        try:
            result = review_trade_proposal(
                proposal_id=args.proposal_id,
                approved=args.approve,
            )
            _print_json(result)
        except (ValueError, TypeError) as exc:
            parser.error(str(exc))
        except Exception as exc:
            parser.error(f"Could not review proposal: {exc}")

    elif args.command == "trade-list":
        try:
            trades = list_paper_trades(
                portfolio_id=args.portfolio_id,
                limit=args.limit,
            )
            _print_json(trades)
        except (ValueError, TypeError) as exc:
            parser.error(str(exc))
        except Exception as exc:
            parser.error(f"Could not list paper trades: {exc}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
