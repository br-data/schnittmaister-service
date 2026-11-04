"""Tests for the Gemini model catalog: every model has settings."""

import pytest

from src.config.gemini_models import MODEL_TOKEN_SETTINGS, GeminiModel, get_token_settings_for_model


@pytest.mark.unit
@pytest.mark.parametrize("model", list(GeminiModel))
def test_every_model_has_token_settings(model: GeminiModel) -> None:
    """Test that every model has token settings, so the lookup only fails for unknown model IDs."""
    assert model in MODEL_TOKEN_SETTINGS


@pytest.mark.unit
def test_unknown_model_raises() -> None:
    """Test that an unknown model ID fails instead of silently using the settings of another model."""
    with pytest.raises(ValueError, match="gemini-unknown"):
        get_token_settings_for_model("gemini-unknown")
