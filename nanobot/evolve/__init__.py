"""nanobot.evolve — M4 offline skeleton (DSPy + GEPA).

Lazy: importing this package MUST succeed without DSPy/GEPA installed
(per §3.5.1 lazy-guard contract). Heavy bits live behind function-local imports.
"""
from nanobot.evolve.exceptions import (
    ApplyTerminalError,
    BaselineMismatch,
    ConfigError,
    EvolveEnvironmentError,
    EvolveError,
    EvolveExtraNotInstalled,
    GateInternalError,
    JudgeError,
    ManifestPrivacyViolation,
)

__all__ = [
    "EvolveError",
    "EvolveExtraNotInstalled",
    "BaselineMismatch",
    "ApplyTerminalError",
    "JudgeError",
    "ManifestPrivacyViolation",
    "EvolveEnvironmentError",
    "ConfigError",
    "GateInternalError",
]
