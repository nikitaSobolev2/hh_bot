curl ^"https://izhevsk.hh.ru/applicant/vacancy_response/popup^" ^
  -H ^"sec-ch-ua-platform: ^\^"Windows^\^"^" ^
  -H ^"X-GIB-FGSSCgib-w-hh: 20l2b21bfb162fc9803355e7d3a3c549a3f12c31^" ^
  -H ^"Referer: https://izhevsk.hh.ru/vacancy/131481403?hhtmFrom=vacancy_search_list^" ^
  -H ^"sec-ch-ua: ^\^"Chromium^\^";v=^\^"146^\^", ^\^"Not-A.Brand^\^";v=^\^"24^\^", ^\^"Google Chrome^\^";v=^\^"146^\^"^" ^
  -H ^"X-hhtmSource: vacancy^" ^
  -H ^"sec-ch-ua-mobile: ?0^" ^
  -H ^"baggage: sentry-trace_id=d5c32e64eb8248c187a860dcbb38925c,sentry-sample_rand=0.360381,sentry-environment=production,sentry-release=xhh^%^4026.13.2.5,sentry-public_key=0cc3a09b6698423b8ca47d3478cfccac,sentry-transaction=^%^2Fvacancy^%^2F^%^7Bid^%^3Aint^%^7D,sentry-sample_rate=0.001,sentry-sampled=false^" ^
  -H ^"sentry-trace: d5c32e64eb8248c187a860dcbb38925c-864efa12471b63c6-0^" ^
  -H ^"X-hhtmFrom: vacancy_search_list^" ^
  -H ^"X-Requested-With: XMLHttpRequest^" ^
  -H ^"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36^" ^
  -H ^"Accept: application/json^" ^
  -H ^"Content-Type: multipart/form-data; boundary=----WebKitFormBoundarycqbt0YQEdEt7zauc^" ^
  -H ^"X-GIB-GSSCgib-w-hh: MbeBMFjXAwjlwCUBmq4FCsShQL+sc7PKu6MPWMSCt1OIMSaU8z76SRZ+18ugKiryHYJq2X/5VYrDbEl4WwLvbFrxqdEwySCujixVg1al7LzIJNj8aWZUS49aufQOt3dR+/D1fPPkTGpUwi4x6yQWHwFu3ZoiyvchTyle9BzVHovGsAYDSO68onKN/vDr+dEqhSRpBunS2vCWFK6C6fQ+RI6Z5ut7zw/ZOEN2OnW/2eEra7yG28EWXOmIuZf98Zfgog==^" ^
  -H ^"X-Xsrftoken: 1eb883bed235f5fc751db6604f7ad1dc^" ^
  --data-raw ^"------WebKitFormBoundarycqbt0YQEdEt7zauc^

Content-Disposition: form-data; name=^\^"_xsrf^\^"^

^

1eb883bed235f5fc751db6604f7ad1dc^

------WebKitFormBoundarycqbt0YQEdEt7zauc^

Content-Disposition: form-data; name=^\^"vacancy_id^\^"^

^

131481403^

------WebKitFormBoundarycqbt0YQEdEt7zauc^

Content-Disposition: form-data; name=^\^"resume_hash^\^"^

^

df3c734dff0f2fd73c0039ed1f396734705750^

------WebKitFormBoundarycqbt0YQEdEt7zauc^

Content-Disposition: form-data; name=^\^"ignore_postponed^\^"^

^

true^

------WebKitFormBoundarycqbt0YQEdEt7zauc^

Content-Disposition: form-data; name=^\^"incomplete^\^"^

^

false^

------WebKitFormBoundarycqbt0YQEdEt7zauc^

Content-Disposition: form-data; name=^\^"mark_applicant_visible_in_vacancy_country^\^"^

^

false^

------WebKitFormBoundarycqbt0YQEdEt7zauc^

Content-Disposition: form-data; name=^\^"country_ids^\^"^

^

^[^]^

------WebKitFormBoundarycqbt0YQEdEt7zauc^

Content-Disposition: form-data; name=^\^"letter^\^"^

^

^ ^ ^ ^ ^ ^  - Full Stack ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^  ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^  ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^  ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  AI-^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ , ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^ ^  Python, Go ^  React. ^ ^  ^ ^ ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^  Kubernetes, ^ ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^  ^  AI-^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^ , ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^  ^  CI/CD. ^ ^ ^ ^ ^ ^ ^  ^ Full Stack ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^ ^  ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^  ^  ^ ^ ^ ^  ^ ^ ^ ^ ^ ^  ^  ^ ^ ^ ^ ^ ^ ^ ^ ; ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^  ^ ^ ^ ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ ^ ^  ^  ^ ^ ^ ^ ^ ^ ^ ^ ^  AI-^ ^ ^ ^ ^ ^ ^ ^ ^ ^  ^  ^ ^ ^ ^ ^  ^ ^ ^ ^ ^ ^ ^ .^

^

------WebKitFormBoundarycqbt0YQEdEt7zauc^

Content-Disposition: form-data; name=^\^"lux^\^"^

^

true^

------WebKitFormBoundarycqbt0YQEdEt7zauc^

Content-Disposition: form-data; name=^\^"withoutTest^\^"^

^

no^

------WebKitFormBoundarycqbt0YQEdEt7zauc^

Content-Disposition: form-data; name=^\^"hhtmFromLabel^\^"^

^

^

------WebKitFormBoundarycqbt0YQEdEt7zauc^

Content-Disposition: form-data; name=^\^"hhtmSourceLabel^\^"^

^

^

------WebKitFormBoundarycqbt0YQEdEt7zauc--^

^"

Response:
```
{
    "success": "true",
    "topic_id": "5179231635",
    "chat_id": "5212556056",
    "response_label": "nonreq-letter-no-test-with-letter",
    "vacancy_id": "131481403",
    "applicantActivity": {
        "userActivityScore": 12,
        "userActivityScoreChange": 8,
        "showActivity": true
    },
    "requiredAdditionalData": [
        "PHOTO"
    ],
    "resumeFields": {
        "salary": {
            "amount": 250000,
            "currency": "RUR"
        },
        "experience": [
            {
                "id": 2012471339,
                "startDate": "2024-05-01",
                "endDate": null,
                "companyName": "ДОСТАЕВСКИЙ",
                "companyIndustryId": 27,
                "companyIndustries": [
                    517,
                    585,
                    558,
                    528
                ],
                "companyAreaId": 2,
                "industries": [
                    {
                        "id": 50,
                        "name": "industry.50",
                        "parentId": null,
                        "children": [
                            {
                                "id": 528,
                                "name": "industry.sec.528",
                                "parentId": 50,
                                "children": [],
                                "translit": "restoran_obshestvennoe_pitanie_fast_fud"
                            }
                        ],
                        "translit": "gostinicy_restorany_obshepit_kejtering"
                    },
                    {
                        "id": 41,
                        "name": "industry.41",
                        "parentId": null,
                        "children": [
                            {
                                "id": 517,
                                "name": "industry.sec.517",
                                "parentId": 41,
                                "children": [],
                                "translit": "roznichnaya_set_produktovaya"
                            }
                        ],
                        "translit": "roznichnaya_torgovlya"
                    },
                    {
                        "id": 27,
                        "name": "industry.27",
                        "parentId": null,
                        "children": [
                            {
                                "id": 585,
                                "name": "industry.sec.585",
                                "parentId": 27,
                                "children": [],
                                "translit": "khlebobulochnye_izdeliya_proizvodstvo"
                            },
                            {
                                "id": 558,
                                "name": "industry.sec.558",
                                "parentId": 27,
                                "children": [],
                                "translit": "konditerskie_izdeliya_proizvodstvo"
                            }
                        ],
                        "translit": "produkty_pitaniya"
                    }
                ],
                "companyUrl": null,
                "companyId": 1340780,
                "position": "Middle Fullstack-разработчик",
                "description": "- Разработал и поддерживал высоконагруженные сервисы на Python с использованием FastAPI, обеспечивая масштабируемый REST API для обмена данными между микросервисами.  \n- Организовал пайплайн CI/CD через GitLab, автоматизировав сборку Docker‑образов и деплой в Kubernetes, что ускорило цикл релизов и повысило надёжность окружения.  \n- Проектировал архитектуру очередей с Kafka и RabbitMQ, реализовав асинхронную обработку задач и интеграцию с Graylog для централизованного логирования.  \n- Реализовал frontend‑компоненты на Next.js и TypeScript, связывая их с backend‑API и обеспечивая согласованность данных.  \n- Проводил code review и оптимизацию кода на Python и Node.js, улучшая читаемость и снижая время отклика сервисов.  \n- Настроил мониторинг и алёрты на базе Elastic Stack, обеспечив прозрачность работы приложений и своевременное реагирование на сбои.  \n- Внедрил PostgreSQL и MariaDB как основные источники данных, работая с SQL‑запросами, индексацией и резервным копированием для обеспечения целостности информации.  \n- Участвовал в ежедневных Scrum‑сессиях, активно участвовал в планировании спринтов и ретроспективах, повышая эффективность командной работы.",
                "employerId": 1340780,
                "companyState": "APPROVED",
                "companyLogos": {
                    "logo": [
                        {
                            "type": "ORIGINAL",
                            "url": "/employer-logo-original-round/3708314.jpeg"
                        },
                        {
                            "type": "small",
                            "url": "/employer-logo-round/3708315.jpeg"
                        },
                        {
                            "type": "medium",
                            "url": "/employer-logo-round/3708316.jpeg"
                        },
                        {
                            "type": "employerPage",
                            "url": "/employer-logo-round/3708314.jpeg"
                        },
                        {
                            "type": "searchResultsPage",
                            "url": "/employer-logo-round/3708315.jpeg"
                        },
                        {
                            "type": "vacancyPage",
                            "url": "/employer-logo-round/3708316.jpeg"
                        }
                    ]
                },
                "professionId": null,
                "professionName": null
            },
            {
                "id": 2012471342,
                "startDate": "2022-10-01",
                "endDate": "2024-05-01",
                "companyName": "ИП \"В. А. Казарин\"",
                "companyIndustryId": null,
                "companyIndustries": [
                    515,
                    526,
                    525
                ],
                "companyAreaId": 1,
                "industries": [
                    {
                        "id": 41,
                        "name": "industry.41",
                        "parentId": null,
                        "children": [
                            {
                                "id": 515,
                                "name": "industry.sec.515",
                                "parentId": 41,
                                "children": [],
                                "translit": "roznichnaya_set_odezhda_obuv_aksessuary"
                            },
                            {
                                "id": 526,
                                "name": "industry.sec.526",
                                "parentId": 41,
                                "children": [],
                                "translit": "nesetevaya_roznica_melkij_opt"
                            },
                            {
                                "id": 525,
                                "name": "industry.sec.525",
                                "parentId": 41,
                                "children": [],
                                "translit": "internet_magazin"
                            }
                        ],
                        "translit": "roznichnaya_torgovlya"
                    }
                ],
                "companyUrl": null,
                "companyId": null,
                "position": "Ведущий разработчик",
                "description": "- Разработал и поддерживал функционал на Laravel для интернет‑магазина, интегрируя API‑интерфейсы с внешними платежными сервисами.  \n- Настраивал SEO‑оптимизацию страниц, работая с шаблонами Blade и мета‑тегами, повышая видимость продукта в поисковых системах.  \n- Проводил код‑ревью и refactoring PHP‑кода, повышая читаемость и снижая количество ошибок в миграциях MySQL.  \n- Создавал динамические страницы в WordPress и Bitrix, используя JavaScript, CSS и jQuery для улучшения пользовательского взаимодействия.  \n- Оптимизировал производительность запросов к MySQL, применяя индексы и кэширование, улучшая отклик сайта.  \n- Управлял версиями через Git, организовывал ветвление и слияние, обеспечивая стабильность релизов.  \n- Внедрил CI/CD‑пайплайн в GitLab, автоматизировав сборку и деплой на Linux‑серверы.  \n- Участвовал в спринтовой работе Agile‑команды, планировав и оценив задачи, повышая скорость итераций.",
                "employerId": null,
                "companyState": null,
                "companyLogos": null,
                "professionId": null,
                "professionName": null
            },
            {
                "id": 2038949133,
                "startDate": "2021-02-01",
                "endDate": "2022-09-01",
                "companyName": "Веб-студия Алангасар",
                "companyIndustryId": null,
                "companyIndustries": [],
                "companyAreaId": null,
                "industries": [],
                "companyUrl": null,
                "companyId": null,
                "position": "Fullstack-разработчик",
                "description": "- fullstack-разработчик в аутсорс-студии: web-решения под ключ, полный цикл разработки, frontend (vue, react, angular, jquery) и backend (php, symfony, node.js);\n- Реализовал пользовательские интерфейсы на React и Vue.js, используя JavaScript и TypeScript, создавая адаптивные компоненты с поддержкой Vite.  \n- Создавал RESTful API на Node.js и Symfony, обеспечивая взаимодействие между CRM и ERP‑системами через JSON‑формат.  \n- Настраивал Docker‑контейнеры для локальной разработки и CI/CD‑pipeline в GitLab, ускоряя процесс деплоя на Linux‑серверы и интегрируя RabbitMQ для обмена сообщениями между микросервисами.  \n- Проводил код‑ревью и тестирование микросервисов, применяя Jest и Cypress для обеспечения качества front‑ и back‑end кода.  \n- Интегрировал Redis для кэширования частых запросов и MySQL для хранения данных, улучшая отклик ERP‑модулей и снижая нагрузку на PostgreSQL.  \n- Работал в рамках Agile‑методологии, участвовал в ежедневных стендапах, спринт‑планировании и ретроспективах.  \n- Проектировал архитектуру микросервисов, разделяя функциональность на отдельные Node.js‑приложения и облегчая их масштабирование.  \n- Разработал и поддерживал административные панели на Angular и Laravel, используя HTML, CSS и jQuery для улучшения пользовательского опыта.",
                "employerId": null,
                "companyState": null,
                "companyLogos": null,
                "professionId": null,
                "professionName": null
            }
        ]
    },
    "achievementExamples": [
        "Успешная разработка и внедрение новой функциональности для корпоративного сайта, увеличившей его производительность на 20%",
        "Создание мобильного приложения с нуля, которое стало популярным в App Store и Google Play, собрав более 100 тысяч загрузок",
        "Проектирование и разработка высоко эффективной системы управления базами данных, которая уменьшила время обработки данных на 30%",
        "Участие в команде по разработке программного продукта, который был номинирован на премию «Лучшее ИТ-решение года»",
        "Успешное завершение проекта по внедрению системы управления проектами в компании, что улучшило процесс управления проектами на 25%"
    ],
    "metroCities": [
        78,
        135,
        160,
        1,
        117,
        88,
        4,
        2,
        115,
        1002,
        3,
        66
    ],
    "preferredWorkAreas": [
        {
            "area": {
                "id": 96,
                "name": "Ижевск"
            },
            "districts": [],
            "metroStations": [],
            "metroLines": []
        }
    ],
    "askJobSearchStatus": false,
    "responsesStreak": {
        "vacancyId": "131481403",
        "responsesCount": 172,
        "responsesRequired": 10
    },
    "responseStatus": {
        "test": {
            "hasTests": false
        },
        "negotiations": {
            "topicList": [
                {
                    "id": 5179231635,
                    "applicantUserId": 121838812,
                    "employerId": 11793943,
                    "employerManagerId": 16352067,
                    "chatId": 5212556056,
                    "communicationContext": {
                        "chatData": {
                            "id": 5212556056,
                            "type": "NEGOTIATION",
                            "subtype": null
                        }
                    },
                    "initialState": "RESPONSE",
                    "initialEmployerState": null,
                    "lastState": "RESPONSE",
                    "lastEmployerState": null,
                    "lastEmployerStateExtName": null,
                    "lastFunnelStage": null,
                    "archived": false,
                    "creationTime": "2026-03-24T18:08:49.867+03:00",
                    "platform": null,
                    "applicantQuestionState": false,
                    "initialTopicType": "RESPONSE_BY_APPLICANT",
                    "currentTopicType": "RESPONSE_BY_APPLICANT",
                    "initialTopicTypeGroups": [
                        "BY_APPLICANT",
                        "WITH_RESUME_AND_VACANCY"
                    ],
                    "currentTopicTypeGroups": [
                        "BY_APPLICANT",
                        "WITH_RESUME_AND_VACANCY"
                    ],
                    "hasResponseLetter": true,
                    "lastSubState": "SHOW",
                    "applicantSubState": "SHOW",
                    "employerSubState": "NEW",
                    "hasText": true,
                    "viewedByOpponent": false,
                    "hasNewMessages": false,
                    "lastModified": "2026-03-24T18:08:49.867+03:00",
                    "lastModifiedMillis": 1774364929867,
                    "chatIsArchived": false,
                    "creationTimeMillis": 1774364929867,
                    "employerCreationTime": null,
                    "employerLastChangeTime": null,
                    "lastChangeDateTimeExceptEmployerInbox": "2026-03-24T18:08:49.867+03:00",
                    "conversationMessagesCount": 1,
                    "conversationUnreadByEmployerCount": 1,
                    "inboxAvailabilityState": "AVAILABLE",
                    "responseReminderState": {
                        "allowed": false
                    },
                    "topicSource": "NEGOTIATION",
                    "declineByApplicantAllowed": true,
                    "declinedByApplicant": false,
                    "employerViolatesRules": false,
                    "applicantStateInfo": {
                        "funnelStageKey": null
                    },
                    "vacancyId": 131481403,
                    "resumeId": 254793532,
                    "resources": [
                        {
                            "id": 131481403,
                            "type": "VACANCY"
                        },
                        {
                            "id": 254793532,
                            "type": "RESUME"
                        },
                        {
                            "id": 0,
                            "type": "RESPONSE_LETTER"
                        }
                    ],
                    "availableTransitions": [],
                    "availableStages": [],
                    "responded": true,
                    "invited": false,
                    "discarded": false
                }
            ],
            "total": 1,
            "readOnlyInterval": 180,
            "untrustedEmployerRestrictionsApplied": null
        },
        "by_country_applicant_visibility": {
            "responseAllowed": true
        },
        "letterMaxLength": 10000,
        "shortVacancy": {
            "@workSchedule": "remote",
            "@showContact": false,
            "@responseLetterRequired": true,
            "vacancyId": 131481403,
            "name": "Full Stack разработчик",
            "company": {
                "@showSimilarVacancies": true,
                "@trusted": true,
                "@category": "COMPANY",
                "@countryId": 1,
                "@state": "APPROVED",
                "id": 11793943,
                "name": "Сеченов Олег Витальевич",
                "visibleName": "Сеченов Олег Витальевич",
                "logos": {
                    "logo": [
                        {
                            "@type": "ORIGINAL",
                            "@url": "/employer-logo-original/1497636.png"
                        },
                        {
                            "@type": "employerPage",
                            "@url": "/employer-logo/12280894.png"
                        },
                        {
                            "@type": "searchResultsPage",
                            "@url": "/employer-logo/12280895.png"
                        },
                        {
                            "@type": "small",
                            "@url": "/employer-logo/12280895.png"
                        },
                        {
                            "@type": "vacancyPage",
                            "@url": "/employer-logo/12280896.png"
                        },
                        {
                            "@type": "medium",
                            "@url": "/employer-logo/12280896.png"
                        }
                    ]
                },
                "employerOrganizationFormId": 9,
                "showOrganizationForm": true,
                "companySiteUrl": "",
                "accreditedITEmployer": false
            },
            "compensation": {
                "from": 3000,
                "currencyCode": "USD",
                "gross": false,
                "perModeFrom": 3000,
                "mode": "MONTH",
                "frequency": "WEEKLY"
            },
            "publicationTime": {
                "@timestamp": 1774276658,
                "$": "2026-03-23T17:37:38.826+03:00"
            },
            "area": {
                "@id": 1,
                "name": "Москва",
                "path": ".113.232.1."
            },
            "acceptTemporary": false,
            "creationSite": "ekaterinburg.hh.ru",
            "creationSiteId": 9,
            "displayHost": "izhevsk.hh.ru",
            "lastChangeTime": {
                "@timestamp": 1774283250,
                "$": "2026-03-23T19:27:30.591+03:00"
            },
            "creationTime": "2026-03-23T17:37:38.826+03:00",
            "canBeShared": true,
            "employerManager": {
                "@hhid": 189285403,
                "@managerId": 16352067,
                "@userId": 166315732,
                "@firstName": "Пётр",
                "@middleName": "Иванович",
                "@lastName": "Соколов"
            },
            "inboxPossibility": true,
            "chatWritePossibility": "ENABLED_AFTER_INVITATION",
            "notify": false,
            "links": {
                "desktop": "https://izhevsk.hh.ru/vacancy/131481403",
                "mobile": "https://m.hh.ru/vacancy/131481403"
            },
            "acceptIncompleteResumes": false,
            "driverLicenseTypes": [
                {}
            ],
            "languages": [
                {}
            ],
            "workingDays": [
                {}
            ],
            "workingTimeIntervals": [
                {}
            ],
            "workingTimeModes": [
                {}
            ],
            "vacancyProperties": {
                "properties": [
                    {
                        "property": [
                            {
                                "id": 616471499,
                                "propertyType": "HH_STANDARD",
                                "defining": true,
                                "classifying": true,
                                "bundle": "HH",
                                "propertyWeight": 400,
                                "parameters": [
                                    {
                                        "parameter": [
                                            {
                                                "key": "packageName",
                                                "value": "VP"
                                            },
                                            {
                                                "key": "serviceId",
                                                "value": "66134286"
                                            }
                                        ]
                                    }
                                ],
                                "startTimeIso": "2026-03-23T17:37:38.826+03:00",
                                "endTimeIso": "2026-04-22T17:37:38.826+03:00"
                            },
                            {
                                "id": 616471497,
                                "propertyType": "HH_RESUME_GIFTS",
                                "bundle": "HH",
                                "propertyWeight": 400,
                                "parameters": [
                                    {
                                        "parameter": [
                                            {
                                                "key": "giftsCount",
                                                "value": "15"
                                            },
                                            {
                                                "key": "packageName",
                                                "value": "VP"
                                            },
                                            {
                                                "key": "serviceId",
                                                "value": "66134286"
                                            }
                                        ]
                                    }
                                ],
                                "startTimeIso": "2026-03-23T17:37:38.826+03:00",
                                "endTimeIso": "2026-04-22T17:37:38.826+03:00"
                            },
                            {
                                "id": 616471498,
                                "propertyType": "HH_SEARCH_RESULTS_NORMAL_POSITION",
                                "bundle": "HH",
                                "propertyWeight": 400,
                                "parameters": [
                                    {
                                        "parameter": [
                                            {
                                                "key": "packageName",
                                                "value": "VP"
                                            },
                                            {
                                                "key": "serviceId",
                                                "value": "66134286"
                                            }
                                        ]
                                    }
                                ],
                                "startTimeIso": "2026-03-23T17:37:38.826+03:00",
                                "endTimeIso": "2026-04-22T17:37:38.826+03:00"
                            }
                        ]
                    }
                ],
                "calculatedStates": {
                    "HH": {
                        "advertising": false,
                        "anonymous": false,
                        "filteredPropertyNames": [
                            "HH_STANDARD",
                            "HH_SEARCH_RESULTS_NORMAL_POSITION",
                            "HH_RESUME_GIFTS"
                        ],
                        "free": false,
                        "optionPremium": false,
                        "payForPerformance": false,
                        "premium": false,
                        "standard": true,
                        "standardPlus": false,
                        "translationKeys": [
                            "employer.VacancyCreate.PublicationType.STANDARD"
                        ]
                    }
                }
            },
            "vacancyPlatforms": [
                "HH"
            ],
            "professionalRoleIds": [
                {
                    "professionalRoleId": [
                        96
                    ]
                }
            ],
            "workExperience": "between1And3",
            "employment": {
                "@type": "FULL"
            },
            "closedForApplicants": false,
            "userTestPresent": false,
            "employmentForm": "FULL",
            "flyInFlyOutDurations": [
                {}
            ],
            "internship": false,
            "nightShifts": false,
            "workFormats": [
                {
                    "workFormatsElement": [
                        "REMOTE"
                    ]
                }
            ],
            "workScheduleByDays": [
                {
                    "workScheduleByDaysElement": [
                        "FIVE_ON_TWO_OFF"
                    ]
                }
            ],
            "workingHours": [
                {
                    "workingHoursElement": [
                        "HOURS_8",
                        "FLEXIBLE"
                    ]
                }
            ],
            "experimentalModes": [
                {
                    "experimentalMode": [
                        "flyInFlyOutModalSwitch",
                        "newEmploymentTerms",
                        "ageRestrictions",
                        "newContractFields",
                        "newCompensationModes"
                    ]
                }
            ],
            "acceptLaborContract": false,
            "civilLawContracts": [
                {}
            ],
            "autoResponse": {
                "acceptAutoResponse": true
            }
        },
        "usedResumeIds": [
            "254793532"
        ],
        "unusedResumeIds": [
            "270633823",
            "270633563"
        ],
        "unfinishedResumeIds": [],
        "hiddenResumeIds": [],
        "resumes": {
            "270633823": {
                "forbidden": null,
                "_attributes": {
                    "canPublishOrUpdate": false,
                    "created": 1771543241483,
                    "hasConditions": true,
                    "hasErrors": false,
                    "hasPublicVisibility": false,
                    "hash": "8e224251ff10218b5f0039ed1f7450507a696d",
                    "hhid": "144074240",
                    "id": "270633823",
                    "isSearchable": true,
                    "lang": "RU",
                    "lastEditTime": 1773134473520,
                    "markServiceExpireTime": "2061-02-28T15:05:21+0300",
                    "marked": true,
                    "moderated": "2026-02-20T02:40:51+03:00",
                    "nextPublishAt": null,
                    "parentResumeId": "254793532",
                    "percent": 100,
                    "permission": "edit",
                    "publishState": null,
                    "renewal": true,
                    "renewalServiceExpireTime": "2061-02-28T15:05:21+0300",
                    "siteId": 12,
                    "sitePlatform": "HEADHUNTER",
                    "source": "flexible_resume_builder",
                    "status": "modified",
                    "tags": [
                        "RESUME_MARK",
                        "RESUME_RENEWAL"
                    ],
                    "update_timeout": 14400000,
                    "updated": 1774361276656,
                    "user": "121838812",
                    "vacancySearchLastUsageDate": 1774300848,
                    "validation_schema": ""
                },
                "_conditions": {
                    "accessType": {
                        "status": "ok",
                        "weight": 0,
                        "mincount": 1,
                        "maxcount": 1,
                        "parts": [
                            {
                                "string": {
                                    "required": true,
                                    "type": "string",
                                    "enum": [
                                        "clients",
                                        "whitelist",
                                        "blacklist",
                                        "direct",
                                        "no_one"
                                    ]
                                }
                            }
                        ]
                    },
                    "educationLevel": {
                        "status": "ok",
                        "weight": 0,
                        "mincount": 1,
                        "maxcount": 1,
                        "parts": [
                            {
                                "string": {
                                    "required": true,
                                    "type": "string",
                                    "enum": [
                                        "secondary",
                                        "doctor",
                                        "candidate",
                                        "unfinished_higher",
                                        "bachelor",
                                        "special_secondary",
                                        "higher",
                                        "master"
                                    ]
                                }
                            }
                        ]
                    },
                    "primaryEducation": {
                        "status": "ok",
                        "weight": 4,
                        "mincount": 0,
                        "maxcount": 64,
                        "parts": [
                            {
                                "id": {
                                    "required": false,
                                    "type": "integer",
                                    "minlength": 1,
                                    "maxlength": 16
                                }
                            },
                            {
                                "name": {
                                    "required": true,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 512
                                }
                            },
                            {
                                "organization": {
                                    "required": false,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 128
                                }
                            },
                            {
                                "result": {
                                    "required": false,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 128
                                }
                            },
                            {
                                "year": {
                                    "required": true,
                                    "type": "integer",
                                    "maxvalue": 2036,
                                    "minvalue": 1950
                                }
                            },
                            {
                                "educationLevel": {
                                    "required": true,
                                    "type": "string",
                                    "enum": [
                                        "special_secondary",
                                        "unfinished_higher",
                                        "higher",
                                        "bachelor",
                                        "master",
                                        "candidate",
                                        "doctor"
                                    ]
                                }
                            }
                        ]
                    },
                    "shortExperience": {
                        "status": "ok",
                        "weight": 5,
                        "mincount": 1,
                        "maxcount": 64,
                        "parts": [
                            {
                                "id": {
                                    "required": false,
                                    "type": "long"
                                }
                            },
                            {
                                "startDate": {
                                    "required": true,
                                    "type": "date",
                                    "maxvalue": "2026-03-24",
                                    "minvalue": "1900-01-01"
                                }
                            },
                            {
                                "endDate": {
                                    "required": false,
                                    "type": "date",
                                    "maxvalue": "2026-03-24",
                                    "minvalue": "1900-01-01"
                                }
                            },
                            {
                                "companyName": {
                                    "required": true,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 512
                                }
                            },
                            {
                                "companyIndustryId": {
                                    "required": false,
                                    "type": "integer",
                                    "minlength": 1,
                                    "maxlength": 5
                                }
                            },
                            {
                                "companyIndustries": {
                                    "required": false,
                                    "type": "list",
                                    "subtype": "integer",
                                    "minsize": 0,
                                    "maxsize": 5
                                }
                            },
                            {
                                "companyAreaId": {
                                    "required": false,
                                    "type": "integer",
                                    "minlength": 1,
                                    "maxlength": 5
                                }
                            },
                            {
                                "companyUrl": {
                                    "required": false,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 255
                                }
                            },
                            {
                                "companyId": {
                                    "required": false,
                                    "type": "integer",
                                    "minlength": 1,
                                    "maxlength": 16
                                }
                            },
                            {
                                "position": {
                                    "required": true,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 512
                                }
                            }
                        ]
                    },
                    "specialization": {
                        "status": "ok",
                        "weight": 2,
                        "mincount": 1,
                        "maxcount": 3,
                        "parts": [
                            {
                                "string": {
                                    "required": true,
                                    "type": "integer"
                                }
                            }
                        ]
                    },
                    "title": {
                        "status": "ok",
                        "weight": 2,
                        "mincount": 1,
                        "maxcount": 1,
                        "parts": [
                            {
                                "string": {
                                    "required": true,
                                    "type": "string",
                                    "minlength": 2,
                                    "maxlength": 100,
                                    "not_in": [
                                        "Backend-разработчик",
                                        "Fullstack-разработчик"
                                    ]
                                }
                            }
                        ]
                    }
                },
                "_defaults": {},
                "accessType": [
                    {
                        "string": "clients"
                    }
                ],
                "educationLevel": [
                    {
                        "string": "higher"
                    }
                ],
                "fieldsViewStatus": [
                    {
                        "contactViewStatus": null,
                        "vacancyPermissions": [],
                        "rolePermissions": []
                    }
                ],
                "primaryEducation": [
                    {
                        "id": 388442577,
                        "name": "Ижевский государственный технический университет имени М.Т. Калашников, Ижевск",
                        "organization": "Прикладная математика и информационные технологии",
                        "result": "Информационные системы и программирование",
                        "year": 2020,
                        "universityId": 42422,
                        "universityAcronym": "ИжГТУ имени М.Т. Калашникова",
                        "specialtyId": null,
                        "facultyId": null,
                        "educationLevel": "higher"
                    }
                ],
                "shortExperience": [
                    {
                        "id": 2047522769,
                        "startDate": "2024-05-01",
                        "endDate": null,
                        "companyName": "ДОСТАЕВСКИЙ",
                        "companyIndustryId": 27,
                        "companyIndustries": [
                            517,
                            585,
                            558,
                            528
                        ],
                        "companyAreaId": 2,
                        "industries": [
                            {
                                "id": 50,
                                "name": "industry.50",
                                "parentId": null,
                                "children": [
                                    {
                                        "id": 528,
                                        "name": "industry.sec.528",
                                        "parentId": 50,
                                        "children": [],
                                        "translit": "restoran_obshestvennoe_pitanie_fast_fud"
                                    }
                                ],
                                "translit": "gostinicy_restorany_obshepit_kejtering"
                            },
                            {
                                "id": 41,
                                "name": "industry.41",
                                "parentId": null,
                                "children": [
                                    {
                                        "id": 517,
                                        "name": "industry.sec.517",
                                        "parentId": 41,
                                        "children": [],
                                        "translit": "roznichnaya_set_produktovaya"
                                    }
                                ],
                                "translit": "roznichnaya_torgovlya"
                            },
                            {
                                "id": 27,
                                "name": "industry.27",
                                "parentId": null,
                                "children": [
                                    {
                                        "id": 585,
                                        "name": "industry.sec.585",
                                        "parentId": 27,
                                        "children": [],
                                        "translit": "khlebobulochnye_izdeliya_proizvodstvo"
                                    },
                                    {
                                        "id": 558,
                                        "name": "industry.sec.558",
                                        "parentId": 27,
                                        "children": [],
                                        "translit": "konditerskie_izdeliya_proizvodstvo"
                                    }
                                ],
                                "translit": "produkty_pitaniya"
                            }
                        ],
                        "companyUrl": null,
                        "companyId": 1340780,
                        "position": "Middle Fullstack-разработчик",
                        "description": null,
                        "employerId": 1340780,
                        "companyState": "APPROVED",
                        "companyLogos": {
                            "logo": [
                                {
                                    "type": "searchResultsPage",
                                    "url": "/employer-logo-round/3708315.jpeg"
                                },
                                {
                                    "type": "employerPage",
                                    "url": "/employer-logo-round/3708314.jpeg"
                                },
                                {
                                    "type": "ORIGINAL",
                                    "url": "/employer-logo-original-round/3708314.jpeg"
                                },
                                {
                                    "type": "small",
                                    "url": "/employer-logo-round/3708315.jpeg"
                                },
                                {
                                    "type": "medium",
                                    "url": "/employer-logo-round/3708316.jpeg"
                                },
                                {
                                    "type": "vacancyPage",
                                    "url": "/employer-logo-round/3708316.jpeg"
                                }
                            ]
                        },
                        "professionId": 44,
                        "professionName": "Fullstack-разработчик"
                    },
                    {
                        "id": 2047522747,
                        "startDate": "2022-10-01",
                        "endDate": "2024-05-01",
                        "companyName": "ИП \"В. А. Казарин\"",
                        "companyIndustryId": null,
                        "companyIndustries": [
                            515,
                            526,
                            525
                        ],
                        "companyAreaId": 1,
                        "industries": [
                            {
                                "id": 41,
                                "name": "industry.41",
                                "parentId": null,
                                "children": [
                                    {
                                        "id": 515,
                                        "name": "industry.sec.515",
                                        "parentId": 41,
                                        "children": [],
                                        "translit": "roznichnaya_set_odezhda_obuv_aksessuary"
                                    },
                                    {
                                        "id": 526,
                                        "name": "industry.sec.526",
                                        "parentId": 41,
                                        "children": [],
                                        "translit": "nesetevaya_roznica_melkij_opt"
                                    },
                                    {
                                        "id": 525,
                                        "name": "industry.sec.525",
                                        "parentId": 41,
                                        "children": [],
                                        "translit": "internet_magazin"
                                    }
                                ],
                                "translit": "roznichnaya_torgovlya"
                            }
                        ],
                        "companyUrl": null,
                        "companyId": null,
                        "position": "Ведущий разработчик",
                        "description": null,
                        "employerId": null,
                        "companyState": null,
                        "companyLogos": null,
                        "professionId": 40,
                        "professionName": "Frontend-разработчик"
                    },
                    {
                        "id": 2047522725,
                        "startDate": "2021-02-01",
                        "endDate": "2022-09-01",
                        "companyName": "Веб-студия Алангасар",
                        "companyIndustryId": null,
                        "companyIndustries": [],
                        "companyAreaId": null,
                        "industries": [],
                        "companyUrl": null,
                        "companyId": null,
                        "position": "Fullstack-разработчик",
                        "description": null,
                        "employerId": null,
                        "companyState": null,
                        "companyLogos": null,
                        "professionId": 44,
                        "professionName": "Fullstack-разработчик"
                    }
                ],
                "specialization": [
                    {
                        "string": 221
                    }
                ],
                "title": [
                    {
                        "string": "Frontend-разработчик"
                    }
                ],
                "hash": "8e224251ff10218b5f0039ed1f7450507a696d",
                "id": "270633823",
                "isIncomplete": false
            },
            "270633563": {
                "forbidden": null,
                "_attributes": {
                    "canPublishOrUpdate": false,
                    "created": 1771541981077,
                    "hasConditions": true,
                    "hasErrors": false,
                    "hasPublicVisibility": false,
                    "hash": "22e1313dff10218a5b0039ed1f494848613448",
                    "hhid": "144074240",
                    "id": "270633563",
                    "isSearchable": true,
                    "lang": "RU",
                    "lastEditTime": 1773134027041,
                    "markServiceExpireTime": "2031-03-08T15:05:29+0300",
                    "marked": true,
                    "moderated": "2026-02-20T02:19:56+03:00",
                    "nextPublishAt": null,
                    "parentResumeId": "254793532",
                    "percent": 100,
                    "permission": "edit",
                    "publishState": null,
                    "renewal": true,
                    "renewalServiceExpireTime": "2031-03-08T15:05:27+0300",
                    "siteId": 12,
                    "sitePlatform": "HEADHUNTER",
                    "source": "flexible_resume_builder",
                    "status": "modified",
                    "tags": [
                        "RESUME_MARK",
                        "RESUME_RENEWAL"
                    ],
                    "update_timeout": 14400000,
                    "updated": 1774356773999,
                    "user": "121838812",
                    "vacancySearchLastUsageDate": 1774300848,
                    "validation_schema": ""
                },
                "_conditions": {
                    "accessType": {
                        "status": "ok",
                        "weight": 0,
                        "mincount": 1,
                        "maxcount": 1,
                        "parts": [
                            {
                                "string": {
                                    "required": true,
                                    "type": "string",
                                    "enum": [
                                        "clients",
                                        "whitelist",
                                        "blacklist",
                                        "direct",
                                        "no_one"
                                    ]
                                }
                            }
                        ]
                    },
                    "educationLevel": {
                        "status": "ok",
                        "weight": 0,
                        "mincount": 1,
                        "maxcount": 1,
                        "parts": [
                            {
                                "string": {
                                    "required": true,
                                    "type": "string",
                                    "enum": [
                                        "secondary",
                                        "doctor",
                                        "candidate",
                                        "unfinished_higher",
                                        "bachelor",
                                        "special_secondary",
                                        "higher",
                                        "master"
                                    ]
                                }
                            }
                        ]
                    },
                    "primaryEducation": {
                        "status": "ok",
                        "weight": 4,
                        "mincount": 0,
                        "maxcount": 64,
                        "parts": [
                            {
                                "id": {
                                    "required": false,
                                    "type": "integer",
                                    "minlength": 1,
                                    "maxlength": 16
                                }
                            },
                            {
                                "name": {
                                    "required": true,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 512
                                }
                            },
                            {
                                "organization": {
                                    "required": false,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 128
                                }
                            },
                            {
                                "result": {
                                    "required": false,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 128
                                }
                            },
                            {
                                "year": {
                                    "required": true,
                                    "type": "integer",
                                    "maxvalue": 2036,
                                    "minvalue": 1950
                                }
                            },
                            {
                                "educationLevel": {
                                    "required": true,
                                    "type": "string",
                                    "enum": [
                                        "special_secondary",
                                        "unfinished_higher",
                                        "higher",
                                        "bachelor",
                                        "master",
                                        "candidate",
                                        "doctor"
                                    ]
                                }
                            }
                        ]
                    },
                    "shortExperience": {
                        "status": "ok",
                        "weight": 5,
                        "mincount": 1,
                        "maxcount": 64,
                        "parts": [
                            {
                                "id": {
                                    "required": false,
                                    "type": "long"
                                }
                            },
                            {
                                "startDate": {
                                    "required": true,
                                    "type": "date",
                                    "maxvalue": "2026-03-24",
                                    "minvalue": "1900-01-01"
                                }
                            },
                            {
                                "endDate": {
                                    "required": false,
                                    "type": "date",
                                    "maxvalue": "2026-03-24",
                                    "minvalue": "1900-01-01"
                                }
                            },
                            {
                                "companyName": {
                                    "required": true,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 512
                                }
                            },
                            {
                                "companyIndustryId": {
                                    "required": false,
                                    "type": "integer",
                                    "minlength": 1,
                                    "maxlength": 5
                                }
                            },
                            {
                                "companyIndustries": {
                                    "required": false,
                                    "type": "list",
                                    "subtype": "integer",
                                    "minsize": 0,
                                    "maxsize": 5
                                }
                            },
                            {
                                "companyAreaId": {
                                    "required": false,
                                    "type": "integer",
                                    "minlength": 1,
                                    "maxlength": 5
                                }
                            },
                            {
                                "companyUrl": {
                                    "required": false,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 255
                                }
                            },
                            {
                                "companyId": {
                                    "required": false,
                                    "type": "integer",
                                    "minlength": 1,
                                    "maxlength": 16
                                }
                            },
                            {
                                "position": {
                                    "required": true,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 512
                                }
                            }
                        ]
                    },
                    "specialization": {
                        "status": "ok",
                        "weight": 2,
                        "mincount": 1,
                        "maxcount": 3,
                        "parts": [
                            {
                                "string": {
                                    "required": true,
                                    "type": "integer"
                                }
                            }
                        ]
                    },
                    "title": {
                        "status": "ok",
                        "weight": 2,
                        "mincount": 1,
                        "maxcount": 1,
                        "parts": [
                            {
                                "string": {
                                    "required": true,
                                    "type": "string",
                                    "minlength": 2,
                                    "maxlength": 100,
                                    "not_in": [
                                        "Fullstack-разработчик",
                                        "Frontend-разработчик"
                                    ]
                                }
                            }
                        ]
                    }
                },
                "_defaults": {},
                "accessType": [
                    {
                        "string": "clients"
                    }
                ],
                "educationLevel": [
                    {
                        "string": "higher"
                    }
                ],
                "fieldsViewStatus": [
                    {
                        "contactViewStatus": null,
                        "vacancyPermissions": [],
                        "rolePermissions": []
                    }
                ],
                "primaryEducation": [
                    {
                        "id": 388442388,
                        "name": "Ижевский государственный технический университет имени М.Т. Калашников, Ижевск",
                        "organization": "Прикладная математика и информационные технологии",
                        "result": "Информационные системы и программирование",
                        "year": 2020,
                        "universityId": 42422,
                        "universityAcronym": "ИжГТУ имени М.Т. Калашникова",
                        "specialtyId": null,
                        "facultyId": null,
                        "educationLevel": "higher"
                    }
                ],
                "shortExperience": [
                    {
                        "id": 2047521556,
                        "startDate": "2024-05-01",
                        "endDate": null,
                        "companyName": "ДОСТАЕВСКИЙ",
                        "companyIndustryId": 27,
                        "companyIndustries": [
                            517,
                            585,
                            558,
                            528
                        ],
                        "companyAreaId": 2,
                        "industries": [
                            {
                                "id": 50,
                                "name": "industry.50",
                                "parentId": null,
                                "children": [
                                    {
                                        "id": 528,
                                        "name": "industry.sec.528",
                                        "parentId": 50,
                                        "children": [],
                                        "translit": "restoran_obshestvennoe_pitanie_fast_fud"
                                    }
                                ],
                                "translit": "gostinicy_restorany_obshepit_kejtering"
                            },
                            {
                                "id": 41,
                                "name": "industry.41",
                                "parentId": null,
                                "children": [
                                    {
                                        "id": 517,
                                        "name": "industry.sec.517",
                                        "parentId": 41,
                                        "children": [],
                                        "translit": "roznichnaya_set_produktovaya"
                                    }
                                ],
                                "translit": "roznichnaya_torgovlya"
                            },
                            {
                                "id": 27,
                                "name": "industry.27",
                                "parentId": null,
                                "children": [
                                    {
                                        "id": 585,
                                        "name": "industry.sec.585",
                                        "parentId": 27,
                                        "children": [],
                                        "translit": "khlebobulochnye_izdeliya_proizvodstvo"
                                    },
                                    {
                                        "id": 558,
                                        "name": "industry.sec.558",
                                        "parentId": 27,
                                        "children": [],
                                        "translit": "konditerskie_izdeliya_proizvodstvo"
                                    }
                                ],
                                "translit": "produkty_pitaniya"
                            }
                        ],
                        "companyUrl": null,
                        "companyId": 1340780,
                        "position": "Middle Fullstack-разработчик",
                        "description": null,
                        "employerId": 1340780,
                        "companyState": "APPROVED",
                        "companyLogos": {
                            "logo": [
                                {
                                    "type": "employerPage",
                                    "url": "/employer-logo-round/3708314.jpeg"
                                },
                                {
                                    "type": "medium",
                                    "url": "/employer-logo-round/3708316.jpeg"
                                },
                                {
                                    "type": "ORIGINAL",
                                    "url": "/employer-logo-original-round/3708314.jpeg"
                                },
                                {
                                    "type": "searchResultsPage",
                                    "url": "/employer-logo-round/3708315.jpeg"
                                },
                                {
                                    "type": "small",
                                    "url": "/employer-logo-round/3708315.jpeg"
                                },
                                {
                                    "type": "vacancyPage",
                                    "url": "/employer-logo-round/3708316.jpeg"
                                }
                            ]
                        },
                        "professionId": 44,
                        "professionName": "Fullstack-разработчик"
                    },
                    {
                        "id": 2047521517,
                        "startDate": "2022-10-01",
                        "endDate": "2024-05-01",
                        "companyName": "ИП \"В. А. Казарин\"",
                        "companyIndustryId": null,
                        "companyIndustries": [
                            515,
                            526,
                            525
                        ],
                        "companyAreaId": 1,
                        "industries": [
                            {
                                "id": 41,
                                "name": "industry.41",
                                "parentId": null,
                                "children": [
                                    {
                                        "id": 515,
                                        "name": "industry.sec.515",
                                        "parentId": 41,
                                        "children": [],
                                        "translit": "roznichnaya_set_odezhda_obuv_aksessuary"
                                    },
                                    {
                                        "id": 526,
                                        "name": "industry.sec.526",
                                        "parentId": 41,
                                        "children": [],
                                        "translit": "nesetevaya_roznica_melkij_opt"
                                    },
                                    {
                                        "id": 525,
                                        "name": "industry.sec.525",
                                        "parentId": 41,
                                        "children": [],
                                        "translit": "internet_magazin"
                                    }
                                ],
                                "translit": "roznichnaya_torgovlya"
                            }
                        ],
                        "companyUrl": null,
                        "companyId": null,
                        "position": "Ведущий разработчик",
                        "description": null,
                        "employerId": null,
                        "companyState": null,
                        "companyLogos": null,
                        "professionId": 49,
                        "professionName": "PHP-разработчик"
                    },
                    {
                        "id": 2047521529,
                        "startDate": "2021-02-01",
                        "endDate": "2022-09-01",
                        "companyName": "Веб-студия Алангасар",
                        "companyIndustryId": null,
                        "companyIndustries": [],
                        "companyAreaId": null,
                        "industries": [],
                        "companyUrl": null,
                        "companyId": null,
                        "position": "Fullstack-разработчик",
                        "description": null,
                        "employerId": null,
                        "companyState": null,
                        "companyLogos": null,
                        "professionId": 44,
                        "professionName": "Fullstack-разработчик"
                    }
                ],
                "specialization": [
                    {
                        "string": 221
                    }
                ],
                "title": [
                    {
                        "string": "Backend-разработчик"
                    }
                ],
                "hash": "22e1313dff10218a5b0039ed1f494848613448",
                "id": "270633563",
                "isIncomplete": false
            },
            "254793532": {
                "forbidden": null,
                "_attributes": {
                    "canPublishOrUpdate": false,
                    "created": 1753691316748,
                    "hasConditions": true,
                    "hasErrors": false,
                    "hasPublicVisibility": false,
                    "hash": "df3c734dff0f2fd73c0039ed1f396734705750",
                    "hhid": "144074240",
                    "id": "254793532",
                    "isSearchable": true,
                    "lang": "RU",
                    "lastEditTime": 1773134290987,
                    "markServiceExpireTime": "2031-03-08T15:05:30+0300",
                    "marked": true,
                    "moderated": "2025-07-28T15:05:39+03:00",
                    "nextPublishAt": null,
                    "parentResumeId": "247712534",
                    "percent": 100,
                    "permission": "edit",
                    "publishState": null,
                    "renewal": true,
                    "renewalServiceExpireTime": "2031-03-08T15:05:28+0300",
                    "siteId": 12,
                    "sitePlatform": "HEADHUNTER",
                    "source": "flexible_resume_builder",
                    "status": "modified",
                    "tags": [
                        "RESUME_MARK",
                        "RESUME_RENEWAL"
                    ],
                    "update_timeout": 14400000,
                    "updated": 1774356773005,
                    "user": "121838812",
                    "vacancySearchLastUsageDate": 1774300848,
                    "validation_schema": ""
                },
                "_conditions": {
                    "accessType": {
                        "status": "ok",
                        "weight": 0,
                        "mincount": 1,
                        "maxcount": 1,
                        "parts": [
                            {
                                "string": {
                                    "required": true,
                                    "type": "string",
                                    "enum": [
                                        "clients",
                                        "whitelist",
                                        "blacklist",
                                        "direct",
                                        "no_one"
                                    ]
                                }
                            }
                        ]
                    },
                    "educationLevel": {
                        "status": "ok",
                        "weight": 0,
                        "mincount": 1,
                        "maxcount": 1,
                        "parts": [
                            {
                                "string": {
                                    "required": true,
                                    "type": "string",
                                    "enum": [
                                        "secondary",
                                        "doctor",
                                        "candidate",
                                        "unfinished_higher",
                                        "bachelor",
                                        "special_secondary",
                                        "higher",
                                        "master"
                                    ]
                                }
                            }
                        ]
                    },
                    "primaryEducation": {
                        "status": "ok",
                        "weight": 4,
                        "mincount": 0,
                        "maxcount": 64,
                        "parts": [
                            {
                                "id": {
                                    "required": false,
                                    "type": "integer",
                                    "minlength": 1,
                                    "maxlength": 16
                                }
                            },
                            {
                                "name": {
                                    "required": true,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 512
                                }
                            },
                            {
                                "organization": {
                                    "required": false,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 128
                                }
                            },
                            {
                                "result": {
                                    "required": false,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 128
                                }
                            },
                            {
                                "year": {
                                    "required": true,
                                    "type": "integer",
                                    "maxvalue": 2036,
                                    "minvalue": 1950
                                }
                            },
                            {
                                "educationLevel": {
                                    "required": true,
                                    "type": "string",
                                    "enum": [
                                        "special_secondary",
                                        "unfinished_higher",
                                        "higher",
                                        "bachelor",
                                        "master",
                                        "candidate",
                                        "doctor"
                                    ]
                                }
                            }
                        ]
                    },
                    "shortExperience": {
                        "status": "ok",
                        "weight": 5,
                        "mincount": 1,
                        "maxcount": 64,
                        "parts": [
                            {
                                "id": {
                                    "required": false,
                                    "type": "long"
                                }
                            },
                            {
                                "startDate": {
                                    "required": true,
                                    "type": "date",
                                    "maxvalue": "2026-03-24",
                                    "minvalue": "1900-01-01"
                                }
                            },
                            {
                                "endDate": {
                                    "required": false,
                                    "type": "date",
                                    "maxvalue": "2026-03-24",
                                    "minvalue": "1900-01-01"
                                }
                            },
                            {
                                "companyName": {
                                    "required": true,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 512
                                }
                            },
                            {
                                "companyIndustryId": {
                                    "required": false,
                                    "type": "integer",
                                    "minlength": 1,
                                    "maxlength": 5
                                }
                            },
                            {
                                "companyIndustries": {
                                    "required": false,
                                    "type": "list",
                                    "subtype": "integer",
                                    "minsize": 0,
                                    "maxsize": 5
                                }
                            },
                            {
                                "companyAreaId": {
                                    "required": false,
                                    "type": "integer",
                                    "minlength": 1,
                                    "maxlength": 5
                                }
                            },
                            {
                                "companyUrl": {
                                    "required": false,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 255
                                }
                            },
                            {
                                "companyId": {
                                    "required": false,
                                    "type": "integer",
                                    "minlength": 1,
                                    "maxlength": 16
                                }
                            },
                            {
                                "position": {
                                    "required": true,
                                    "type": "string",
                                    "minlength": 1,
                                    "maxlength": 512
                                }
                            }
                        ]
                    },
                    "specialization": {
                        "status": "ok",
                        "weight": 2,
                        "mincount": 1,
                        "maxcount": 3,
                        "parts": [
                            {
                                "string": {
                                    "required": true,
                                    "type": "integer"
                                }
                            }
                        ]
                    },
                    "title": {
                        "status": "ok",
                        "weight": 2,
                        "mincount": 1,
                        "maxcount": 1,
                        "parts": [
                            {
                                "string": {
                                    "required": true,
                                    "type": "string",
                                    "minlength": 2,
                                    "maxlength": 100,
                                    "not_in": [
                                        "Backend-разработчик",
                                        "Frontend-разработчик"
                                    ]
                                }
                            }
                        ]
                    }
                },
                "_defaults": {},
                "accessType": [
                    {
                        "string": "clients"
                    }
                ],
                "educationLevel": [
                    {
                        "string": "higher"
                    }
                ],
                "fieldsViewStatus": [
                    {
                        "contactViewStatus": null,
                        "vacancyPermissions": [],
                        "rolePermissions": []
                    }
                ],
                "primaryEducation": [
                    {
                        "id": 387718438,
                        "name": "Ижевский государственный технический университет имени М.Т. Калашников, Ижевск",
                        "organization": "Прикладная математика и информационные технологии",
                        "result": "Информационные системы и программирование",
                        "year": 2020,
                        "universityId": 42422,
                        "universityAcronym": "ИжГТУ имени М.Т. Калашникова",
                        "specialtyId": null,
                        "facultyId": null,
                        "educationLevel": "higher"
                    }
                ],
                "shortExperience": [
                    {
                        "id": 2012471339,
                        "startDate": "2024-05-01",
                        "endDate": null,
                        "companyName": "ДОСТАЕВСКИЙ",
                        "companyIndustryId": 27,
                        "companyIndustries": [
                            517,
                            585,
                            558,
                            528
                        ],
                        "companyAreaId": 2,
                        "industries": [
                            {
                                "id": 50,
                                "name": "industry.50",
                                "parentId": null,
                                "children": [
                                    {
                                        "id": 528,
                                        "name": "industry.sec.528",
                                        "parentId": 50,
                                        "children": [],
                                        "translit": "restoran_obshestvennoe_pitanie_fast_fud"
                                    }
                                ],
                                "translit": "gostinicy_restorany_obshepit_kejtering"
                            },
                            {
                                "id": 41,
                                "name": "industry.41",
                                "parentId": null,
                                "children": [
                                    {
                                        "id": 517,
                                        "name": "industry.sec.517",
                                        "parentId": 41,
                                        "children": [],
                                        "translit": "roznichnaya_set_produktovaya"
                                    }
                                ],
                                "translit": "roznichnaya_torgovlya"
                            },
                            {
                                "id": 27,
                                "name": "industry.27",
                                "parentId": null,
                                "children": [
                                    {
                                        "id": 585,
                                        "name": "industry.sec.585",
                                        "parentId": 27,
                                        "children": [],
                                        "translit": "khlebobulochnye_izdeliya_proizvodstvo"
                                    },
                                    {
                                        "id": 558,
                                        "name": "industry.sec.558",
                                        "parentId": 27,
                                        "children": [],
                                        "translit": "konditerskie_izdeliya_proizvodstvo"
                                    }
                                ],
                                "translit": "produkty_pitaniya"
                            }
                        ],
                        "companyUrl": null,
                        "companyId": 1340780,
                        "position": "Middle Fullstack-разработчик",
                        "description": null,
                        "employerId": 1340780,
                        "companyState": "APPROVED",
                        "companyLogos": {
                            "logo": [
                                {
                                    "type": "searchResultsPage",
                                    "url": "/employer-logo-round/3708315.jpeg"
                                },
                                {
                                    "type": "employerPage",
                                    "url": "/employer-logo-round/3708314.jpeg"
                                },
                                {
                                    "type": "small",
                                    "url": "/employer-logo-round/3708315.jpeg"
                                },
                                {
                                    "type": "vacancyPage",
                                    "url": "/employer-logo-round/3708316.jpeg"
                                },
                                {
                                    "type": "medium",
                                    "url": "/employer-logo-round/3708316.jpeg"
                                },
                                {
                                    "type": "ORIGINAL",
                                    "url": "/employer-logo-original-round/3708314.jpeg"
                                }
                            ]
                        },
                        "professionId": 44,
                        "professionName": "Fullstack-разработчик"
                    },
                    {
                        "id": 2012471342,
                        "startDate": "2022-10-01",
                        "endDate": "2024-05-01",
                        "companyName": "ИП \"В. А. Казарин\"",
                        "companyIndustryId": null,
                        "companyIndustries": [
                            515,
                            526,
                            525
                        ],
                        "companyAreaId": 1,
                        "industries": [
                            {
                                "id": 41,
                                "name": "industry.41",
                                "parentId": null,
                                "children": [
                                    {
                                        "id": 515,
                                        "name": "industry.sec.515",
                                        "parentId": 41,
                                        "children": [],
                                        "translit": "roznichnaya_set_odezhda_obuv_aksessuary"
                                    },
                                    {
                                        "id": 526,
                                        "name": "industry.sec.526",
                                        "parentId": 41,
                                        "children": [],
                                        "translit": "nesetevaya_roznica_melkij_opt"
                                    },
                                    {
                                        "id": 525,
                                        "name": "industry.sec.525",
                                        "parentId": 41,
                                        "children": [],
                                        "translit": "internet_magazin"
                                    }
                                ],
                                "translit": "roznichnaya_torgovlya"
                            }
                        ],
                        "companyUrl": null,
                        "companyId": null,
                        "position": "Ведущий разработчик",
                        "description": null,
                        "employerId": null,
                        "companyState": null,
                        "companyLogos": null,
                        "professionId": 49,
                        "professionName": "PHP-разработчик"
                    },
                    {
                        "id": 2038949133,
                        "startDate": "2021-02-01",
                        "endDate": "2022-09-01",
                        "companyName": "Веб-студия Алангасар",
                        "companyIndustryId": null,
                        "companyIndustries": [],
                        "companyAreaId": null,
                        "industries": [],
                        "companyUrl": null,
                        "companyId": null,
                        "position": "Fullstack-разработчик",
                        "description": null,
                        "employerId": null,
                        "companyState": null,
                        "companyLogos": null,
                        "professionId": 44,
                        "professionName": "Fullstack-разработчик"
                    }
                ],
                "specialization": [
                    {
                        "string": 221
                    }
                ],
                "title": [
                    {
                        "string": "Fullstack-разработчик"
                    }
                ],
                "hash": "df3c734dff0f2fd73c0039ed1f396734705750",
                "id": "254793532",
                "isIncomplete": false
            }
        },
        "responseImpossible": false,
        "alreadyApplied": false
    },
    "respondedWithResume": {
        "forbidden": null,
        "_attributes": {
            "canPublishOrUpdate": false,
            "created": 1753691316748,
            "hasConditions": true,
            "hasErrors": false,
            "hasPublicVisibility": false,
            "hash": "df3c734dff0f2fd73c0039ed1f396734705750",
            "hhid": "144074240",
            "id": "254793532",
            "isSearchable": true,
            "lang": "RU",
            "lastEditTime": 1773134290987,
            "markServiceExpireTime": "2031-03-08T15:05:30+0300",
            "marked": true,
            "moderated": "2025-07-28T15:05:39+03:00",
            "nextPublishAt": null,
            "parentResumeId": "247712534",
            "percent": 100,
            "permission": "edit",
            "publishState": null,
            "renewal": true,
            "renewalServiceExpireTime": "2031-03-08T15:05:28+0300",
            "siteId": 12,
            "sitePlatform": "HEADHUNTER",
            "source": "flexible_resume_builder",
            "status": "modified",
            "tags": [
                "RESUME_MARK",
                "RESUME_RENEWAL"
            ],
            "update_timeout": 14400000,
            "updated": 1774356773005,
            "user": "121838812",
            "vacancySearchLastUsageDate": 1774300848,
            "validation_schema": ""
        },
        "_conditions": {
            "accessType": {
                "status": "ok",
                "weight": 0,
                "mincount": 1,
                "maxcount": 1,
                "parts": [
                    {
                        "string": {
                            "required": true,
                            "type": "string",
                            "enum": [
                                "clients",
                                "whitelist",
                                "blacklist",
                                "direct",
                                "no_one"
                            ]
                        }
                    }
                ]
            },
            "educationLevel": {
                "status": "ok",
                "weight": 0,
                "mincount": 1,
                "maxcount": 1,
                "parts": [
                    {
                        "string": {
                            "required": true,
                            "type": "string",
                            "enum": [
                                "secondary",
                                "doctor",
                                "candidate",
                                "unfinished_higher",
                                "bachelor",
                                "special_secondary",
                                "higher",
                                "master"
                            ]
                        }
                    }
                ]
            },
            "primaryEducation": {
                "status": "ok",
                "weight": 4,
                "mincount": 0,
                "maxcount": 64,
                "parts": [
                    {
                        "id": {
                            "required": false,
                            "type": "integer",
                            "minlength": 1,
                            "maxlength": 16
                        }
                    },
                    {
                        "name": {
                            "required": true,
                            "type": "string",
                            "minlength": 1,
                            "maxlength": 512
                        }
                    },
                    {
                        "organization": {
                            "required": false,
                            "type": "string",
                            "minlength": 1,
                            "maxlength": 128
                        }
                    },
                    {
                        "result": {
                            "required": false,
                            "type": "string",
                            "minlength": 1,
                            "maxlength": 128
                        }
                    },
                    {
                        "year": {
                            "required": true,
                            "type": "integer",
                            "maxvalue": 2036,
                            "minvalue": 1950
                        }
                    },
                    {
                        "educationLevel": {
                            "required": true,
                            "type": "string",
                            "enum": [
                                "special_secondary",
                                "unfinished_higher",
                                "higher",
                                "bachelor",
                                "master",
                                "candidate",
                                "doctor"
                            ]
                        }
                    }
                ]
            },
            "shortExperience": {
                "status": "ok",
                "weight": 5,
                "mincount": 1,
                "maxcount": 64,
                "parts": [
                    {
                        "id": {
                            "required": false,
                            "type": "long"
                        }
                    },
                    {
                        "startDate": {
                            "required": true,
                            "type": "date",
                            "maxvalue": "2026-03-24",
                            "minvalue": "1900-01-01"
                        }
                    },
                    {
                        "endDate": {
                            "required": false,
                            "type": "date",
                            "maxvalue": "2026-03-24",
                            "minvalue": "1900-01-01"
                        }
                    },
                    {
                        "companyName": {
                            "required": true,
                            "type": "string",
                            "minlength": 1,
                            "maxlength": 512
                        }
                    },
                    {
                        "companyIndustryId": {
                            "required": false,
                            "type": "integer",
                            "minlength": 1,
                            "maxlength": 5
                        }
                    },
                    {
                        "companyIndustries": {
                            "required": false,
                            "type": "list",
                            "subtype": "integer",
                            "minsize": 0,
                            "maxsize": 5
                        }
                    },
                    {
                        "companyAreaId": {
                            "required": false,
                            "type": "integer",
                            "minlength": 1,
                            "maxlength": 5
                        }
                    },
                    {
                        "companyUrl": {
                            "required": false,
                            "type": "string",
                            "minlength": 1,
                            "maxlength": 255
                        }
                    },
                    {
                        "companyId": {
                            "required": false,
                            "type": "integer",
                            "minlength": 1,
                            "maxlength": 16
                        }
                    },
                    {
                        "position": {
                            "required": true,
                            "type": "string",
                            "minlength": 1,
                            "maxlength": 512
                        }
                    }
                ]
            },
            "specialization": {
                "status": "ok",
                "weight": 2,
                "mincount": 1,
                "maxcount": 3,
                "parts": [
                    {
                        "string": {
                            "required": true,
                            "type": "integer"
                        }
                    }
                ]
            },
            "title": {
                "status": "ok",
                "weight": 2,
                "mincount": 1,
                "maxcount": 1,
                "parts": [
                    {
                        "string": {
                            "required": true,
                            "type": "string",
                            "minlength": 2,
                            "maxlength": 100,
                            "not_in": [
                                "Backend-разработчик",
                                "Frontend-разработчик"
                            ]
                        }
                    }
                ]
            }
        },
        "_defaults": {},
        "accessType": [
            {
                "string": "clients"
            }
        ],
        "educationLevel": [
            {
                "string": "higher"
            }
        ],
        "fieldsViewStatus": [
            {
                "contactViewStatus": null,
                "vacancyPermissions": [],
                "rolePermissions": []
            }
        ],
        "primaryEducation": [
            {
                "id": 387718438,
                "name": "Ижевский государственный технический университет имени М.Т. Калашников, Ижевск",
                "organization": "Прикладная математика и информационные технологии",
                "result": "Информационные системы и программирование",
                "year": 2020,
                "universityId": 42422,
                "universityAcronym": "ИжГТУ имени М.Т. Калашникова",
                "specialtyId": null,
                "facultyId": null,
                "educationLevel": "higher"
            }
        ],
        "shortExperience": [
            {
                "id": 2012471339,
                "startDate": "2024-05-01",
                "endDate": null,
                "companyName": "ДОСТАЕВСКИЙ",
                "companyIndustryId": 27,
                "companyIndustries": [
                    517,
                    585,
                    558,
                    528
                ],
                "companyAreaId": 2,
                "industries": [
                    {
                        "id": 50,
                        "name": "industry.50",
                        "parentId": null,
                        "children": [
                            {
                                "id": 528,
                                "name": "industry.sec.528",
                                "parentId": 50,
                                "children": [],
                                "translit": "restoran_obshestvennoe_pitanie_fast_fud"
                            }
                        ],
                        "translit": "gostinicy_restorany_obshepit_kejtering"
                    },
                    {
                        "id": 41,
                        "name": "industry.41",
                        "parentId": null,
                        "children": [
                            {
                                "id": 517,
                                "name": "industry.sec.517",
                                "parentId": 41,
                                "children": [],
                                "translit": "roznichnaya_set_produktovaya"
                            }
                        ],
                        "translit": "roznichnaya_torgovlya"
                    },
                    {
                        "id": 27,
                        "name": "industry.27",
                        "parentId": null,
                        "children": [
                            {
                                "id": 585,
                                "name": "industry.sec.585",
                                "parentId": 27,
                                "children": [],
                                "translit": "khlebobulochnye_izdeliya_proizvodstvo"
                            },
                            {
                                "id": 558,
                                "name": "industry.sec.558",
                                "parentId": 27,
                                "children": [],
                                "translit": "konditerskie_izdeliya_proizvodstvo"
                            }
                        ],
                        "translit": "produkty_pitaniya"
                    }
                ],
                "companyUrl": null,
                "companyId": 1340780,
                "position": "Middle Fullstack-разработчик",
                "description": null,
                "employerId": 1340780,
                "companyState": "APPROVED",
                "companyLogos": {
                    "logo": [
                        {
                            "type": "searchResultsPage",
                            "url": "/employer-logo-round/3708315.jpeg"
                        },
                        {
                            "type": "employerPage",
                            "url": "/employer-logo-round/3708314.jpeg"
                        },
                        {
                            "type": "small",
                            "url": "/employer-logo-round/3708315.jpeg"
                        },
                        {
                            "type": "vacancyPage",
                            "url": "/employer-logo-round/3708316.jpeg"
                        },
                        {
                            "type": "medium",
                            "url": "/employer-logo-round/3708316.jpeg"
                        },
                        {
                            "type": "ORIGINAL",
                            "url": "/employer-logo-original-round/3708314.jpeg"
                        }
                    ]
                },
                "professionId": 44,
                "professionName": "Fullstack-разработчик"
            },
            {
                "id": 2012471342,
                "startDate": "2022-10-01",
                "endDate": "2024-05-01",
                "companyName": "ИП \"В. А. Казарин\"",
                "companyIndustryId": null,
                "companyIndustries": [
                    515,
                    526,
                    525
                ],
                "companyAreaId": 1,
                "industries": [
                    {
                        "id": 41,
                        "name": "industry.41",
                        "parentId": null,
                        "children": [
                            {
                                "id": 515,
                                "name": "industry.sec.515",
                                "parentId": 41,
                                "children": [],
                                "translit": "roznichnaya_set_odezhda_obuv_aksessuary"
                            },
                            {
                                "id": 526,
                                "name": "industry.sec.526",
                                "parentId": 41,
                                "children": [],
                                "translit": "nesetevaya_roznica_melkij_opt"
                            },
                            {
                                "id": 525,
                                "name": "industry.sec.525",
                                "parentId": 41,
                                "children": [],
                                "translit": "internet_magazin"
                            }
                        ],
                        "translit": "roznichnaya_torgovlya"
                    }
                ],
                "companyUrl": null,
                "companyId": null,
                "position": "Ведущий разработчик",
                "description": null,
                "employerId": null,
                "companyState": null,
                "companyLogos": null,
                "professionId": 49,
                "professionName": "PHP-разработчик"
            },
            {
                "id": 2038949133,
                "startDate": "2021-02-01",
                "endDate": "2022-09-01",
                "companyName": "Веб-студия Алангасар",
                "companyIndustryId": null,
                "companyIndustries": [],
                "companyAreaId": null,
                "industries": [],
                "companyUrl": null,
                "companyId": null,
                "position": "Fullstack-разработчик",
                "description": null,
                "employerId": null,
                "companyState": null,
                "companyLogos": null,
                "professionId": 44,
                "professionName": "Fullstack-разработчик"
            }
        ],
        "specialization": [
            {
                "string": 221
            }
        ],
        "title": [
            {
                "string": "Fullstack-разработчик"
            }
        ],
        "hash": "df3c734dff0f2fd73c0039ed1f396734705750",
        "id": "254793532",
        "isIncomplete": false
    }
}
```

Headers:
access-control-allow-credentials
true
access-control-allow-origin
https://izhevsk.hh.ru
cache-control
no-cache, no-store
content-encoding
gzip
content-type
application/json
date
Tue, 24 Mar 2026 15:08:50 GMT
nel
{"success_fraction":0,"report_to":"nel","max_age":3600}
report-to
{"group":"nel","endpoints":[{"url":"https:\/\/nel.hhdev.ru\/report\/hh"}],"max_age":3600}, {"group":"csp-endpoint","max_age":3600,"endpoints":[{"url":"https:\/\/nel.hhdev.ru\/report\/hh"}]}
server
ddos-guard
server-timing
frontik;desc="frontik execution time";dur=0.34479641914367676
strict-transport-security
max-age=31536000; includeSubDomains
vary
Accept-Encoding, Origin
x-content-type-options
nosniff
x-hhid
144074240
x-hhuid
yG71zsVC4Bqaq2g9_klKAw--
x-request-id
17743649297117a1c4d017d2dd8d3034, 17743649297117a1c4d017d2dd8d3034
accept
application/json
baggage
sentry-trace_id=d5c32e64eb8248c187a860dcbb38925c,sentry-sample_rand=0.360381,sentry-environment=production,sentry-release=xhh%4026.13.2.5,sentry-public_key=0cc3a09b6698423b8ca47d3478cfccac,sentry-transaction=%2Fvacancy%2F%7Bid%3Aint%7D,sentry-sample_rate=0.001,sentry-sampled=false
content-type
multipart/form-data; boundary=----WebKitFormBoundarycqbt0YQEdEt7zauc
referer
https://izhevsk.hh.ru/vacancy/131481403?hhtmFrom=vacancy_search_list
sec-ch-ua
"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"
sec-ch-ua-mobile
?0
sec-ch-ua-platform
"Windows"
sentry-trace
d5c32e64eb8248c187a860dcbb38925c-864efa12471b63c6-0
user-agent
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36
x-gib-fgsscgib-w-hh
20l2b21bfb162fc9803355e7d3a3c549a3f12c31
x-gib-gsscgib-w-hh
MbeBMFjXAwjlwCUBmq4FCsShQL+sc7PKu6MPWMSCt1OIMSaU8z76SRZ+18ugKiryHYJq2X/5VYrDbEl4WwLvbFrxqdEwySCujixVg1al7LzIJNj8aWZUS49aufQOt3dR+/D1fPPkTGpUwi4x6yQWHwFu3ZoiyvchTyle9BzVHovGsAYDSO68onKN/vDr+dEqhSRpBunS2vCWFK6C6fQ+RI6Z5ut7zw/ZOEN2OnW/2eEra7yG28EWXOmIuZf98Zfgog==
x-hhtmfrom
vacancy_search_list
x-hhtmsource
vacancy
x-requested-with
XMLHttpRequest
x-xsrftoken
1eb883bed235f5fc751db6604f7ad1dc