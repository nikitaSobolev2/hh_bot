from src.models.autoparse import AutoparseCompany, AutoparsedVacancy


class TestAutoparseCompany:
    def test_default_values(self):
        company = AutoparseCompany(
            user_id=1,
            vacancy_title="Python Dev",
            search_url="https://hh.ru/search/vacancy?text=python",
            is_enabled=True,
            is_deleted=False,
            total_runs=0,
            total_vacancies_found=0,
            keyword_filter="",
            skills="",
        )
        assert company.is_enabled is True
        assert company.is_deleted is False
        assert company.total_runs == 0
        assert company.total_vacancies_found == 0
        assert company.keyword_filter == ""
        assert company.skills == ""

    def test_repr(self):
        company = AutoparseCompany(
            id=1,
            user_id=1,
            vacancy_title="Test",
            search_url="https://hh.ru",
            is_enabled=True,
        )
        r = repr(company)
        assert "AutoparseCompany" in r
        assert "Test" in r


class TestAutoparsedVacancy:
    def test_default_values(self):
        vacancy = AutoparsedVacancy(
            autoparse_company_id=1,
            hh_vacancy_id="12345",
            url="https://hh.ru/vacancy/12345",
            title="Test Vacancy",
            description="",
        )
        assert vacancy.description == ""
        assert vacancy.compatibility_score is None
        assert vacancy.salary is None
        assert vacancy.tags is None

    def test_repr(self):
        vacancy = AutoparsedVacancy(
            id=1,
            autoparse_company_id=1,
            hh_vacancy_id="12345",
            url="https://hh.ru/vacancy/12345",
            title="Dev",
        )
        r = repr(vacancy)
        assert "AutoparsedVacancy" in r
        assert "12345" in r
