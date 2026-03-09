# ── Welcome ──────────────────────────────────────────────
welcome =
    <b>HH Bot</b> — your HeadHunter vacancy parser

    Analyze vacancies, extract keywords, and build better resumes.

# ── Main menu buttons ────────────────────────────────────
btn-new-parsing = 🔍 New Parsing
btn-my-parsings = 📋 My Parsings
btn-profile = 👤 Profile
btn-settings = ⚙️ Settings
btn-admin = 🛠 Admin Panel
btn-back = ◀️ Back
btn-back-menu = ◀️ Back to Menu

# ── Profile ──────────────────────────────────────────────
profile-title = <b>👤 Profile</b>
profile-name = <b>Name:</b> { $first_name } { $last_name }
profile-username = <b>Username:</b> @{ $username }
profile-role = <b>Role:</b> { $role }
profile-balance = <b>Balance:</b> { $balance }
profile-language = <b>Language:</b> { $language }
profile-joined = <b>Joined:</b> { $date }

btn-stats = 📊 Stats
btn-referral = 🔗 Referral Link

stats-title = <b>📊 Stats</b>
stats-total-parsings = Total parsings: { $count }
stats-blacklisted = Active blacklisted vacancies: { $count }

referral-title = <b>🔗 Referral Link</b>
referral-share = Share this link to invite friends:
referral-code = Your referral code: <code>{ $code }</code>

# ── Settings ─────────────────────────────────────────────
settings-title = <b>⚙️ Settings</b>
settings-subtitle = Manage your preferences.

btn-language = 🌐 Language
btn-clear-blacklist = 🗑 Clear Blacklist
btn-notifications = 🔔 Notifications
btn-topup = 💰 Top Up Balance
btn-delete-data = ⚠️ Delete My Data

language-title = <b>🌐 Language</b>
language-subtitle = Select your language:
language-set = Language set to <b>{ $language }</b>

blacklist-cleared = Cleared <b>{ $count }</b> blacklist entries.
blacklist-cleared-ctx = Cleared <b>{ $count }</b> entries for <b>{ $context }</b>.
blacklist-empty =
    <b>🗑 Blacklist</b>

    No active blacklist entries.
blacklist-management-title = <b>🗑 Blacklist Management</b>
blacklist-vacancies = { $count } vacancies

notifications-title = <b>🔔 Notifications</b>
notifications-soon = Coming soon.

topup-title = <b>💰 Top Up Balance</b>
topup-soon = Payment methods coming soon.

delete-data-title = <b>⚠️ Delete Data</b>
delete-data-warning = This feature will permanently delete all your data. Implementation details to be confirmed.

btn-clear-all = 🗑 Clear All
btn-clear-context = 🗑 Clear: { $context }

# ── Parsing flow ─────────────────────────────────────────
parsing-new-title = <b>🔍 New Parsing</b>
parsing-enter-title =
    Enter the vacancy title for your resume
    (e.g. Frontend Developer, Маркетолог):
parsing-title-empty = Title cannot be empty. Please try again:
parsing-step2 =
    <b>Step 2/4</b>

    Enter the HH.ru search page URL
    (e.g. <code>https://hh.ru/search/vacancy?text=Frontend</code>):
parsing-invalid-url =
    Please enter a valid HH.ru URL
    (e.g. <code>https://hh.ru/search/vacancy?text=Python</code>)
parsing-step3 =
    <b>Step 3/4</b>

    Enter keyword filter for vacancy titles
    ("<code>|</code>" = OR, "<code>,</code>" = AND)
    Example: <code>frontend|backend,fullstack</code>

    Send <code>-</code> to skip filtering:
parsing-step4 =
    <b>Step 4/4</b>

    How many vacancies to process?
    (e.g. 30):
parsing-positive-number = Please enter a positive number:
parsing-max-200 = Maximum is 200 vacancies. Please enter a smaller number:
parsing-enter-url = Enter HH.ru search page URL:
parsing-enter-keyword = Enter keyword filter (or leave empty):
parsing-enter-count = How many vacancies to process?
parsing-started = Parsing started! Please wait for results.
parsing-empty =
    <b>📋 My Parsings</b>

    No parsings yet. Start a new one!
parsing-list-title = <b>📋 My Parsings</b>

parsing-blacklist-check =
    <b>⚠️ Blacklist Check</b>

    You have <b>{ $count }</b> blacklisted vacancies
    for <b>{ $title }</b>.

    Include previously parsed vacancies?

parsing-not-found = Not found

parsing-restarted =
    <b>🔄 Parsing restarted!</b>

    <b>Title:</b> { $title }
    <b>Target:</b> { $count } vacancies
    <b>Filter:</b> { $filter }

    New parsing #{ $new_id } has been started.
    You will be notified when results are ready.

parsing-no-results = No results available yet
parsing-truncated = <i>...truncated. Download full report.</i>
parsing-file-sent = File sent

# ── Parsing detail ───────────────────────────────────────
detail-status = <b>Status:</b> { $status }
detail-processed = <b>Processed:</b> { $processed }/{ $total }
detail-filter = <b>Filter:</b> { $filter }
detail-filter-none = none
detail-created = <b>Created:</b> { $date }
detail-completed = <b>Completed:</b> { $date }

# ── Parsing confirmation ────────────────────────────────
parsing-confirm =
    <b>🚀 Parsing Started!</b>

    <b>Title:</b> { $title }
    <b>Target:</b> { $count } vacancies
    <b>Filter:</b> { $filter }
    <b>Blacklist:</b> { $blacklist }

    You will be notified when results are ready.
parsing-confirm-include-all = including all
parsing-confirm-skip-bl = skipping blacklisted

# ── Parsing completed (worker notification) ──────────────
parsing-completed =
    <b>✅ Parsing completed!</b>

    Your parsing #{ $id } is ready.
    Choose how to view the results:

# ── Parsing buttons ──────────────────────────────────────
btn-view-message = 💬 View as Message
btn-download-md = 📄 Download .md
btn-download-txt = 📝 Download .txt
btn-generate-keyphrases = ✨ Generate Key Phrases (AI)
btn-cancel = ❌ Cancel
btn-skip-count = ⏭ Skip (up to 30)
btn-skip-blacklisted = ✅ Skip blacklisted
btn-include-all = 🔄 Include all
btn-try-again = 🔄 Try Again

# ── Pagination ───────────────────────────────────────────
btn-prev = ◀️ Prev
btn-next = Next ▶️

# ── Key phrases ──────────────────────────────────────────
keyphrase-title = <b>✨ Generate Key Phrases</b>
keyphrase-count-prompt =
    How many phrases to generate? (1-30)
    Or press Skip for up to 30:
keyphrase-select-lang = Select output language:
keyphrase-enter-number = Please enter a number from 1 to 30:
keyphrase-max-30 = Maximum is 30 phrases. Please enter a smaller number:
keyphrase-max-8 = Maximum is 8 phrases per company. Please enter a smaller number:
keyphrase-per-company-count =
    How many phrases per company? (1-8):
keyphrase-select-style = Select a style:
keyphrase-no-keywords = No keywords available. Run parsing first.
keyphrase-generating =
    ⏳ Generating key phrases with AI streaming...
    You will see the result appear shortly.
keyphrase-header = <b>✨ Key Phrases for { $title }</b>
keyphrase-style-label = Style: { $style } | { $lang }

# ── Work experience ─────────────────────────────────────
work-exp-prompt =
    Add your previous work experience (companies and tech stack).
    This helps generate more relevant phrases.
work-exp-enter-name = Enter the company name:
work-exp-enter-stack =
    Enter the tech stack for <b>{ $company }</b>
    (comma-separated, e.g. Python, Django, PostgreSQL):
work-exp-name-invalid = Company name cannot be empty (max 255 characters).
work-exp-stack-invalid = Tech stack cannot be empty.
work-exp-max-reached = Maximum 6 companies. Remove one to add another.
btn-add-company = ➕ Add Company
btn-remove = Remove
btn-skip = ⏭ Skip
btn-continue = ▶️ Continue

# ── Key phrases styles ──────────────────────────────────
style-formal = formal / business
style-results = results-oriented (metrics and achievements)
style-brief = concise / telegraphic
style-detailed = descriptive / detailed
style-expert = expert / professional

# ── Format selection ─────────────────────────────────────
format-select = Select output format:
btn-format-message = 💬 View as Message
btn-format-md = 📄 Download .md
btn-format-txt = 📝 Download .txt

# ── Admin panel ──────────────────────────────────────────
admin-title = <b>🛠 Admin Panel</b>
admin-subtitle = Manage users, settings, and tasks.
admin-users-title = <b>👥 Users</b>
admin-settings-title = <b>⚙️ App Settings</b>
admin-support-title = <b>📬 Support Inbox</b>
admin-support-empty = No messages yet.
admin-support-description = Users can send support messages which will appear here.
admin-access-denied = Access denied

btn-users = 👥 Users
btn-app-settings = ⚙️ App Settings
btn-support = 📬 Support Inbox

admin-users-empty =
    <b>👥 Users</b>

    No users found.
admin-users-page = <b>👥 Users</b> (page { $page })
admin-search-prompt =
    <b>🔍 Search Users</b>

    Enter username, name, or Telegram ID:
admin-user-not-found = User not found
admin-user-banned = User banned
admin-user-unbanned = User unbanned
admin-balance-prompt =
    <b>💰 Adjust Balance</b>

    Enter amount (positive to add, negative to deduct):
admin-send-message-prompt =
    <b>✉️ Send Message</b>

    Type the message to send to this user:
admin-search-empty = No users found for <b>{ $query }</b>
admin-search-results = <b>🔍 Results for «{ $query }»</b>
admin-invalid-amount = Invalid amount. Enter a number.
admin-balance-adjusted = Balance adjusted by <b>{ $amount }</b> for user #{ $user_id }.
admin-message-from-admin = <b>📢 Message from Admin</b>
admin-message-sent = Message sent.
admin-message-failed = Failed to send message.
admin-setting-select =
    <b>⚙️ App Settings</b>

    Select a setting to view or edit:
admin-setting-current =
    <b>⚙️ { $label }</b>

    Current value: <code>{ $value }</code>
admin-setting-set = Set to { $value }
admin-setting-edit =
    <b>✏️ Edit { $label }</b>

    Enter new value:
admin-setting-updated = <b>⚙️ { $label }</b> updated.
admin-setting-unknown = Unknown setting
admin-user-not-found-short = User not found.
admin-balance-description = Adjusted by admin #{ $admin_id }
admin-not-set = (not set)

# ── Admin buttons ────────────────────────────────────────
btn-search = 🔍 Search
btn-unban = ✅ Unban
btn-ban = 🚫 Ban
btn-adjust-balance = 💰 Adjust Balance
btn-send-message = ✉️ Send Message
btn-back-users = ◀️ Back to Users
btn-back-settings = ◀️ Back to Settings
btn-toggle = 🔄 Toggle
btn-edit = ✏️ Edit

# ── Admin user detail ────────────────────────────────────
admin-user-detail-title = <b>👤 User #{ $id }</b>
admin-user-detail-name = <b>Name:</b> { $name }
admin-user-detail-username = <b>Username:</b> @{ $username }
admin-user-detail-telegram-id = <b>Telegram ID:</b> <code>{ $telegram_id }</code>
admin-user-detail-role = <b>Role:</b> { $role }
admin-user-detail-balance = <b>Balance:</b> { $balance }
admin-user-detail-banned = <b>Banned:</b> { $banned }
admin-user-detail-language = <b>Language:</b> { $language }
admin-user-detail-joined = <b>Joined:</b> { $date }
yes = Yes
no = No

# ── Auth / System ────────────────────────────────────────
account-suspended = Your account has been suspended.
access-denied = Access denied

# ── Report generator ────────────────────────────────────
report-msg-title = <b>📊 Parsing Results: { $title }</b>
report-vacancies-processed = Vacancies processed: { $count }
report-top-keywords = <b>Top-{ $n } Keywords (AI):</b>
report-top-skills = <b>Top-{ $n } Skills (tags):</b>
report-key-phrases = <b>Key Phrases ({ $style }):</b>
report-md-title = # Parsing Report: { $title }
report-md-date = **Date:** { $date } UTC
report-md-vacancies = **Vacancies processed:** { $count }
report-md-keywords-header = ## Top-{ $n } Keywords (AI)
report-md-skills-header = ## Top-{ $n } Skills (tags)
report-md-keyphrases-header = ## Key Phrases
report-md-style = **Style:** { $style }
report-txt-title = PARSING REPORT: { $title }
report-txt-date = Date: { $date } UTC
report-txt-vacancies = Vacancies processed: { $count }
report-txt-keywords-header = TOP-{ $n } KEYWORDS (AI)
report-txt-skills-header = TOP-{ $n } SKILLS (TAGS)
report-txt-keyphrases-header = KEY PHRASES
report-txt-style = Style: { $style }
report-md-keyword-col = Keyword
report-md-skill-col = Skill
report-md-count-col = Count

# ── Support ─────────────────────────────────────────────────
btn-support-user = 🎫 Support
btn-new-ticket = ➕ New Ticket
btn-back-tickets = ◀️ Back to Tickets
btn-enter-conversation = 💬 Enter Chat
btn-skip-attachments = ⏭ Skip
btn-done-attachments = ✅ Done
btn-quit-conversation = 🚪 Quit Chat
btn-close-ticket = 🔒 Close Ticket
btn-close-ticket-admin = 🔒 Close Ticket
btn-take-into-work = 📌 Take Into Work
btn-view-profile = 👤 User Profile
btn-check-companies = 📋 Companies
btn-check-tickets = 🎫 Tickets
btn-check-notifications = 🔔 Notifications
btn-message-history = 📜 Message History
btn-filter-all = All
btn-filter-new = New
btn-filter-progress = In Progress
btn-filter-closed = Closed
btn-status-valid = ✅ Valid
btn-status-invalid = ❌ Invalid
btn-status-bug = 🐛 Bug

support-title = <b>🎫 Support</b>
support-subtitle = Your support tickets.
support-empty = No tickets yet. Create a new one!
support-ticket-detail =
    <b>🎫 Ticket #{ $id }</b>

    <b>Subject:</b> { $title }
    <b>Status:</b> { $status }
    <b>Created:</b> { $date }
support-ticket-status-new = 🆕 New
support-ticket-status-progress = 🔄 In Progress
support-ticket-status-closed = ✅ Closed

support-enter-title =
    <b>🎫 New Ticket</b>

    Enter the ticket subject:
support-enter-description =
    <b>Subject:</b> { $title }

    Now describe your issue in detail:
support-enter-attachments =
    Attach files (photos: webp/png/jpg/jpeg, txt, mp4)
    or press Skip / Done:
support-session-expired = ⚠️ Session expired. Please create a new ticket.
support-title-empty = Subject cannot be empty. Please try again:
support-desc-empty = Description cannot be empty. Please try again:
support-attachment-saved = ✅ File attached ({ $count })
support-attachment-invalid = ❌ Invalid file type. Allowed: photos (webp/png/jpg/jpeg), txt, mp4.
support-ticket-created =
    <b>✅ Ticket #{ $id } created!</b>

    You are in chat mode. Send messages — they will be forwarded to support.
support-conversation-entered =
    <b>💬 Chat Mode — Ticket #{ $id }</b>

    Send messages. They will be forwarded to support.
support-conversation-left = You left the chat mode.
support-ticket-closed-user = <b>🔒 Ticket #{ $id } closed.</b>
support-ticket-closed-admin =
    <b>🔒 Ticket #{ $id } closed</b>

    <b>Result:</b> { $result }
    <b>Status:</b> { $status }
support-ticket-already-closed = Ticket is already closed.
support-message-saved = 💬 Message saved.
support-no-admin = No admin has taken this ticket yet. Message saved and will be delivered later.

support-channel-new-ticket = 🆕 <b>New Support Ticket</b>
support-ticket-title-label = Subject
support-ticket-desc-label = Description
support-ticket-author = Author
support-ticket-id-label = Ticket ID

support-admin-reply = Support
support-user-label = User
support-admin-label = Admin
support-user-profile = User Profile
support-blacklist-count = Blacklist entries
support-referral-code = Referral code
support-referred-by = Referred by
support-ban-history = Ban history
support-no-messages = No messages in this ticket.

support-taken =
    <b>📌 Ticket #{ $id } taken into work</b>

    <b>Subject:</b> { $title }
    <b>Description:</b>
    { $description }

    <b>Status:</b> 🔄 In Progress
support-taken-popup = Ticket #{ $id } taken into work
support-already-taken = Ticket is already taken.
support-close-enter-result = Enter the result / closing comment for this ticket:
support-close-select-status = Select the closing status:
support-ban-enter-period =
    Enter the ban period (e.g. 1d, 7d, 30d, 1h)
    or <code>0</code> for permanent:
support-ban-enter-reason = Enter the ban reason:
support-ban-applied =
    <b>🚫 User banned</b>

    <b>Period:</b> { $period }
    <b>Reason:</b> { $reason }
support-ban-invalid-period = Invalid format. Use: 1d, 7d, 30d, 1h or 0.
support-ban-cancelled = ❌ Ban cancelled.
support-close-cancelled = ❌ Close cancelled.
support-ban-started-channel = 🚫 Admin started ban process for the user.
support-close-started-channel = 🔒 Admin started closing the ticket.
support-notifications-soon = 🔔 Notifications — coming soon.
support-companies-empty = User has no companies.
support-tickets-empty = User has no tickets.
support-history-sent = 📜 Sent { $count } messages.

support-inbox-title = <b>📬 Support Inbox</b>
support-inbox-empty = No tickets.
support-search-prompt =
    <b>🔍 Search Tickets</b>

    Enter text to search by subject or description:
support-search-results = <b>🔍 Results for "{ $query }"</b>
support-search-empty = No tickets found for <b>{ $query }</b>

support-ticket-closed-notify-user =
    <b>🔒 Your ticket #{ $id } was closed by admin.</b>

    <b>Result:</b> { $result }
    <b>Status:</b> { $status }
support-ticket-closed-notify-admin =
    <b>🔒 Ticket #{ $id } was closed by the user.</b>
support-unseen-delivered = 📬 Delivered { $count } unseen messages.

# ── Autoparse ──────────────────────────────────────────────────
btn-autoparse = 🔄 Autoparse
autoparse-hub-title = Vacancy Autoparse
autoparse-hub-subtitle = Create automated parsing jobs to track new vacancies.
autoparse-create-new = ➕ Create new company
autoparse-list-title = 📋 My autoparsers
autoparse-select-template = Select a template from your parsing companies or skip:
autoparse-skip-template = ⏭️ Skip (manual input)
autoparse-enter-title = Enter vacancy title:
autoparse-enter-url = Enter HH.ru filter URL:
autoparse-enter-keywords = Enter keywords to search in title:
autoparse-enter-skills = Enter skills separated by commas (skill1, skill2, ...):
autoparse-created-success = ✅ Autoparse company #{ $id } created successfully!
autoparse-empty-list = You have no autoparse companies yet.
autoparse-status-enabled = On
autoparse-status-disabled = Off
autoparse-detail-title = Autoparse Details
autoparse-detail-metrics = Metrics
autoparse-not-found = Company not found.
autoparse-toggle-enabled = ✅ Autoparse enabled
autoparse-toggle-disabled = ⏸️ Autoparse disabled
autoparse-deleted = 🗑️ Autoparse company deleted.
autoparse-confirm-delete = ❌ Delete
autoparse-download-title = 📥 Download vacancies
autoparse-download-links = 🔗 Links only (.txt)
autoparse-download-summary = 📊 Summary (.txt)
autoparse-download-full = 📄 Full info (.md)
autoparse-settings-title = ⚙️ Autoparse Settings
autoparse-settings-work-exp = 💼 Work Experience
autoparse-settings-send-time = 🕐 Send Time
autoparse-settings-tech-stack = 🛠️ Tech Stack
autoparse-settings-saved = ✅ Settings saved.
autoparse-enter-work-exp = Describe your work experience (position, years, domains):
autoparse-enter-send-time = Enter time to send results (format HH:MM):
autoparse-enter-tech-stack = Enter technologies separated by commas (Python, React, Docker, ...):
autoparse-compatibility-label = Compatibility
autoparse-compatibility-na-hint = Add your experience and tech stack in Autoparse Settings to see compatibility scores.
btn-confirm = ✅ Confirm
btn-timezone = 🌍 Timezone
settings-timezone-current = Current timezone: { $tz }
settings-timezone-select = Select your timezone:
settings-timezone-search = Enter city or region name to search:
settings-timezone-set = Timezone set to { $tz }
settings-timezone-no-results = No timezones found for your query. Try again.
btn-tz-search = 🔍 Search
