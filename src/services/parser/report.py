"""Report generator for parsing results in multiple formats."""

from datetime import UTC, datetime


class ReportGenerator:
    def __init__(
        self,
        vacancy_title: str,
        top_keywords: dict[str, int],
        top_skills: dict[str, int],
        vacancies_processed: int,
        key_phrases: str | None = None,
        key_phrases_style: str | None = None,
    ) -> None:
        self._title = vacancy_title
        self._keywords = top_keywords
        self._skills = top_skills
        self._vacancies_processed = vacancies_processed
        self._key_phrases = key_phrases
        self._key_phrases_style = key_phrases_style

    def generate_message(self, top_n: int = 25) -> str:
        lines = [
            f"<b>📊 Parsing Results: {self._title}</b>\n",
            f"Vacancies processed: {self._vacancies_processed}\n",
        ]

        if self._keywords:
            lines.append(f"<b>Top-{top_n} Keywords (AI):</b>")
            total = sum(self._keywords.values())
            for rank, (kw, count) in enumerate(
                sorted(self._keywords.items(), key=lambda x: -x[1])[:top_n],
                1,
            ):
                pct = f"{count / total * 100:.1f}%" if total else "—"
                lines.append(f"  {rank}. {kw} — {count} ({pct})")

        if self._skills:
            lines.append(f"\n<b>Top-{top_n} Skills (tags):</b>")
            total = sum(self._skills.values())
            for rank, (sk, count) in enumerate(
                sorted(self._skills.items(), key=lambda x: -x[1])[:top_n],
                1,
            ):
                pct = f"{count / total * 100:.1f}%" if total else "—"
                lines.append(f"  {rank}. {sk} — {count} ({pct})")

        if self._key_phrases:
            lines.append(f"\n<b>Key Phrases ({self._key_phrases_style or 'default'}):</b>")
            lines.append(self._key_phrases)

        return "\n".join(lines)

    def generate_md(self, top_n: int = 25) -> str:
        lines = [
            f"# Parsing Report: {self._title}\n",
            f"**Date:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC",
            f"**Vacancies processed:** {self._vacancies_processed}\n",
        ]

        if self._keywords:
            lines.append(f"## Top-{top_n} Keywords (AI)\n")
            lines.append("| # | Keyword | Count | % |")
            lines.append("|---|---------|-------|---|")
            total = sum(self._keywords.values())
            for rank, (kw, count) in enumerate(
                sorted(self._keywords.items(), key=lambda x: -x[1])[:top_n],
                1,
            ):
                pct = f"{count / total * 100:.1f}%" if total else "—"
                lines.append(f"| {rank} | {kw} | {count} | {pct} |")

        if self._skills:
            lines.append(f"\n## Top-{top_n} Skills (tags)\n")
            lines.append("| # | Skill | Count | % |")
            lines.append("|---|-------|-------|---|")
            total = sum(self._skills.values())
            for rank, (sk, count) in enumerate(
                sorted(self._skills.items(), key=lambda x: -x[1])[:top_n],
                1,
            ):
                pct = f"{count / total * 100:.1f}%" if total else "—"
                lines.append(f"| {rank} | {sk} | {count} | {pct} |")

        if self._key_phrases:
            lines.append("\n## Key Phrases\n")
            if self._key_phrases_style:
                lines.append(f"**Style:** {self._key_phrases_style}\n")
            lines.append(self._key_phrases)

        return "\n".join(lines)

    def generate_txt(self, top_n: int = 25) -> str:
        lines = [
            f"PARSING REPORT: {self._title}",
            f"Date: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC",
            f"Vacancies processed: {self._vacancies_processed}",
            "",
        ]

        if self._keywords:
            lines.append(f"TOP-{top_n} KEYWORDS (AI)")
            lines.append("-" * 50)
            total = sum(self._keywords.values())
            for rank, (kw, count) in enumerate(
                sorted(self._keywords.items(), key=lambda x: -x[1])[:top_n],
                1,
            ):
                pct = f"{count / total * 100:.1f}%" if total else "—"
                lines.append(f"  {rank:>3}. {kw:<30} {count:>4}  ({pct})")
            lines.append("")

        if self._skills:
            lines.append(f"TOP-{top_n} SKILLS (TAGS)")
            lines.append("-" * 50)
            total = sum(self._skills.values())
            for rank, (sk, count) in enumerate(
                sorted(self._skills.items(), key=lambda x: -x[1])[:top_n],
                1,
            ):
                pct = f"{count / total * 100:.1f}%" if total else "—"
                lines.append(f"  {rank:>3}. {sk:<30} {count:>4}  ({pct})")
            lines.append("")

        if self._key_phrases:
            lines.append("KEY PHRASES")
            lines.append("-" * 50)
            if self._key_phrases_style:
                lines.append(f"Style: {self._key_phrases_style}")
            lines.append(self._key_phrases)

        return "\n".join(lines)
