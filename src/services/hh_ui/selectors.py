"""HeadHunter.ru DOM selectors — edit here when hh.ru changes layout.

All UI automation should import from this module only.
"""

from __future__ import annotations

# Vacancy page: primary "Respond" / "Откликнуться" entry points (try in order).
VACANCY_APPLY_BUTTON: tuple[str, ...] = (
    '[data-qa="vacancy-response-link-top"]',
    '[data-qa="vacancy-response-link-bottom"]',
    'a[data-qa="vacancy-response-link-top"]',
    'button[data-qa="vacancy-response-link-top"]',
)

# Cookie / privacy banners (best-effort dismiss).
COOKIE_ACCEPT: tuple[str, ...] = (
    '[data-qa="cookies-policy-informer-accept"]',
    'button:has-text("Хорошо")',
    'button:has-text("OK")',
)

# Post-click: employer questionnaire (cannot auto-fill ethically in MVP).
EMPLOYER_QUESTION_HINTS: tuple[str, ...] = (
    '[data-qa="employer-questions"]',
    "text=Ответьте на вопросы",
    "text=вопросы работодателя",
)

# Already applied indicators.
ALREADY_APPLIED_HINTS: tuple[str, ...] = (
    "text=Вы уже откликнулись",
    "text=уже откликались",
    "text=Already responded",
)

# Captcha / bot challenge (avoid iframe[src*='captcha'] — matches unrelated URLs and causes false positives).
CAPTCHA_HINTS: tuple[str, ...] = (
    "iframe[src*='smartcaptcha']",
    "iframe[src*='hcaptcha.com']",
    "iframe[src*='captcha.yandex']",
    '[data-qa="challenge-form"]',
)

# Login / session expired.
LOGIN_FORM: tuple[str, ...] = (
    '[data-qa="login"]',
    "text=Вход в личный кабинет",
    'a[href*="account/login"]',
)

# Magritte bottom sheet: "Резюме для отклика" (respond flow on vacancy page).
RESPONSE_MODAL_CONTENT: str = '[data-qa="bottom-sheet-content"]'
# Swipe container (often appears before/without inner content matching).
BOTTOM_SHEET_CONTAINER: str = '[data-qa="bottom-sheet-container"]'
RESPONSE_MODAL_TITLE_TEXT: str = "Резюме для отклика"
RESPONSE_MODAL_CLOSE: str = '[data-qa="response-popup-close"]'
# Radio list inside the sheet (value = resume id for API/UI apply).
RESUME_RADIO: str = 'input[type="radio"][name="resumeId"]'
RESUME_TITLE_IN_MODAL: str = '[data-qa="resume-title"]'

# Resume picker in modal (try in order) — legacy <select> layouts.
RESUME_SELECT: tuple[str, ...] = (
    'select[data-qa="resume-select"]',
    "select[name='resumeId']",
    'select[data-qa="negotiation-resume-select"]',
)

RESUME_SUBMIT: tuple[str, ...] = (
    'button[data-qa="vacancy-response-submit"]',
    'button[type="submit"]:has-text("Откликнуться")',
    'button:has-text("Откликнуться")',
    'button:has-text("Отправить")',
)

# Applicant resume list page (HTML fetch + parse in applicant_http).
APPLICANT_RESUMES_URL = "https://hh.ru/applicant/resumes"
