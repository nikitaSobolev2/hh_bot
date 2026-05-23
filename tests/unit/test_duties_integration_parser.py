"""Unit tests for integrated duties JSON parser and formatter."""

import json

import pytest

from src.services.ai.duties_integration import (
    build_integrated_duties_payload,
    duties_list_to_text,
    format_integrated_duties_report,
    parse_integrated_duties_response,
    payload_to_result,
)


def test_parse_integrated_duties_response_valid_json():
    raw = json.dumps(
        {
            "work_experiences": [
                {"work_exp_id": 1, "duties": ["Разрабатывал API", "Проводил code review"]},
                {"work_exp_id": 2, "duties": ["- Поддерживал сервисы"]},
            ]
        }
    )
    blocks = parse_integrated_duties_response(raw, {1, 2})

    assert len(blocks) == 2
    assert blocks[0].work_exp_id == 1
    assert blocks[0].duties == ["Разрабатывал API", "Проводил code review"]
    assert blocks[1].duties == ["Поддерживал сервисы"]


def test_parse_integrated_duties_response_strips_markdown_fence():
    raw = """```json
{"work_experiences":[{"work_exp_id":5,"duties":["Duty one"]}]}
```"""
    blocks = parse_integrated_duties_response(raw, {5})

    assert blocks[0].work_exp_id == 5
    assert blocks[0].duties == ["Duty one"]


def test_parse_integrated_duties_response_rejects_unknown_work_exp_id():
    raw = json.dumps({"work_experiences": [{"work_exp_id": 99, "duties": ["A"]}]})

    with pytest.raises(ValueError, match="Unknown work_exp_id"):
        parse_integrated_duties_response(raw, {1})


def test_parse_integrated_duties_response_rejects_missing_block():
    raw = json.dumps({"work_experiences": [{"work_exp_id": 1, "duties": ["A"]}]})

    with pytest.raises(ValueError, match="Missing work_exp_id"):
        parse_integrated_duties_response(raw, {1, 2})


def test_parse_integrated_duties_response_rejects_empty_duties():
    raw = json.dumps({"work_experiences": [{"work_exp_id": 1, "duties": []}]})

    with pytest.raises(ValueError, match="Empty duties"):
        parse_integrated_duties_response(raw, {1})


def test_build_integrated_duties_payload_and_report():
    from src.services.ai.duties_integration import IntegratedWorkExperienceBlock

    payload = build_integrated_duties_payload(
        vacancy_title="Python Dev",
        keywords_used=["Django", "PostgreSQL"],
        blocks=[
            IntegratedWorkExperienceBlock(
                work_exp_id=1,
                company_name="Acme",
                title="Backend Dev",
                duties=["Разрабатывал на Django"],
            )
        ],
    )
    result = payload_to_result(payload)
    report = format_integrated_duties_report(payload, locale="en")

    assert result.keywords_used == ["Django", "PostgreSQL"]
    assert result.work_experiences[0].company_name == "Acme"
    assert "Django" in report
    assert "Acme" in report


def test_duties_list_to_text_formats_bullets():
    assert duties_list_to_text(["First", "Second"]) == "- First\n- Second"


def test_paginate_integrated_duties_report_splits_by_company_blocks():
    from src.services.ai.duties_integration import (
        IntegratedWorkExperienceBlock,
        paginate_integrated_duties_report,
    )

    long_duty = "Разрабатывал " + ("API " * 200)
    payload = build_integrated_duties_payload(
        vacancy_title="Backend",
        keywords_used=["Python"],
        blocks=[
            IntegratedWorkExperienceBlock(1, "Company A", "Dev", [long_duty]),
            IntegratedWorkExperienceBlock(2, "Company B", "Dev", ["Short duty"]),
        ],
    )

    pages = paginate_integrated_duties_report(payload, locale="en", max_len=500)

    assert len(pages) >= 2
    assert "Company A" in pages[0] or "Company A" in pages[1]
    assert any("Company B" in page for page in pages)


def test_get_integrated_duties_report_page_returns_requested_page():
    from src.services.ai.duties_integration import (
        IntegratedWorkExperienceBlock,
        get_integrated_duties_report_page,
        paginate_integrated_duties_report,
    )

    payload = build_integrated_duties_payload(
        vacancy_title="Backend Developer Role",
        keywords_used=["Python", "Docker", "Kubernetes"],
        blocks=[
            IntegratedWorkExperienceBlock(
                1,
                "Company A With Long Name",
                "Senior Developer",
                ["Duty A " * 20],
            ),
            IntegratedWorkExperienceBlock(
                2,
                "Company B With Long Name",
                "Middle Developer",
                ["Duty B " * 20],
            ),
        ],
    )
    pages = paginate_integrated_duties_report(payload, locale="en", max_len=250)
    assert len(pages) >= 2

    text, total = get_integrated_duties_report_page(payload, locale="en", page=1, max_len=250)

    assert total == len(pages)
    assert text == pages[1]
