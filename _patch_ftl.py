from pathlib import Path

en = Path("src/locales/en/LC_MESSAGES/messages.ftl")
ru = Path("src/locales/ru/LC_MESSAGES/messages.ftl")
insert_en = """btn-iv-employer-qa-edit = \u270f\ufe0f Edit answer
btn-iv-employer-qa-list = \U0001f4cb All questions
iv-employer-qa-list-hint = Choose a question below to view, edit, or regenerate the draft answer.
iv-employer-qa-edit-prompt = Send the new answer in one message (plain text). It replaces the current draft.
iv-employer-qa-edit-too-long = Answer is too long. Send a shorter text.
iv-employer-qa-edit-empty = Answer is empty. Send non-blank text or tap Cancel.

"""
insert_ru = """btn-iv-employer-qa-edit = \u270f\ufe0f \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u043e\u0442\u0432\u0435\u0442
btn-iv-employer-qa-list = \U0001f4cb \u0412\u0441\u0435 \u0432\u043e\u043f\u0440\u043e\u0441\u044b
iv-employer-qa-list-hint = \u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0432\u043e\u043f\u0440\u043e\u0441 \u043d\u0438\u0436\u0435, \u0447\u0442\u043e\u0431\u044b \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a, \u0438\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0438\u043b\u0438 \u043f\u0435\u0440\u0435\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043e\u0442\u0432\u0435\u0442.
iv-employer-qa-edit-prompt = \u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u043d\u043e\u0432\u044b\u0439 \u043e\u0442\u0432\u0435\u0442 \u043e\u0434\u043d\u0438\u043c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435\u043c (\u043e\u0431\u044b\u0447\u043d\u044b\u0439 \u0442\u0435\u043a\u0441\u0442). \u041e\u043d \u0437\u0430\u043c\u0435\u043d\u0438\u0442 \u0442\u0435\u043a\u0443\u0449\u0438\u0439 \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a.
iv-employer-qa-edit-too-long = \u041e\u0442\u0432\u0435\u0442 \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u0434\u043b\u0438\u043d\u043d\u044b\u0439. \u0421\u043e\u043a\u0440\u0430\u0442\u0438\u0442\u0435 \u0442\u0435\u043a\u0441\u0442.
iv-employer-qa-edit-empty = \u041f\u0443\u0441\u0442\u043e\u0439 \u043e\u0442\u0432\u0435\u0442. \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0442\u0435\u043a\u0441\u0442 \u0438\u043b\u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u00ab\u041e\u0442\u043c\u0435\u043d\u0430\u00bb.

"""
needle_en = (
    "iv-employer-qa-too-short = Message is too short. Send the full employer question.\n\n"
)
needle_ru = (
    "iv-employer-qa-too-short = Сообщение слишком короткое. Введите полный вопрос работодателя.\n\n"
)
for path, ins, needle in [(en, insert_en, needle_en), (ru, insert_ru, needle_ru)]:
    t = path.read_text(encoding="utf-8")
    if ins.split("=", 1)[0].strip() in t:
        print(f"skip {path} (already patched)")
        continue
    if needle not in t:
        raise SystemExit(f"missing needle in {path}")
    path.write_text(t.replace(needle, needle + ins, 1), encoding="utf-8")
    print(f"patched {path}")
