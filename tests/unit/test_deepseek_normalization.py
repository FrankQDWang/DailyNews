from libs.core.schemas.llm import L0SummaryOutput
from libs.integrations.deepseek_client import _coerce_schema_payload


def test_coerce_l0_summary_payload_from_weak_structure() -> None:
    raw = {
        "language": "zh",
        "tldr": "test",
        "key_points": ["point-a", "point-b"],
        "ai_pm_takeaways": ["takeaway-a"],
        "tags": ["rss", "agents"],
        "entities": [
            "David Pogue",
            {"name": "Apple", "type": "company"},
            {"name": "CHM", "type": "project"},
            {"name": "Paper A", "type": "paper", "url": "https://example.com/paper"},
        ],
        "claims": ["claim-a"],
        "risk_flags": [{"flag": "INJECTION"}, "LOW_CONFIDENCE"],
        "reading_time_min": "3",
        "summary_confidence": "0.82",
    }

    coerced = _coerce_schema_payload(L0SummaryOutput, raw)
    output = L0SummaryOutput.model_validate(coerced)

    assert output.key_points[0].point == "point-a"
    assert output.key_points[0].confidence == 0.5
    assert output.ai_pm_takeaways[0].takeaway == "takeaway-a"
    assert output.entities.companies == ["Apple"]
    assert output.entities.projects == ["CHM"]
    assert output.entities.papers == [{"title": "Paper A", "url": "https://example.com/paper"}]
    assert output.entities.people == ["David Pogue"]
    assert output.claims[0].claim == "claim-a"
    assert output.claims[0].needs_verification is True
    assert output.risk_flags == ["INJECTION", "LOW_CONFIDENCE"]
    assert output.reading_time_min == 3
    assert output.summary_confidence == 0.82
