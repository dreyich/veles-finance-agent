"""Progressive Disclosure — load_skill tool (Phase 3.2).

Implements Hermes-style skill loading: the agent reads a short skill index
from the system prompt, then calls load_skill(name) to get the full workflow
only when it actually needs it.

Benefits:
  - Base system prompt shrinks from ~2500 to ~700 tokens
  - Agent pays context cost only for skills it actually uses
  - New skills can be added without touching the system prompt
  - Skills are plain Markdown files — editable without code changes
"""

from pathlib import Path
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

_SKILLS_DIR = Path(__file__).parent.parent.parent / "prompts" / "skills"


def _list_available_skills() -> list[str]:
    """Return stems of all .md files in the skills directory."""
    if not _SKILLS_DIR.exists():
        return []
    return sorted(f.stem for f in _SKILLS_DIR.glob("*.md"))


class LoadSkillInput(BaseModel):
    skill_name: str = Field(
        ...,
        description=(
            "Name of the skill to load. Available: equity_analysis, fx_macro, "
            "debt_sustainability, sandbox_patterns. "
            "Call this BEFORE starting any multi-step analysis."
        ),
    )


@tool("load_skill", args_schema=LoadSkillInput)
def load_skill(skill_name: str) -> str:
    """Load detailed workflow instructions for a specific financial analysis domain.

    Call this at the START of a complex analysis to get the full step-by-step
    blueprint. For simple queries (current rate, current price) — call data
    tools directly without loading a skill.

    Available skills:
    - equity_analysis   : Stock DD, DCF valuation, APPROVED/REJECTED verdict
    - fx_macro          : FX forecast, IRP, yield curves, capital flows
    - debt_sustainability : Government debt trajectory (IMF r-vs-g framework)
    - sandbox_patterns  : Python templates for Monte Carlo, FCF, sensitivity

    Args:
        skill_name: One of the available skill names above.

    Returns:
        Full Markdown workflow instructions for the requested skill.
    """
    skill_file = _SKILLS_DIR / f"{skill_name}.md"

    if skill_file.exists():
        content = skill_file.read_text(encoding="utf-8")
        return f"# Loaded skill: {skill_name}\n\n{content}"

    available = _list_available_skills()
    return (
        f"Skill '{skill_name}' not found.\n"
        f"Available skills: {', '.join(available) if available else 'none'}\n"
        f"Skills directory: {_SKILLS_DIR}"
    )
