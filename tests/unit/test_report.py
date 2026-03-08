from src.services.parser.report import ReportGenerator

_LOCALE = "en"


class TestReportGenerator:
    def setup_method(self):
        self.generator = ReportGenerator(
            vacancy_title="Frontend Developer",
            top_keywords={"React": 15, "TypeScript": 12, "CSS": 8},
            top_skills={"JavaScript": 20, "React": 18, "HTML": 10},
            vacancies_processed=30,
            key_phrases="• Developed React applications\n• Used TypeScript",
            key_phrases_style="formal",
            locale=_LOCALE,
        )

    def test_generate_message_contains_title(self):
        result = self.generator.generate_message()
        assert "Frontend Developer" in result

    def test_generate_message_contains_keywords(self):
        result = self.generator.generate_message()
        assert "React" in result
        assert "TypeScript" in result

    def test_generate_message_contains_skills(self):
        result = self.generator.generate_message()
        assert "JavaScript" in result

    def test_generate_message_contains_key_phrases(self):
        result = self.generator.generate_message()
        assert "Developed React applications" in result

    def test_generate_md_has_markdown_tables(self):
        result = self.generator.generate_md()
        assert "| # | Keyword |" in result
        assert "| # | Skill |" in result

    def test_generate_md_has_title(self):
        result = self.generator.generate_md()
        assert "# Parsing Report: Frontend Developer" in result

    def test_generate_txt_has_plain_text_format(self):
        result = self.generator.generate_txt()
        assert "PARSING REPORT: Frontend Developer" in result
        assert "TOP-" in result

    def test_generate_txt_has_dashes_separator(self):
        result = self.generator.generate_txt()
        assert "-" * 50 in result

    def test_empty_keywords_handled(self):
        gen = ReportGenerator(
            vacancy_title="Test",
            top_keywords={},
            top_skills={},
            vacancies_processed=0,
            locale=_LOCALE,
        )
        msg = gen.generate_message()
        assert "Test" in msg

        md = gen.generate_md()
        assert "# Parsing Report: Test" in md

        txt = gen.generate_txt()
        assert "PARSING REPORT: Test" in txt

    def test_no_key_phrases_omits_section(self):
        gen = ReportGenerator(
            vacancy_title="Test",
            top_keywords={"Python": 5},
            top_skills={},
            vacancies_processed=10,
            locale=_LOCALE,
        )
        msg = gen.generate_message()
        assert "Key Phrases" not in msg
