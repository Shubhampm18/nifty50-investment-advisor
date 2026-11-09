---
name: stock-research
description: Structured workflow for researching one supported NIFTY 50 stock or index, or comparing 2 to 5 supported NSE stock tickers using price, technical, fundamental, and news evidence.
---

# Stock Research Skill

Use this skill for a single supported NIFTY 50 stock or index research question, or to guide a user to the dedicated stock-comparison workflow. Comparison is handled by the CLI and Streamlit service, not an agent tool. Do not present separate single-stock reports as a comparison.

## Supported Stock Comparison

- The comparison workflow accepts 2 to 5 distinct, explicitly supplied current NIFTY 50 constituents. It validates against the NSE Indices constituent CSV at submission, caches a successful list for six hours per process, and reports when it has to use stale cached membership. Symbols may be entered with or without `.NS`.
- Use `nifty50-advisor compare TICKER1.NS TICKER2.NS` or Research & Reports → Stock comparison in the Streamlit UI. The user must submit the request; saving is a separate explicit action (`--save` in the CLI or Save this comparison in the UI).
- The service requests one month of daily market history and six months of technical history for every ticker, plus fundamentals and company-specific news. Providers can return different latest dates or incomplete fields; keep each ticker's values, timestamps, missing information, and retrieval errors separate.
- The comparison summary is deterministic and lists returned values and retrieval status only. It does not call an LLM to write a comparison narrative, so it cannot declare a winner. Single-stock reports still use the configured LLM. Do not invent missing data or turn a price or ratio difference into a ranking. A source timestamp may be absent, especially for fundamentals; state that limitation.
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
