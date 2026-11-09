"""CLI cost assumptions are forwarded to the deterministic ledger."""

from nifty50_investment_advisor import cli


def test_proposal_cli_forwards_user_supplied_cost_rate(monkeypatch, capsys):
    captured = {}
    monkeypatch.setattr(cli, "initialize_database", lambda: None)
    monkeypatch.setattr(
        cli,
        "create_trade_proposal",
        lambda **kwargs: captured.update(kwargs) or 7,
    )
    monkeypatch.setattr(cli, "list_trade_proposals", lambda **_kwargs: [])
    monkeypatch.setattr(
        "sys.argv",
        [
            "nifty50-advisor",
            "proposal-create",
            "--portfolio-id",
            "1",
            "--ticker",
            "RELIANCE.NS",
            "--side",
            "BUY",
            "--quantity",
            "2",
            "--price",
            "100",
            "--cost-bps",
            "12.5",
            "--rationale",
            "Test-only proposal",
        ],
    )

    cli.main()

    assert captured["transaction_cost_bps"] == 12.5
    assert "Created trade proposal with ID: 7" in capsys.readouterr().out
