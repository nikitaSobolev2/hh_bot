# ── Welcome ──────────────────────────────────────────────
welcome =
    <b>HH Bot</b> — ваш парсер вакансий HeadHunter

    Анализируйте вакансии, извлекайте ключевые слова и создавайте лучшие резюме.

# ── Main menu buttons ────────────────────────────────────
btn-new-parsing = 🔍 Новый парсинг
btn-my-parsings = 📋 Мои парсинги
btn-profile = 👤 Профиль
btn-settings = ⚙️ Настройки
btn-admin = 🛠 Админ панель
btn-back = ◀️ Назад
btn-back-menu = ◀️ В меню
btn-my-interviews = 🎤 Мои собеседования
btn-autoparse = 🤖 Автопарсинг
btn-work-experience = 💼 Опыт работы
btn-achievements = 🏆 Достижения
btn-interview-qa = 💬 Вопросы собеседования
btn-vacancy-summary = 📄 Резюме "О себе"
btn-resume = 📋 Генератор резюме
btn-support-user = 🆘 Поддержка
btn-skip = ⏩ Пропустить
btn-continue = ▶️ Продолжить
btn-cancel = ✖️ Отмена
btn-add-company = ➕ Добавить компанию
btn-remove = ❌ Удалить
btn-yes = ✅ Да
btn-no = ❌ Нет
btn-type-manually = ✏️ Ввести вручную

# ── Profile ──────────────────────────────────────────────
profile-title = <b>👤 Профиль</b>
profile-name = <b>Имя:</b> { $first_name } { $last_name }
profile-username = <b>Имя пользователя:</b> @{ $username }
profile-role = <b>Роль:</b> { $role }
profile-balance = <b>Баланс:</b> { $balance }
profile-language = <b>Язык:</b> { $language }
profile-joined = <b>Дата регистрации:</b> { $date }

btn-stats = 📊 Статистика
btn-referral = 🔗 Реферальная ссылка

stats-title = <b>📊 Статистика</b>
stats-total-parsings = Всего парсингов: { $count }
stats-blacklisted = Активных вакансий в чёрном списке: { $count }

referral-title = <b>🔗 Реферальная ссылка</b>
referral-share = Поделитесь этой ссылкой, чтобы пригласить друзей:
referral-code = Ваш реферальный код: <code>{ $code }</code>

# ── Settings ─────────────────────────────────────────────
settings-title = <b>⚙️ Настройки</b>
settings-subtitle = Управляйте своими предпочтениями.

btn-language = 🌐 Язык
btn-clear-blacklist = 🗑 Очистить чёрный список
btn-notifications = 🔔 Уведомления
btn-topup = 💰 Пополнить баланс
btn-delete-data = ⚠️ Удалить мои данные

language-title = <b>🌐 Язык</b>
language-subtitle = Выберите язык:
language-set = Язык установлен: <b>{ $language }</b>

blacklist-cleared = Очищено <b>{ $count }</b> записей из чёрного списка.
blacklist-cleared-ctx = Очищено <b>{ $count }</b> записей для <b>{ $context }</b>.
blacklist-empty =
    <b>🗑 Чёрный список</b>

    Активных записей нет.
blacklist-management-title = <b>🗑 Управление чёрным списком</b>
blacklist-vacancies = { $count } вакансий

notifications-title = <b>🔔 Уведомления</b>
notifications-soon = Скоро.

topup-title = <b>💰 Пополнение баланса</b>
topup-soon = Платёжные методы скоро.

delete-data-title = <b>⚠️ Удаление данных</b>
delete-data-warning = Эта функция безвозвратно удалит все ваши данные. Детали реализации будут уточнены.

btn-clear-all = 🗑 Очистить всё
btn-clear-context = 🗑 Очистить: { $context }

# ── Parsing flow ─────────────────────────────────────────
parsing-new-title = <b>🔍 Новый парсинг</b>
parsing-enter-title =
    Введите название вакансии для вашего резюме
    (например, Frontend Developer, Маркетолог):
parsing-title-empty = Название не может быть пустым. Попробуйте снова:
parsing-step2 =
    <b>Шаг 2/4</b>

    Введите URL страницы поиска HH.ru
    (например, <code>https://hh.ru/search/vacancy?text=Frontend</code>):
parsing-invalid-url =
    Введите корректный URL HH.ru
    (например, <code>https://hh.ru/search/vacancy?text=Python</code>)
parsing-step3 =
    <b>Шаг 3/4</b>

    Введите ключевое слово для фильтрации заголовков вакансий
    ("<code>|</code>" = ИЛИ, "<code>,</code>" = И)
    Пример: <code>frontend|backend,fullstack</code>

    Отправьте <code>-</code> чтобы пропустить фильтрацию:
parsing-step4 =
    <b>Шаг 4/4</b>

    Сколько вакансий обработать?
    (например, 30):
parsing-positive-number = Введите положительное число:
parsing-max-200 = Максимум 200 вакансий. Введите число поменьше:
parsing-max-50 = Максимум 50 вакансий. Введите число поменьше:
parsing-enter-url = Введите URL страницы поиска HH.ru:
parsing-enter-keyword = Введите ключевое слово для фильтрации (или оставьте пустым):
parsing-enter-count = Сколько вакансий обработать?
parsing-started = Парсинг запущен! Ожидайте результатов.
parsing-empty =
    <b>📋 Мои парсинги</b>

    Парсингов пока нет. Начните новый!
parsing-list-title = <b>📋 Мои парсинги</b>

parsing-blacklist-check =
    <b>⚠️ Проверка чёрного списка</b>

    У вас <b>{ $count }</b> вакансий в чёрном списке
    для <b>{ $title }</b>.

    Включить ранее обработанные вакансии?

parsing-not-found = Не найдено

parsing-retry-count-prompt =
    <b>🔄 Повтор парсинга</b>

    Сколько вакансий обработать?
    (по умолчанию: { $default })

    Введите число или нажмите кнопку ниже:

parsing-restarted =
    <b>🔄 Парсинг перезапущен!</b>

    <b>Название:</b> { $title }
    <b>Цель:</b> { $count } вакансий
    <b>Фильтр:</b> { $filter }

    Новый парсинг #{ $new_id } запущен.
    Вы получите уведомление, когда результаты будут готовы.

parsing-no-results = Результаты ещё недоступны
parsing-truncated = <i>...обрезано. Скачайте полный отчёт.</i>
parsing-file-sent = Файл отправлен

# ── Parsing detail ───────────────────────────────────────
detail-status = <b>Статус:</b> { $status }
detail-filter-link = <b>Ссылка на фильтр:</b> <a href='{ $link }'>Ссылка</a>
detail-processed = <b>Обработано:</b> { $processed }/{ $total }
detail-filter = <b>Фильтр:</b> { $filter }
detail-filter-none = нет
detail-created = <b>Создано:</b> { $date }
detail-completed = <b>Завершено:</b> { $date }

# ── Parsing confirmation ────────────────────────────────
parsing-confirm =
    <b>🚀 Парсинг запущен!</b>

    <b>Название:</b> { $title }
    <b>Цель:</b> { $count } вакансий
    <b>Фильтр:</b> { $filter }
    <b>Чёрный список:</b> { $blacklist }

    Вы получите уведомление, когда результаты будут готовы.
parsing-confirm-include-all = включая все
parsing-confirm-skip-bl = пропуская из чёрного списка
parsing-confirm-compat = Проверка совместимости: ✅ включена (порог: { $threshold }%)

# ── Parsing compat check ─────────────────────────────────
parsing-compat-check-prompt =
    <b>🎯 Проверка совместимости</b>

    Запустить AI-проверку совместимости вакансий с вашим профилем?
    Вакансии ниже порогового значения будут отфильтрованы.

parsing-retry-compat-prompt =
    <b>🎯 Проверка совместимости</b>

    Запустить AI-проверку совместимости для этого повтора?
    Вакансии ниже порогового значения будут отфильтрованы.

parsing-compat-threshold-prompt =
    Введите минимальный порог совместимости (1–100).

    Будут включены только вакансии с оценкой ≥ этого значения.

parsing-compat-threshold-invalid = Введите целое число от 1 до 100.

# ── Parsing completed (worker notification) ──────────────
parsing-completed =
    <b>✅ Парсинг завершён!</b>

    Ваш парсинг #{ $id } готов.
    Выберите способ просмотра результатов:

# ── Parsing buttons ──────────────────────────────────────
parsing-btn-delete = 🗑 Удалить
parsing-deleted = Парсинг удалён из вашего списка.
btn-view-message = 💬 Показать сообщением
btn-download-md = 📄 Скачать .md
btn-download-txt = 📝 Скачать .txt
btn-generate-keyphrases = ✨ Генерация ключевых фраз (AI)
btn-cancel = ❌ Отмена
btn-skip-count = ⏭ Пропустить (до 30)
btn-skip-blacklisted = ✅ Пропустить из чёрного списка
btn-include-all = 🔄 Включить все
btn-try-again = 🔄 Попробовать снова
btn-use-default = ✓ По умолчанию ({ $count })
btn-compat-yes = ✅ Да
btn-compat-skip = ⏭ Пропустить

# ── Pagination ───────────────────────────────────────────
btn-prev = ◀️ Назад
btn-next = Далее ▶️

# ── Key phrases ──────────────────────────────────────────
keyphrase-title = <b>✨ Генерация ключевых фраз</b>
keyphrase-count-prompt =
    Сколько фраз сгенерировать? (1-30)
    Или нажмите «Пропустить» для генерации до 30:
keyphrase-select-lang = Выберите язык вывода:
keyphrase-enter-number = Введите число от 1 до 30:
keyphrase-max-30 = Максимум 30 фраз. Введите число поменьше:
keyphrase-max-8 = Максимум 8 фраз на компанию. Введите число поменьше:
keyphrase-per-company-count =
    Сколько фраз сгенерировать на каждую компанию? (1-8):
keyphrase-select-style = Выберите стиль:
parsing-enter-lang-manual = Введите код языка (например ru, en, de):
parsing-enter-style-manual = Введите ключ стиля (например formal, results, brief):
keyphrase-no-keywords = Нет ключевых слов. Сначала запустите парсинг.
keyphrase-generating =
    ⏳ Генерация ключевых фраз с помощью AI...
    Результат появится в ближайшее время.
keyphrase-header = <b>✨ Ключевые фразы для { $title }</b>
keyphrase-style-label = Стиль: { $style } | { $lang }

# ── Work experience ─────────────────────────────────────
work-exp-prompt =
    Укажите предыдущий опыт работы (компании и стек).
    Это поможет создать более релевантные фразы.
work-exp-enter-name = Введите название компании:
work-exp-enter-stack =
    Введите стек технологий для <b>{ $company }</b>
    (через запятую, например: Python, Django, PostgreSQL):
work-exp-name-invalid = Название компании не может быть пустым (макс. 255 символов).
work-exp-title-invalid = Должность не может превышать 255 символов.
work-exp-stack-invalid = Стек технологий не может быть пустым.
work-exp-max-reached = Максимум 6 компаний. Удалите одну, чтобы добавить новую.
work-exp-not-found = Запись об опыте работы не найдена.
work-exp-enter-title =
    Введите вашу должность в этой компании
    (например: Backend Developer, Senior Engineer) или пропустите:
work-exp-enter-period =
    Укажите период работы
    (например: 2020-2023, 3 года) или пропустите:
work-exp-enter-achievements-edit = Введите новые достижения (или выберите вариант ниже):
work-exp-enter-duties-edit = Введите новые обязанности (или выберите вариант ниже):
we-edit-enter-stack = Введите новый стек технологий (через запятую):
we-label-achievements = Достижения
we-label-duties = Обязанности
we-not-set = Не указано
we-deleted = ✅ Запись удалена
we-btn-edit-company-name = ✏️ Название компании
we-btn-edit-title = 📋 Должность
we-btn-edit-period = 📅 Период работы
we-btn-edit-stack = 🛠 Стек технологий
we-btn-edit-achievements = 🏆 Достижения
we-btn-edit-duties = 🔧 Обязанности
we-btn-delete = 🗑 Удалить
work-exp-enter-achievements =
    🏆 <b>{ $company }</b> — достижения

    Опишите ваши реальные достижения (или выберите вариант ниже):
work-exp-enter-duties =
    🔧 <b>{ $company }</b> — обязанности

    Опишите ваши рабочие обязанности и задачи (или выберите вариант ниже):
work-exp-generating = ⏳ Генерирую...
work-exp-generated-achievements =
    ✅ Сгенерированные достижения:

    { $text }
work-exp-generated-duties =
    ✅ Сгенерированные обязанности:

    { $text }
work-exp-generation-failed = Не удалось сгенерировать. Введите вручную или пропустите.
work-exp-ai-result-achievements =
    ✅ Сгенерированные достижения:

    { $text }
work-exp-ai-result-duties =
    ✅ Сгенерированные обязанности:

    { $text }
work-exp-ai-generation-done = ✅ Готово! Нажмите, чтобы посмотреть результат.
we-btn-accept-draft = ✅ Использовать
we-btn-regenerate = 🔄 Попробовать снова
we-btn-view-result = 👁 Посмотреть результат
btn-add-company = ➕ Добавить компанию
btn-remove = Удалить
btn-skip = ⏭ Пропустить
btn-continue = ▶️ Продолжить
btn-generate-ai = 🤖 Сгенерировать с AI

# ── Key phrases styles ──────────────────────────────────
style-formal = формальный / деловой
style-results = результато-ориентированный (метрики и достижения)
style-brief = лаконичный / телеграфный
style-detailed = описательный / подробный
style-expert = экспертный / профессиональный

# ── Format selection ─────────────────────────────────────
format-select = Выберите формат вывода:
btn-format-message = 💬 Показать сообщением
btn-format-md = 📄 Скачать .md
btn-format-txt = 📝 Скачать .txt

# ── Admin panel ──────────────────────────────────────────
admin-title = <b>🛠 Админ панель</b>
admin-subtitle = Управление пользователями, настройками и задачами.
admin-users-title = <b>👥 Пользователи</b>
admin-settings-title = <b>⚙️ Настройки приложения</b>
admin-support-title = <b>📬 Входящие сообщения</b>
admin-support-empty = Нет сообщений.
admin-support-description = Пользователи могут отправлять сообщения в поддержку, которые будут отображаться здесь.
admin-access-denied = Доступ запрещён

btn-users = 👥 Пользователи
btn-app-settings = ⚙️ Настройки приложения
btn-support = 📬 Входящие

admin-users-empty =
    <b>👥 Пользователи</b>

    Пользователи не найдены.
admin-users-page = <b>👥 Пользователи</b> (страница { $page })
admin-search-prompt =
    <b>🔍 Поиск пользователей</b>

    Введите имя пользователя, имя или Telegram ID:
admin-user-not-found = Пользователь не найден
admin-user-banned = Пользователь заблокирован
admin-user-unbanned = Пользователь разблокирован
admin-balance-prompt =
    <b>💰 Изменение баланса</b>

    Введите сумму (положительная для начисления, отрицательная для списания):
admin-send-message-prompt =
    <b>✉️ Отправка сообщения</b>

    Введите сообщение для отправки пользователю:
admin-search-empty = Пользователи не найдены по запросу <b>{ $query }</b>
admin-search-results = <b>🔍 Результаты для «{ $query }»</b>
admin-invalid-amount = Некорректная сумма. Введите число.
admin-balance-adjusted = Баланс изменён на <b>{ $amount }</b> для пользователя #{ $user_id }.
admin-message-from-admin = <b>📢 Сообщение от администратора</b>
admin-message-sent = Сообщение отправлено.
admin-message-failed = Не удалось отправить сообщение.
admin-setting-select =
    <b>⚙️ Настройки приложения</b>

    Выберите настройку для просмотра или редактирования:
admin-setting-current =
    <b>⚙️ { $label }</b>

    Текущее значение: <code>{ $value }</code>
admin-setting-set = Установлено: { $value }
admin-setting-edit =
    <b>✏️ Редактирование { $label }</b>

    Введите новое значение:
admin-setting-updated = <b>⚙️ { $label }</b> обновлено.
admin-setting-unknown = Неизвестная настройка
admin-user-not-found-short = Пользователь не найден.
admin-balance-description = Изменено администратором #{ $admin_id }
admin-not-set = (не задано)

# ── Admin buttons ────────────────────────────────────────
btn-search = 🔍 Поиск
btn-unban = ✅ Разблокировать
btn-ban = 🚫 Заблокировать
btn-adjust-balance = 💰 Изменить баланс
btn-send-message = ✉️ Отправить сообщение
btn-back-users = ◀️ К пользователям
btn-back-settings = ◀️ К настройкам
btn-toggle = 🔄 Переключить
btn-edit = ✏️ Редактировать

# ── Admin user detail ────────────────────────────────────
admin-user-detail-title = <b>👤 Пользователь #{ $id }</b>
admin-user-detail-name = <b>Имя:</b> { $name }
admin-user-detail-username = <b>Имя пользователя:</b> @{ $username }
admin-user-detail-telegram-id = <b>Telegram ID:</b> <code>{ $telegram_id }</code>
admin-user-detail-role = <b>Роль:</b> { $role }
admin-user-detail-balance = <b>Баланс:</b> { $balance }
admin-user-detail-banned = <b>Заблокирован:</b> { $banned }
admin-user-detail-language = <b>Язык:</b> { $language }
admin-user-detail-joined = <b>Регистрация:</b> { $date }
yes = Да
no = Нет

# ── Auth / System ────────────────────────────────────────
account-suspended = Ваш аккаунт был заблокирован.
access-denied = Доступ запрещён

# ── Report generator ────────────────────────────────────
report-msg-title = <b>📊 Результаты парсинга: { $title }</b>
report-vacancies-processed = Обработано вакансий: { $count }
report-top-keywords = <b>Топ-{ $n } ключевых слов (AI):</b>
report-top-skills = <b>Топ-{ $n } навыков (теги):</b>
report-key-phrases = <b>Ключевые фразы ({ $style }):</b>
report-md-title = # Отчёт парсинга: { $title }
report-md-date = **Дата:** { $date } UTC
report-md-vacancies = **Обработано вакансий:** { $count }
report-md-keywords-header = ## Топ-{ $n } ключевых слов (AI)
report-md-skills-header = ## Топ-{ $n } навыков (теги)
report-md-keyphrases-header = ## Ключевые фразы
report-md-style = **Стиль:** { $style }
report-txt-title = ОТЧЁТ ПАРСИНГА: { $title }
report-txt-date = Дата: { $date } UTC
report-txt-vacancies = Обработано вакансий: { $count }
report-txt-keywords-header = ТОП-{ $n } КЛЮЧЕВЫХ СЛОВ (AI)
report-txt-skills-header = ТОП-{ $n } НАВЫКОВ (ТЕГИ)
report-txt-keyphrases-header = КЛЮЧЕВЫЕ ФРАЗЫ
report-txt-style = Стиль: { $style }
report-md-keyword-col = Ключевое слово
report-md-skill-col = Навык
report-md-count-col = Кол-во

# ── Support ─────────────────────────────────────────────────
btn-support-user = 🎫 Поддержка
btn-new-ticket = ➕ Новый тикет
btn-back-tickets = ◀️ К тикетам
btn-enter-conversation = 💬 Войти в чат
btn-skip-attachments = ⏭ Пропустить
btn-done-attachments = ✅ Готово
btn-quit-conversation = 🚪 Выйти из чата
btn-close-ticket = 🔒 Закрыть тикет
btn-close-ticket-admin = 🔒 Закрыть тикет
btn-take-into-work = 📌 Взять в работу
btn-view-profile = 👤 Профиль пользователя
btn-check-companies = 📋 Компании
btn-check-tickets = 🎫 Тикеты
btn-check-notifications = 🔔 Уведомления
btn-message-history = 📜 История сообщений
btn-filter-all = Все
btn-filter-new = Новые
btn-filter-progress = В работе
btn-filter-closed = Закрытые
btn-status-valid = ✅ Валидный
btn-status-invalid = ❌ Невалидный
btn-status-bug = 🐛 Баг

support-title = <b>🎫 Поддержка</b>
support-subtitle = Ваши тикеты в поддержку.
support-empty = Тикетов пока нет. Создайте новый!
support-ticket-detail =
    <b>🎫 Тикет #{ $id }</b>

    <b>Тема:</b> { $title }
    <b>Статус:</b> { $status }
    <b>Создан:</b> { $date }
support-ticket-status-new = 🆕 Новый
support-ticket-status-progress = 🔄 В работе
support-ticket-status-closed = ✅ Закрыт

support-enter-title =
    <b>🎫 Новый тикет</b>

    Введите тему тикета:
support-enter-description =
    <b>Тема:</b> { $title }

    Теперь опишите вашу проблему подробно:
support-enter-attachments =
    Прикрепите файлы (фото: webp/png/jpg/jpeg, txt, mp4)
    или нажмите «Пропустить» / «Готово»:
support-session-expired = ⚠️ Сессия истекла. Пожалуйста, создайте тикет заново.
support-title-empty = Тема не может быть пустой. Попробуйте снова:
support-desc-empty = Описание не может быть пустым. Попробуйте снова:
support-attachment-saved = ✅ Файл прикреплён ({ $count })
support-attachment-invalid = ❌ Недопустимый тип файла. Разрешены: фото (webp/png/jpg/jpeg), txt, mp4.
support-ticket-created =
    <b>✅ Тикет #{ $id } создан!</b>

    Вы в режиме чата. Отправляйте сообщения — они будут переданы в поддержку.
support-conversation-entered =
    <b>💬 Режим чата — Тикет #{ $id }</b>

    Отправляйте сообщения. Они будут переданы в поддержку.
support-conversation-left = Вы вышли из режима чата.
support-ticket-closed-user = <b>🔒 Тикет #{ $id } закрыт.</b>
support-ticket-closed-admin =
    <b>🔒 Тикет #{ $id } закрыт</b>

    <b>Результат:</b> { $result }
    <b>Статус:</b> { $status }
support-ticket-already-closed = Тикет уже закрыт.
support-message-saved = 💬 Сообщение сохранено.
support-no-admin = Администратор ещё не взял тикет. Сообщение сохранено и будет доставлено позже.

support-channel-new-ticket = 🆕 <b>Новый тикет в поддержку</b>
support-ticket-title-label = Тема
support-ticket-desc-label = Описание
support-ticket-author = Автор
support-ticket-id-label = Тикет ID

support-admin-reply = Поддержка
support-user-label = Пользователь
support-admin-label = Администратор
support-user-profile = Профиль пользователя
support-blacklist-count = Записей в чёрном списке
support-referral-code = Реферальный код
support-referred-by = Приведён пользователем
support-ban-history = История банов
support-no-messages = Нет сообщений в этом тикете.

support-taken =
    <b>📌 Тикет #{ $id } взят в работу</b>

    <b>Тема:</b> { $title }
    <b>Описание:</b>
    { $description }

    <b>Статус:</b> 🔄 В работе
support-taken-popup = Тикет #{ $id } взят в работу
support-already-taken = Тикет уже взят в работу.
support-close-enter-result = Введите результат / комментарий к закрытию тикета:
support-close-select-status = Выберите статус закрытия:
support-ban-enter-period =
    Введите срок бана (например: 1d, 7d, 30d, 1h)
    или <code>0</code> для перманентного:
support-ban-enter-reason = Введите причину бана:
support-ban-applied =
    <b>🚫 Пользователь заблокирован</b>

    <b>Срок:</b> { $period }
    <b>Причина:</b> { $reason }
support-ban-invalid-period = Некорректный формат. Используйте: 1d, 7d, 30d, 1h или 0.
support-ban-cancelled = ❌ Бан отменён.
support-close-cancelled = ❌ Закрытие отменено.
support-ban-started-channel = 🚫 Админ начал процесс бана для пользователя.
support-close-started-channel = 🔒 Админ начал закрытие тикета.
support-notifications-soon = 🔔 Уведомления — будет реализовано позже.
support-companies-empty = У пользователя нет компаний.
support-tickets-empty = У пользователя нет тикетов.
support-history-sent = 📜 Отправлено { $count } сообщений.

support-inbox-title = <b>📬 Входящие тикеты</b>
support-inbox-empty = Нет тикетов.
support-search-prompt =
    <b>🔍 Поиск тикетов</b>

    Введите текст для поиска по теме или описанию:
support-search-results = <b>🔍 Результаты для «{ $query }»</b>
support-search-empty = Тикеты не найдены по запросу <b>{ $query }</b>

support-ticket-closed-notify-user =
    <b>🔒 Ваш тикет #{ $id } был закрыт администратором.</b>

    <b>Результат:</b> { $result }
    <b>Статус:</b> { $status }
support-ticket-closed-notify-admin =
    <b>🔒 Тикет #{ $id } был закрыт пользователем.</b>
support-unseen-delivered = 📬 Доставлено { $count } непрочитанных сообщений.

# ── Autoparse ──────────────────────────────────────────────────
btn-autoparse = 🔄 Автопарсинг
autoparse-hub-title = Автопарсинг вакансий
autoparse-hub-subtitle = Создавайте автоматические парсинг-компании для отслеживания новых вакансий.
autoparse-create-new = ➕ Создать новую компанию
autoparse-list-title = 📋 Мои автопарсинги
autoparse-select-template = Выберите шаблон из ваших парсинг-компаний или пропустите:
autoparse-skip-template = ⏭️ Пропустить (ввести вручную)
autoparse-enter-title = Введите название вакансии:
autoparse-enter-url = Введите URL фильтра HH.ru:
autoparse-enter-keywords = Введите ключевые слова для поиска в заголовке:
autoparse-enter-skills = Введите навыки через запятую (React, skill2, ...):
autoparse-created-success = ✅ Автопарсинг-компания #{ $id } успешно создана!
autoparse-empty-list = У вас пока нет автопарсинг-компаний.
autoparse-status-enabled = Вкл
autoparse-status-disabled = Выкл
autoparse-detail-title = Детали автопарсинга
autoparse-detail-status = Статус
autoparse-detail-url = URL
autoparse-detail-keywords = Ключевые слова
autoparse-detail-skills = Навыки
autoparse-detail-metrics = Метрики
autoparse-detail-runs = Запусков
autoparse-detail-vacancies = Вакансий
autoparse-detail-last-run = Последний запуск
autoparse-run-now = ▶️ Запустить сейчас
autoparse-run-started = ✅ Парсинг запущен!
autoparse-run-finished = ✅ Парсинг завершён! Найдено { $count } { $count ->
    [one] новая вакансия
    [few] новые вакансии
   *[other] новых вакансий
  }.
autoparse-run-finished-empty = ✅ Парсинг завершён. Новых вакансий не найдено.
autoparse-run-already-running = ⏳ Парсинг уже выполняется или был недавно завершён.
autoparse-show-now = 📨 Показать новые вакансии сейчас
autoparse-delivering-now = 📨 Отправляю новые вакансии...
autoparse-not-found = Компания не найдена.
autoparse-toggle-enabled = ✅ Автопарсинг включён
autoparse-toggle-disabled = ⏸️ Автопарсинг выключен
autoparse-deleted = 🗑️ Автопарсинг-компания удалена.
autoparse-confirm-delete = ❌ Удалить
autoparse-download-title = 📥 Скачать вакансии
autoparse-download-links = 🔗 Только ссылки (.txt)
autoparse-download-summary = 📊 Сводка (.txt)
autoparse-download-full = 📄 Полная информация (.md)
autoparse-settings-title = ⚙️ Настройки автопарсинга
autoparse-settings-work-exp = 💼 Опыт работы
autoparse-settings-send-time = 🕐 Время отправки
autoparse-settings-tech-stack = 🛠️ Стек технологий
autoparse-settings-stack-auto = авто из опыта работы
autoparse-settings-saved = ✅ Настройки сохранены.
autoparse-enter-work-exp = Опишите ваш опыт работы (должность, годы, домены):
autoparse-enter-send-time = Введите время отправки результатов (формат ЧЧ:ММ):
autoparse-enter-tech-stack = Введите технологии через запятую (Python, React, Docker, ...):
autoparse-compatibility-label = Совместимость
autoparse-compatibility-na-hint = Добавьте опыт и стек в настройках автопарсинга для расчёта совместимости.
autoparse-settings-min-compat = 🎯 Мин. совместимость
autoparse-enter-min-compat = Введите минимальный процент совместимости (0–100):
autoparse-min-compat-invalid = Введите целое число от 0 до 100.
autoparse-delivery-header = 📥 <b>{ $title }</b> — { $count } новых вакансий

# ── Vacancy Feed ──────────────────────────────────────────
feed-stats-count = 🆕 { $count } новых вакансий
feed-stats-avg-compat = 📊 Средняя совместимость: { $avg }%
feed-stats-hint = Нажмите кнопку ниже, чтобы начать просмотр.
feed-btn-start = ▶️ Начать просмотр
feed-vacancy-progress = [{ $current } / { $total }]
feed-btn-open = 🔗 Открыть на HH.ru
feed-btn-like = 👍 Нравится
feed-btn-dislike = 👎 Не нравится
feed-btn-show-later = 🔄 Показать позже
feed-btn-stop = ⏹ Остановить
feed-results-header = 📊 Результаты просмотра
feed-results-seen = Просмотрено: { $seen } из { $total }
feed-results-liked = 👍 Понравилось: { $liked }
feed-results-disliked = 👎 Не понравилось: { $disliked }
feed-results-avg-liked-compat = 📊 Средняя совместимость понравившихся: { $avg }%
feed-session-not-found = Сессия просмотра не найдена или уже завершена.
btn-confirm = ✅ Подтвердить
btn-timezone = 🌍 Часовой пояс
settings-timezone-current = Текущий часовой пояс: { $tz }
settings-timezone-select = Выберите ваш часовой пояс:
settings-timezone-search = Введите название города или региона для поиска:
settings-timezone-set = Часовой пояс установлен: { $tz }
settings-timezone-no-results = Часовые пояса не найдены по вашему запросу. Попробуйте снова.
btn-tz-search = 🔍 Поиск

# ── My Interviews ─────────────────────────────────────────
btn-my-interviews = 🎤 Мои собеседования
btn-cancel = ❌ Отмена

iv-list-title = <b>🎤 Мои собеседования</b>

iv-list-empty =
    <b>🎤 Мои собеседования</b>

    У вас пока нет записей о собеседованиях.
    Нажмите «Добавить», чтобы начать.

btn-iv-add-new = ➕ Добавить собеседование

iv-fsm-source-choice =
    <b>🎤 Новое собеседование</b>

    Это было собеседование по вакансии с HH.ru?

btn-iv-source-hh = 🔗 Да, вакансия с HH.ru
btn-iv-source-manual = ✏️ Нет, ввести вручную

iv-fsm-enter-hh-link =
    Введите ссылку на вакансию HH.ru:
    (например: https://hh.ru/vacancy/12345678)

iv-fsm-parsing-hh = ⏳ Загружаю данные вакансии с HH.ru...
iv-fsm-hh-parsed = ✅ Вакансия загружена:
iv-parsed-company = Компания: { $value }
iv-parsed-experience = Опыт: { $value }
iv-fsm-hh-parse-failed =
    ❌ Не удалось загрузить вакансию. Проверьте ссылку и попробуйте снова.
iv-fsm-invalid-link = Пожалуйста, введите корректную ссылку (начинающуюся с http).

iv-fsm-enter-title =
    <b>Шаг 1/4 — Название вакансии</b>

    Введите название вакансии, на которую проходили собеседование:
iv-fsm-title-empty = Название не может быть пустым. Попробуйте снова:

iv-fsm-enter-description =
    <b>Шаг 2/4 — Описание вакансии</b>

    Введите описание вакансии (можно скопировать из объявления):
    Или отправьте любой текст, чтобы пропустить.

iv-fsm-enter-company =
    <b>Шаг 3/4 — Компания</b>

    Введите название компании:

iv-fsm-enter-experience =
    <b>Шаг 4/4 — Опыт</b>

    Какой опыт ожидался в вакансии?

btn-iv-exp-none = 👶 Без опыта
btn-iv-exp-junior = 🔰 1–3 года
btn-iv-exp-middle = 💼 3–6 лет
btn-iv-exp-senior = 🚀 6+ лет
btn-iv-exp-other = 🔧 Другое

iv-fsm-now-add-questions =
    <b>Теперь добавьте вопросы и ответы</b>

    Отправьте вопрос, который вам задали на собеседовании.
    После каждого вопроса введите ваш ответ или впечатление о нём.

iv-fsm-enter-answer = Теперь введите ваш ответ или ощущение о том, как вы ответили:
iv-fsm-question-empty = Вопрос не может быть пустым.
iv-fsm-question-added = ✅ Вопрос { $count } добавлен. Введите следующий или нажмите «Готово».
btn-iv-questions-done = ✅ Готово, перейти дальше

iv-fsm-enter-notes =
    <b>Что вы хотите улучшить?</b>

    Напишите, что, по вашему мнению, стоит доработать после этого собеседования.
    Это поможет сделать рекомендации более точными.
    Или нажмите «Пропустить».

btn-iv-skip = ⏭ Пропустить

iv-fsm-confirm-title = <b>📋 Проверьте данные перед отправкой</b>
iv-not-specified = не указано

btn-iv-proceed = 🚀 Анализировать
btn-cancel-form = ❌ Отмена

iv-fsm-analyzing = ⏳ Анализирую собеседование, это может занять до минуты...

iv-summary-label = 📊 Итог собеседования:
iv-qa-label = 💬 Вопросы и ответы:
iv-no-summary = Резюме не сформировано.
iv-no-questions = Вопросы не добавлены.

iv-improvement-flow-label = 📚 План улучшения:
iv-generating-flow = ⏳ Генерирую план улучшения...
iv-flow-generation-failed = Не удалось сгенерировать план. Попробуйте позже.
iv-analysis-failed = Не удалось проанализировать собеседование. Попробуйте позже.

btn-iv-generate-flow = 🔍 Сгенерировать план улучшения (AI)
btn-iv-set-improved = ✅ Отметить как изученное
btn-iv-set-incorrect = ❌ Некорректная оценка
btn-iv-back-improvements = ◀️ К списку тем

btn-iv-delete = 🗑 Удалить собеседование
iv-delete-confirm-prompt = Вы уверены? Запись будет скрыта из вашего списка.
btn-iv-delete-confirm = Да, удалить
iv-deleted = Собеседование удалено.
iv-not-found = Запись не найдена.

# Progress bars
progress-title = ⏳ Обработка задач
progress-completed-title = ✅ Все задачи выполнены!
progress-retrying = ⚠️ Что-то пошло не так, повторяем...
progress-bar-scraping = 🌐 Парсинг
progress-bar-keywords = 🧠 Ключевые слова
progress-bar-ai = 🧠 AI-совместимость
progress-btn-cancel = ❌ Отмена
progress-task-cancelled = Задача отменена.
progress-task-already-finished = Задача уже завершена.

# ── Work Experience (shared module) ──────────────────────────
work-exp-title = 💼 Опыт работы

# ── Feed buttons (F1, F2) ─────────────────────────────────────
feed-btn-fits-me = ✅ Подходит
feed-btn-not-fit = ❌ Не подходит
feed-btn-show-description = 📄 Показать описание
feed-btn-show-summary = 📝 Показать краткое

# ── Achievement Generator ─────────────────────────────────────
ach-list-title = 🏆 Мои достижения
ach-list-empty = У вас пока нет сгенерированных достижений. Нажмите кнопку ниже, чтобы создать первые!
ach-btn-generate-new = ✨ Сгенерировать достижения
ach-companies-count = компаний
ach-detail-title = 🏆 Достижения
ach-no-generated-text = Текст ещё генерируется...
ach-enter-achievements = 📝 Компания <b>{ $company }</b> ({ $current } из { $total })

    Опишите ваши реальные достижения в этой компании (или нажмите Пропустить):
ach-enter-responsibilities = 🔧 Компания <b>{ $company }</b> ({ $current } из { $total })

    Опишите ваши обязанности и задачи (или нажмите Пропустить):
ach-proceed-title = 📋 Подтверждение
ach-has-achievements = достижения ✓
ach-has-responsibilities = обязанности ✓
ach-no-input = без данных
ach-btn-proceed = 🚀 Генерировать достижения
ach-btn-delete = 🗑 Удалить из списка
ach-generating = ⏳ Генерирую достижения... Это может занять несколько минут.
ach-generation-completed = ✅ Достижения успешно сгенерированы!
ach-btn-view-result = 🏆 Посмотреть результат
ach-not-found = Генерация не найдена.
ach-deleted = Удалено из списка.
ach-current-value = Текущее значение

# ── Interview Q&A Generator ───────────────────────────────────
iqa-list-title = 💬 Вопросы к собеседованию
iqa-list-description = Здесь вы найдёте подготовленные ответы на стандартные вопросы работодателей.
iqa-btn-why-new-job = ❓ Почему ищете новую работу?
iqa-btn-generate-all = ✨ Сгенерировать ответы (AI)
iqa-btn-view = 💬 Посмотреть ответы
iqa-btn-regenerate = 🔄 Перегенерировать
iqa-generating = ⏳ Генерирую ответы... Подождите немного.
iqa-generation-completed = ✅ Ответы на вопросы готовы!
iqa-generation-timeout = ⚠️ Генерация заняла слишком много времени. Попробуйте ещё раз.
iqa-why-new-job-title = ❓ Почему вы ищете новую работу?
iqa-why-new-job-hint = Выберите вашу основную причину:
iqa-reason-label = Причина
iqa-enter-reason-manual = Введите причину поиска новой работы (произвольный текст):
iqa-reason-salary = 💰 Зарплата не росла
iqa-reason-bored = 😴 Не было новых задач
iqa-reason-relationship = 😤 Конфликты в коллективе
iqa-reason-growth = 📈 Нет карьерного роста
iqa-reason-relocation = 🌍 Переезд / смена локации
iqa-reason-other = 🔄 Другая причина
iqa-why-answer-salary = Я ценю честный разговор — основная причина в том, что мой доход не соответствовал рыночному уровню и не рос пропорционально моему развитию. Я не ставлю деньги на первое место, но считаю, что справедливая компенсация важна для долгосрочного сотрудничества.
iqa-why-answer-bored = Я очень ценю профессиональный рост. После того как я реализовал основные цели на прежнем месте, почувствовал, что пора двигаться дальше — искать новые сложные задачи, которые позволят мне развиваться.
iqa-why-answer-relationship = В каждой организации бывают ситуации, когда взгляды расходятся. У нас возникли разногласия в профессиональных вопросах с руководством. Я убеждён, что продуктивнее найти среду, где мои подходы разделяют.
iqa-why-answer-growth = Мне важна траектория развития. К сожалению, на прежнем месте возможности для роста были ограничены, и я принял осознанное решение двигаться туда, где смогу реализовать больший потенциал.
iqa-why-answer-relocation = Я переезжаю / меняю город проживания, поэтому ищу позицию, которая соответствует новой географии моей жизни.
iqa-why-answer-other = Я решил взять паузу для переосмысления своего карьерного пути и сейчас нахожусь в активном поиске возможности, которая совпадёт с моими профессиональными целями.
iqa-no-answer = Ответ ещё не сгенерирован.
iqa-not-found = Вопрос не найден.
iqa-question-best_achievement = Чем вы больше всего гордитесь на предыдущей работе?
iqa-question-worst_achievement = Что вы считаете своей наибольшей профессиональной неудачей?
iqa-question-biggest_challenge = Расскажите о самом сложном проекте или задаче.
iqa-question-five_year_plan = Где вы видите себя через 5 лет?
iqa-question-team_conflict = Расскажите о конфликте в команде и как вы его разрешили.
iqa-question-learning_new_tech = Как вы изучаете новые технологии?
iqa-generate-select-title = ✨ Выберите вопрос для генерации ответа
iqa-generate-select-description = Нажмите на вопрос, чтобы сгенерировать ответ с вашим опытом работы. ✅ — уже готов, ❌ — ещё не сгенерирован.
iqa-btn-generate-pending = ✨ Сгенерировать все оставшиеся ({ $count })
iqa-no-work-experience = Чтобы генерировать ответы, сначала добавьте опыт работы в профиле.

# ── Vacancy Summary Generator ────────────────────────────────
vs-list-title = 📄 Мои резюме "О себе"
vs-list-empty = У вас пока нет сгенерированных текстов. Нажмите ниже, чтобы создать первый!
vs-btn-generate-new = ✨ Создать новый
vs-btn-regenerate = 🔄 Перегенерировать
vs-btn-delete = 🗑 Удалить
vs-btn-view = 📄 Посмотреть
vs-btn-use-for-resume = ✅ Использовать для резюме
vs-enter-excluded-industries = 🚫 Какие сферы/компании <b>НЕ</b> хотите рассматривать?

    Напишите через запятую (например: казино, ставки, микрозаймы) или нажмите Пропустить:
vs-enter-location = 📍 Укажите ваш город/страну:
vs-enter-remote = 🏠 Ваши предпочтения по формату работы:

    (удалёнка / офис / гибрид / готов к релокации)
vs-enter-additional = 📝 Хотите добавить что-то ещё? (или Пропустить):
vs-generating = ⏳ Генерирую текст резюме... Подождите немного.
vs-generation-completed = ✅ Текст "О себе" готов!
vs-not-found = Текст не найден.
vs-deleted = Удалено.

# ── Resume Generator ──────────────────────────────────────────
res-welcome = 📋 <b>Генератор резюме</b>

    Этот инструмент поможет вам создать готовое резюме за несколько шагов:
    1. Отредактируйте опыт работы
    2. Сгенерируйте ключевые фразы
    3. Создайте текст "О себе"
    4. Получите готовое резюме
res-list-empty = 📋 У вас пока нет сохранённых резюме. Нажмите ниже, чтобы создать первое!
res-list-title = 📋 <b>Ваши резюме</b>
res-btn-create-new = ✨ Создать новое
res-not-found = Резюме не найдено.
res-btn-delete = 🗑 Удалить
res-deleted = Резюме удалено.
res-btn-start = 🚀 Начать
res-btn-generate-keyphrases = 🧠 Генерировать ключевые фразы
res-btn-create-autoparser = 🤖 Создать автопарсинг
res-step2-keyphrases = 🧠 <b>Шаг 2: Ключевые фразы</b>

    Нажмите кнопку, чтобы сгенерировать ключевые фразы, или пропустите этот шаг.
res-keywords-source-prompt = Хотите добавить ключевые слова для интеграции в ключевые фразы?
res-btn-keywords-manual = ✍️ Ввести вручную
res-btn-keywords-from-parsing = 🔍 Из парсинга
res-keywords-enter-prompt = Введите ключевые слова через запятую:
res-keywords-no-parsings = Нет завершённых парсингов с ключевыми словами. Генерирую без них.
res-select-parsing-company = Выберите парсинг для использования ключевых слов:
res-generating-keyphrases = ⏳ Генерирую ключевые фразы...
res-keyphrases-ready = ✅ Ключевые фразы для резюме:
res-btn-continue-step3 = ▶️ Продолжить: текст «О себе»
res-btn-show-result = 📋 Показать резюме
res-step3-summary = 📄 <b>Шаг 3: Текст "О себе"</b>

    Создайте или выберите существующий текст для резюме.
res-result-title = 📋 Ваше резюме
res-work-experiences = 💼 Опыт работы
res-about-me = 📄 О себе
res-no-experiences = Добавьте опыт работы для генерации резюме.
res-cancelled = Генерация резюме отменена.

# New resume flow
res-enter-job-title = 📋 <b>Шаг 1: Название вакансии</b>

    Введите название вакансии или желаемую должность (например: «Python Developer», «Product Manager»):
res-job-title-required = Пожалуйста, введите название вакансии.
res-enter-skill-level = 🎯 <b>Шаг 2: Уровень</b>

    Выберите ваш уровень или введите произвольно (например: «2 года опыта», «5+ лет»):
res-label-job-title = 📌 Должность
res-label-skill-level = 🎯 Уровень

# Work experience toggle for resume session
we-btn-disable-for-resume = 🚫 Не использовать в этом резюме
we-btn-enable-for-resume = ✅ Использовать в этом резюме

# Keyphrases step continue
res-btn-continue-rec-letters = ▶️ Продолжить: рекомендательные письма

# Recommendation letter flow
res-ask-rec-letter = 💼 <b>{ $company }</b>

    Хотите сгенерировать рекомендательное письмо для этой компании?
res-rec-enter-speaker-name = 👤 Введите имя и фамилию человека, от чьего лица пишется письмо:
res-rec-speaker-name-required = Пожалуйста, введите имя рекомендателя.
res-rec-enter-speaker-position = 💼 Введите должность рекомендателя (или пропустите):
res-rec-pick-character = 🎭 Выберите основной акцент рекомендательного письма:
res-rec-enter-focus = 📝 Что особо упомянуть в письме? (или пропустите):
res-rec-generating = ⏳ Генерирую рекомендательное письмо...
res-rec-letter-ready = ✅ Рекомендательное письмо готово!
res-rec-letter-not-found = Письмо не найдено.
res-btn-next-job-letter = ▶️ Следующая компания

# Result view buttons
res-btn-show-parsed-keywords = 🔑 Показать ключевые слова из парсинга
res-btn-show-job-keyphrases = 📝 Ключевые фразы
res-btn-show-summary = 📄 Текст «О себе»
res-btn-show-rec-letter = 📄 Рекомендательное письмо
res-no-keywords = Ключевые слова не найдены.
res-no-keyphrases = Ключевые фразы не найдены.
res-parsed-keywords-title = 🔑 Ключевые слова из парсинга

# ── Interview Preparation ─────────────────────────────────────
btn-iv-source-plain = 📝 Просто сохранить вакансию
btn-iv-add-results = ➕ Добавить результаты
btn-iv-prepare-me = 🎯 Подготовь меня
iv-plain-title = Вакансия
iv-plain-created = ✅ Вакансия сохранена. Теперь вы можете начать подготовку или добавить результаты интервью.
prep-generating = ⏳ Генерирую план подготовки...
prep-generating-deep = ⏳ Генерирую углублённый материал...
prep-generating-test = ⏳ Генерирую тест...
prep-guide-completed = ✅ План подготовки готов!
prep-deep-completed = ✅ Углублённый материал готов!
prep-test-ready = ✅ Тест готов! Нажмите, чтобы начать.
prep-steps-title = 🎯 Шаги подготовки
prep-steps-description = Выберите шаг для изучения:
prep-step-not-found = Шаг не найден.
prep-btn-skip = ⏩ Пропустить
prep-btn-continue = 📖 Изучить глубже
prep-btn-view-steps = 📋 Посмотреть шаги
prep-btn-view-deep = 📚 Углублённый материал
prep-btn-start-test = 🧪 Пройти тест
prep-btn-create-test = 🧪 Создать тест
prep-deep-title = 📚 Углублённое изучение
prep-deep-not-ready = Углублённый материал ещё не готов.
prep-test-not-ready = Тест ещё не готов.
prep-test-done = Тест завершён.
prep-test-question = Вопрос
prep-test-correct = ✅ Правильно!
prep-test-wrong = ❌ Неверно.
prep-test-right-answer = Правильный ответ
prep-test-results = Результат

# == Task UX ==
task-soft-timeout = ⏱ Задача превысила лимит времени. Попробуйте снова.
task-progress-started = ⏳ { $title }...
btn-edit-field = ✏️ Редактировать { $field }
btn-review = 👁 Проверить
form-step-counter = Шаг { $current } из { $total }
form-review-title = Проверьте данные перед отправкой
prep-guide-failed = ❌ Не удалось сгенерировать план подготовки.
prep-deep-failed = ❌ Не удалось сгенерировать углублённый материал.
prep-test-failed = ❌ Не удалось сгенерировать тест.
res-rec-letter-failed = ❌ Не удалось сгенерировать рекомендательное письмо.
