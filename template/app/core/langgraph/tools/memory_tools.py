"""Procedural memory tools — let the agent persist reusable trading skills.

Implements the 'Closed Learning Loop': after analysing a trade or lesson the
agent can call save_trading_skill to write a structured Markdown file into
app/skills/. These files act as the agent's long-term procedural memory and
can be loaded back into future sessions.
"""

import os
import re
from datetime import datetime

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "skills")


def _safe_filename(name: str) -> str:
    """Convert an arbitrary skill name to a safe .md filename."""
    name = name.strip().lower()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s]+", "_", name)
    return name + ".md"


class SaveSkillInput(BaseModel):
    """Input schema for save_trading_skill."""

    skill_name: str = Field(
        ...,
        description="Short snake_case identifier for the skill (e.g. 'earnings_hedge_rule').",
        min_length=2,
        max_length=80,
    )
    skill_content: str = Field(
        ...,
        description="Full skill content in Markdown format. Must include: what the rule is, why it exists, and concrete action steps.",
        min_length=20,
    )

    @field_validator("skill_name")
    @classmethod
    def no_path_traversal(cls, v: str) -> str:
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("skill_name must not contain path separators.")
        return v


@tool("save_trading_skill", args_schema=SaveSkillInput)
def save_trading_skill(skill_name: str, skill_content: str) -> str:
    """Save a reusable trading skill or rule to the agent's procedural memory.

    Use this tool whenever you:
    - Analyse a trading mistake or loss and derive a rule to prevent recurrence
    - Identify a repeatable strategy or decision framework worth documenting
    - Learn a new financial principle that should be remembered across sessions
    - Are explicitly asked to 'save', 'remember', or 'document' a trading rule

    The skill is saved as a Markdown file in the agent's skills library and
    will persist across all future sessions.

    Args:
        skill_name:    Short identifier for the skill (e.g. 'earnings_hedge_rule').
        skill_content: Full skill description in Markdown format. Include:
                       - What the rule is
                       - Why it was created (the lesson / incident)
                       - Concrete action steps to follow
                       - Any relevant examples or thresholds

    Returns:
        Confirmation string with the path where the skill was saved.
    """
    os.makedirs(SKILLS_DIR, exist_ok=True)

    filename = _safe_filename(skill_name)
    filepath = os.path.join(SKILLS_DIR, filename)

    header = (
        f"---\n"
        f"skill: {skill_name}\n"
        f"created_at: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"---\n\n"
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(header + skill_content.strip() + "\n")

    return (
        f"Skill '{skill_name}' saved successfully to procedural memory.\n"
        f"File: app/skills/{filename}\n"
        f"Size: {len(skill_content)} characters\n"
        f"This rule will be available in all future sessions."
    )


@tool("list_trading_skills")
def list_trading_skills() -> str:
    """List all trading skills currently saved in the agent's procedural memory.

    Use this tool when the user asks what rules or skills the agent has learned,
    or before making a trading decision to check if a relevant rule already exists.

    Returns:
        A formatted list of all saved skill files with their names.
    """
    os.makedirs(SKILLS_DIR, exist_ok=True)

    files = [f for f in os.listdir(SKILLS_DIR) if f.endswith(".md") and f != ".gitkeep"]

    if not files:
        return "No trading skills saved yet. Use save_trading_skill to document your first rule."

    skill_list = "\n".join(f"  - {f.replace('.md', '')}" for f in sorted(files))
    return f"Saved trading skills ({len(files)} total):\n{skill_list}"
