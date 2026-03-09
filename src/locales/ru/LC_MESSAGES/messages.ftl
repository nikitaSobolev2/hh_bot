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

# ── Parsing completed (worker notification) ──────────────
parsing-completed =
    <b>✅ Парсинг завершён!</b>

    Ваш парсинг #{ $id } готов.
    Выберите способ просмотра результатов:

# ── Parsing buttons ──────────────────────────────────────
btn-view-message = 💬 Показать сообщением
btn-download-md = 📄 Скачать .md
btn-download-txt = 📝 Скачать .txt
btn-generate-keyphrases = ✨ Генерация ключевых фраз (AI)
btn-cancel = ❌ Отмена
btn-skip-count = ⏭ Пропустить (до 30)
btn-skip-blacklisted = ✅ Пропустить из чёрного списка
btn-include-all = 🔄 Включить все
btn-try-again = 🔄 Попробовать снова

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
work-exp-stack-invalid = Стек технологий не может быть пустым.
work-exp-max-reached = Максимум 6 компаний. Удалите одну, чтобы добавить новую.
btn-add-company = ➕ Добавить компанию
btn-remove = Удалить
btn-skip = ⏭ Пропустить
btn-continue = ▶️ Продолжить

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
