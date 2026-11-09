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