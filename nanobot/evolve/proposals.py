from __future__ import annotations

import json
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback keeps transition guards active.
    fcntl = None

from pydantic import Field, field_validator

from nanobot.curator.models import CuratorAction, CuratorProposal
from nanobot.evolve._base import FrozenEvolveBase
from nanobot.evolve.artifacts import atomic_write_text
from nanobot.evolve.harness import OfflineHarness
from nanobot.evolve.privacy.redact import redact
from nanobot.evolve.schemas import EvolutionProposalContext, RunManifest

ProposalSource = Literal["manual", "curator", "dream"]
ProposalStatus = Literal["proposed", "running", "completed", "failed"]

_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
_PROPOSAL_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
_SKILL_NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
_MIN_PREFIX_LENGTH = len("evolve-000000")
_EVOLUTION_ACTIONS = {CuratorAction.PATCH_CANDIDATE, CuratorAction.MERGE_CANDIDATE}
_LOCKS: dict[Path, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


@contextmanager
def _proposal_lock(path: Path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    with _LOCKS_GUARD:
        thread_lock = _LOCKS.setdefault(lock_path, threading.Lock())
    with thread_lock:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


class EvolutionProposal(FrozenEvolveBase):
    schema_version: Literal["1"] = "1"
    proposal_id: str
    created_at: datetime
    source: ProposalSource
    skill_name: str
    rationale_redacted: str = Field(min_length=1, max_length=4000)
    trigger_ref: str | None = Field(default=None, max_length=500)
    status: ProposalStatus = "proposed"
    run_id: str | None = None
    manifest_path: str | None = None
    error_redacted: str | None = Field(default=None, max_length=1000)

    @field_validator("skill_name")
    @classmethod
    def _skill_name_safe(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("skill_name must not be empty")
        if not _SKILL_NAME_RE.fullmatch(value):
            raise ValueError("skill_name must contain only letters, numbers, '.', '_', or '-'")
        if ".." in value:
            raise ValueError("skill_name must not contain '..'")
        return value


class EvolutionRunResult(FrozenEvolveBase):
    proposal: EvolutionProposal
    manifest: RunManifest | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_id_part(value: str) -> str:
    value = _SAFE_ID_RE.sub("-", value.strip()).strip("-").lower()
    return value or "proposal"


def _validate_lookup_id(value: str, *, allow_prefix: bool) -> str:
    value = value.strip()
    if not value:
        raise ValueError("proposal id must not be empty")
    if not _PROPOSAL_ID_RE.fullmatch(value):
        raise ValueError("proposal id must contain only letters, numbers, '.', '_', or '-'")
    if allow_prefix and len(value) < _MIN_PREFIX_LENGTH:
        raise ValueError(f"proposal id prefix must be at least {_MIN_PREFIX_LENGTH} characters")
    return value


def _relative_to_workspace(path: Path, workspace: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        return redact(str(path)).text


class ProposalStore:
    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        self.proposals_dir = self.workspace / "evals" / "proposals"
        self.proposals_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        source: ProposalSource,
        skill_name: str,
        rationale: str,
        now: datetime | None = None,
        trigger_ref: str | None = None,
    ) -> EvolutionProposal:
        created_at = now or _utc_now()
        proposal_id = self._generate_id(skill_name, created_at)
        proposal = EvolutionProposal(
            proposal_id=proposal_id,
            created_at=created_at,
            source=source,
            skill_name=skill_name,
            rationale_redacted=redact(rationale).text[:4000],
            trigger_ref=redact(trigger_ref).text[:500] if trigger_ref else None,
        )
        self.write(proposal)
        return proposal

    def write(self, proposal: EvolutionProposal) -> None:
        path = self._path_for_id(proposal.proposal_id)
        text = json.dumps(proposal.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        atomic_write_text(path, f"{text}\n")

    def list(self) -> list[EvolutionProposal]:
        if not self.proposals_dir.is_dir():
            return []
        proposals: list[EvolutionProposal] = []
        for path in self.proposals_dir.glob("*.json"):
            proposals.append(self._load_path(path))
        return sorted(proposals, key=lambda item: (item.created_at, item.proposal_id), reverse=True)

    def get(self, proposal_id_or_prefix: str) -> EvolutionProposal:
        proposal_id_or_prefix = _validate_lookup_id(proposal_id_or_prefix, allow_prefix=True)
        exact = self._path_for_id(proposal_id_or_prefix)
        if exact.is_file():
            return self._load_path(exact)
        matches = [
            path
            for path in self.proposals_dir.glob("*.json")
            if path.stem.startswith(proposal_id_or_prefix)
        ]
        if not matches:
            raise FileNotFoundError(f"proposal not found: {proposal_id_or_prefix}")
        if len(matches) > 1:
            raise ValueError(f"ambiguous proposal id prefix: {proposal_id_or_prefix}")
        return self._load_path(matches[0])

    def mark_running(self, proposal: EvolutionProposal) -> EvolutionProposal:
        with _proposal_lock(self._path_for_id(proposal.proposal_id)):
            current = self.get(proposal.proposal_id)
            if current.status == "running":
                raise RuntimeError(f"proposal is already running: {proposal.proposal_id}")
            if current.status == "completed":
                raise RuntimeError(f"proposal is already completed: {proposal.proposal_id}")
            updated = current.model_copy(update={"status": "running", "error_redacted": None})
            self.write(updated)
            return updated

    def mark_completed(self, proposal: EvolutionProposal, manifest: RunManifest) -> EvolutionProposal:
        with _proposal_lock(self._path_for_id(proposal.proposal_id)):
            current = self.get(proposal.proposal_id)
            if current.status != "running":
                raise RuntimeError(f"proposal is not running: {proposal.proposal_id}")
            manifest_path = self.workspace / "evals" / "runs" / manifest.run_id / "manifest.json"
            updated = current.model_copy(
                update={
                    "status": "completed",
                    "run_id": manifest.run_id,
                    "manifest_path": _relative_to_workspace(manifest_path, self.workspace),
                    "error_redacted": None,
                }
            )
            self.write(updated)
            return updated

    def mark_failed(self, proposal: EvolutionProposal, exc: BaseException) -> EvolutionProposal:
        with _proposal_lock(self._path_for_id(proposal.proposal_id)):
            current = self.get(proposal.proposal_id)
            if current.status == "completed":
                return current
            updated = current.model_copy(
                update={"status": "failed", "error_redacted": redact(str(exc)).text[:1000]}
            )
            self.write(updated)
            return updated

    def _generate_id(self, skill_name: str, created_at: datetime) -> str:
        stamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        prefix = f"evolve-{stamp}-{_safe_id_part(skill_name)}"
        used = {path.stem for path in self.proposals_dir.glob(f"{prefix}-*.json")}
        for index in range(1, 10_000):
            candidate = f"{prefix}-{index:04d}"
            if candidate not in used:
                return candidate
        raise FileExistsError(f"no available proposal-id suffix for {prefix}")

    def _path_for_id(self, proposal_id: str) -> Path:
        proposal_id = _validate_lookup_id(proposal_id, allow_prefix=False)
        path = self.proposals_dir / f"{proposal_id}.json"
        try:
            path.resolve().relative_to(self.proposals_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"invalid proposal id: {proposal_id}") from exc
        return path

    def _load_path(self, path: Path) -> EvolutionProposal:
        return EvolutionProposal.model_validate(json.loads(path.read_text(encoding="utf-8")))


def create_manual_proposal(
    store: ProposalStore,
    *,
    skill_name: str,
    rationale: str,
    now: datetime | None = None,
) -> EvolutionProposal:
    return store.create(source="manual", skill_name=skill_name, rationale=rationale, now=now)


def proposals_from_curator(
    store: ProposalStore,
    curator_proposals: list[CuratorProposal],
    *,
    now: datetime | None = None,
) -> list[EvolutionProposal]:
    created: list[EvolutionProposal] = []
    for proposal in curator_proposals:
        if proposal.action not in _EVOLUTION_ACTIONS:
            continue
        reason_text = "; ".join(
            f"{reason.code} "
            + " ".join(f"{key}={value}" for key, value in sorted(reason.params.items()))
            for reason in proposal.reasons
        ).strip()
        rationale = (
            f"Curator suggested {proposal.action.value} for skill {proposal.name} "
            f"with {proposal.confidence.value} confidence. {reason_text}"
        )
        created.append(
            store.create(
                source="curator",
                skill_name=proposal.name,
                rationale=rationale,
                now=now,
                trigger_ref=f"curator:{proposal.action.value}",
            )
        )
    return created


def create_dream_proposal(
    store: ProposalStore,
    *,
    skill_name: str,
    rationale: str,
    now: datetime | None = None,
    trigger_ref: str | None = None,
) -> EvolutionProposal:
    trigger_ref = trigger_ref or "dream:completed"
    for proposal in store.list():
        if proposal.source == "dream" and proposal.trigger_ref == trigger_ref:
            return proposal
    return store.create(
        source="dream",
        skill_name=skill_name,
        rationale=rationale,
        now=now,
        trigger_ref=trigger_ref,
    )


def maybe_create_dream_proposal(
    loop,
    *,
    completed: bool,
    processed_entries: int,
) -> EvolutionProposal | None:
    if not completed:
        return None
    config = getattr(loop, "evolution_config", None)
    if config is None or not config.enabled or "dream" not in config.proposal_triggers:
        return None

    store = ProposalStore(config.resolve_workspace(loop.workspace))
    skill_name = "dream-memory"
    trigger_ref = f"dream:cursor:{processed_entries}"
    return create_dream_proposal(
        store,
        skill_name=skill_name,
        rationale=f"Dream completed after processing {processed_entries} history entries.",
        trigger_ref=trigger_ref,
    )


def format_proposal_list(proposals: list[EvolutionProposal]) -> str:
    lines = ["## Evolution proposals", ""]
    if not proposals:
        lines.append("No evolution proposals found.")
        return "\n".join(lines)
    for proposal in proposals:
        lines.append(
            f"- `{proposal.proposal_id}` {proposal.skill_name} "
            f"source={proposal.source} status={proposal.status}"
        )
    return "\n".join(lines)


def format_proposal_show(proposal: EvolutionProposal) -> str:
    lines = [
        "## Proposal",
        f"- ID: `{proposal.proposal_id}`",
        f"- Skill: `{proposal.skill_name}`",
        f"- Source: `{proposal.source}`",
        f"- Status: `{proposal.status}`",
        f"- Created: `{proposal.created_at.isoformat()}`",
        f"- Trigger: `{proposal.trigger_ref or '<none>'}`",
        f"- Run: `{proposal.run_id or '<none>'}`",
        f"- Manifest: `{proposal.manifest_path or '<none>'}`",
        "",
        "## Rationale",
        proposal.rationale_redacted,
    ]
    if proposal.error_redacted:
        lines.extend(["", "## Last error", proposal.error_redacted])
    return "\n".join(lines)


class ProposalRunner:
    def __init__(self, store: ProposalStore) -> None:
        self.store = store

    def run(
        self,
        proposal_id_or_prefix: str,
        *,
        optimizer_command: list[str],
        tiers: list[str],
        max_candidates: int,
        optimizer_timeout_seconds: int,
    ) -> EvolutionRunResult:
        proposal = self.store.get(proposal_id_or_prefix)
        running = self.store.mark_running(proposal)
        try:
            harness = OfflineHarness(workspace=self.store.workspace)
            manifest = harness.run(
                skill_name=running.skill_name,
                optimizer_command=optimizer_command,
                tiers=tiers,
                max_candidates=max_candidates,
                optimizer_timeout_seconds=optimizer_timeout_seconds,
                proposal_context=EvolutionProposalContext(
                    proposal_id=running.proposal_id,
                    source=running.source,
                ),
            )
        except Exception as exc:
            self.store.mark_failed(running, exc)
            raise
        completed = self.store.mark_completed(running, manifest)
        return EvolutionRunResult(proposal=completed, manifest=manifest)


def format_run_result(result: EvolutionRunResult) -> str:
    proposal = result.proposal
    lines = [
        "## Evolution run",
        f"- Proposal: `{proposal.proposal_id}`",
        f"- Skill: `{proposal.skill_name}`",
        f"- Status: `{proposal.status}`",
        f"- Run: `{proposal.run_id or '<none>'}`",
        f"- Manifest: `{proposal.manifest_path or '<none>'}`",
    ]
    if result.manifest is not None:
        lines.append(f"- Final status: `{result.manifest.final_status}`")
    return "\n".join(lines)
