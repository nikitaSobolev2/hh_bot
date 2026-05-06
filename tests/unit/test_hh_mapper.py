"""Unit tests for HH API vacancy mapper."""


from src.services.parser.hh_mapper import map_api_vacancy_to_orm_fields


class TestMapApiVacancyToOrmFields:
    def test_extracts_employer_and_area_from_list_item(self):
        api_response = {
            "id": "1",
            "name": "Python Dev",
            "employer": {
                "id": "100",
                "name": "Acme",
                "url": "https://api.hh.ru/employers/100",
                "alternate_url": "https://hh.ru/employer/100",
                "logo_urls": {"90": "https://example.com/logo.png"},
                "vacancies_url": "https://api.hh.ru/vacancies?employer_id=100",
                "accredited_it_employer": True,
                "trusted": False,
            },
            "area": {"id": "1", "name": "Москва", "url": "https://api.hh.ru/areas/1"},
            "snippet": {
                "requirement": "Python 3+",
                "responsibility": "Backend development",
            },
            "experience": {"id": "between1And3", "name": "1–3 года"},
            "schedule": {"id": "remote", "name": "Удалённо"},
            "employment": {"id": "full", "name": "Полная занятость"},
            "salary": {"from": 100000, "to": 200000, "currency": "RUR", "gross": False},
            "address": {
                "raw": "Москва, ул. Примерная, 1",
                "city": "Москва",
                "street": "ул. Примерная",
                "building": "1",
                "lat": 55.75,
                "lng": 37.62,
                "metro_stations": [],
            },
            "type": {"id": "open", "name": "Открытая"},
            "published_at": "2026-03-15T10:00:00+0300",
            "work_format": [{"id": "REMOTE", "name": "Удалённо"}],
            "professional_roles": [{"id": "96", "name": "Программист"}],
        }
        result = map_api_vacancy_to_orm_fields(api_response)

        assert result["employer_data"]["id"] == "100"
        assert result["employer_data"]["name"] == "Acme"
        assert result["area_data"]["id"] == "1"
        assert result["area_data"]["name"] == "Москва"

        of = result["orm_fields"]
        assert of["snippet_requirement"] == "Python 3+"
        assert of["snippet_responsibility"] == "Backend development"
        assert of["experience_id"] == "between1And3"
        assert of["experience_name"] == "1–3 года"
        assert of["schedule_id"] == "remote"
        assert of["employment_id"] == "full"
        assert of["salary_from"] == 100000
        assert of["salary_to"] == 200000
        assert of["salary_currency"] == "RUR"
        assert of["address_raw"] == "Москва, ул. Примерная, 1"
        assert of["address_city"] == "Москва"
        assert of["vacancy_type_id"] == "open"
        assert of["published_at"] is not None
        assert len(of["work_format"]) == 1
        assert of["work_format"][0]["name"] == "Удалённо"

    def test_handles_detail_response_without_snippet(self):
        """Detail /vacancies/{id} has key_skills and description but no snippet."""
        api_response = {
            "id": "2",
            "name": "Senior Dev",
            "employer": {"id": "200", "name": "Corp"},
            "area": {"id": "2", "name": "СПб", "url": "https://api.hh.ru/areas/2"},
            "key_skills": [{"name": "Python"}, {"name": "Go"}],
            "description": "<p>Full description</p>",
            "experience": {"id": "moreThan6", "name": "Более 6 лет"},
            "schedule": {"id": "fullDay", "name": "Полный день"},
            "employment": {"id": "full", "name": "Полная занятость"},
        }
        result = map_api_vacancy_to_orm_fields(api_response)

        assert result["employer_data"]["id"] == "200"
        assert result["area_data"]["id"] == "2"
        of = result["orm_fields"]
        assert of["snippet_requirement"] is None
        assert of["snippet_responsibility"] is None
        assert of["experience_id"] == "moreThan6"
        assert of["experience_name"] == "Более 6 лет"

    def test_handles_missing_employer_and_area(self):
        api_response = {"id": "3", "name": "Vacancy", "employer": {}, "area": {}}
        result = map_api_vacancy_to_orm_fields(api_response)

        assert result["employer_data"] == {}
        assert result["area_data"] == {}
        assert result["orm_fields"]["snippet_requirement"] is None

    def test_salary_from_salary_range_when_salary_null(self):
        api_response = {
            "id": "4",
            "employer": {"id": "1", "name": "X"},
            "area": {"id": "1", "name": "M"},
            "salary": None,
            "salary_range": {
                "from": 150000,
                "to": None,
                "currency": "RUR",
                "gross": True,
            },
        }
        result = map_api_vacancy_to_orm_fields(api_response)
        of = result["orm_fields"]
        assert of["salary_from"] == 150000
        assert of["salary_to"] is None
        assert of["salary_currency"] == "RUR"
        assert of["salary_gross"] is True

    def test_maps_has_test_true_from_api_flag(self):
        api_response = {
            "id": "t1",
            "employer": {"id": "1", "name": "X"},
            "area": {"id": "1", "name": "M"},
            "has_test": True,
        }
        result = map_api_vacancy_to_orm_fields(api_response)
        assert result["orm_fields"]["has_test"] is True

    def test_maps_has_test_true_from_test_required(self):
        api_response = {
            "id": "t2",
            "employer": {"id": "1", "name": "X"},
            "area": {"id": "1", "name": "M"},
            "has_test": False,
            "test": {"required": True},
        }
        result = map_api_vacancy_to_orm_fields(api_response)
        assert result["orm_fields"]["has_test"] is True

    def test_maps_has_test_false_when_absent(self):
        api_response = {
            "id": "t3",
            "employer": {"id": "1", "name": "X"},
            "area": {"id": "1", "name": "M"},
        }
        result = map_api_vacancy_to_orm_fields(api_response)
        assert result["orm_fields"]["has_test"] is False
