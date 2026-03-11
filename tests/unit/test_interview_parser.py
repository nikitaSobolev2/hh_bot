"""Unit tests for the interview AI response parser."""

import pytest

from src.services.ai.interview_parser import parse_interview_analysis


class TestParseInterviewAnalysis:
    def test_extracts_summary(self):
        text = (
            "[InterviewSummaryStart]\n"
            "Кандидат показал хорошее понимание базовых концепций.\n"
            "[InterviewSummaryEnd]\n"
        )
        summary, improvements = parse_interview_analysis(text)
        assert "Кандидат показал хорошее понимание базовых концепций." in summary
        assert improvements == []

    def test_extracts_single_improvement_block(self):
        text = (
            "[InterviewSummaryStart]\nОбщий итог.\n[InterviewSummaryEnd]\n\n"
            "[ImproveStart]:React\n"
            "Не знает хуки и жизненный цикл компонентов.\n"
            "[ImproveEnd]:React\n"
        )
        summary, improvements = parse_interview_analysis(text)
        assert summary == "Общий итог."
        assert len(improvements) == 1
        assert improvements[0]["title"] == "React"
        assert "хуки" in improvements[0]["summary"]

    def test_extracts_multiple_improvement_blocks(self):
        text = (
            "[InterviewSummaryStart]\nИтог.\n[InterviewSummaryEnd]\n\n"
            "[ImproveStart]:Python\n"
            "Не знает декораторы.\n"
            "[ImproveEnd]:Python\n\n"
            "[ImproveStart]:SQL\n"
            "Слабое знание JOIN-ов.\n"
            "[ImproveEnd]:SQL\n"
        )
        summary, improvements = parse_interview_analysis(text)
        assert len(improvements) == 2
        titles = [imp["title"] for imp in improvements]
        assert "Python" in titles
        assert "SQL" in titles

    def test_improvement_summaries_are_correct(self):
        text = (
            "[InterviewSummaryStart]\nИтог.\n[InterviewSummaryEnd]\n\n"
            "[ImproveStart]:Docker\n"
            "Не умеет работать с volumes.\n"
            "[ImproveEnd]:Docker\n"
        )
        _, improvements = parse_interview_analysis(text)
        assert improvements[0]["summary"] == "Не умеет работать с volumes."

    def test_handles_missing_summary_block_gracefully(self):
        text = "[ImproveStart]:Go\nНе знает горутины.\n[ImproveEnd]:Go\n"
        summary, improvements = parse_interview_analysis(text)
        assert summary == text.strip()
        assert len(improvements) == 1

    def test_returns_empty_improvements_for_summary_only(self):
        text = "[InterviewSummaryStart]\nОтличные ответы по всем темам.\n[InterviewSummaryEnd]\n"
        _, improvements = parse_interview_analysis(text)
        assert improvements == []

    def test_handles_completely_empty_string(self):
        summary, improvements = parse_interview_analysis("")
        assert summary == ""
        assert improvements == []

    def test_strips_whitespace_from_summary(self):
        text = "[InterviewSummaryStart]\n\n   Итог с пробелами.   \n\n[InterviewSummaryEnd]\n"
        summary, _ = parse_interview_analysis(text)
        assert summary == "Итог с пробелами."

    def test_strips_whitespace_from_improvement_summary(self):
        text = (
            "[InterviewSummaryStart]\nИтог.\n[InterviewSummaryEnd]\n"
            "[ImproveStart]:TypeScript\n\n   Слабые дженерики.   \n\n[ImproveEnd]:TypeScript\n"
        )
        _, improvements = parse_interview_analysis(text)
        assert improvements[0]["summary"] == "Слабые дженерики."

    def test_technology_title_with_spaces_in_name(self):
        text = (
            "[InterviewSummaryStart]\nИтог.\n[InterviewSummaryEnd]\n"
            "[ImproveStart]:Node.js\n"
            "Плохое понимание event loop.\n"
            "[ImproveEnd]:Node.js\n"
        )
        _, improvements = parse_interview_analysis(text)
        assert improvements[0]["title"] == "Node.js"

    @pytest.mark.parametrize(
        "tech",
        ["React", "Python", "Docker", "PostgreSQL", "Redis", "TypeScript"],
    )
    def test_various_technology_names_extracted(self, tech: str):
        text = (
            "[InterviewSummaryStart]\nИтог.\n[InterviewSummaryEnd]\n"
            f"[ImproveStart]:{tech}\n"
            f"Слабые знания {tech}.\n"
            f"[ImproveEnd]:{tech}\n"
        )
        _, improvements = parse_interview_analysis(text)
        assert improvements[0]["title"] == tech

    def test_returns_tuple_of_correct_types(self):
        summary, improvements = parse_interview_analysis("")
        assert isinstance(summary, str)
        assert isinstance(improvements, list)

    def test_improvement_dicts_have_title_and_summary_keys(self):
        text = (
            "[InterviewSummaryStart]\nИтог.\n[InterviewSummaryEnd]\n"
            "[ImproveStart]:Kubernetes\nНе знает деплой.\n[ImproveEnd]:Kubernetes\n"
        )
        _, improvements = parse_interview_analysis(text)
        assert "title" in improvements[0]
        assert "summary" in improvements[0]
