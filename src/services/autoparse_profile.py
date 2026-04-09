from src.models.work_experience import UserWorkExperience


def derive_tech_stack_from_experiences(experiences: list[UserWorkExperience]) -> list[str]:
    """Return a stable, deduplicated tech stack derived from work history."""
    seen: set[str] = set()
    result: list[str] = []
    for exp in experiences:
        for tech in exp.stack.split(","):
            normalized = tech.strip()
            lowered = normalized.lower()
            if normalized and lowered not in seen:
                seen.add(lowered)
                result.append(normalized)
    return result
