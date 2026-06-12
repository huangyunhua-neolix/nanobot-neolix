import inspect
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pathlib import Path


class EvolveError:
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


class EvolveExtraNotInstalled(EvolveError, ImportError):  # noqa: N818 — spec §5.3 verbatim name
    INSTALL_HINT = "pip install nanobot[evolve]"


class BaselineMismatch(EvolveError, ValueError):  # noqa: N818 — spec §5.3 verbatim name
    ...


class ApplyTerminalError(EvolveError, ValueError):
    STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"final_status", "manifest_path"})
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"ValueError", "ConfigError"})

    def __init__(self, message: str, *, final_status: str, manifest_path: "Path") -> None:
        super().__init__(message)
        self.final_status = final_status
        self.manifest_path = manifest_path


class JudgeError(EvolveError, RuntimeError):
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})


class ManifestPrivacyViolation(EvolveError, RuntimeError):  # noqa: N818 — spec §5.3 verbatim name
    STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"violated_invariant"})
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})

    def __init__(
        self,
        message: str,
        *,
        violated_invariant: str,
        offending_path: "Path | None" = None,
        offending_fields: "list[str] | None" = None,
    ) -> None:
        super().__init__(message)
        self.violated_invariant = violated_invariant
        self.offending_path = offending_path
        self.offending_fields = offending_fields or []


class EvolveEnvironmentError(EvolveError, RuntimeError):
    STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset()
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})


class ConfigError(EvolveError, ValueError): ...
