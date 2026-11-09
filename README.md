
# NIFTY 50 Agentic Investment Advisor with Paper Trading

An educational Python project for evidence-based research and paper trading
of stocks in the NIFTY 50 universe using Deep Agents.

## Project goals

- Research one supported NIFTY 50 stock or index, or compare 2 to 5 explicitly supplied current NIFTY 50 constituents.
- Examine historical prices, technical indicators, company fundamentals,
  and recent news.
- Use one main Deep Agent and two specialist subagents.
- Support configurable OpenAI, Groq, Google Gemini, and NVIDIA models.
- Generate research reports that explain evidence, uncertainty, and risks.
- Maintain a persistent virtual portfolio using SQLite.
- Require explicit human approval before every paper trade.

## Safety

This project is intended for education and research. It must not connect
to a real brokerage or execute real-money transactions.

LLM-generated analysis is not a guarantee of future investment performance.
When reliable evidence is unavailable, the application should communicate
the limitation rather than inventing facts.

## Technology stack

- Python 3.12
- uv
- Deep Agents
- LangChain model integrations
- Streamlit local interface
- Pydantic
- pandas and yfinance
- SQLite
- pytest

## Development status

The project includes the CLI and a local Streamlit interface for research,
saved reports, private user preferences, and deterministic paper trading.
Research uses configured live data sources and one of the supported LLM
providers. Paper proposals are created and reviewed separately from model
research. The agent cannot inspect portfolios or create paper trades; the
Streamlit interface and CLI provide those actions.

The comparison service validates symbols against the current NIFTY 50 member
file published by [NSE Indices](https://niftyindices.com/indices/equity/broad-based-indices/nifty--50)
([constituent CSV](https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv)).
It requests that file when a comparison is submitted and caches a successful result in-process for six hours. A cached
list is marked stale if refresh fails; without a successful list it fails
clearly rather than silently accepting an outdated universe. The deterministic
summary and structured differences only list fetched values and retrieval
status; no LLM-generated comparison narrative is used, so the summary cannot
choose a winner. Each per-ticker research report still uses the configured LLM
for single-stock analysis.

## Initial setup

From the project directory, run:

    uv lock
    uv sync --group dev

Verify the Python environment:

    uv run python --version

Verify installed imports:

    uv run python -c "import deepagents; print('Deep Agents import OK')"

The lockfile and dependency environment are managed by uv.

## Configuration

Copy the template and fill in your own values:

    copy .env.example .env

Then set at least `LLM_PROVIDER` and the API key for that provider:

| Variable | Required for | Default |
|---|---|---|
| `LLM_PROVIDER` | Research (agent + LLM) | — (required) |
| `LLM_MODEL` | Research | per-provider default (see `.env.example`) |
| `OPENAI_MODEL` / `GROQ_MODEL` / `GOOGLE_MODEL` / `NVIDIA_MODEL` | Research | per-provider defaults |
| `OPENAI_API_KEY` / `GROQ_API_KEY` / `GOOGLE_API_KEY` / `NVIDIA_API_KEY` | Research | — (only the active provider's key is needed) |
| `NVIDIA_BASE_URL` | NVIDIA provider only | — |
| `DATABASE_PATH` | Database location | `data/paper_trading.db` |
| `INITIAL_PAPER_CASH` | New portfolio starting cash | `100000` |

`DATABASE_PATH` and `INITIAL_PAPER_CASH` work without any LLM provider or
API key. Research features need a provider and its API key. Never commit
the real `.env`; only `.env.example` belongs in version control.

## Database and starting-cash settings

`DATABASE_PATH` selects the SQLite database and defaults to
`data/paper_trading.db`. A relative configured path resolves from the project
root, regardless of the current working directory. The database stores saved
research reports and the paper-trading ledger. `INITIAL_PAPER_CASH` defaults to
₹100,000 and supplies the default in the portfolio API, CLI, and Streamlit
form. A caller can pass a different amount, `portfolio-create --cash` can
override it, and the UI form accepts an explicit amount. Persistence settings
can be used without configuring an LLM provider or API key.

## CLI workflows

The CLI remains available alongside the browser interface. For example:

    uv run nifty50-advisor research "Review RELIANCE.NS" --save
    uv run nifty50-advisor research-list
    uv run nifty50-advisor compare RELIANCE.NS TCS.NS
    uv run nifty50-advisor compare RELIANCE.NS TCS.NS --question "Compare recent evidence" --save
    uv run nifty50-advisor portfolio-create
    uv run nifty50-advisor proposal-create --portfolio-id 1 --ticker RELIANCE.NS --side BUY --quantity 1 --price 1000 --cost-bps 5 --rationale "Example proposal"
    uv run nifty50-advisor proposal-review 1 --approve

Research is run only when the research command is invoked; `--save` explicitly
persists a successful single-stock report. `compare` accepts 2 to 5 distinct
supported tickers, normalizes case and whitespace, and requests the same market
and technical lookback periods for each. It retains per-ticker data, timestamps,
missing fields, and source errors. Its `--save` option explicitly persists a
completed typed comparison separately from single-stock reports. The
comparison universe comes from the current official NSE Indices CSV; enter a
Yahoo symbol such as `RELIANCE.NS` or the NSE symbol `RELIANCE`. Creating a
paper proposal leaves it pending. `--cost-bps` records a user-supplied simulated
cost rate per proposal; its default is zero and it is not a brokerage or tax
estimate. The human must explicitly approve or reject it with `proposal-review`
before the deterministic ledger can apply it. This does not connect to a broker
or place a real order.

## Local browser interface

Start the local interface from the project directory with:

    uv run streamlit run src/nifty50_investment_advisor/ui.py --server.address 127.0.0.1

The interface has five sections: **Dashboard** (portfolio KPIs, saved-report
counts, and cost-vs-value / unrealized-P&L charts for priced holdings),
Research & Reports (single-stock and Stock comparison), Saved Reports, Paper
Trading, and Preferences. Research runs after
form submission and successful reports are saved only after an explicit save
action. Saved Reports identifies comparison records separately and can reopen
them; any opened or freshly generated report can be downloaded as Markdown
or JSON (Markdown is the human-readable format; JSON is the faithful archive). Comparison supports the current NIFTY 50 constituent list and displays a
deterministic summary plus differences only for metrics returned for multiple
tickers. In Paper Trading, refresh prices explicitly to view last returned
daily closes, per-holding unrealized P&L, realized P&L, and total return. The
full portfolio value and return stay unavailable if any holding lacks a valid
quote. Calculated return excludes dividends and corporate actions. Proposal
cost assumptions are user-entered basis points; they are
simulation inputs, not actual fee or tax schedules. Creating a proposal leaves
it pending; approval requires a separate explicit action and confirmation,
while rejection is also explicit. Research and report
generation use the configured data sources and LLM. Portfolio and proposal
actions use deterministic Python code and SQLite, separate from the agent's
tools. Preferences are stored separately from reports and the paper ledger.
The command binds Streamlit to the local machine. The project configuration
also defaults the server address to `127.0.0.1`.

This is a single-user local application. Do not expose the Streamlit port on a
public network: the app does not provide authentication or per-user database
isolation. A hosted multi-user deployment requires an identity layer and
separate storage for each user before it is safe to publish.

## End-to-end demo walkthrough

This is the exact sequence used to demo the project end to end:

    # 1. Research a single stock and save the report
    uv run nifty50-advisor research "Review RELIANCE.NS" --save

    # 2. Compare 2-5 NIFTY 50 stocks (deterministic, no LLM narrative)
    uv run nifty50-advisor compare RELIANCE.NS TCS.NS

    # 3. Create a portfolio
    uv run nifty50-advisor portfolio-create --name Demo

    # 4. Create a pending proposal (creates nothing executable yet)
    uv run nifty50-advisor proposal-create --portfolio-id 1 \
        --ticker RELIANCE.NS --side BUY --quantity 1 --price 1000 \
        --cost-bps 5 --rationale "Example proposal"

    # 5. A human explicitly approves it (only then does the ledger move)
    uv run nifty50-advisor proposal-review 1 --approve

    # 6. View the updated portfolio
    uv run nifty50-advisor portfolio-show 1

The same flow exists in the Streamlit UI under Paper Trading, where price
refresh explicitly shows last returned closes, per-holding unrealized P&L,
and realized P&L.

## Testing

    uv run pytest
    uv run ruff check

The `tests/` suite is fully mocked (no network, no LLM calls). The
`scripts/` directory holds live/manual checks that call real services;
they are not part of the automated suite.

## Long-form report

See [REPORT.md](REPORT.md) for the full written report: problem framing,
model-vs-harness design, architecture, tools, subagents, skills, memory,
safety (human-approval gate), limitations, and the complete skill files in
the appendix.
