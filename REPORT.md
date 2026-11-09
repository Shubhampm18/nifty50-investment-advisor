# Building an Agentic AI Investment Research Assistant

**Project:** NIFTY 50 Agentic Investment Advisor with Paper Trading
**Stack:** Python 3.12, uv, Deep Agents, LangChain, SQLite, Pydantic, pytest
**What it does:** researches NIFTY 50 stocks from real market data, technical indicators,
fundamentals and news; writes a validated, evidence-based research report; and keeps a
paper-trading portfolio where every trade needs explicit human approval.

---

## 1. The problem

I set out to research Indian stocks and then paper-trade them. Written down properly, that is
not a data problem — a useful stock answer is never one number. It is "the latest close was X on
date D, the 50-day average sits above the price, margins improved but debt grew, and three
earnings stories appeared this week that I could only see as headlines — so here is what the
evidence supports and what it does not."

Producing that needs four different kinds of work: deciding which evidence this question needs,
retrieving it, reasoning over incomplete and partly contradictory evidence, and stating the
uncertainty honestly. The first and last need judgement, and a fixed pipeline cannot supply it —
it cannot decide that a question about a recent price move needs no fundamentals, and it cannot
phrase the difference between "revenue grew" and "revenue grew, according to one unaudited
source".

So: deterministic Python for the arithmetic, the cash and the positions; a model for the
judgement. That split is the spine of the design.

One constraint shaped everything else. This is a money system: it must never reach a real broker
and must never execute a trade on its own. That single sentence decided the architecture, because
it forced me to choose exactly where the model's authority stops.

## 2. Model versus harness

The most useful idea I applied was to stop treating "the AI" as one thing:

- **The model** turns text into text, and can decide to call a tool. That is all it does.
- **The harness** is everything around it: which tools exist, what they may touch, what evidence
  reaches the model, in what shape, what it is told to do with it, what gets validated
  afterwards, and what is simply impossible for it to do.

Most of the reliability here comes from the harness. The model is a good reader and a poor
calculator, so it never calculates. It is persuasive, so it is never the only voice on whether a
trade happens. It can remember explicitly saved preferences, but it is never trusted to remember
a portfolio.

## 3. Architecture

```
             CLI and Streamlit UI
                          |
        +-----------------+------------------+
        |                                    |
   research pipeline                  trading actions
   (deterministic Python)             (deterministic Python)
        |                                    |
        |  1. question -> ticker              |  create portfolio
        |  2. retrieve evidence               |  create proposal  (never executes)
        |  3. build context blocks            |  approve / reject  --> SQLite
        |  4. invoke the agent                |        (atomic transaction)
        v                                    |
   MAIN DEEP AGENT  (the model)              |
        |                                    |
        |-- market-research sub-agent ------> get_market_data
        |                                    get_technical_indicators
        |                                    get_company_fundamentals
        |-- news-research sub-agent   ------> search_market_news
        |    (only when news is not already supplied)
        |
        |-- skills (3)     procedures, read on demand
        |-- filesystem     permission-scoped to the project
        v
   Structured ResearchReport (Pydantic-validated)
```

The point of that diagram: the model sits in the middle of the research path and is **absent from
the money path**. The agent produces a report; separate deterministic CLI and UI actions turn a
human decision into a database transaction. They meet only at the SQLite file.

## 4. The model layer

Four providers are supported — OpenAI, Groq, Google Gemini, NVIDIA — and switching between them
means editing one line in `.env`. That requirement exists because every provider failed
differently during development: one rejected a parameter my code sent, one warned the chosen
model was unknown to the integration, one behaved differently when binding tools.

Provider quirks are noise. If they leaked into the tools and prompts, swapping providers would
become a refactor. So all of it lives in one function:

```python
# model_provider.py — the only place provider differences exist
def create_chat_model(settings: Settings | None = None) -> BaseChatModel:
    config = settings or get_settings()
    api_key = config.require_api_key()          # names the exact env var to set
    model_name = config.selected_model

    if config.llm_provider == "nvidia":
        options = {"model": model_name, "api_key": api_key, "temperature": 0, ...}
        if config.nvidia_base_url:
            options["base_url"] = config.nvidia_base_url
        return ChatNVIDIA(**options)

    common = {"model": model_name, "temperature": 0, "timeout": 60, "max_retries": 2}
    if config.llm_provider == "openai":
        return ChatOpenAI(**common, api_key=api_key)
    if config.llm_provider == "groq":
        return ChatGroq(**common, api_key=api_key)
    if config.llm_provider == "google":
        return ChatGoogleGenerativeAI(**common, google_api_key=api_key)
    raise ValueError(f"Unsupported LLM provider: {config.llm_provider}")
```

Two deliberate choices. **There is no mock path** — no fallback returning a canned answer when an
API call fails, because replacing failed research with fake research is worse than failing
loudly. And temperature is 0, so the same question produces the same report, which makes
behaviour testable.

## 5. The harness

### 5.1 Tools — the agent's only way to act

| Tool | Returns |
| --- | --- |
| `get_market_data` | latest and previous close, percentage change, recent daily observations, source |
| `get_technical_indicators` | SMA 20/50, EMA 12/26, RSI 14, MACD line/signal/histogram, annualised volatility |
| `get_company_fundamentals` | company profile plus ~20 valuation, profitability and balance-sheet metrics |
| `search_market_news` | headlines, publishers, publication times and URLs from Google News RSS |

Four tools, each answering a different kind of question, so the agent can pick the depth the
question needs instead of calling everything. All four only read.

**The arithmetic is not in the model.** Indicators are computed in Python, not asked for.
Language models produce plausible wrong numbers without hesitating; a moving average is a
deterministic function of a price series and belongs in code. The model explains the numbers, it
never produces them.

**Failure is data, not an exception.** Every tool returns a structured result:

```python
# tools/market_data.py — the convention all four tools follow
if history.empty:
    return {"ok": False, "symbol": symbol,
            "error": "Yahoo Finance returned no historical data.",
            "source": "Yahoo Finance via yfinance"}
...
except Exception as exc:
    # error type only: no internal details sprayed into a prompt
    return {"ok": False, "symbol": symbol,
            "error": f"Market-data retrieval failed: {type(exc).__name__}",
            "source": "Yahoo Finance via yfinance"}
```

Numeric fields pass through a `_number()` helper that turns NaN and infinity into `None`, so a
missing value stays visibly missing instead of becoming `0.0`. In a financial report, missing and
zero mean very different things, and the code keeps them apart all the way into the finished
document. The ugly edges are handled too: RSI has an explicit branch for a series with no losses
(which would divide by zero) and for a flat series (50 by convention). The news tool separates
HTTP errors from network errors, and validates every URL before returning it — the whole point of
that tool is that the model never has to reconstruct a link.

### 5.2 Sub-agents and the Deep Agent itself

Two specialists: `market-research`, holding the three market tools, and `news-research`, holding
the news tool.

**Why delegate.** The three market tools return long, detailed output. If the main agent held
every tool, its context would fill with raw price tables before it reached the reasoning.
A specialist does noisy work in a separate context and returns only the conclusion — which also
mirrors how the job is really done: one person pulls the numbers, another checks the news,
someone else decides what it means.

Here is the whole agent construction:

```python
# agent.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_SOURCE = "/skills/"

# Skills are read from disk, so the agent's filesystem root is the project.
# Rules are evaluated in order and the first match wins; anything unmatched is allowed,
# which is why the credentials and the trading ledger are named here.
SENSITIVE_PATH_RULES = [
    FilesystemPermission(
        operations=["read", "write"], paths=["/.env", "/.env.*", "/data/**"], mode="deny",
    ),
    FilesystemPermission(
        operations=["read", "write"], paths=["/.venv/**", "/.git/**", "/.zcode/**"], mode="deny",
    ),
]


def create_investment_agent(include_news_subagent: bool = True):
    model = create_chat_model()

    market_research_subagent = {
        "name": "market-research",
        "description": (
            "Researches NIFTY 50 and Indian equities using real historical "
            "prices, technical indicators, and company fundamentals. ..."
        ),
        "tools": [get_market_data, get_technical_indicators, get_company_fundamentals],
        "system_prompt": MARKET_RESEARCH_PROMPT,
    }
    subagents = [market_research_subagent]

    if include_news_subagent:
        subagents.append({
            "name": "news-research",
            "description": "Searches real Google News RSS results ...",
            "model": model,
            "tools": [search_market_news],
            "system_prompt": NEWS_RESEARCH_PROMPT,
        })

    return create_deep_agent(
        model=model,
        tools=[],
        system_prompt=MAIN_SYSTEM_PROMPT,
        subagents=subagents,
        backend=FilesystemBackend(root_dir=PROJECT_ROOT, virtual_mode=True),
        skills=[SKILLS_SOURCE],
        permissions=SENSITIVE_PATH_RULES,
    )
```

**Delegation is bounded, not just permitted.** The main agent must make *at most one call to
each specialist per request*, must not re-call one for a "more polished" answer, and must treat a
concise reply as complete rather than truncated. Those rules exist because I watched the agent do
the opposite: when a specialist answered briefly, the main agent assumed the answer was
incomplete and called it again. Each retry costs money, fills the context with duplicate
evidence, and produces no better answer. Constraining delegation in the prompt fixed a real
failure mode.

**Context removes work rather than discouraging it.** The pipeline builds the agent with
`include_news_subagent=not has_structured_news`. If news was already retrieved, the specialist is
not built at all, so the model cannot waste a turn rediscovering what is already in front of it.
Preventing an action beats asking the model not to take it.

For the viva: `create_deep_agent` also adds a `general-purpose` sub-agent by default when a
synchronous one is not supplied, so the running agent has three, not two. I know it is there.

### 5.3 Skills

Three skills live as Markdown files under `skills/` — **the full text of all three is in
Appendix A**. In one line each: *stock-research* is how to research a stock, *news-verification*
is how to treat news as evidence, and *investment-risk* is how to reason about risk and refuse
unsupported certainty.

**Why skills rather than a longer prompt.** These are procedures, not facts, and each is only
relevant sometimes. Putting all of it in the system prompt would spend context on every request,
including the ones needing none of it. A skill is written once, applies to any question, and
contains no stock-specific opinion — the checklists are reusable, the numbers never are.

**How it is implemented.** Deep Agents loads skills from a source directory and discloses them
progressively: the model sees each skill's name and description and reads the full file only when
it decides the skill is relevant. That only works because the agent has a filesystem to read
from — which is why enabling skills meant also giving the agent a real filesystem backend, and
why the next section exists. I verified this end to end rather than assuming it: the compiled
agent exposes the state channels only the skills middleware creates
(`skills_metadata`, `skills_load_errors`, `pinned_skills`), with `stock-research`,
`news-verification` and `investment-risk` loaded and no load errors.

### 5.4 Permissions — the cost of giving the agent a filesystem

To read skills from disk, the agent needs a filesystem backend rooted at the project. The moment
that exists, the agent can read and write every file in the project — including `.env`, which
holds live API keys, and the SQLite file holding the portfolio. The previous in-memory backend
gave the agent no access to the real disk at all, so adding skills would have quietly opened a
path for credentials to reach a prompt.

The deny rules above close it. I checked the result rather than trusting it:

| path | read | write |
| --- | --- | --- |
| `/.env`, `/.env.local` | deny | deny |
| `/data/investment_advisor.db` | deny | deny |
| `/.venv/...`, `/.git/...` | deny | deny |
| `/skills/stock-research/SKILL.md` | **allow** | allow |

The agent can reach its own skills and the source tree; the keys and the ledger are out of reach.
That check matters — it is easy to write a rule that locks the agent out of the files it needs,
or one that looks tight and is not.

### 5.5 Memory

The advisor has working context for the current request, durable application state, persistent
user-preference memory, and procedural memory. Those layers serve different purposes.

**Working memory — the context window.** What the agent reasons over during one request: the
question, the retrieved evidence, and the report being written. It disappears when the request
finishes.

**Durable application state — SQLite.** Portfolios, proposals, trades, holdings and saved reports
survive restarts. This remains application state, not agent memory: the agent has no portfolio
tool and cannot recall positions or use the ledger as financial evidence.

**Persistent preferences — Deep Agents memory.** The native memory middleware loads
`/memories/PREFERENCES.md` at startup. A composite filesystem backend routes that virtual path to
an OS-user application-data directory outside the repository, separate from the paper-trading
database. The agent's system policy limits it to preferences the user explicitly asks it to
remember, such as report style, research interests, and explicitly stated horizon or risk
constraints. The policy forbids inferring financial goals or risk tolerance, and forbids storing
portfolio state, research evidence, reports, market claims, credentials, or conversation history.
A current request takes precedence; memory is not evidence, and fresh market data is still
retrieved for each research request.
`nifty50-advisor memory-show` displays the saved preferences, and
`nifty50-advisor memory-clear --confirm` deliberately clears them.

**Procedural memory — skills and prompts.** Memory in the sense of remembered *how*: how to
verify a source, handle missing values, and check risks. These files are loaded from the project
and versioned with the code.

There is no conversation history or checkpointer. Preferences are the only durable information
the agent itself is allowed to retain; money and reports remain in SQLite with their existing
constraints and application workflows.

### 5.6 MCP servers — why I did not use one

I considered MCP for the data tools and decided against it, for scope reasons rather than
difficulty. Both data sources are ordinary Python libraries already running in the agent's
process, wrapped as native tools in a few dozen lines. An MCP server would add a second process to
start, a second thing that can be down, a trust boundary between two halves of the application,
and a harder failure to debug — for no capability I did not already have.

Where MCP would earn its place is the case it was designed for: when the tool is not yours. If I
swapped `yfinance` for a paid market-data vendor with its own authentication and rate limits, or
wanted the same research tools available to a second application, the protocol becomes the right
boundary because it decouples the source from every consumer. I wrote `tools/market_data.py` so
that replacing the source means rewriting one function and nothing else. I would rather explain
why I skipped it and where I would use it than bolt a protocol onto a project it does not help.

### 5.7 The approval gate — why it is outside the model

**The problem.** The model must research and must never trade. A prompt saying "do not execute
trades" is not a security boundary; prompts are suggestions, and anything depending on the
model's compliance eventually fails open.

**The design.** The model has no trading tool at all — there is nothing to refuse because there is
no capability. The CLI and Streamlit UI call deterministic persistence functions directly; the
agent cannot reach them:

1. `create_trade_proposal()` validates the input, checks the portfolio exists, and writes a
   `PENDING` row. It deliberately does not execute.
2. A human reviews the proposal in the CLI or Streamlit Paper Trading section. The CLI requires
   `--approve` or `--reject` as a mutually exclusive **required** choice. In the UI, approval has
   an explicit confirmation checkbox and submit action; rejection also requires its own action.
3. Only `review_trade_proposal()` can move cash or holdings, and it re-checks everything: the
   proposal exists, is still `PENDING`, and there is enough cash to buy or enough shares to sell.
4. The whole thing runs inside `BEGIN IMMEDIATE`, so cash and holdings either both change or
   neither does.

**Why it is structural.** Three independent mechanisms prevent a double trade: the status check,
the atomic transaction, and a `UNIQUE` constraint on the proposal id in the trades table, so the
database itself refuses to record the same proposal twice. Bypass any one and the others still
hold. That is what a real approval gate is — a capability the model does not have, backed by
constraints the database enforces — not a rule it was asked to follow.

### 5.8 The UI layer — dashboard, charts, and export

The Streamlit interface has five pages: **Dashboard**, Research & Reports, Saved Reports,
Paper Trading, and Preferences. The Dashboard focuses only on a single portfolio at a glance —
cash, portfolio value, total P&L, total return, realized P&L, holdings count — plus counts of
saved reports, saved comparisons, and pending proposals. Charts use Streamlit's native
`bar_chart` (backed by pandas, which is already a dependency) to show cost basis vs market
value and unrealized P&L per holding.

The quote refresh on the Dashboard and Paper Trading pages shares one session-state cache
(`portfolio_quotes_{id}`), so refreshing prices on one page instantly updates the other —
one explicit action per portfolio, either page. Holdings without a valid quote are excluded
from charts with a caption rather than plotted as zero; the "Incomplete" valuation warning
from `build_portfolio_valuation` is preserved. No portfolio-value history is persisted, so
there is deliberately no performance-over-time chart.

Saved research reports and comparisons can be exported as Markdown (human-readable, mirroring
what the UI renders) or JSON (the faithful archive of the exact saved payload). Export uses
pure string formatting over the already-JSON-safe `get_*` dicts — no new dependencies, no PDF
library — and is offered both on the Saved Reports page and next to Save on fresh research
and comparison runs. Comparison export preserves the deterministic no-winner semantics.

## 6. Action, Reasoning, Memory

**Action.** The most important decision was limiting it. The agent can call four read-only tools,
delegate to two specialists, read skill files, and write research artifacts. It cannot write to
the database, reach a broker, or execute a trade. Two things make those actions reliable: every
action returns a structured result with an explicit success flag, so the agent always knows
whether it worked, and tools return failures as data instead of raising, so an outage produces a
report that *says* retrieval failed rather than a crash or a confident answer built on nothing. I
also bounded how many actions it may take — the one-call-per-specialist rule exists because
unbounded retrying quietly burns budget and degrades the agent's own context.

**Reasoning.** The model earns its place in four narrow decisions: how deep to research, whether
a specialist is warranted, what the evidence means, and what the evidence *cannot* support. The
last is the one I care most about. The model is instructed to separate retrieved facts from its
own interpretation, never invent a figure, headline or source, report a failed retrieval as a
failure, and say plainly when the evidence is too thin. Without that instruction, a model asked
about a stock produces a confident answer from nothing — and a confident wrong answer about money
is the most dangerous output this system can produce. Correspondingly, I removed the reasoning it
is bad at: all arithmetic happens in Python. The model interprets numbers; it never produces
them, and that boundary is what makes the numbers trustworthy.

**Memory.** As section 5.5 sets out, preferences explicitly saved by the user persist in a private
per-user file, while portfolio state and reports remain in SQLite. The system policy instructs
the agent to treat preferences as neither evidence nor live account state and to modify the file
only after an explicit request to remember or save a preference. Each research request still
depends on freshly retrieved data.

## 7. Context engineering

Almost every quality problem I hit turned out to be a context problem, not a model problem. The
model was rarely wrong; it was reading the wrong thing.

- **I control what evidence reaches the model, in what shape, once.** Python retrieves first and
  hands over two labelled blocks, `STRUCTURED MARKET DATA` and `STRUCTURED NEWS EVIDENCE`, with an
  explicit instruction to use them directly and not repeat the tool calls. So the model sees
  exactly what was retrieved and whether it succeeded, it cannot loop re-fetching, and every
  report rests on an identical, inspectable evidence set.
- **Absence is information, so I preserve it.** Missing values stay `None` instead of being
  dropped or zeroed, and failed retrievals become named missing information in the report. A
  report that silently omits what it could not find is more dangerous than one that says so,
  because the reader cannot tell "no news" from "the news lookup broke".
- **Progressive disclosure keeps the prompt small.** Skills cost one or two lines each until the
  model decides one is relevant, then it reads the full file. Procedures that apply sometimes are
  not paid for on every request.
- **Bounded fields stop long evidence crowding out reasoning.** Long free-text fields are
  truncated to fixed lengths before entering the report model, so one verbose source cannot
  consume the budget the analysis needs.
- **Duplicate work is prevented structurally.** Omitting the news specialist when news is already
  retrieved removes a decision the model could get wrong, rather than telling it not to.
- **Secrets never enter the context.** The permission rules keep `.env` and the database outside
  everything the agent can read, so no path exists for a key to reach a prompt.
- **Determinism aids debugging.** Temperature 0 means an unexpected output is reproducible rather
  than a one-off.

## 8. What I could not finish

I would rather name the gaps than have them found in the demo.

**The missing agent tools matter most.** There is no `get_paper_portfolio` and no
`propose_paper_trade`, so the agent cannot see holdings or prepare a proposal. The Streamlit UI
and CLI provide separate deterministic portfolio and proposal actions. Creating a proposal leaves
it `PENDING`; a human must explicitly approve or reject it in the UI or use the CLI review command.
The research agent does not participate in that transaction path.

**Financial completeness.** The paper ledger can apply a user-supplied basis-point cost assumption
to each approved simulated trade and reports realized P&L and fees. The UI can explicitly refresh
last-returned daily closes and calculate unrealized P&L and total return. The cost rate is not an
official brokerage or tax estimate. Quotes can be delayed, incomplete, or from different dates; if
any holding lacks a valid quote, full portfolio value and total return remain unavailable. Dividends
and corporate actions are not modeled.

**Research scope.** Question-to-ticker resolution for single-stock requests still recognises a
fixed set of Indian stocks and indices. Stock comparison accepts 2 to 5 explicitly supplied
current NIFTY 50 constituents, validated against the official NSE Indices CSV when the user
submits the request. A successful list is cached in-process for six hours; a stale cache is
identified, and without a valid cache or network response the comparison fails clearly. The
workflow requests comparable market and technical periods, retains data, timestamps, missing
fields, and retrieval errors per ticker, and saves typed comparisons separately from single-stock
reports. Its summary is deterministic and lists values and retrieval status; no LLM-generated
comparison narrative is used, so it cannot rank stocks or select a winner.

**Configuration and schema fixes.** Database initialization now creates `research_reports` with
`CREATE TABLE IF NOT EXISTS`, before the table that references it. Persistence uses storage-only
settings, so report and paper-ledger operations do not require an LLM provider or API key. The
configured `DATABASE_PATH` is the default across database and paper-trading operations; a
relative configured path resolves from the project root, and explicit `db_path` arguments remain
overrides. `INITIAL_PAPER_CASH` is the shared default for portfolio creation, CLI, and Streamlit;
explicit cash values still take precedence.

**Testing.** Automated tests cover paper-trading rules, report persistence and schema creation,
preference isolation, and Streamlit action wiring using temporary services. They do not make live
market-data or LLM calls. The research tools, provider configuration, and report models are also
checked by scripts under `scripts/`; those script checks are separate from the automated suite.

## 9. What I take away

The thing I understand differently now is where an agent's intelligence actually lives. I started
thinking of it as a model plus some tools. I finished thinking of it as a model inside a carefully
shaped environment: tools it cannot misuse, evidence handed over in a form it can reason about,
permissions that keep secrets out of reach, arithmetic it is not allowed to do, and a security
boundary that holds because the capability does not exist rather than because it was asked nicely
to behave.

The model is why this project can say something useful about a stock. The harness is why that
answer can be trusted, and why a bad answer cannot cost real money.

---

# Appendix A — the three skills, in full

## A.1 `skills/stock-research/SKILL.md`

```markdown
---
name: stock-research
description: Structured workflow for researching one supported NIFTY 50 stock or index, or comparing 2 to 5 supported NSE stock tickers using price, technical, fundamental, and news evidence.
---

# Stock Research Skill

Use this skill for a single supported NIFTY 50 stock or index research question, or to guide a user to the dedicated stock-comparison workflow. Comparison is handled by the CLI and Streamlit service, not an agent tool. Do not present separate single-stock reports as a comparison.

## Supported Stock Comparison

- The comparison workflow accepts 2 to 5 distinct, explicitly supplied current NIFTY 50 symbols. It checks the official NSE Indices constituent CSV when submitted and accepts symbols with or without `.NS`.
- Use `nifty50-advisor compare TICKER1.NS TICKER2.NS` or Research & Reports → Stock comparison in the Streamlit UI. The user must submit the request; saving is a separate explicit action (`--save` in the CLI or Save this comparison in the UI).
- The service requests one month of daily market history and six months of technical history for every ticker, plus fundamentals and company-specific news. Providers can return different latest dates or incomplete fields; keep each ticker's values, timestamps, missing information, and retrieval errors separate.
- The comparison summary is deterministic and lists returned values and retrieval status only; it does not call an LLM to write a comparison narrative. Do not invent missing data or turn a price or ratio difference into a ranking. A source timestamp may be absent, especially for fundamentals; state that limitation.
- Recommendation labels in prose are not validated schema fields in either `ResearchReport` or `StockComparisonReport`.

## Procedure

1. **Identify the Stock and Research Question**
   - Confirm one target symbol (e.g., `^NSEI` for NIFTY 50, or a supported NSE ticker ending in `.NS` such as `RELIANCE.NS`, `TCS.NS`, `HDFCBANK.NS`, or `INFY.NS`). The research pipeline resolves a limited set of symbols; do not claim that every NIFTY 50 constituent is supported.
   - Determine which evidence sources are needed (price history, technical indicators, company fundamentals, or recent news).

2. **Retrieve Relevant Data Selectively**
   - Use the market-research specialist's `get_market_data` for recent closing prices, daily percentage changes, and price ranges.
   - Use `get_technical_indicators` for moving averages (`sma_20`, `sma_50`, `ema_12`, `ema_26`), `rsi_14`, MACD, and annualized volatility.
   - Use `get_company_fundamentals` for valuation (`trailing_pe`, `forward_pe`, `price_to_book`), margins, revenue/earnings growth, debt, and cash.
   - Use supplied structured news evidence when present, or delegate to the news specialist only when news is needed and not already supplied.

3. **Check Timestamps and Missing Values**
   - Record the latest observation date and data source (`Yahoo Finance via yfinance` or `Google News RSS`).
   - Distinguish `None` / unavailable values from `0.0`. Never treat missing index volume (`0.0`) as proof that no trading occurred.
   - Flag stale, delayed, or incomplete fields explicitly.

4. **Separate Facts, Calculations, and Interpretations**
   - **Facts:** Exact figures and dates returned by tools.
   - **Calculations:** Deterministic indicators and ratios returned by Python tools (do not recompute or guess arithmetic).
   - **Interpretations:** Analytical takeaways (e.g., price above SMA-20 but below SMA-50) clearly labeled as descriptive commentary rather than guaranteed predictions.

5. **Produce a Concise, Evidence-Based Report**
   - Include an executive summary, price/technical observations, fundamental highlights, news catalysts, key risks/contradictory evidence, and data limitations.
   - Use recommendation labels (`BUY`, `SELL`, `HOLD`, or `INSUFFICIENT_EVIDENCE`) as prose in a single-stock summary or conclusion only when an investment assessment is requested. Use `INSUFFICIENT_EVIDENCE` in prose when evidence is missing or contradictory. `ResearchReport` has no validated recommendation field or label enum, so the schema does not enforce these labels. Do not imply that it does.
```

## A.2 `skills/news-verification/SKILL.md`

```markdown
---
name: news-verification
description: Rules for verifying Indian stock market news sources, preserving original URLs and timestamps, deduplicating headlines, and separating reported facts from speculation.
---

# News Verification Skill

Use this skill whenever analyzing news headlines, RSS search results, or potential market catalysts.

## Procedure

1. **Verify Sources and URLs**
   - Report the exact publisher name and complete URL as returned by the tool or supplied structured evidence.
   - Never invent, shorten, paraphrase, or guess a URL. If a URL is missing or truncated, state that it is unavailable.

2. **Record Publication and Retrieval Timestamps**
   - State the publication timestamp (`published`) for every cited article.
   - Note when articles are older than recent trading sessions so stale stories are not presented as breaking catalysts.

3. **Check Relevance and Flag Duplicates**
   - Verify that the article directly pertains to the requested company, sector, or index.
   - When multiple outlets report the same underlying event (e.g., daily closing recaps), group them and avoid counting repeated coverage as independent confirmation.

4. **Separate Confirmed Facts from Speculation**
   - Clearly state when only RSS headlines and summaries were inspected rather than full article bodies.
   - Distinguish reported events (e.g., quarterly earnings released, regulatory filing) from opinion or pre-market outlook pieces.
   - Never claim that a news headline proves causation for a stock price move.
```

## A.3 `skills/investment-risk/SKILL.md`

```markdown
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
   - Do not infer the user's holdings, available cash, or concentration from conversation or saved preferences. The user can inspect the portfolio in the Streamlit Paper Trading section or with the portfolio CLI commands.

3. **Check Data Freshness and Trading Constraints**
   - When discussing a possible trade, cite the retrieval date for any market price. The Paper Trading UI can explicitly refresh holding valuations, but proposal prices remain user-entered and are not verified against a quote at approval time.
   - The agent cannot create a proposal: `propose_paper_trade` is not an available agent tool. Do not say that you created, queued, or reviewed a paper trade.
   - The CLI or Streamlit UI lets the user enter a ticker, side, quantity, price, rationale, optional saved-report ID, and an optional user-supplied transaction-cost assumption in basis points. This is a simulation input, not a brokerage or tax estimate. The deterministic ledger checks cash or held shares when a human reviews the pending proposal; it does not fetch a price at review time.
   - Portfolio valuation uses the last daily close returned by the market-data provider. Keep the source timestamp visible; if any holding lacks a valid quote, do not present a full portfolio value or total return.

4. **Enforce Mandatory Human Approval**
   - Creating a proposal in the CLI or UI creates a `PENDING` record only.
   - A human must explicitly approve or reject it: the CLI requires `proposal-review <id> --approve` or `--reject`; the UI requires a separate review action and confirmation before approval. Approval changes only the deterministic paper ledger. There is no broker connection or real order execution.
```

> **Note on the appendix:** `get_paper_portfolio` and `propose_paper_trade` are not available
> agent tools. Paper-trading actions are separate deterministic CLI and UI workflows (see
> section 8).
