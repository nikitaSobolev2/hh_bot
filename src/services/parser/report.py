"""Report generator for parsing results in multiple formats."""

from datetime import UTC, datetime

from src.core.i18n import get_text


class ReportGenerator:
    def __init__(
        self,
        vacancy_title: str,
        top_keywords: dict[str, int],
        top_skills: dict[str, int],
        vacancies_processed: int,
        key_phrases: str | None = None,
        key_phrases_style: str | None = None,
        locale: str = "ru",
    ) -> None:
        self._title = vacancy_title
        self._keywords = top_keywords
        self._skills = top_skills
        self._vacancies_processed = vacancies_processed
        self._key_phrases = key_phrases
        self._key_phrases_style = key_phrases_style
        self._locale = locale

    def _t(self, key: str, **kwargs: str) -> str:
        return get_text(key, self._locale, **kwargs)

    def _rank_items(self, items: dict[str, int], top_n: int) -> list[tuple[int, str, int, str]]:
        """Return ranked items as (rank, name, count, pct_str) tuples."""
        total = sum(items.values())
        ranked = []
        for rank, (name, count) in enumerate(
            sorted(items.items(), key=lambda x: -x[1])[:top_n],
            1,
        ):
            pct = f"{count / total * 100:.1f}%" if total else "—"
            ranked.append((rank, name, count, pct))
        return ranked

    def generate_message(self, top_n: int = 25) -> str:
        lines = [
            self._t("report-msg-title", title=self._title),
            "",
            self._t("report-vacancies-processed", count=str(self._vacancies_processed)),
            "",
        ]

        if self._keywords:
            lines.append(self._t("report-top-keywords", n=str(top_n)))
            for rank, kw, count, pct in self._rank_items(self._keywords, top_n):
                lines.append(f"  {rank}. <code>{kw}</code> — {count} ({pct})")

        if self._skills:
            lines.append(f"\n{self._t('report-top-skills', n=str(top_n))}")
            for rank, sk, count, pct in self._rank_items(self._skills, top_n):
                lines.append(f"  {rank}. <code>{sk}</code> — {count} ({pct})")

        if self._key_phrases:
            style = self._key_phrases_style or "default"
            lines.append(f"\n{self._t('report-key-phrases', style=style)}")
            lines.append(self._key_phrases)

        return "\n".join(lines)

    def generate_md(self, top_n: int = 25) -> str:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            self._t("report-md-title", title=self._title),
            "",
            self._t("report-md-date", date=now),
            self._t("report-md-vacancies", count=str(self._vacancies_processed)),
            "",
        ]

        if self._keywords:
            lines.append(self._t("report-md-keywords-header", n=str(top_n)))
            lines.append("")
            kw_col = self._t("report-md-keyword-col")
            count_col = self._t("report-md-count-col")
            lines.append(f"| # | {kw_col} | {count_col} | % |")
            lines.append("|---|---------|-------|---|")
            for rank, kw, count, pct in self._rank_items(self._keywords, top_n):
                lines.append(f"| {rank} | {kw} | {count} | {pct} |")

        if self._skills:
            skill_col = self._t("report-md-skill-col")
            count_col = self._t("report-md-count-col")
            lines.append(f"\n{self._t('report-md-skills-header', n=str(top_n))}")
            lines.append("")
            lines.append(f"| # | {skill_col} | {count_col} | % |")
            lines.append("|---|-------|-------|---|")
            for rank, sk, count, pct in self._rank_items(self._skills, top_n):
                lines.append(f"| {rank} | {sk} | {count} | {pct} |")

        if self._key_phrases:
            lines.append(f"\n{self._t('report-md-keyphrases-header')}")
            lines.append("")
            if self._key_phrases_style:
                lines.append(self._t("report-md-style", style=self._key_phrases_style))
                lines.append("")
            lines.append(self._key_phrases)

        return "\n".join(lines)

    def generate_txt(self, top_n: int = 25) -> str:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            self._t("report-txt-title", title=self._title),
            self._t("report-txt-date", date=now),
            self._t("report-txt-vacancies", count=str(self._vacancies_processed)),
            "",
        ]

        if self._keywords:
            lines.append(self._t("report-txt-keywords-header", n=str(top_n)))
            lines.append("-" * 50)
            for rank, kw, count, pct in self._rank_items(self._keywords, top_n):
                lines.append(f"  {rank:>3}. {kw:<30} {count:>4}  ({pct})")
            lines.append("")

        if self._skills:
            lines.append(self._t("report-txt-skills-header", n=str(top_n)))
            lines.append("-" * 50)
            for rank, sk, count, pct in self._rank_items(self._skills, top_n):
                lines.append(f"  {rank:>3}. {sk:<30} {count:>4}  ({pct})")
            lines.append("")

        if self._key_phrases:
            lines.append(self._t("report-txt-keyphrases-header"))
            lines.append("-" * 50)
            if self._key_phrases_style:
                lines.append(self._t("report-txt-style", style=self._key_phrases_style))
            lines.append(self._key_phrases)

        return "\n".join(lines)
