"""Deterministic Curator proposal policy.

Pure function: no file writes, no provider calls, no command imports.
All protection and scoring rules live here.

Protection hierarchy
--------------------
Hard protection (blocks ALL proposals including advisory merge/patch):
  - Non-agent visible origin (user, builtin)
  - Telemetry origin unknown
  - Protect list (exact match)
  - Protect patterns (fnmatch glob)
  - Always-on metadata marker

Recent-use protection (soft): recently-used skills produce PROTECT/KEEP only;
they are also excluded from the merge-candidate scan so no advisory proposal
fires for them.  High-confidence delete candidates are excluded from the merge
scan as well (DELETE_CANDIDATE takes precedence).  Patch advisory proposals
fire independently of recent-use status.
"""

from __future__ import annotations

import fnmatch
import re
from datetime import datetime, timezone
from typing import Any

from nanobot.config.schema import CuratorConfig
from nanobot.curator.models import (
    ApplyStatus,
    Confidence,
    CuratorAction,
    CuratorProposal,
    ProposalReason,
)

UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Origins that are always hard-protected regardless of telemetry.
_PROTECTED_ORIGINS = {"user", "builtin"}


def generate_proposals(
    *,
    visible_skills: list[dict[str, Any]],
    telemetry_entries: dict[str, dict[str, Any]],
    metadata_by_name: dict[str, dict[str, Any]],
    config: CuratorConfig,
    now: datetime,
    include_protected: bool,
) -> list[CuratorProposal]:
    """Return a deterministic list of CuratorProposals for the given skill set.

    Args:
        visible_skills: Skill dicts from SkillsLoader (name, effective_origin, shadowed_origins, path).
        telemetry_entries: Raw telemetry dict keyed by skill name.
        metadata_by_name: Per-skill metadata dict keyed by skill name.
        config: CuratorConfig from the agent configuration.
        now: Current UTC datetime (injected for determinism).
        include_protected: If False, PROTECT and KEEP proposals are omitted from output.

    Returns:
        List of proposals.  Order mirrors visible_skills.
    """
    # Build merge candidates map: scans non-hard-protected, non-recently-used,
    # non-high-confidence-delete agent skills.
    _merge_map: dict[str, tuple[str, float]] = _build_merge_candidates(
        visible_skills=visible_skills,
        telemetry_entries=telemetry_entries,
        metadata_by_name=metadata_by_name,
        config=config,
        now=now,
    )

    proposals: list[CuratorProposal] = []
    for skill in visible_skills:
        name = str(skill["name"])
        telemetry = telemetry_entries.get(name, _empty_telemetry())
        metadata = metadata_by_name.get(name) or {}

        proposal = _proposal_for_skill(
            skill=skill,
            telemetry=telemetry,
            metadata=metadata,
            merge_entry=_merge_map.get(name),
            config=config,
            now=now,
        )

        if not include_protected and proposal.action in {CuratorAction.PROTECT, CuratorAction.KEEP}:
            continue
        proposals.append(proposal)

    return proposals


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_utc(value: str | None) -> datetime | None:
    """Parse a UTC ISO-8601 string to a timezone-aware datetime, or return None."""
    if not value:
        return None
    try:
        return datetime.strptime(value, UTC_FORMAT).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _age_days(now: datetime, value: str | None) -> int | None:
    """Return whole days between value and now, or None if value is missing/malformed."""
    dt = _parse_utc(value)
    if dt is None:
        return None
    delta = now - dt
    return max(0, delta.days)


def _empty_telemetry() -> dict[str, Any]:
    """Return a zero-telemetry sentinel for a skill with no history."""
    return {
        "origin": "unknown",
        "shadowed": [],
        "views": 0,
        "uses": 0,
        "patches": 0,
        "entry_created_at": None,
        "last_view": None,
        "last_use": None,
    }


def _is_always_on(metadata: dict[str, Any]) -> bool:
    """Return True when the skill is marked always-on at the top-level or nested metadata."""
    if metadata.get("always") is True:
        return True
    nested = metadata.get("metadata")
    if isinstance(nested, dict):
        if nested.get("always") is True:
            return True
        nanobot_ns = nested.get("nanobot")
        if isinstance(nanobot_ns, dict) and nanobot_ns.get("always") is True:
            return True
    return False


def _is_recent_use(telemetry: dict[str, Any], config: CuratorConfig, now: datetime) -> bool:
    """Return True when the skill has been used recently or exceeds max_uses threshold."""
    uses = int(telemetry.get("uses", 0))
    if uses > config.max_uses_for_delete:
        return True
    last_use = telemetry.get("last_use")
    if last_use:
        age = _age_days(now, last_use)
        if age is not None and age < config.stale_days:
            return True
    return False


def _effective_origin(skill: dict[str, Any], telemetry: dict[str, Any]) -> str:
    """Resolve the visible origin, preferring skill-level then telemetry."""
    return str(skill.get("effective_origin") or telemetry.get("origin") or "unknown")


def _hard_protection_reasons(
    name: str,
    skill: dict[str, Any],
    telemetry: dict[str, Any],
    metadata: dict[str, Any],
    config: CuratorConfig,
) -> list[ProposalReason]:
    """Return reason codes for immutable protections (origin, list, pattern, always-on).

    Hard protections block ALL proposals, including advisory merge and patch candidates.
    """
    origin = _effective_origin(skill, telemetry)

    # Non-agent visible origin
    if origin in _PROTECTED_ORIGINS:
        return [ProposalReason(code="protected_origin", params={"origin": origin})]

    # Telemetry unknown origin
    telemetry_origin = str(telemetry.get("origin") or "unknown")
    if telemetry_origin == "unknown":
        return [ProposalReason(code="protected_unknown_origin", params={})]

    # Protect list (exact match)
    if name in config.protect_list:
        return [ProposalReason(code="protected_name", params={})]

    # Protect patterns (fnmatch glob)
    for pattern in config.protect_patterns:
        if fnmatch.fnmatch(name, pattern):
            return [ProposalReason(code="protected_pattern", params={"pattern": pattern})]

    # Always-on metadata marker
    if _is_always_on(metadata):
        return [ProposalReason(code="protected_always_on", params={})]

    return []


def _delete_candidate(
    name: str,
    skill: dict[str, Any],
    telemetry: dict[str, Any],
    metadata: dict[str, Any],
    config: CuratorConfig,
    now: datetime,
) -> tuple[Confidence, list[ProposalReason]] | None:
    """Evaluate whether this agent skill qualifies as a delete candidate.

    Returns (confidence, reasons) or None if the skill does not qualify.
    Soft protection (recent_use) is checked here; hard protection is checked upstream.
    """
    views = int(telemetry.get("views", 0))
    uses = int(telemetry.get("uses", 0))
    patches = int(telemetry.get("patches", 0))
    entry_created_at = telemetry.get("entry_created_at")
    last_use = telemetry.get("last_use")
    shadowed_origins: list[str] = list(skill.get("shadowed_origins") or [])

    reasons: list[ProposalReason] = []
    confidence = Confidence.HIGH

    # --- Soft protection: recent use ---
    if _is_recent_use(telemetry, config, now):
        return None

    # --- Mandatory gating checks ---

    # Must have reached minimum view threshold
    if views < config.min_views_for_delete:
        return None

    # entry_created_at must exist and be stale enough
    age_created = _age_days(now, entry_created_at)
    if age_created is None or age_created < config.stale_days:
        return None

    # --- Core reasons (all gating conditions passed) ---
    reasons.append(ProposalReason(code="zero_uses_after_views", params={"views": views, "uses": uses}))
    reasons.append(ProposalReason(code="stale_since_created", params={"days": age_created}))

    if last_use is not None:
        age_last_use = _age_days(now, last_use)
        if age_last_use is not None and age_last_use >= config.stale_days:
            reasons.append(ProposalReason(code="stale_since_last_use", params={"days": age_last_use}))

    # --- Confidence reducers ---

    # Patch activity: recent patch prevents delete; stale patch caps confidence
    last_patched_at = metadata.get("last_patched_at")
    if last_patched_at:
        age_patched = _age_days(now, last_patched_at)
        if age_patched is None:
            # Malformed timestamp — cap at medium
            confidence = Confidence.MEDIUM
            reasons.append(ProposalReason(code="patch_history_caps_confidence", params={}))
        elif age_patched < config.stale_days:
            # Recent patch activity — not a delete candidate
            return None
        else:
            # Stale patch history — cap confidence
            confidence = Confidence.MEDIUM
            reasons.append(
                ProposalReason(code="patch_history_caps_confidence", params={"days": age_patched})
            )
    elif patches > 0:
        # Has patch counter but no last_patched_at timestamp — cap at medium
        confidence = Confidence.MEDIUM
        reasons.append(ProposalReason(code="patch_history_caps_confidence", params={"patches": patches}))

    # Shadowed origins: unmasking risk caps confidence
    if shadowed_origins:
        if confidence == Confidence.HIGH:
            confidence = Confidence.MEDIUM
        reasons.append(
            ProposalReason(
                code="shadow_unmasking_caps_confidence",
                params={"count": len(shadowed_origins)},
            )
        )

    return confidence, reasons


def _word_tokens(name: str, metadata: dict[str, Any]) -> set[str]:
    """Return the set of lowercased word tokens from a skill name and description.

    Splits on non-alphanumeric/non-underscore boundaries, matching the spec §6.1
    requirement for word-token Jaccard similarity rather than character bigrams.
    """
    description = metadata.get("description") or ""
    combined = f"{name} {description}".strip().lower()
    return set(re.split(r"[^a-z0-9_]+", combined)) - {""}


def _jaccard(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def _build_merge_candidates(
    *,
    visible_skills: list[dict[str, Any]],
    telemetry_entries: dict[str, dict[str, Any]],
    metadata_by_name: dict[str, dict[str, Any]],
    config: CuratorConfig,
    now: datetime,
) -> dict[str, tuple[str, float]]:
    """Return a mapping name -> (partner_name, similarity) for skills that are merge candidates.

    Per spec §6.2: recently-used skills (soft-protected) are excluded from the merge scan
    because they are in active use — merging them could disrupt ongoing workflows.
    High-confidence delete candidates are also excluded: if a skill satisfies high-confidence
    delete conditions, deletion would not be safer than merge; DELETE_CANDIDATE takes precedence.
    Only the best partner per skill is recorded; pairs are recorded in both directions.
    """
    candidate_names: list[str] = []
    for skill in visible_skills:
        name = str(skill["name"])
        telemetry = telemetry_entries.get(name, _empty_telemetry())
        metadata = metadata_by_name.get(name) or {}

        # Only agent skills that pass hard protection participate
        hard_reasons = _hard_protection_reasons(name, skill, telemetry, metadata, config)
        if hard_reasons:
            continue

        # Recently-used skills are soft-protected — exclude from merge scan (spec §6.2)
        if _is_recent_use(telemetry, config, now):
            continue

        # High-confidence delete candidates: DELETE_CANDIDATE takes precedence over merge
        delete_result = _delete_candidate(name, skill, telemetry, metadata, config, now)
        if delete_result is not None and delete_result[0] == Confidence.HIGH:
            continue

        candidate_names.append(name)

    # Compute word-token sets for similarity comparison (spec §6.1: word-token Jaccard)
    token_sets: dict[str, set[str]] = {
        name: _word_tokens(name, metadata_by_name.get(name) or {})
        for name in candidate_names
    }

    merge_threshold = 0.6
    merge_map: dict[str, tuple[str, float]] = {}

    for i, name_a in enumerate(candidate_names):
        best_sim = 0.0
        best_partner: str | None = None
        tokens_a = token_sets[name_a]
        for name_b in candidate_names[i + 1 :]:
            sim = _jaccard(tokens_a, token_sets[name_b])
            if sim >= merge_threshold and sim > best_sim:
                best_sim = sim
                best_partner = name_b
        if best_partner is not None:
            merge_map[name_a] = (best_partner, best_sim)
            if best_partner not in merge_map:
                merge_map[best_partner] = (name_a, best_sim)

    return merge_map


def _patch_candidate(
    telemetry: dict[str, Any],
    config: CuratorConfig,
) -> list[ProposalReason] | None:
    """Return reasons if this skill is a patch churn candidate, else None.

    Advisory proposal: fires regardless of recent use (soft protection does not apply).
    """
    patches = int(telemetry.get("patches", 0))
    if patches < 3:
        return None

    views = int(telemetry.get("views", 0))
    uses = int(telemetry.get("uses", 0))

    # Low subsequent use ratio check
    if views > 0:
        ratio = uses / views
        if ratio < config.low_use_ratio:
            return [
                ProposalReason(
                    code="patch_churn_low_use",
                    params={"patches": patches, "uses": uses, "views": views},
                )
            ]
    elif uses == 0:
        return [
            ProposalReason(
                code="patch_churn_low_use",
                params={"patches": patches, "uses": uses, "views": views},
            )
        ]

    return None


def _apply_status_for(action: CuratorAction, confidence: Confidence) -> ApplyStatus:
    if action == CuratorAction.DELETE_CANDIDATE and confidence == Confidence.HIGH:
        return ApplyStatus.ELIGIBLE
    if action == CuratorAction.DELETE_CANDIDATE:
        return ApplyStatus.NOT_REQUESTED
    if action in {CuratorAction.MERGE_CANDIDATE, CuratorAction.PATCH_CANDIDATE}:
        return ApplyStatus.NOT_REQUESTED
    return ApplyStatus.NOT_APPLICABLE


def _proposal_for_skill(
    *,
    skill: dict[str, Any],
    telemetry: dict[str, Any],
    metadata: dict[str, Any],
    merge_entry: tuple[str, float] | None,
    config: CuratorConfig,
    now: datetime,
) -> CuratorProposal:
    name = str(skill["name"])
    origin = _effective_origin(skill, telemetry)

    # Normalize origin to allowed literals
    if origin not in {"user", "agent", "builtin", "unknown"}:
        origin = "unknown"

    # Hard protections block all proposals
    hard_reasons = _hard_protection_reasons(name, skill, telemetry, metadata, config)
    if hard_reasons:
        return CuratorProposal(
            name=name,
            origin=origin,
            action=CuratorAction.PROTECT,
            confidence=Confidence.HIGH,
            reasons=hard_reasons,
            protected=True,
            apply_status=ApplyStatus.NOT_APPLICABLE,
        )

    # Check advisory merge candidate (report-only; bypasses soft protection)
    if merge_entry is not None:
        partner_name, similarity = merge_entry
        merge_reasons = [
            ProposalReason(
                code="merge_similarity",
                # Only numeric similarity and partner name (a skill identifier, not body/description)
                params={"partner": partner_name, "similarity": round(similarity, 2)},
            )
        ]
        return CuratorProposal(
            name=name,
            origin=origin,
            action=CuratorAction.MERGE_CANDIDATE,
            confidence=Confidence.MEDIUM,
            reasons=merge_reasons,
            protected=False,
            apply_status=ApplyStatus.NOT_REQUESTED,
        )

    # Check advisory patch churn candidate (report-only; bypasses soft protection)
    patch_reasons = _patch_candidate(telemetry, config)
    if patch_reasons is not None:
        return CuratorProposal(
            name=name,
            origin=origin,
            action=CuratorAction.PATCH_CANDIDATE,
            confidence=Confidence.LOW,
            reasons=patch_reasons,
            protected=False,
            apply_status=ApplyStatus.NOT_REQUESTED,
        )

    # Check delete candidate (applies soft protection internally)
    delete_result = _delete_candidate(name, skill, telemetry, metadata, config, now)
    if delete_result is not None:
        confidence, reasons = delete_result
        return CuratorProposal(
            name=name,
            origin=origin,
            action=CuratorAction.DELETE_CANDIDATE,
            confidence=confidence,
            reasons=reasons,
            protected=False,
            apply_status=_apply_status_for(CuratorAction.DELETE_CANDIDATE, confidence),
        )

    # Soft-protected (recent use) or otherwise non-candidate: protect
    if _is_recent_use(telemetry, config, now):
        return CuratorProposal(
            name=name,
            origin=origin,
            action=CuratorAction.PROTECT,
            confidence=Confidence.HIGH,
            reasons=[ProposalReason(code="recent_use", params={})],
            protected=True,
            apply_status=ApplyStatus.NOT_APPLICABLE,
        )

    # Default: keep
    views = int(telemetry.get("views", 0))
    keep_reasons: list[ProposalReason] = []
    if views < config.min_views_for_delete:
        keep_reasons.append(
            ProposalReason(
                code="not_enough_views",
                params={"views": views, "min": config.min_views_for_delete},
            )
        )
    else:
        age_created = _age_days(now, telemetry.get("entry_created_at"))
        if age_created is not None and age_created < config.stale_days:
            keep_reasons.append(ProposalReason(code="too_fresh", params={"days": age_created}))

    return CuratorProposal(
        name=name,
        origin=origin,
        action=CuratorAction.KEEP,
        confidence=Confidence.HIGH,
        reasons=keep_reasons,
        protected=False,
        apply_status=ApplyStatus.NOT_APPLICABLE,
    )
