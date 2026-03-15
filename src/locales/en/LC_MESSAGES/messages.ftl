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
btn-my-interviews = 🎤 My Interviews
btn-autoparse = 🤖 Auto Parse
btn-work-experience = 💼 Work Experience
btn-achievements = 🏆 Achievements
btn-interview-qa = 💬 Interview Q&A
btn-vacancy-summary = 📄 About Me Summary
btn-resume = 📋 Resume Generator
btn-support-user = 🆘 Support
btn-skip = ⏩ Skip
btn-continue = ▶️ Continue
btn-cancel = ✖️ Cancel
btn-add-company = ➕ Add Company
btn-remove = ❌ Remove
btn-yes = ✅ Yes
btn-no = ❌ No
btn-type-manually = ✏️ Type manually

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
parsing-max-50 = Maximum is 50 vacancies. Please enter a smaller number:
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

parsing-retry-count-prompt =
    <b>🔄 Retry Parsing</b>

    How many vacancies to process?
    (default: { $default })

    Enter a number or press the button below:

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
detail-filter-link = <b>Filter Link:</b> <a href='{ $link }'>Link</a>
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
parsing-confirm-compat = Compatibility check: ✅ enabled (threshold: { $threshold }%)

# ── Parsing compat check ─────────────────────────────────
parsing-compat-check-prompt =
    <b>🎯 Compatibility Check</b>

    Do you want to run AI compatibility check against your profile?
    Vacancies scoring below the threshold will be filtered out.

parsing-retry-compat-prompt =
    <b>🎯 Compatibility Check</b>

    Do you want to run AI compatibility check for this retry?
    Vacancies scoring below the threshold will be filtered out.

parsing-compat-threshold-prompt =
    Enter the minimum compatibility threshold (1–100).

    Only vacancies with a score ≥ this value will be included.

parsing-compat-threshold-invalid = Please enter a whole number between 1 and 100.

# ── Parsing completed (worker notification) ──────────────
parsing-completed =
    <b>✅ Parsing completed!</b>

    Your parsing #{ $id } is ready.
    Choose how to view the results:

# ── Parsing buttons ──────────────────────────────────────
parsing-btn-delete = 🗑 Delete
parsing-deleted = Parsing removed from your list.
btn-view-message = 💬 View as Message
btn-download-md = 📄 Download .md
btn-download-txt = 📝 Download .txt
btn-generate-keyphrases = ✨ Generate Key Phrases (AI)
btn-cancel = ❌ Cancel
btn-skip-count = ⏭ Skip (up to 30)
btn-skip-blacklisted = ✅ Skip blacklisted
btn-include-all = 🔄 Include all
btn-try-again = 🔄 Try Again
btn-use-default = ✓ Use default ({ $count })
btn-compat-yes = ✅ Yes
btn-compat-skip = ⏭ Skip

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
parsing-enter-lang-manual = Enter language code (e.g. ru, en, de):
parsing-enter-style-manual = Enter style key (e.g. formal, results, brief):
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
work-exp-title-invalid = Job title cannot exceed 255 characters.
work-exp-stack-invalid = Tech stack cannot be empty.
work-exp-max-reached = Maximum 6 companies. Remove one to add another.
work-exp-not-found = Work experience entry not found.
work-exp-enter-title =
    Enter your job title at this company
    (e.g. Backend Developer, Senior Engineer) or skip:
work-exp-enter-period =
    Enter your work period
    (e.g. 2020-2023, 3 years) or skip:
work-exp-enter-achievements-edit = Enter new achievements (or choose an option below):
work-exp-enter-duties-edit = Enter new duties (or choose an option below):
we-edit-enter-stack = Enter new tech stack (comma-separated):
we-label-achievements = Achievements
we-label-duties = Duties
we-not-set = Not set
we-deleted = ✅ Entry deleted
we-btn-edit-company-name = ✏️ Company name
we-btn-edit-title = 📋 Job title
we-btn-edit-period = 📅 Work period
we-btn-edit-stack = 🛠 Tech stack
we-btn-edit-achievements = 🏆 Achievements
we-btn-edit-duties = 🔧 Duties
we-btn-delete = 🗑 Delete
work-exp-enter-achievements =
    🏆 <b>{ $company }</b> — achievements

    Describe your real achievements (or choose an option below):
work-exp-enter-duties =
    🔧 <b>{ $company }</b> — duties

    Describe your job duties and responsibilities (or choose an option below):
work-exp-generating = ⏳ Generating...
work-exp-generated-achievements =
    ✅ Generated achievements:

    { $text }
work-exp-generated-duties =
    ✅ Generated duties:

    { $text }
work-exp-generation-failed = Generation failed. Please type manually or skip.
work-exp-ai-result-achievements =
    ✅ Generated achievements:

    { $text }
work-exp-ai-result-duties =
    ✅ Generated duties:

    { $text }
work-exp-ai-generation-done = ✅ Done! Tap to view the result.
we-btn-accept-draft = ✅ Use this
we-btn-regenerate = 🔄 Try again
we-btn-view-result = 👁 View result
btn-add-company = ➕ Add Company
btn-remove = Remove
btn-skip = ⏭ Skip
btn-continue = ▶️ Continue
btn-generate-ai = 🤖 Generate with AI

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
autoparse-detail-status = Status
autoparse-detail-url = URL
autoparse-detail-keywords = Keywords
autoparse-detail-skills = Skills
autoparse-detail-metrics = Metrics
autoparse-detail-runs = Runs
autoparse-detail-vacancies = Vacancies
autoparse-detail-last-run = Last run
autoparse-run-now = ▶️ Run now
autoparse-run-started = ✅ Parsing started!
autoparse-run-finished = ✅ Parsing complete! Found { $count } new { $count ->
    [one] vacancy
   *[other] vacancies
  }.
autoparse-run-finished-empty = ✅ Parsing complete. No new vacancies found.
autoparse-run-already-running = ⏳ Parsing is already in progress or was recently completed.
autoparse-show-now = 📨 Show new vacancies now
autoparse-delivering-now = 📨 Sending new vacancies to you now...
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
autoparse-settings-stack-auto = auto from work experience
autoparse-settings-saved = ✅ Settings saved.
autoparse-enter-work-exp = Describe your work experience (position, years, domains):
autoparse-enter-send-time = Enter time to send results (format HH:MM):
autoparse-enter-tech-stack = Enter technologies separated by commas (Python, React, Docker, ...):
autoparse-compatibility-label = Compatibility
autoparse-compatibility-na-hint = Add your experience and tech stack in Autoparse Settings to see compatibility scores.
autoparse-settings-min-compat = 🎯 Min. compatibility
autoparse-enter-min-compat = Enter minimum compatibility percentage (0–100):
autoparse-min-compat-invalid = Enter a whole number between 0 and 100.
autoparse-delivery-header = 📥 <b>{ $title }</b> — { $count } new vacancies
autoparse-btn-show-liked = 👍 Liked vacancies
autoparse-btn-show-disliked = 👎 Disliked vacancies
autoparse-liked-empty = You have no liked vacancies yet.
autoparse-disliked-empty = You have no disliked vacancies yet.
autoparse-include-reacted-prompt = Include previously reacted vacancies in the feed again?
autoparse-include-reacted-yes = Yes
autoparse-include-reacted-no = No
autoparse-settings-cover-letter-style = ✉️ Cover letter style
autoparse-cover-letter-style-current = Current: { $style }
autoparse-cover-letter-style-choose = Choose style:
autoparse-cover-letter-style-professional = Professional
autoparse-cover-letter-style-friendly = Friendly
autoparse-cover-letter-style-concise = Concise
autoparse-cover-letter-style-detailed = Detailed
autoparse-cover-letter-style-custom = Custom value
autoparse-enter-cover-letter-style = Enter custom style description (e.g. formal, creative):

# ── Vacancy Feed ──────────────────────────────────────────
feed-stats-count = 🆕 { $count } new vacancies
feed-stats-avg-compat = 📊 Average compatibility: { $avg }%
feed-stats-hint = Press the button below to start browsing.
feed-btn-start = ▶️ Start browsing
feed-vacancy-progress = [{ $current } / { $total }]
feed-btn-open = 🔗 Open on HH.ru
feed-btn-like = 👍 Like
feed-btn-dislike = 👎 Dislike
feed-btn-create-cover-letter = ✉️ Create Cover Letter
feed-btn-show-later = 🔄 Show later
feed-btn-stop = ⏹ Stop
feed-cover-letter-generating = ⏳ Generating cover letter...
feed-results-header = 📊 Feed Results
feed-results-seen = Viewed: { $seen } of { $total }
feed-results-liked = 👍 Liked: { $liked }
feed-results-disliked = 👎 Disliked: { $disliked }
feed-results-avg-liked-compat = 📊 Avg. compatibility of liked: { $avg }%
feed-session-not-found = Feed session not found or already completed.
btn-confirm = ✅ Confirm
btn-timezone = 🌍 Timezone
settings-timezone-current = Current timezone: { $tz }
settings-timezone-select = Select your timezone:
settings-timezone-search = Enter city or region name to search:
settings-timezone-set = Timezone set to { $tz }
settings-timezone-no-results = No timezones found for your query. Try again.
btn-tz-search = 🔍 Search

# ── My Interviews ─────────────────────────────────────────
btn-my-interviews = 🎤 My Interviews
btn-cancel = ❌ Cancel

iv-list-title = <b>🎤 My Interviews</b>

iv-list-empty =
    <b>🎤 My Interviews</b>

    You have no interview records yet.
    Tap "Add" to get started.

btn-iv-add-new = ➕ Add Interview

iv-fsm-source-choice =
    <b>🎤 New Interview</b>

    Was this a job interview for a vacancy from HH.ru?

btn-iv-source-hh = 🔗 Yes, it's from HH.ru
btn-iv-source-manual = ✏️ No, I'll enter it manually

iv-fsm-enter-hh-link =
    Enter the HH.ru vacancy link:
    (e.g. https://hh.ru/vacancy/12345678)

iv-fsm-parsing-hh = ⏳ Loading vacancy data from HH.ru...
iv-fsm-hh-parsed = ✅ Vacancy loaded:
iv-parsed-company = Company: { $value }
iv-parsed-experience = Experience: { $value }
iv-fsm-hh-parse-failed =
    ❌ Could not load the vacancy. Check the link and try again.
iv-fsm-invalid-link = Please enter a valid link (starting with http).

iv-fsm-enter-title =
    <b>Step 1/4 — Vacancy Title</b>

    Enter the title of the vacancy you interviewed for:
iv-fsm-title-empty = Title cannot be empty. Please try again:

iv-fsm-enter-description =
    <b>Step 2/4 — Vacancy Description</b>

    Enter the vacancy description (paste from the job posting):
    Or send any text to skip.

iv-fsm-enter-company =
    <b>Step 3/4 — Company</b>

    Enter the company name:

iv-fsm-enter-experience =
    <b>Step 4/4 — Experience Level</b>

    What experience level was expected in this vacancy?

btn-iv-exp-none = 👶 No experience
btn-iv-exp-junior = 🔰 1–3 years
btn-iv-exp-middle = 💼 3–6 years
btn-iv-exp-senior = 🚀 6+ years
btn-iv-exp-other = 🔧 Other

iv-fsm-now-add-questions =
    <b>Now add your questions and answers</b>

    Send a question you were asked during the interview.
    After each question, enter your answer or how you felt about it.

iv-fsm-enter-answer = Now enter your answer or how you felt about your response:
iv-fsm-question-empty = Question cannot be empty.
iv-fsm-question-added = ✅ Question { $count } added. Enter another or tap "Done".
btn-iv-questions-done = ✅ Done, continue

iv-fsm-enter-notes =
    <b>What do you want to improve?</b>

    Write what you think you should work on after this interview.
    This helps make AI recommendations more accurate.
    Or tap "Skip".

btn-iv-skip = ⏭ Skip

iv-fsm-confirm-title = <b>📋 Review your data before submitting</b>
iv-not-specified = not specified

btn-iv-proceed = 🚀 Analyze
btn-cancel-form = ❌ Cancel

iv-fsm-analyzing = ⏳ Analyzing interview, this may take up to a minute...

iv-summary-label = 📊 Interview Summary:
iv-qa-label = 💬 Questions & Answers:
iv-no-summary = Summary not generated.
iv-no-questions = No questions added.

iv-improvement-flow-label = 📚 Improvement Plan:
iv-generating-flow = ⏳ Generating improvement plan...
iv-flow-generation-failed = Could not generate the plan. Please try later.
iv-analysis-failed = Could not analyze the interview. Please try later.

btn-iv-generate-flow = 🔍 Generate Improvement Plan (AI)
btn-iv-set-improved = ✅ Mark as Learned
btn-iv-set-incorrect = ❌ Incorrect Assessment
btn-iv-back-improvements = ◀️ Back to Topics

btn-iv-delete = 🗑 Delete Interview
iv-delete-confirm-prompt = Are you sure? This record will be hidden from your list.
btn-iv-delete-confirm = Yes, delete
iv-deleted = Interview deleted.
iv-not-found = Record not found.

# Progress bars
progress-title = ⏳ Processing tasks
progress-completed-title = ✅ All tasks completed!
progress-retrying = ⚠️ Something went wrong, retrying...
progress-bar-scraping = 🌐 Scraping
progress-bar-keywords = 🧠 Keywords
progress-bar-ai = 🧠 AI Analysis
progress-btn-cancel = ❌ Cancel
progress-btn-cancel-task = ❌ Cancel: { $n } - { $title }
progress-task-cancelled = Task cancelled.
progress-task-already-finished = Task already finished.
progress-parsing-shortage = Only { $count } of { $target } { $entity } found.
progress-entity-vacancies = vacancies

# ── Work Experience (shared module) ──────────────────────────
work-exp-title = 💼 Work Experience

# ── Feed buttons (F1, F2) ─────────────────────────────────────
feed-btn-fits-me = ✅ Fits me
feed-btn-not-fit = ❌ Does not fit
feed-btn-show-description = 📄 Show full description
feed-btn-show-summary = 📝 Show summary

# ── Achievement Generator ─────────────────────────────────────
ach-list-title = 🏆 My Achievements
ach-list-empty = No achievement generations yet. Press the button below to create your first!
ach-btn-generate-new = ✨ Generate Achievements
ach-companies-count = companies
ach-detail-title = 🏆 Achievements
ach-no-generated-text = Text is still being generated...
ach-enter-achievements = 📝 Company <b>{ $company }</b> ({ $current } of { $total })

    Describe your real achievements at this company (or press Skip):
ach-enter-responsibilities = 🔧 Company <b>{ $company }</b> ({ $current } of { $total })

    Describe your responsibilities and tasks (or press Skip):
ach-proceed-title = 📋 Confirmation
ach-has-achievements = achievements ✓
ach-has-responsibilities = responsibilities ✓
ach-no-input = no data
ach-btn-proceed = 🚀 Generate Achievements
ach-btn-delete = 🗑 Remove from List
ach-generating = ⏳ Generating achievements... This may take a few minutes.
ach-generation-completed = ✅ Achievements successfully generated!
ach-btn-view-result = 🏆 View Result
ach-not-found = Generation not found.
ach-deleted = Removed from list.
ach-current-value = Current value

# ── Interview Q&A Generator ───────────────────────────────────
iqa-list-title = 💬 Interview Q&A
iqa-list-description = Here you'll find prepared answers to common interview questions.
iqa-btn-why-new-job = ❓ Why are you looking for a new job?
iqa-btn-generate-all = ✨ Generate Answers (AI)
iqa-btn-view = 💬 View Answers
iqa-btn-regenerate = 🔄 Regenerate
iqa-generating = ⏳ Generating answers... Please wait.
iqa-generation-completed = ✅ Interview answers are ready!
iqa-generation-timeout = ⚠️ Generation took too long. Please try again.
iqa-why-new-job-title = ❓ Why are you looking for a new job?
iqa-why-new-job-hint = Select your main reason:
iqa-reason-label = Reason
iqa-enter-reason-manual = Enter your reason for looking for a new job (custom text):
iqa-reason-salary = 💰 Salary wasn't growing
iqa-reason-bored = 😴 No new challenges
iqa-reason-relationship = 😤 Team conflicts
iqa-reason-growth = 📈 No career growth
iqa-reason-relocation = 🌍 Relocation
iqa-reason-other = 🔄 Other reason
iqa-why-answer-salary = I value honest conversation — the main reason is that my compensation didn't match market rates and wasn't growing in line with my development. I don't put money first, but fair compensation is important for a long-term working relationship.
iqa-why-answer-bored = I greatly value professional growth. After achieving the main goals at my previous role, I felt it was time to move on and find new challenging tasks that would help me develop further.
iqa-why-answer-relationship = Every organization has situations where views differ. We had professional disagreements with management. I believe it's more productive to find an environment where my approaches are shared.
iqa-why-answer-growth = Career trajectory is important to me. Unfortunately, at my previous role the growth opportunities were limited, so I made a deliberate decision to move to a place where I can realize more of my potential.
iqa-why-answer-relocation = I'm relocating, so I'm looking for a position that fits my new geography.
iqa-why-answer-other = I decided to take a pause to reassess my career path, and I'm now actively looking for an opportunity that aligns with my professional goals.
iqa-no-answer = Answer not yet generated.
iqa-not-found = Question not found.
iqa-question-best_achievement = What are you most proud of at your previous job?
iqa-question-worst_achievement = What do you consider your biggest professional failure?
iqa-question-biggest_challenge = Tell me about the most challenging project or task.
iqa-question-five_year_plan = Where do you see yourself in 5 years?
iqa-question-team_conflict = Tell me about a team conflict and how you resolved it.
iqa-question-learning_new_tech = How do you learn new technologies?
iqa-generate-select-title = ✨ Select a question to generate an answer
iqa-generate-select-description = Tap a question to generate an answer using your work experience. ✅ = ready, ❌ = not yet generated.
iqa-btn-generate-pending = ✨ Generate all remaining ({ $count })
iqa-no-work-experience = Please add work experience in your profile before generating answers.

# ── Vacancy Summary Generator ────────────────────────────────
vs-list-title = 📄 My About-Me Summaries
vs-list-empty = No summaries yet. Press below to create your first!
vs-btn-generate-new = ✨ Create New
vs-btn-regenerate = 🔄 Regenerate
vs-btn-delete = 🗑 Delete
vs-btn-view = 📄 View
vs-btn-use-for-resume = ✅ Use for resume
vs-enter-excluded-industries = 🚫 Which industries/companies do you <b>NOT</b> want to consider?

    List them separated by commas (e.g. gambling, loans) or press Skip:
vs-enter-location = 📍 Enter your city/country:
vs-enter-remote = 🏠 Your preferred work format:

    (remote / office / hybrid / open to relocation)
vs-enter-additional = 📝 Anything else to add? (or Skip):
vs-generating = ⏳ Generating your about-me summary...
vs-generation-completed = ✅ About-me summary is ready!
vs-not-found = Summary not found.
vs-deleted = Deleted.

# ── Resume Generator ──────────────────────────────────────────
res-welcome = 📋 <b>Resume Generator</b>

    This tool helps you build a complete resume in a few steps:
    1. Edit your work experience
    2. Generate key phrases
    3. Create an about-me summary
    4. Get your complete resume
res-list-empty = 📋 You have no saved resumes yet. Tap below to create your first!
res-list-title = 📋 <b>Your Resumes</b>
res-btn-create-new = ✨ Create New
res-not-found = Resume not found.
res-btn-delete = 🗑 Delete
res-deleted = Resume deleted.
res-btn-start = 🚀 Start
res-btn-generate-keyphrases = 🧠 Generate Key Phrases
res-btn-create-autoparser = 🤖 Create Auto Parser
res-step2-keyphrases = 🧠 <b>Step 2: Key Phrases</b>

    Click to generate key phrases, or skip this step.
res-keywords-source-prompt = Would you like to add keywords to integrate into the key phrases?
res-btn-keywords-manual = ✍️ Enter manually
res-btn-keywords-from-parsing = 🔍 From parsing
res-keywords-enter-prompt = Enter keywords separated by commas:
res-keywords-no-parsings = No completed parsings with keywords found. Generating without them.
res-select-parsing-company = Select a parsing to use keywords from:
res-generating-keyphrases = ⏳ Generating key phrases...
res-keyphrases-ready = ✅ Key phrases for your resume:
res-btn-continue-step3 = ▶️ Continue: About me text
res-btn-show-result = 📋 Show resume
res-step3-summary = 📄 <b>Step 3: About-Me Summary</b>

    Create or select an existing about-me text for your resume.
res-result-title = 📋 Your Resume
res-work-experiences = 💼 Work Experience
res-about-me = 📄 About Me
res-no-experiences = Please add work experience to generate a resume.
res-cancelled = Resume generation cancelled.

# New resume flow
res-enter-job-title = 📋 <b>Step 1: Job Title</b>

    Enter the vacancy title or desired position (e.g. "Python Developer", "Product Manager"):
res-job-title-required = Please enter a job title.
res-enter-skill-level = 🎯 <b>Step 2: Skill Level</b>

    Select your level or type it freely (e.g. "2 years of experience", "5+ years"):
res-label-job-title = 📌 Position
res-label-skill-level = 🎯 Level

# Work experience toggle for resume session
we-btn-disable-for-resume = 🚫 Exclude from this resume
we-btn-enable-for-resume = ✅ Include in this resume

# Keyphrases step continue
res-btn-continue-rec-letters = ▶️ Continue: recommendation letters

# Recommendation letter flow
res-ask-rec-letter = 💼 <b>{ $company }</b>

    Would you like to generate a recommendation letter for this company?
res-rec-enter-speaker-name = 👤 Enter the full name of the person writing the letter:
res-rec-speaker-name-required = Please enter the recommender's name.
res-rec-enter-speaker-position = 💼 Enter the recommender's job title (or skip):
res-rec-pick-character = 🎭 Select the main focus of the recommendation letter:
res-rec-enter-focus = 📝 What should be especially highlighted? (or skip):
res-rec-generating = ⏳ Generating recommendation letter...
res-rec-letter-ready = ✅ Recommendation letter is ready!
res-rec-letter-not-found = Letter not found.
res-btn-next-job-letter = ▶️ Next company

# Result view buttons
res-btn-show-parsed-keywords = 🔑 Show parsed keywords
res-btn-show-job-keyphrases = 📝 Key phrases
res-btn-show-summary = 📄 About Me text
res-btn-show-rec-letter = 📄 Recommendation letter
res-no-keywords = No keywords found.
res-no-keyphrases = No key phrases found.
res-parsed-keywords-title = 🔑 Parsed keywords

# ── Interview Preparation ─────────────────────────────────────
btn-iv-source-plain = 📝 Just save the vacancy
btn-iv-add-results = ➕ Add Results
btn-iv-prepare-me = 🎯 Prepare Me
iv-plain-title = Vacancy
iv-plain-created = ✅ Vacancy saved. You can now start preparation or add interview results.
prep-generating = ⏳ Generating preparation guide...
prep-generating-deep = ⏳ Generating deep learning summary...
prep-generating-test = ⏳ Generating test...
prep-guide-completed = ✅ Preparation guide is ready!
prep-deep-completed = ✅ Deep learning summary is ready!
prep-test-ready = ✅ Test is ready! Press to start.
prep-steps-title = 🎯 Preparation Steps
prep-steps-description = Select a step to study:
prep-step-not-found = Step not found.
prep-btn-skip = ⏩ Skip
prep-btn-continue = 📖 Study Deeper
prep-btn-view-steps = 📋 View Steps
prep-btn-view-deep = 📚 Deep Learning
prep-btn-start-test = 🧪 Take Test
prep-btn-create-test = 🧪 Create Test
prep-deep-title = 📚 Deep Learning
prep-deep-not-ready = Deep learning summary not ready yet.
prep-test-not-ready = Test not ready yet.
prep-test-done = Test completed.
prep-test-question = Question
prep-test-correct = ✅ Correct!
prep-test-wrong = ❌ Wrong.
prep-test-right-answer = Correct answer
prep-test-results = Score

# == Task UX ==
task-soft-timeout = ⏱ The task exceeded the time limit. Please try again.
parsing-staleness-error = ⏱ No progress was made in the last { $minutes } minutes. The task was stopped. Please try again.
task-progress-started = ⏳ { $title }...
btn-edit-field = ✏️ Edit { $field }
btn-review = 👁 Review
form-step-counter = Step { $current } of { $total }
form-review-title = Review your answers before submitting
prep-guide-failed = ❌ Failed to generate preparation guide.
prep-deep-failed = ❌ Failed to generate deep learning material.
prep-test-failed = ❌ Failed to generate test.
res-rec-letter-failed = ❌ Failed to generate recommendation letter.
