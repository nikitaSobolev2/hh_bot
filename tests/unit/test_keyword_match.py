import pytest

from src.services.parser.keyword_match import matches_keyword_expression, strip_symbols


class TestStripSymbols:
    def test_replaces_special_characters_with_spaces(self):
        assert strip_symbols("hello-world!") == "hello world"

    def test_keeps_letters_numbers_spaces(self):
        assert strip_symbols("Frontend 2024") == "Frontend 2024"

    def test_keeps_cyrillic(self):
        assert strip_symbols("Разработчик!") == "Разработчик"

    def test_empty_string(self):
        assert strip_symbols("") == ""


class TestMatchesKeywordExpression:
    def test_empty_expression_matches_anything(self):
        assert matches_keyword_expression("Frontend Developer", "")

    def test_single_keyword_match(self):
        assert matches_keyword_expression("Frontend Developer", "frontend")

    def test_single_keyword_no_match(self):
        assert not matches_keyword_expression("Backend Engineer", "frontend")

    def test_or_operator_first_matches(self):
        assert matches_keyword_expression("Frontend Developer", "frontend|backend")

    def test_or_operator_second_matches(self):
        assert matches_keyword_expression("Backend Developer", "frontend|backend")

    def test_or_operator_none_matches(self):
        assert not matches_keyword_expression("DevOps Engineer", "frontend|backend")

    def test_and_operator_all_match(self):
        assert matches_keyword_expression("Senior Frontend Developer", "senior,frontend")

    def test_and_operator_partial_match_fails(self):
        assert not matches_keyword_expression("Junior Frontend Developer", "senior,frontend")

    def test_combined_or_and_operators(self):
        assert matches_keyword_expression(
            "Fullstack Frontend Developer",
            "frontend|backend,fullstack",
        )

    def test_combined_or_and_second_or_matches(self):
        assert matches_keyword_expression(
            "Fullstack Backend Developer",
            "frontend|backend,fullstack",
        )

    def test_combined_or_and_no_and_match(self):
        assert not matches_keyword_expression(
            "Frontend Developer",
            "frontend|backend,fullstack",
        )

    def test_case_insensitive(self):
        assert matches_keyword_expression("FRONTEND Developer", "frontend")

    @pytest.mark.parametrize(
        "title,expr,expected",
        [
            ("Python Developer", "python", True),
            ("C++ Developer", "c", True),
            ("React Native Developer", "react|vue,native", True),
            ("Vue.js Developer", "react|vue,native", False),
        ],
    )
    def test_parametrized_cases(self, title: str, expr: str, expected: bool):
        assert matches_keyword_expression(title, expr) == expected

    def test_go_not_inside_category(self):
        assert not matches_keyword_expression(
            "Product owner for category management",
            "go",
        )

    def test_go_not_inside_google(self):
        assert not matches_keyword_expression(
            "Integration with Google Workspace",
            "go",
        )

    def test_go_matches_standalone(self):
        assert matches_keyword_expression(
            "Backend developer Go microservices",
            "go",
        )

    def test_java_not_inside_javascript(self):
        assert not matches_keyword_expression(
            "javascript developer frontend",
            "java",
        )

    def test_java_matches_standalone(self):
        assert matches_keyword_expression(
            "Java developer backend",
            "java",
        )

    def test_python_whole_word_in_snippet_style_text(self):
        assert matches_keyword_expression(
            "Аналитик требований. Знание Python приветствуется.",
            "python",
        )

    def test_react_whole_word_in_react_native(self):
        assert matches_keyword_expression(
            "Mobile React Native analyst",
            "react",
        )

    def test_backend_hyphen_compound_snippet(self):
        """Hyphens become spaces so backend is its own token (HH snippet style)."""
        assert matches_keyword_expression(
            "Коммерческий опыт backend-разработки на PHP",
            "backend",
        )
