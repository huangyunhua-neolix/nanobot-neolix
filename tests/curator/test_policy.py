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
    # Use descriptions with many shared tokens so word-token Jaccard reaches >=0.6.
    # "summarizes data tables by column" vs "summarizes data tables by row":
    # Tokens for "summarize-data summarizes data tables by column":
    #   {summarize, data, summarizes, tables, by, column}  (name + description words)
    # Tokens for "summarize-dataset summarizes data tables by row":
    #   {summarize, dataset, summarizes, tables, by, row}
    # intersection={"summarize","summarizes","tables","by","data"} varies by tokenization;
    # key point: both skills share the description stem so Jaccard lands above 0.6.
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
            "summarize-data": {"description": "summarizes data tables by column"},
            "summarize-dataset": {"description": "summarizes data tables by row"},
            "churned": {"last_patched_at": "2026-05-01T00:00:00Z"},
        },
        config=CuratorConfig(),
        now=NOW,
        include_protected=False,
    )

    actions = {proposal.name: proposal.action for proposal in proposals}
    statuses = {proposal.name: proposal.apply_status for proposal in proposals}
    assert actions["summarize-data"] == CuratorAction.MERGE_CANDIDATE
    assert actions["summarize-dataset"] == CuratorAction.MERGE_CANDIDATE  # both sides of pair
    assert actions["churned"] == CuratorAction.PATCH_CANDIDATE
    assert statuses["summarize-data"] == ApplyStatus.NOT_REQUESTED
    assert statuses["summarize-dataset"] == ApplyStatus.NOT_REQUESTED
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


def test_recently_used_similar_skill_is_protected_not_merge_candidate() -> None:
    """Spec §6.2: recently-used skills must produce PROTECT/KEEP, not MERGE_CANDIDATE.

    A recently-used skill must not participate in the merge scan even if a very similar
    skill exists. include_protected=True shows it as PROTECT; include_protected=False omits it.
    """
    shared_desc = "summarizes data tables by column for reporting"
    # skill-a is recently used (uses=1 exceeds max_uses_for_delete=0)
    proposals_with = generate_proposals(
        visible_skills=[_skill("skill-a"), _skill("skill-b")],
        telemetry_entries={
            "skill-a": _telemetry(views=10, uses=1, last_use="2026-06-12T00:00:00Z"),
            "skill-b": _telemetry(views=10),
        },
        metadata_by_name={
            "skill-a": {"description": shared_desc},
            "skill-b": {"description": shared_desc},
        },
        config=CuratorConfig(),
        now=NOW,
        include_protected=True,
    )

    actions = {p.name: p.action for p in proposals_with}
    # skill-a is recently-used → must be PROTECT (soft protection), not MERGE_CANDIDATE
    assert actions["skill-a"] in {CuratorAction.PROTECT, CuratorAction.KEEP}
    assert actions["skill-a"] != CuratorAction.MERGE_CANDIDATE

    # With include_protected=False, skill-a is omitted from output
    proposals_without = generate_proposals(
        visible_skills=[_skill("skill-a"), _skill("skill-b")],
        telemetry_entries={
            "skill-a": _telemetry(views=10, uses=1, last_use="2026-06-12T00:00:00Z"),
            "skill-b": _telemetry(views=10),
        },
        metadata_by_name={
            "skill-a": {"description": shared_desc},
            "skill-b": {"description": shared_desc},
        },
        config=CuratorConfig(),
        now=NOW,
        include_protected=False,
    )

    names_without = {p.name for p in proposals_without}
    assert "skill-a" not in names_without, "recently-used skill must be omitted when include_protected=False"


def test_high_confidence_delete_candidate_excluded_from_merge_scan() -> None:
    """A stale zero-use skill that meets high-confidence delete conditions must remain
    DELETE_CANDIDATE with apply_status ELIGIBLE even when a similar skill exists.
    DELETE_CANDIDATE takes precedence over MERGE_CANDIDATE.
    """
    # stale-skill: views=30, uses=0, created 43 days ago → high-confidence delete
    # similar-skill: views=10 (below min_views_for_delete=30) → not a delete candidate
    proposals = generate_proposals(
        visible_skills=[_skill("stale-skill"), _skill("similar-skill")],
        telemetry_entries={
            "stale-skill": _telemetry(views=30, uses=0),
            "similar-skill": _telemetry(views=10, uses=0),
        },
        metadata_by_name={
            "stale-skill": {"description": "summarizes data tables by column for reporting"},
            "similar-skill": {"description": "summarizes data tables by column for reporting"},
        },
        config=CuratorConfig(),
        now=NOW,
        include_protected=False,
    )

    actions = {p.name: p.action for p in proposals}
    # stale-skill satisfies high-confidence delete → must not become MERGE_CANDIDATE
    assert actions["stale-skill"] == CuratorAction.DELETE_CANDIDATE
    stale_proposal = next(p for p in proposals if p.name == "stale-skill")
    assert stale_proposal.confidence == Confidence.HIGH
    assert stale_proposal.apply_status == ApplyStatus.ELIGIBLE


def test_medium_confidence_delete_candidate_becomes_merge_candidate() -> None:
    """Medium/low-confidence delete candidates are NOT excluded from the merge scan.

    Only high-confidence deletes take precedence over MERGE_CANDIDATE.
    A skill with stale patch history (caps confidence at MEDIUM) that has a similar
    partner must become MERGE_CANDIDATE with apply_status=NOT_REQUESTED, not
    DELETE_CANDIDATE, because the advisory merge supersedes the weaker delete signal.

    Also verifies that merge reason params are plain scalars (no token lists or
    description snippets).
    """
    # medium-patched: has stale patch history → confidence capped at MEDIUM → not excluded
    # from merge scan.  Both skills share the same description → Jaccard >= 0.6.
    shared_desc = "generates pdf reports from structured data by column"
    proposals = generate_proposals(
        visible_skills=[_skill("medium-patched"), _skill("medium-twin")],
        telemetry_entries={
            "medium-patched": _telemetry(views=30, uses=0, patches=1),
            "medium-twin": _telemetry(views=10, uses=0),
        },
        metadata_by_name={
            # Stale last_patched_at: 43 days ago (stale_days default is 30) → caps at MEDIUM
            "medium-patched": {"description": shared_desc, "last_patched_at": "2026-05-01T00:00:00Z"},
            "medium-twin": {"description": shared_desc},
        },
        config=CuratorConfig(),
        now=NOW,
        include_protected=False,
    )

    actions = {p.name: p.action for p in proposals}
    # medium-patched is a MEDIUM-confidence delete candidate but is not excluded from the
    # merge scan, so the advisory merge (similarity > delete) takes precedence.
    assert actions["medium-patched"] == CuratorAction.MERGE_CANDIDATE, (
        "MEDIUM-confidence delete must not block merge; only HIGH-confidence delete takes precedence"
    )

    medium_proposal = next(p for p in proposals if p.name == "medium-patched")
    # Advisory merge is report-only
    assert medium_proposal.apply_status == ApplyStatus.NOT_REQUESTED

    # Reason params must not contain token lists or description text
    for reason in medium_proposal.reasons:
        if reason.code == "merge_similarity":
            for key, val in reason.params.items():
                assert not isinstance(val, list), f"param {key!r} must not be a list"
                assert not isinstance(val, dict), f"param {key!r} must not be a dict"


def test_word_token_jaccard_reaches_threshold_with_shared_descriptions() -> None:
    """Confirm the word-token Jaccard implementation correctly identifies similarity.

    report-generator tokens: {report, generator, generates, pdf, reports, from, structured, data, by, column}
    report-builder tokens:   {report, builder,   generates, pdf, reports, from, structured, data, by, row}
    intersection=8, union=12 → Jaccard = 8/12 ≈ 0.667 >= 0.6 threshold.
    """
    proposals = generate_proposals(
        visible_skills=[_skill("report-generator"), _skill("report-builder")],
        telemetry_entries={
            "report-generator": _telemetry(views=10),
            "report-builder": _telemetry(views=10),
        },
        metadata_by_name={
            "report-generator": {"description": "generates pdf reports from structured data by column"},
            "report-builder": {"description": "generates pdf reports from structured data by row"},
        },
        config=CuratorConfig(),
        now=NOW,
        include_protected=False,
    )

    merge_proposals = [p for p in proposals if p.action == CuratorAction.MERGE_CANDIDATE]
    assert len(merge_proposals) == 2, "both skills in a similar pair must be MERGE_CANDIDATE"
    names = {p.name for p in merge_proposals}
    assert "report-generator" in names
    assert "report-builder" in names
