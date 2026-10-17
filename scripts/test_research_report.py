import pytest
from pydantic import ValidationError

from nifty50_investment_advisor.reports import EvidenceItem, ResearchReport


def make_report(**overrides):
    data = {
        "ticker": "RELIANCE.NS",
        "research_question": "Summarize the available evidence for Reliance.",
        "summary": "A limited summary based on supplied evidence.",
        "evidence": [
            {
                "claim": "Placeholder claim, not verified market evidence.",
                "source_name": "Example source",
                "source_url": "https://example.com/source",
                "evidence_type": "other",
                "limitations": "Placeholder evidence only.",
            }
        ],
        "uncertainty": ["The available evidence is limited."],
        "risks": ["Market prices can move unexpectedly."],
        "conclusion": "No investment decision should be made from placeholder evidence.",
    }
    data.update(overrides)
    return data


def test_research_report_validates_and_serializes():
    report = ResearchReport(**make_report())
    serialized = report.model_dump(mode="json")

    assert serialized["ticker"] == "RELIANCE.NS"
    assert serialized["evidence"][0]["source_url"] == "https://example.com/source"
    assert serialized["uncertainty"]
    assert serialized["risks"]
    assert serialized["generated_at"]


def test_evidence_rejects_invalid_url():
    with pytest.raises(ValidationError):
        EvidenceItem(
            claim="Example claim",
            source_name="Example source",
            source_url="not-a-url",
            evidence_type="other",
        )


def test_report_requires_uncertainty_and_risks():
    with pytest.raises(ValidationError):
        ResearchReport(**make_report(uncertainty=[]))

    with pytest.raises(ValidationError):
        ResearchReport(**make_report(risks=[]))


def test_report_rejects_unexpected_fields():
    with pytest.raises(ValidationError):
        ResearchReport(**make_report(unreviewed_recommendation="BUY"))
