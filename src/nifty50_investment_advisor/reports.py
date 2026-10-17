
"""Validated, evidence-based research report models."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class EvidenceItem(BaseModel):
    """A claim's supporting evidence and source."""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1, max_length=1000)
    source_name: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    published_at: datetime | None = None
    evidence_type: Literal[
        "market_data",
        "news",
        "fundamentals",
        "technical",
        "other",
    ]
    limitations: str | None = Field(default=None, max_length=1000)


class ResearchData(BaseModel):
    """Structured outputs from the real research tools."""

    model_config = ConfigDict(extra="allow")

    market_data: dict[str, Any] | None = None
    technical_indicators: dict[str, Any] | None = None
    fundamentals: dict[str, Any] | None = None

    # Record retrieval status and errors without replacing missing values
    # with zeros or discarding successfully retrieved results.
    retrieval_status: dict[str, str] = Field(default_factory=dict)
    retrieval_errors: dict[str, str] = Field(default_factory=dict)


class ResearchReport(BaseModel):
    """Structured research output; not a trade instruction."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=30)
    company_name: str | None = Field(default=None, max_length=200)
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
    research_question: str = Field(min_length=1, max_length=2000)
    summary: str = Field(min_length=1, max_length=5000)

    # Original outputs from the market-data, technical, and
    # fundamentals tools, kept separately from the LLM's summary.
    data: ResearchData = Field(default_factory=ResearchData)

    evidence: list[EvidenceItem] = Field(default_factory=list)
    uncertainty: list[str] = Field(min_length=1)
    risks: list[str] = Field(min_length=1)
    missing_information: list[str] = Field(default_factory=list)
    conclusion: str = Field(min_length=1, max_length=5000)

    disclaimer: str = (
        "Educational research only. This report is not a guarantee of future "
        "performance and does not constitute personalized financial advice."
    )
