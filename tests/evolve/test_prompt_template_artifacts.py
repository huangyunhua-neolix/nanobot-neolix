from __future__ import annotations

from nanobot.evolve.prompt_template_artifacts import matching_prompt_template_snapshot
from tests.evolve.prompt_template_test_helpers import make_candidate, make_snapshot


def test_matching_prompt_template_snapshot_requires_skill_and_hash_match() -> None:
    snapshot = make_snapshot(
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Use concise answers.\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )
    candidate = make_candidate(snapshot, snapshot.body_text)

    assert matching_prompt_template_snapshot(candidate, [snapshot]) == snapshot

    wrong_skill = make_candidate(snapshot, snapshot.body_text, skill_name="other-skill")
    wrong_hash = make_candidate(snapshot, snapshot.body_text, baseline_snapshot_hash="wrong-hash")

    assert matching_prompt_template_snapshot(wrong_skill, [snapshot]) is None
    assert matching_prompt_template_snapshot(wrong_hash, [snapshot]) is None
    assert matching_prompt_template_snapshot(candidate, []) is None
