"""Tests for the deterministic Curator proposal policy engine."""

from datetime import datetime, timezone

from nanobot.config.schema import CuratorConfig
from nanobot.curator.models import ApplyStatus, Confidence, CuratorAction
from nanobot.curator.policy import generate_proposals

NOW = datetime(2026, 6, 13, tzinfo=timezone.utc)


def _skill(name: str, origin: str = "agent", shadowed: list[str] | None = None) -> dict:
    return {
        "name": name,
        "effective_origin": origin,
        "shadowed_origins": shadowed or [],
        "path": f"/workspace/skills/{origin}/{name}/SKILL.md",
    }


def _telemetry(
    *,
    origin: str = "agent",
    views: int = 30,
    uses: int = 0,
    patches: int = 0,
    entry_created_at: str = "2026-05-01T00:00:00Z",
    last_use: str | None = None,
) -> dict:
    return {
        "origin": origin,
        "shadowed": [],
        "views": views,
        "uses": uses,
        "patches": patches,
        "entry_created_at": entry_created_at,
        "last_view": "2026-06-01T00:00:00Z",
        "last_use": last_use,
    }


def test_high_confidence_stale_agent_skill_becomes_delete_candidate() -> None:
    proposals = generate_proposals(
        visible_skills=[_skill("old-debug-helper")],
        telemetry_entries={"old-debug-helper": _telemetry()},
        metadata_by_name={"old-debug-helper": {}},
        config=CuratorConfig(),
        now=NOW,
        include_protected=False,
    )

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.action == CuratorAction.DELETE_CANDIDATE
    assert proposal.confidence == Confidence.HIGH
    assert proposal.apply_status == ApplyStatus.ELIGIBLE
    assert {reason.code for reason in proposal.reasons} >= {
        "zero_uses_after_views",
        "stale_since_created",
    }


def test_user_builtin_and_unknown_origins_are_protected() -> None:
    proposals = generate_proposals(
        visible_skills=[
            _skill("user-skill", "user"),
            _skill("builtin-skill", "builtin"),
            _skill("mystery"),
        ],
        telemetry_entries={
            "user-skill": _telemetry(origin="user"),
            "builtin-skill": _telemetry(origin="builtin"),
            "mystery": _telemetry(origin="unknown"),
        },
        metadata_by_name={"user-skill": {}, "builtin-skill": {}, "mystery": {}},
        config=CuratorConfig(),
        now=NOW,
        include_protected=True,
    )

    assert [p.action for p in proposals] == [
        CuratorAction.PROTECT,
        CuratorAction.PROTECT,
        CuratorAction.PROTECT,
    ]
    assert [p.apply_status for p in proposals] == [
        ApplyStatus.NOT_APPLICABLE,
        ApplyStatus.NOT_APPLICABLE,
        ApplyStatus.NOT_APPLICABLE,
    ]


def test_fresh_skill_is_not_delete_candidate() -> None:
    proposals = generate_proposals(
        visible_skills=[_skill("fresh")],
        telemetry_entries={"fresh": _telemetry(entry_created_at="2026-06-10T00:00:00Z")},
        metadata_by_name={"fresh": {}},
        config=CuratorConfig(),
        now=NOW,
        include_protected=True,
    )

    assert proposals[0].action == CuratorAction.KEEP
    assert proposals[0].apply_status == ApplyStatus.NOT_APPLICABLE


def test_recent_use_and_protect_list_prevent_deletion() -> None:
    proposals = generate_proposals(
        visible_skills=[_skill("recent"), _skill("protected")],
        telemetry_entries={
            "recent": _telemetry(uses=1, last_use="2026-06-12T00:00:00Z"),
            "protected": _telemetry(),
        },
        metadata_by_name={"recent": {}, "protected": {}},
        config=CuratorConfig(protect_list=["protected"]),
        now=NOW,
        include_protected=True,
    )

    assert [p.action for p in proposals] == [CuratorAction.PROTECT, CuratorAction.PROTECT]


def test_patch_history_and_shadowing_cap_delete_confidence_at_medium() -> None:
    proposals = generate_proposals(
        visible_skills=[_skill("patched", shadowed=["builtin"])],
        telemetry_entries={"patched": _telemetry(patches=1)},
        metadata_by_name={"patched": {"last_patched_at": "2026-05-01T00:00:00Z"}},
        config=CuratorConfig(),
        now=NOW,
        include_protected=False,
    )

    assert proposals[0].action == CuratorAction.DELETE_CANDIDATE
    assert proposals[0].confidence == Confidence.MEDIUM
    assert proposals[0].apply_status == ApplyStatus.NOT_REQUESTED


def test_merge_and_patch_candidates_are_report_only() -> None:
    proposals = generate_proposals(
        visible_skills=[
            _skill("summarize-data"),
            _skill("summarize-dataset"),
            _skill("churned"),
        ],
        telemetry_entries={
            "summarize-data": _telemetry(views=10),
            "summarize-dataset": _telemetry(views=10),
            "churned": _telemetry(views=100, uses=1, patches=3),
        },
        metadata_by_name={
            "summarize-data": {"description": "summarize data"},
            "summarize-dataset": {"description": "summarize dataset"},
            "churned": {"last_patched_at": "2026-05-01T00:00:00Z"},
        },
        config=CuratorConfig(),
        now=NOW,
        include_protected=False,
    )

    actions = {proposal.name: proposal.action for proposal in proposals}
    statuses = {proposal.name: proposal.apply_status for proposal in proposals}
    assert actions["summarize-data"] == CuratorAction.MERGE_CANDIDATE
    assert actions["churned"] == CuratorAction.PATCH_CANDIDATE
    assert statuses["summarize-data"] == ApplyStatus.NOT_REQUESTED
    assert statuses["churned"] == ApplyStatus.NOT_REQUESTED


def test_merge_reasons_do_not_include_token_lists_or_description_snippets() -> None:
    proposals = generate_proposals(
        visible_skills=[_skill("foo-bar"), _skill("foo-baz")],
        telemetry_entries={
            "foo-bar": _telemetry(views=10),
            "foo-baz": _telemetry(views=10),
        },
        metadata_by_name={
            "foo-bar": {"description": "A tool that does foo bar operations on data"},
            "foo-baz": {"description": "A tool that does foo baz operations on data"},
        },
        config=CuratorConfig(),
        now=NOW,
        include_protected=False,
    )

    merge_proposals = [p for p in proposals if p.action == CuratorAction.MERGE_CANDIDATE]
    assert len(merge_proposals) >= 1

    for proposal in merge_proposals:
        for reason in proposal.reasons:
            if reason.code == "merge_similarity":
                for key, val in reason.params.items():
                    # No token lists or description-derived strings — only numeric/string scalars
                    assert not isinstance(val, list), f"param {key!r} is a list"
                    assert not isinstance(val, dict), f"param {key!r} is a dict"
                    # Values must be simple scalars (int, float, str, bool)
                    # A string value should not look like a token list or description snippet
                    if isinstance(val, str):
                        assert len(val) < 100, (
                            f"param {key!r} value looks like a snippet: {val!r}"
                        )


def test_protect_pattern_via_fnmatch() -> None:
    proposals = generate_proposals(
        visible_skills=[_skill("prod-analytics"), _skill("prod-cleanup"), _skill("dev-tool")],
        telemetry_entries={
            "prod-analytics": _telemetry(),
            "prod-cleanup": _telemetry(),
            "dev-tool": _telemetry(),
        },
        metadata_by_name={"prod-analytics": {}, "prod-cleanup": {}, "dev-tool": {}},
        config=CuratorConfig(protect_patterns=["prod-*"]),
        now=NOW,
        include_protected=True,
    )

    actions = {p.name: p.action for p in proposals}
    assert actions["prod-analytics"] == CuratorAction.PROTECT
    assert actions["prod-cleanup"] == CuratorAction.PROTECT
    # dev-tool is not protected by pattern and is stale — should be delete candidate
    assert actions["dev-tool"] == CuratorAction.DELETE_CANDIDATE


def test_skills_with_not_enough_views_are_kept() -> None:
    proposals = generate_proposals(
        visible_skills=[_skill("low-views")],
        telemetry_entries={"low-views": _telemetry(views=5)},
        metadata_by_name={"low-views": {}},
        config=CuratorConfig(),
        now=NOW,
        include_protected=True,
    )

    assert proposals[0].action == CuratorAction.KEEP
    assert proposals[0].apply_status == ApplyStatus.NOT_APPLICABLE


def test_missing_telemetry_treats_origin_as_unknown_and_protects() -> None:
    """A skill with no telemetry entry should not be a high-confidence delete candidate."""
    proposals = generate_proposals(
        visible_skills=[_skill("ghost-skill")],
        telemetry_entries={},
        metadata_by_name={"ghost-skill": {}},
        config=CuratorConfig(),
        now=NOW,
        include_protected=True,
    )

    assert proposals[0].action == CuratorAction.PROTECT


def test_protected_skills_excluded_when_include_protected_false() -> None:
    proposals = generate_proposals(
        visible_skills=[_skill("user-skill", "user"), _skill("stale-agent")],
        telemetry_entries={
            "user-skill": _telemetry(origin="user"),
            "stale-agent": _telemetry(),
        },
        metadata_by_name={"user-skill": {}, "stale-agent": {}},
        config=CuratorConfig(),
        now=NOW,
        include_protected=False,
    )

    names = {p.name for p in proposals}
    assert "user-skill" not in names
    assert "stale-agent" in names


def test_recent_patch_prevents_delete() -> None:
    """A skill with a very recent last_patched_at should not be a delete candidate."""
    proposals = generate_proposals(
        visible_skills=[_skill("recently-patched")],
        telemetry_entries={"recently-patched": _telemetry(patches=1)},
        metadata_by_name={"recently-patched": {"last_patched_at": "2026-06-10T00:00:00Z"}},
        config=CuratorConfig(),
        now=NOW,
        include_protected=True,
    )

    # Recent patch activity means we should keep rather than delete
    assert proposals[0].action in {CuratorAction.KEEP, CuratorAction.PROTECT}


def test_shadowed_origins_cap_confidence_at_medium() -> None:
    proposals = generate_proposals(
        visible_skills=[_skill("shadowed-skill", shadowed=["user"])],
        telemetry_entries={"shadowed-skill": _telemetry()},
        metadata_by_name={"shadowed-skill": {}},
        config=CuratorConfig(),
        now=NOW,
        include_protected=False,
    )

    assert proposals[0].action == CuratorAction.DELETE_CANDIDATE
    assert proposals[0].confidence == Confidence.MEDIUM
    assert proposals[0].apply_status == ApplyStatus.NOT_REQUESTED
