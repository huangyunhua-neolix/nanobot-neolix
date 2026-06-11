"""Regression tests for tests/agent/conftest.py helpers."""

from tests.agent.conftest import make_provider


def test_make_provider_spec_true_estimate_prompt_tokens_works() -> None:
    """`make_provider(spec=True)` must NOT raise AttributeError on
    `estimate_prompt_tokens`.

    `nanobot.providers.base.LLMProvider` does NOT declare
    `estimate_prompt_tokens` — production code accesses it via
    `getattr(provider, "estimate_prompt_tokens", None)` in
    `nanobot/utils/helpers.py:510`. A spec-limited MagicMock therefore
    rejects attribute-access chains like
    `provider.estimate_prompt_tokens.return_value = ...`. The conftest
    fix assigns a fresh MagicMock directly to the attribute name to
    bypass that enforcement; this test guards against regression.
    """
    provider = make_provider(spec=True)
    tokens, source = provider.estimate_prompt_tokens()
    assert tokens == 10_000
    assert source == "test"


def test_make_provider_spec_false_estimate_prompt_tokens_works() -> None:
    """Same contract for spec=False (free-form MagicMock)."""
    provider = make_provider(spec=False)
    tokens, source = provider.estimate_prompt_tokens()
    assert tokens == 10_000
    assert source == "test"


def test_make_provider_spec_true_get_default_model() -> None:
    """`get_default_model` IS on LLMProvider spec; access must work."""
    provider = make_provider(spec=True, default_model="my-model")
    assert provider.get_default_model() == "my-model"


def test_make_provider_generation_settings() -> None:
    provider = make_provider(spec=True, max_tokens=8192)
    assert provider.generation.max_tokens == 8192
    assert provider.generation.temperature == 0.1
    assert provider.generation.reasoning_effort is None
