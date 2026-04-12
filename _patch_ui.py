from pathlib import Path

# format_vacancy_header
svc = Path("src/bot/modules/interviews/services.py")
t = svc.read_text(encoding="utf-8")
old = """) -> str:
    lines = [f\"<b>\U0001f3e2 {vacancy_title}</b>\"]
    if company_name:
        lines.append(f\"Компания: {company_name}\")
    if experience_level:
        lines.append(f\"Опыт: {experience_level}\")
    if hh_vacancy_url:
        lines.append(f'<a href=\"{hh_vacancy_url}\">Открыть на HH.ru</a>')
    return \"\\n\".join(lines)
"""
new = """) -> str:
    title_esc = html.escape(vacancy_title or \"\")
    lines = [f\"<b>\U0001f3e2 {title_esc}</b>\"]
    if company_name:
        lines.append(f\"Компания: {html.escape(company_name)}\")
    if experience_level:
        lines.append(f\"Опыт: {html.escape(experience_level)}\")
    if hh_vacancy_url:
        url = hh_vacancy_url.replace('\"', \"%22\")
        lines.append(f'<a href=\"{url}\">Открыть на HH.ru</a>')
    return \"\\n\".join(lines)
"""
if old not in t:
    raise SystemExit("services block not found")
svc.write_text(t.replace(old, new, 1), encoding="utf-8")

# interview_list_keyboard loop
kb = Path("src/bot/modules/interviews/keyboards.py")
t2 = kb.read_text(encoding="utf-8")
old2 = """    for interview in interviews:
        date_str = interview.created_at.strftime(\"%m/%d\")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f\"\U0001f4dd {interview.vacancy_title} ({date_str})\",
                    callback_data=InterviewCallback(
                        action=\"detail\", interview_id=interview.id
                    ).pack(),
                )
            ]
        )
"""
new2 = """    for interview in interviews:
        date_str = interview.created_at.strftime(\"%d.%m.%Y\")
        co = (interview.company_name or \"\").strip()
        title = (interview.vacancy_title or \"\").strip()
        prefix = f\"{co[:22]}{'\u2026' if len(co) > 22 else ''} · \" if co else \"\"
        label = f\"\U0001f4dd {prefix}{title} ({date_str})\"
        if len(label.encode(\"utf-8\")) > 62:
            label = label.encode(\"utf-8\")[:59].decode(\"utf-8\", errors=\"ignore\") + \"\u2026\"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=InterviewCallback(
                        action=\"detail\", interview_id=interview.id
                    ).pack(),
                )
            ]
        )
"""
if old2 not in t2:
    raise SystemExit("keyboard block not found")
kb.write_text(t2.replace(old2, new2, 1), encoding="utf-8")
print("patched")
