"""Prompt builders for AI requests."""

from __future__ import annotations

from dataclasses import dataclass


def build_compatibility_system_prompt() -> str:
    """Return the system prompt for candidate-vacancy compatibility scoring."""
    return (
        "Ты — Senior Technical Recruitment Analyst с 30-летним опытом оценки соответствия "
        "инженерных кандидатов техническим вакансиям.\n"
        "Твоя задача: вычислить процент совместимости кандидата с вакансией.\n\n"
        "Ты получаешь:\n"
        "1. Вакансия: название, требуемые навыки, описание.\n"
        "2. Кандидат: технический стек, краткое описание опыта работы.\n\n"
        "[ПРАВИЛА ОЦЕНКИ]\n"
        "- Каждая совпадающая или смежная технология увеличивает балл.\n"
        "- Релевантность области и уровня опыта кандидата вакансии важна.\n"
        "- Название вакансии задаёт вес каждого навыка.\n"
        "- Частичные совпадения (близкие технологии, смежные домены)"
        " учитываются пропорционально.\n\n"
        "[ПРАВИЛО ВЫВОДА]\n"
        "Ответь ТОЛЬКО одним целым числом от 0 до 100. Без текста, без пояснений, без единиц. "
        "Только число.\n\n"
        "Шкала:\n"
        "0-20: почти нет совпадений\n"
        "21-50: частичное совпадение, не хватает ключевых требований\n"
        "51-75: хорошее совпадение, большинство требований покрыто\n"
        "76-100: сильное совпадение, покрывает почти все требования"
    )


_COMPAT_DESCRIPTION_LIMIT = 4000


def build_compatibility_user_content(
    vacancy_title: str,
    vacancy_skills: list[str],
    vacancy_description: str,
    user_tech_stack: list[str],
    user_work_experience: str,
) -> str:
    """Return the user message for the compatibility scoring request."""
    return (
        f"Вакансия: {vacancy_title}\n"
        f"Требуемые навыки: {', '.join(vacancy_skills)}\n"
        f"Описание (сокращённое): {vacancy_description[:_COMPAT_DESCRIPTION_LIMIT]}\n\n"
        f"Стек кандидата: {', '.join(user_tech_stack)}\n"
        f"Опыт кандидата: {user_work_experience}"
    )


def build_vacancy_analysis_system_prompt(
    user_tech_stack: list[str],
    user_work_experience: str,
) -> str:
    """Return the system prompt for combined vacancy analysis.

    The model analyses the vacancy against the candidate profile and returns a
    structured three-block response: a brief candidate-aware summary, a full
    tech stack extracted from the vacancy, and a compatibility percentage.
    """
    stack_str = ", ".join(user_tech_stack) if user_tech_stack else "не указан"
    exp_str = user_work_experience if user_work_experience else "не указан"
    return (
        "Ты — Senior Technical Recruitment Analyst с 30-летним опытом.\n\n"
        "[ПРОФИЛЬ КАНДИДАТА]\n"
        f"Стек: {stack_str}\n"
        f"Опыт работы: {exp_str}\n\n"
        "Проанализируй предоставленную вакансию и дай ответ СТРОГО в следующем формате "
        "(ничего лишнего, никакого дополнительного текста после последней строки):\n\n"
        "<краткий анализ>\n"
        "[Stack]:<технологии>\n"
        "[Compatibility]:<число>\n\n"
        "[ПРАВИЛА ДЛЯ КАЖДОГО БЛОКА]\n\n"
        "Блок 1 — краткое описание вакансии как предложения (2–4 предложения):\n"
        "- Плюсы: что привлекательного в самой вакансии — интересность проекта или домена, "
        "уровень зарплаты, бонусы и льготы, удалённая работа, возможности роста и обучения.\n"
        "- Минусы: что настораживает в вакансии — низкая или скрытая зарплата, легаси-стек, "
        "завышенные требования, признаки нестабильной компании, отсутствие льгот.\n"
        "- Пиши исключительно про вакансию и компанию как работодателя. "
        "НЕ пиши про совпадение со стеком кандидата — это только для блока [Compatibility].\n"
        "- Конкретно и по делу. Без буллетов и списков. Объём: не более 1000 символов.\n\n"
        "Блок 2 — [Stack]:<значения>:\n"
        "- Перечисли ВСЕ технологии, фреймворки и методологии из вакансии.\n"
        "- Формат строго: [Stack]:React,TypeScript,Docker,SCRUM\n"
        "- Только одна строка.\n\n"
        "Блок 3 — [Compatibility]:<число>:\n"
        "- Одно целое число от 0 до 100, отражающее совместимость кандидата с вакансией.\n"
        "- Формат строго: [Compatibility]:72\n"
        "- Только одна строка."
    )


def build_vacancy_analysis_user_content(
    vacancy_title: str,
    vacancy_skills: list[str],
    vacancy_description: str,
) -> str:
    """Return the user message for the combined vacancy analysis request.

    The full description is passed without truncation so the model can produce
    an accurate summary and extract the complete technology stack.
    """
    return (
        f"Вакансия: {vacancy_title}\n"
        f"Требуемые навыки: {', '.join(vacancy_skills)}\n\n"
        f"Полное описание вакансии:\n{vacancy_description}"
    )


@dataclass(frozen=True)
class WorkExperienceEntry:
    company_name: str
    stack: str


def _quality_rules() -> str:
    return (
        "[ТРЕБОВАНИЯ К КАЧЕСТВУ]\n"
        "- Каждый пункт должен описывать конкретную задачу или зону ответственности, "
        "а не абстрактное достижение.\n"
        "- ЗАПРЕЩЕНО выдумывать цифры, проценты, метрики и статистику. "
        "Не пиши 'сократил на 30%', 'ускорил на 45%', 'до 99.9% аптайма' и подобное.\n"
        "- Ключевые слова должны быть вплетены в текст естественно. "
        "Плохо: 'Оформлял стили с помощью CSS'. "
        "Хорошо: 'Вёрстка адаптивных интерфейсов (HTML, CSS, responsive design)'.\n"
        "- Пиши разнообразно: чередуй структуру фраз, не начинай каждый пункт одинаково.\n"
        "- Пункты должны звучать как реальный опыт специалиста, "
        "а не как шаблонная генерация.\n"
        "- Допускается объединять несколько связанных ключевых слов в одном пункте.\n"
    )


def _format_rules(style: str, language: str) -> str:
    return (
        "[ФОРМАТ]\n"
        "- Каждый пункт начинай с дефиса (-).\n"
        "- Никакого форматирования: без **, *, >, +, номеров.\n"
        f"- Стиль описания: {style}\n"
        f"- Язык: {language}"
    )


def build_key_phrases_prompt(
    resume_title: str,
    main_keywords: list[str],
    secondary_keywords: list[str],
    style: str,
    count: int = 10,
    language: str = "ru",
) -> str:
    main_joined = ", ".join(main_keywords)
    secondary_joined = ", ".join(secondary_keywords)
    count_instruction = (
        f"ненумерованный список из ровно {count} должностных обязанностей, "
        if count > 0
        else "ненумерованный список не более чем из 30 должностных обязанностей, "
    )

    return (
        f"Ты — опытный карьерный консультант. "
        f"Составь для резюме на позицию '{resume_title}' "
        f"{count_instruction}"
        f"который естественно включает ключевые слова из двух групп.\n\n"
        f"Основные ключевые слова (каждое должно появиться хотя бы раз): "
        f"[{main_joined}].\n"
        f"Дополнительные ключевые слова (используй уместные): "
        f"[{secondary_joined}].\n\n"
        f"{_quality_rules()}\n"
        f"{_format_rules(style, language)}"
    )


def build_interview_analysis_system_prompt() -> str:
    """Return the system prompt for analyzing a user's interview performance.

    The model evaluates the candidate's answers to interview questions against
    the vacancy requirements and outputs a structured report identifying weak
    areas and actionable improvement topics.
    """
    return (
        "Ты — опытный технический интервьюер и карьерный консультант с 20-летним опытом.\n\n"
        "[ЗАДАЧА]\n"
        "Проанализируй ответы кандидата на вопросы собеседования с учётом требований вакансии "
        "и уровня опыта. Определи слабые места и области для улучшения.\n\n"
        "[ПРАВИЛА АНАЛИЗА]\n"
        "- Оценивай ответы по следующим критериям: глубина знаний, практический опыт, "
        "понимание технологий, правильность подхода к решению задач.\n"
        "- Учитывай уровень опыта кандидата при оценке — требования к джуну и сеньору разные.\n"
        "- Выявляй конкретные технологии/темы, где ответы были слабыми, неполными или неверными.\n"
        "- Если ответ был хорошим — не включай эту тему в блоки улучшений.\n\n"
        "[ФОРМАТ ОТВЕТА — СТРОГО]\n"
        "Ответ ТОЛЬКО в следующем формате, без дополнительного текста до или после:\n\n"
        "[InterviewSummaryStart]\n"
        "Общее резюме собеседования: что было хорошо, что плохо, общее впечатление "
        "от уровня кандидата относительно вакансии. Конкретно и по делу. "
        "Не более 1500 символов.\n"
        "[InterviewSummaryEnd]\n\n"
        "[ImproveStart]:<название_технологии_или_темы>\n"
        "Конкретное описание того, что именно было плохо в ответах по данной теме: "
        "какие знания отсутствуют, какие концепции не поняты, что нужно изучить. "
        "Не более 800 символов.\n"
        "[ImproveEnd]:<название_технологии_или_темы>\n\n"
        "Повтори блок [ImproveStart]/[ImproveEnd] для каждой слабой области.\n"
        "Если слабых областей нет — после [InterviewSummaryEnd] не добавляй ничего."
    )


def build_interview_analysis_user_content(
    vacancy_title: str,
    vacancy_description: str | None,
    company_name: str | None,
    experience_level: str | None,
    questions_answers: list[dict[str, str]],
    user_improvement_notes: str | None,
) -> str:
    """Return the user message for interview analysis.

    Formats all interview data: vacancy context, Q&A pairs, and optional
    self-assessment notes from the candidate.
    """
    description_block = (
        f"Описание вакансии:\n{vacancy_description}\n\n" if vacancy_description else ""
    )
    company_block = f"Компания: {company_name}\n" if company_name else ""
    experience_block = f"Ожидаемый опыт: {experience_level}\n" if experience_level else ""

    qa_lines = []
    for idx, qa in enumerate(questions_answers, 1):
        qa_lines.append(f"Вопрос {idx}: {qa['question']}")
        qa_lines.append(f"Ответ кандидата: {qa['answer']}\n")
    qa_block = "\n".join(qa_lines)

    notes_block = (
        f"\n[ЗАМЕТКИ КАНДИДАТА О СЛАБЫХ МЕСТАХ]\n{user_improvement_notes}\n"
        if user_improvement_notes
        else ""
    )

    return (
        f"[ВАКАНСИЯ]\n"
        f"Название: {vacancy_title}\n"
        f"{company_block}"
        f"{experience_block}"
        f"{description_block}"
        f"[ВОПРОСЫ И ОТВЕТЫ КАНДИДАТА]\n"
        f"{qa_block}"
        f"{notes_block}"
    )


def build_improvement_flow_system_prompt() -> str:
    """Return the system prompt for generating a step-by-step improvement guide."""
    return (
        "Ты — опытный технический ментор и карьерный консультант.\n\n"
        "[ЗАДАЧА]\n"
        "Составь подробный пошаговый план изучения и улучшения знаний кандидата "
        "по конкретной технологии или теме на основе выявленных слабых мест.\n\n"
        "[ПРАВИЛА]\n"
        "- План должен быть конкретным и практическим, не абстрактным.\n"
        "- Каждый шаг должен содержать: что изучить, как практиковаться, "
        "как проверить свои знания.\n"
        "- Учитывай контекст вакансии — фокусируйся на том, что реально нужно для работы.\n"
        "- Давай конкретные рекомендации: темы для изучения, типы задач для практики, "
        "подходы к закреплению знаний.\n"
        "- Разбей план на логичные этапы от базового к продвинутому.\n"
        "- Объём: 5–10 конкретных шагов.\n\n"
        "[ФОРМАТ]\n"
        "Используй нумерованный список. Каждый пункт начинай с номера и точки. "
        "Никакого дополнительного форматирования (без **, *, >).\n"
        "Пиши на русском языке."
    )


def build_improvement_flow_user_content(
    technology_title: str,
    improvement_summary: str,
    vacancy_title: str,
    vacancy_description: str | None,
) -> str:
    """Return the user message for improvement flow generation."""
    description_block = (
        f"\nКонтекст вакансии:\n{vacancy_description[:3000]}\n" if vacancy_description else ""
    )

    return (
        f"Вакансия: {vacancy_title}{description_block}\n"
        f"Технология/тема для улучшения: {technology_title}\n\n"
        f"Выявленные проблемы в знаниях кандидата:\n{improvement_summary}\n\n"
        f"Составь пошаговый план улучшения знаний по теме '{technology_title}'."
    )


@dataclass(frozen=True)
class AchievementExperienceEntry:
    company_name: str
    stack: str
    user_achievements: str | None
    user_responsibilities: str | None


def build_achievement_generation_prompt(
    experiences: list[AchievementExperienceEntry],
) -> str:
    """Return a prompt for generating resume achievement bullet points per work experience."""
    companies_block_parts = []
    for e in experiences:
        lines = [f"Компания: {e.company_name}", f"Технологии: {e.stack}"]
        if e.user_achievements:
            lines.append(f"Реальные достижения (от пользователя): {e.user_achievements}")
        if e.user_responsibilities:
            lines.append(f"Обязанности и задачи (от пользователя): {e.user_responsibilities}")
        companies_block_parts.append("\n".join(lines))

    companies_block = "\n\n".join(companies_block_parts)

    return (
        "Ты — опытный карьерный консультант, специализирующийся на написании резюме.\n\n"
        "[ЗАДАЧА]\n"
        "Сгенерируй достижения для каждого места работы кандидата. "
        "Достижения должны звучать убедительно, конкретно и профессионально.\n\n"
        "[ДАННЫЕ КАНДИДАТА]\n"
        f"{companies_block}\n\n"
        "[ПРАВИЛА]\n"
        "- Для каждой компании сгенерируй 4-6 пунктов достижений.\n"
        "- Используй реальные достижения и обязанности, предоставленные пользователем, "
        "как основу. Если не предоставлены — придумай реалистичные на основе стека.\n"
        "- ЗАПРЕЩЕНО выдумывать конкретные цифры и проценты. "
        "Пиши 'значительно', 'существенно', 'заметно' вместо 'на X%'.\n"
        "- Пункты должны начинаться с глагола действия.\n"
        "- Органично вплетай технологии из стека.\n\n"
        "[ФОРМАТ ОТВЕТА — СТРОГО]\n"
        "Ответ ТОЛЬКО в следующем формате, без лишнего текста:\n\n"
        "[AchStart]:<название_компании>\n"
        "- пункт 1\n"
        "- пункт 2\n"
        "[AchEnd]:<название_компании>\n\n"
        "Повтори блок [AchStart]/[AchEnd] для каждой компании."
    )


def build_standard_qa_system_prompt() -> str:
    """Return the system prompt for generating interview Q&A answers."""
    return (
        "Ты — опытный карьерный консультант и эксперт по подготовке к собеседованиям.\n\n"
        "[ЗАДАЧА]\n"
        "Составь подготовленные, убедительные ответы на стандартные вопросы собеседования "
        "для конкретного кандидата на основе его опыта работы.\n\n"
        "[ПРАВИЛА]\n"
        "- Ответы должны быть честными, конкретными и адаптированными под опыт кандидата.\n"
        "- Каждый ответ должен демонстрировать профессиональную зрелость.\n"
        "- Используй технологии и достижения из опыта кандидата.\n"
        "- Пиши от первого лица, естественно и профессионально.\n"
        "- Не используй клише и шаблонные фразы.\n\n"
        "[ФОРМАТ ОТВЕТА — СТРОГО]\n"
        "Ответ ТОЛЬКО в следующем формате:\n\n"
        "[QAStart]:<ключ_вопроса>\n"
        "Текст ответа (2-5 предложений).\n"
        "[QAEnd]:<ключ_вопроса>\n\n"
        "Повтори блок для каждого вопроса."
    )


def build_standard_qa_user_content(
    work_experiences: list[WorkExperienceEntry],
    question_keys: list[str],
    question_texts: list[str],
) -> str:
    """Return the user message for standard Q&A generation."""
    exp_block = "\n".join(
        f"  {i + 1}. {e.company_name} — {e.stack}" for i, e in enumerate(work_experiences)
    )
    questions_block = "\n".join(
        f"  {key}: {text}" for key, text in zip(question_keys, question_texts, strict=True)
    )
    return (
        f"[ОПЫТ РАБОТЫ КАНДИДАТА]\n{exp_block}\n\n"
        f"[ВОПРОСЫ ДЛЯ ПОДГОТОВКИ]\n{questions_block}\n\n"
        "Составь развёрнутые ответы на каждый вопрос."
    )


def build_vacancy_summary_system_prompt() -> str:
    """Return the system prompt for generating a vacancy application summary (about-me text)."""
    return (
        "Ты — опытный карьерный консультант, специализирующийся на написании "
        "профессиональных резюме и сопроводительных текстов.\n\n"
        "[ЗАДАЧА]\n"
        "Напиши профессиональный текст 'О себе' для резюме кандидата. "
        "Текст должен быть структурированным, убедительным и ориентированным на работодателя.\n\n"
        "[СТРУКТУРА ТЕКСТА]\n"
        "1. Кто я — представление: специальность, опыт, ключевые технологии и достижения.\n"
        "2. Как достигаю результата — методы и подходы к работе.\n"
        "3. Мои сильные стороны — конкретные достижения и вклад в проекты.\n"
        "4. Для кого буду полезен — тип компаний и задач, где я наиболее эффективен.\n"
        "5. Ограничения — сферы, которые не рассматриваю (если указаны).\n"
        "6. Локация и формат — где живу, готовность к удалёнке/релокации.\n\n"
        "[ПРАВИЛА]\n"
        "- Пиши конкретно, избегай расплывчатых фраз.\n"
        "- Используй эмодзи для структурирования (🔥, ⭐️, ⚠️) — "
        "как в профессиональных LinkedIn-профилях.\n"
        "- ЗАПРЕЩЕНО выдумывать цифры и метрики без подтверждения от кандидата.\n"
        "- Каждый раздел должен быть отдельным абзацем.\n"
        "- Объём: 300-600 слов.\n\n"
        "[ФОРМАТ]\n"
        "Обычный текст без markdown. Только эмодзи для структурирования. "
        "Каждый раздел с новой строки."
    )


def build_vacancy_summary_user_content(
    work_experiences: list[WorkExperienceEntry],
    tech_stack: list[str],
    excluded_industries: str | None,
    location: str | None,
    remote_preference: str | None,
    additional_notes: str | None,
) -> str:
    """Return the user message for vacancy summary generation."""
    exp_block = "\n".join(
        f"  {i + 1}. {e.company_name} — {e.stack}" for i, e in enumerate(work_experiences)
    )
    stack_str = ", ".join(tech_stack) if tech_stack else "не указан"
    parts = [
        f"[ОПЫТ РАБОТЫ]\n{exp_block}",
        f"[ТЕХНОЛОГИЧЕСКИЙ СТЕК]\n{stack_str}",
    ]
    if excluded_industries:
        parts.append(f"[НЕ РАССМАТРИВАЕТ СФЕРЫ]\n{excluded_industries}")
    if location:
        parts.append(f"[ЛОКАЦИЯ]\n{location}")
    if remote_preference:
        parts.append(f"[ПРЕДПОЧТЕНИЯ ПО ФОРМАТУ РАБОТЫ]\n{remote_preference}")
    if additional_notes:
        parts.append(f"[ДОПОЛНИТЕЛЬНО]\n{additional_notes}")
    parts.append("Напиши профессиональный текст 'О себе' на основе этих данных.")
    return "\n\n".join(parts)


def build_preparation_guide_prompt(
    vacancy_title: str,
    vacancy_description: str | None,
    user_tech_stack: list[str],
    user_work_experience: str,
) -> str:
    """Return a prompt for generating an interview preparation guide."""
    stack_str = ", ".join(user_tech_stack) if user_tech_stack else "не указан"
    desc_block = (
        f"\n[ОПИСАНИЕ ВАКАНСИИ]\n{vacancy_description[:2000]}" if vacancy_description else ""
    )
    return (
        "Ты — эксперт по техническим собеседованиям.\n\n"
        "[ЗАДАЧА]\n"
        "Составь подробный пошаговый план подготовки к собеседованию на позицию: "
        f"<{vacancy_title}>.\n\n"
        f"[ТЕХНОЛОГИЧЕСКИЙ СТЕК КАНДИДАТА]\n{stack_str}\n\n"
        f"[ОПЫТ РАБОТЫ КАНДИДАТА]\n{user_work_experience}"
        f"{desc_block}\n\n"
        "[ПРАВИЛА]\n"
        "- Создай 5-8 шагов подготовки.\n"
        "- Каждый шаг должен быть конкретным и практичным.\n"
        "- Учитывай текущий стек кандидата и опыт работы.\n"
        "- Шаги должны логически следовать один за другим.\n\n"
        "[ФОРМАТ ОТВЕТА — СТРОГО]\n"
        "Ответ ТОЛЬКО в следующем формате:\n\n"
        "[PrepStepStart]:1:<название_шага>\n"
        "Содержание шага (2-4 абзаца).\n"
        "[PrepStepEnd]:1:<название_шага>\n\n"
        "[PrepStepStart]:2:<название_шага>\n"
        "Содержание шага.\n"
        "[PrepStepEnd]:2:<название_шага>\n\n"
        "И так далее для каждого шага."
    )


def build_deep_learning_summary_prompt(
    step_title: str,
    step_content: str,
    vacancy_context: str,
) -> str:
    """Return a prompt for generating a deep-dive summary for a prep step."""
    return (
        "Ты — технический ментор и эксперт по собеседованиям.\n\n"
        "[ЗАДАЧА]\n"
        f"Создай углублённый учебный материал по теме: <{step_title}>.\n\n"
        f"[КОНТЕКСТ ВАКАНСИИ]\n{vacancy_context}\n\n"
        f"[БАЗОВЫЙ МАТЕРИАЛ]\n{step_content}\n\n"
        "[ПРАВИЛА]\n"
        "- Углубись значительно глубже базового материала.\n"
        "- Приведи конкретные примеры, антипаттерны, типичные вопросы на интервью.\n"
        "- Используй структуру: 1) Теория 2) Практика 3) Типичные вопросы интервью "
        "4) Красные флаги (чего избегать).\n"
        "- Объём: 400-800 слов.\n\n"
        "Напиши углублённый материал."
    )


def build_preparation_test_prompt(
    step_title: str,
    step_content: str,
    deep_summary: str | None,
) -> str:
    """Return a prompt for generating a multiple-choice test for a prep step."""
    material = (deep_summary or step_content)[:2000]
    return (
        "Ты — эксперт по техническим собеседованиям.\n\n"
        "[ЗАДАЧА]\n"
        f"Создай тест с вопросами на тему: <{step_title}>.\n\n"
        f"[УЧЕБНЫЙ МАТЕРИАЛ]\n{material}\n\n"
        "[ПРАВИЛА]\n"
        "- 3-5 вопросов с вариантами ответов.\n"
        "- 4 варианта ответа на каждый вопрос.\n"
        "- Один правильный ответ, помеченный звёздочкой (*).\n"
        "- Вопросы должны проверять понимание, а не памятование.\n\n"
        "[ФОРМАТ ОТВЕТА — СТРОГО]\n"
        "Ответ ТОЛЬКО в следующем формате:\n\n"
        "[TestStart]\n"
        "[Q]:Текст вопроса\n"
        "[A]:Вариант 1\n"
        "[A]:Вариант 2*\n"
        "[A]:Вариант 3\n"
        "[A]:Вариант 4\n"
        "[TestEnd]\n\n"
        "Символ * обозначает правильный ответ. Повтори блок [Q]/[A] для каждого вопроса."
    )


def build_per_company_key_phrases_prompt(
    resume_title: str,
    main_keywords: list[str],
    secondary_keywords: list[str],
    style: str,
    per_company_count: int,
    language: str,
    work_experiences: list[WorkExperienceEntry],
) -> str:
    main_joined = ", ".join(main_keywords)
    secondary_joined = ", ".join(secondary_keywords)

    companies_block = "\n".join(
        f"  {idx}. {e.company_name} — стек: {e.stack}" for idx, e in enumerate(work_experiences, 1)
    )

    return (
        f"Ты — опытный карьерный консультант. "
        f"Составь для резюме на позицию '{resume_title}' "
        f"ненумерованный список должностных обязанностей, "
        f"который естественно включает ключевые слова из двух групп.\n\n"
        f"Основные ключевые слова (каждое должно появиться хотя бы раз): "
        f"[{main_joined}].\n"
        f"Дополнительные ключевые слова (используй уместные): "
        f"[{secondary_joined}].\n\n"
        f"[ОПЫТ РАБОТЫ КАНДИДАТА]\n"
        f"Кандидат имеет опыт работы в следующих компаниях:\n"
        f"{companies_block}\n\n"
        f"Сгенерируй по {per_company_count} пунктов для каждой компании, "
        f"адаптируя формулировки к указанному стеку компании и используя "
        f"ключевые слова из групп выше.\n"
        f"Выводи результат сгруппировано по компаниям в формате:\n"
        f"Компания: Название компании\n"
        f"- пункт 1\n"
        f"- пункт 2\n\n"
        f"{_quality_rules()}\n"
        f"{_format_rules(style, language)}"
    )
