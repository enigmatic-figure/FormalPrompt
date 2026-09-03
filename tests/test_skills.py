from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

SKILL_ROOT = Path(__file__).parents[1] / "skills"
EXPECTED_SKILLS = {
    "agent-canvas-authoring",
    "formalprompt-facilitation",
    "formalprompt-handoff",
    "formalprompt-initialization-lifecycle",
}


@pytest.mark.parametrize("name", sorted(EXPECTED_SKILLS))
def test_agent_skill_has_valid_compact_frontmatter_and_procedure(name):
    path = SKILL_ROOT / name / "SKILL.md"
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    match = re.search(r"\n---\s*\n", content[4:])
    assert match is not None
    end = match.start() + 4
    frontmatter = yaml.safe_load(content[4:end])
    assert frontmatter["name"] == name
    assert frontmatter["description"].endswith(".")
    assert len(frontmatter["description"]) <= 60
    assert set(frontmatter) <= {"name", "description", "license", "metadata", "allowed-tools"}
    assert "## When to Use" in content
    assert "## Procedure" in content
    assert "## Pitfalls" in content
    assert "## Verification" in content


def test_authoring_skill_points_to_protocol_and_validation_command():
    content = (SKILL_ROOT / "agent-canvas-authoring" / "SKILL.md").read_text(encoding="utf-8")
    assert "docs/protocol.md" in content
    assert "formalprompt validate" in content
    assert "--renderer carbonyl" in content


def test_handoff_skill_forbids_importing_full_deliberation_by_default():
    content = (SKILL_ROOT / "formalprompt-handoff" / "SKILL.md").read_text(encoding="utf-8")
    assert "Do not load `events.jsonl`" in content
