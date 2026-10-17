
# NIFTY 50 Agentic Investment Advisor with Paper Trading

An educational Python project for evidence-based research and paper trading
of stocks in the NIFTY 50 universe using Deep Agents.

## Project goals

- Research individual NIFTY 50 stocks and compare multiple stocks.
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
- Pydantic
- pandas and yfinance
- SQLite
- pytest

## Development status

Phase 1 establishes the project structure and dependencies.

Provider configuration, live LLM connectivity, research tools, subagents,
reporting, the database, paper trading, human approval, and the CLI will be
implemented in subsequent development phases.

## Initial setup

From the project directory, run:

    uv lock
    uv sync --group dev

Verify the Python environment:

    uv run python --version

Verify installed imports:

    uv run python -c "import deepagents; print('Deep Agents import OK')"

The lockfile and dependency environment are managed by uv.
