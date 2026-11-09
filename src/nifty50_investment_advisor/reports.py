
"""Validated, evidence-based research report models."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

ComparisonTicker = Annotated[
    str,
    StringConstraints(
        min_length=4,
        max_length=30,
        pattern=r"^[A-Z0-9&-]+\.NS$",
    ),
]


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


class ComparisonTickerReport(BaseModel):
    """Evidence and raw company-specific news for one comparison ticker."""

    model_config = ConfigDict(extra="forbid")

    ticker: ComparisonTicker
    company_name: str | None = Field(default=None, max_length=200)
    report: ResearchReport
    news: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def report_ticker_matches(self) -> "ComparisonTickerReport":
        if self.report.ticker != self.ticker:
            raise ValueError("ticker must match the nested research report ticker")
        return self


class ComparisonObservation(BaseModel):
    """One numeric value from a specific ticker and source timestamp."""

    model_config = ConfigDict(extra="forbid")

    ticker: ComparisonTicker
    value: float = Field(allow_inf_nan=False)
    as_of: str | None = Field(default=None, max_length=100)
    source_name: str = Field(min_length=1, max_length=200)


class ComparisonDifference(BaseModel):
    """Comparable returned values, without assigning a better/worse rank."""

    model_config = ConfigDict(extra="forbid")

    category: Literal["market_data", "technical_indicators", "fundamentals"]
    metric: str = Field(min_length=1, max_length=100)
    observations: list[ComparisonObservation] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def observations_are_distinct(self) -> "ComparisonDifference":
        tickers = [observation.ticker for observation in self.observations]
        if len(tickers) != len(set(tickers)):
            raise ValueError("difference observations must use distinct tickers")
        return self


class StockComparisonReport(BaseModel):
    """Validated multi-ticker report with evidence retained per company."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    research_question: str = Field(min_length=1, max_length=2000)
    universe_checked_at: datetime | None = None
    universe_stale: bool = False
    tickers: list[ComparisonTicker] = Field(min_length=2, max_length=5)
    stocks: list[ComparisonTickerReport] = Field(min_length=2, max_length=5)
    summary: str = Field(
        min_length=1,
        max_length=5000,
        description=(
            "Deterministic summary of fetched values and retrieval status; "
            "it does not select or rank a winner."
        ),
    )
    differences: list[ComparisonDifference] = Field(default_factory=list)
    uncertainty: list[str] = Field(min_length=1)
    missing_information: list[str] = Field(default_factory=list)
    conclusion: str = Field(min_length=1, max_length=5000)
    disclaimer: str = (
        "Educational comparison of returned evidence only. This report is "
        "not a guarantee of future performance or personalized financial advice."
    )

    @model_validator(mode="after")
    def tickers_match_stock_records(self) -> "StockComparisonReport":
        if len(self.tickers) != len(set(self.tickers)):
            raise ValueError("comparison tickers must be distinct")
        if self.tickers != [stock.ticker for stock in self.stocks]:
            raise ValueError("tickers must match the ordered per-stock records")
        for difference in self.differences:
            if any(item.ticker not in self.tickers for item in difference.observations):
                raise ValueError("difference observations must belong to this comparison")
        return self
