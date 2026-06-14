import inspect
from pathlib import Path
from typing import ClassVar


class EvolveError:
    """Mixin enforcing two invariants on each subclass.

    1. ``STRUCTURED_KWARGS`` (``frozenset[str]``) must be a subset of the
       kw-only parameters in ``__init__``.
    2. If any parent in the MRO declares ``STRUCTURED_KWARGS``, the subclass
       MUST redeclare it (even as ``frozenset()``) — explicit opt-out is
       required to prevent silent dropping of structured fields.

    Empty ``frozenset()`` is the explicit "no structured kwargs" signal.

    ``MUST_PRECEDE``: documentary-only handler-order hint. NOT enforced at
    runtime; M5 may add a static check. Treat as informational metadata
    for now.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        declared = cls.__dict__.get("STRUCTURED_KWARGS")
        if declared is None:
            for base in cls.__mro__[1:]:
                if base is EvolveError:
                    continue
                if "STRUCTURED_KWARGS" in base.__dict__:
                    raise TypeError(
                        f"{cls.__name__}: parent {base.__name__} declares STRUCTURED_KWARGS; "
                        f"subclasses MUST redeclare their own STRUCTURED_KWARGS."
                    )
            return
        if not isinstance(declared, frozenset):
            raise TypeError(f"{cls.__name__}.STRUCTURED_KWARGS must be frozenset[str]")
        sig = inspect.signature(cls.__init__)
        kw_only = {
            n for n, p in sig.parameters.items() if p.kind is inspect.Parameter.KEYWORD_ONLY
        }
        if not set(declared).issubset(kw_only):
            missing = set(declared) - kw_only
            raise TypeError(
                f"{cls.__name__}: STRUCTURED_KWARGS={set(declared)!r} contains {missing!r} "
                f"not in __init__ kw-only params={kw_only!r}"
            )


# noqa: N818 — spec §5.3 verbatim name
class EvolveExtraNotInstalled(EvolveError, ImportError):  # noqa: N818
    INSTALL_HINT = "pip install nanobot[evolve]"


# noqa: N818 — spec §5.3 verbatim name
class BaselineMismatch(EvolveError, ValueError):  # noqa: N818
    ...


class ApplyTerminalError(EvolveError, ValueError):
    STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"final_status", "manifest_path"})
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"ValueError", "ConfigError"})

    def __init__(self, message: str, *, final_status: str, manifest_path: Path) -> None:
        super().__init__(message)
        self.final_status = final_status
        self.manifest_path = manifest_path


class JudgeError(EvolveError, RuntimeError):
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})


# noqa: N818 — spec §5.3 verbatim name
class ManifestPrivacyViolation(EvolveError, RuntimeError):  # noqa: N818
    # All three kw-only fields of __init__ are part of the public structured
    # surface — consumers iterating STRUCTURED_KWARGS to e.g. log structured
    # context need the full set; under-declaration would silently drop fields.
    STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset(
        {"violated_invariant", "offending_path", "offending_fields"}
    )
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})

    def __init__(
        self,
        message: str,
        *,
        violated_invariant: str,
        offending_path: Path | None = None,
        offending_fields: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.violated_invariant = violated_invariant
        self.offending_path = offending_path
        self.offending_fields = offending_fields or []


class EvolveEnvironmentError(EvolveError, RuntimeError):
    STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset()
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})


class ConfigError(EvolveError, ValueError): ...


class GateInternalError(EvolveError, RuntimeError):
    """Raised when a gate cannot evaluate due to malformed inputs.

    Distinct from a gate FAIL verdict: this signals a precondition violation
    (e.g. missing tier-C records, tier sizes below §1.1 invariant floor).
    Spec §6.1.2 / decision #120. Harness §6.0 point 3 wraps this into an
    abort/failure path for the candidate.
    """

    STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset()
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})


class OptimizerRunError(EvolveError, RuntimeError):
    STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"run_dir", "exit_code"})
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})

    def __init__(self, message: str, *, run_dir: str, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.run_dir = run_dir
        self.exit_code = exit_code
