"""M2 §3.5 / §3.6 — `_validate_skill_name` accepts safe names, rejects everything else.

Sweeps the full reject surface called out in the spec:
* empty / too-long
* Unicode confusables (Cyrillic look-alikes, CJK, em-dash, NBSP)
* uppercase
* leading hyphen / leading dot / dot-anywhere
* whitespace and other punctuation
* reserved tier names (case-insensitive)
"""

from __future__ import annotations

import pytest


def test_valid_names_accepted() -> None:
    from nanobot.agent.tools.skill_manage import _validate_skill_name

    valid = [
        "a",
        "abc",
        "abc-def",
        "abc-def-ghi",
        "a1",
        "1",
        "a-b-1",
        "x" * 64,
        "0",
        "z9-z9-z9",
        "long-skill-name-with-many-hyphens-and-digits-1234567890",
    ]
    for name in valid:
        # Should not raise.
        _validate_skill_name(name)


def test_invalid_names_rejected() -> None:
    from nanobot.agent._atomic_io import SkillManageError
    from nanobot.agent.tools.skill_manage import _validate_skill_name

    bad = [
        # empty / too long
        "",
        "x" * 65,
        # Unicode confusables (must be rejected — re.ASCII)
        "аbc",       # leading char is Cyrillic 'а' (U+0430)
        "abс",       # 'с' is Cyrillic (U+0441)
        "中文",
        "ab\u2014cd",  # em-dash
        "ab\u00a0cd",  # NBSP
        # uppercase
        "ABC",
        "abC",
        "Abc",
        # leading hyphen
        "-abc",
        "-",
        # leading dot / dot-anywhere
        ".abc",
        "..",
        ".",
        "abc.def",
        # whitespace
        " abc",
        "abc ",
        "a b",
        "\tabc",
        # other punctuation / path separators
        "a/b",
        "a.b",
        "a_b",
        "a@b",
        "a:b",
        "a\\b",
    ]
    for name in bad:
        with pytest.raises(SkillManageError) as ei:
            _validate_skill_name(name)
        assert ei.value.error_code == "invalid_name", f"name={name!r}"


def test_reserved_names_rejected() -> None:
    from nanobot.agent._atomic_io import SkillManageError
    from nanobot.agent.tools.skill_manage import _validate_skill_name

    # Lowercase forms must trip the explicit reserved-set check.
    for reserved in ("agent", "user", "bundled", "hub"):
        with pytest.raises(SkillManageError) as ei:
            _validate_skill_name(reserved)
        assert ei.value.error_code == "invalid_name", f"reserved={reserved!r}"

    # Mixed-case forms must trip either the regex (uppercase) OR the
    # case-insensitive reserved check — either way it's invalid_name.
    for reserved in ("AGENT", "User", "Bundled", "HUB"):
        with pytest.raises(SkillManageError) as ei:
            _validate_skill_name(reserved)
        assert ei.value.error_code == "invalid_name", f"reserved={reserved!r}"
