"""Sanity-check HH respond modal HTML shape (Magritte bottom sheet)."""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup


@pytest.fixture
def sample_modal_html() -> str:
    p = Path(__file__).resolve().parents[2] / "docs" / "hhpage.html"
    if not p.is_file():
        pytest.skip("docs/hhpage.html not present")
    return p.read_text(encoding="utf-8")


def test_modal_has_bottom_sheet_and_resume_radios(sample_modal_html: str) -> None:
    soup = BeautifulSoup(sample_modal_html, "html.parser")
    assert soup.select_one('[data-qa="bottom-sheet-content"]') is not None
    assert "Резюме для отклика" in sample_modal_html
    radios = soup.select('input[type="radio"][name="resumeId"]')
    assert len(radios) >= 2
    values = [r.get("value") for r in radios if r.get("value")]
    assert "e0df4ecaff103ad8170039ed1f337772516a30" in values
    assert "77062fccff103cf2550039ed1f71384a425751" in values
    titles = soup.select('[data-qa="resume-title"]')
    assert len(titles) >= 2
    assert any("Backend" in t.get_text() for t in titles)
