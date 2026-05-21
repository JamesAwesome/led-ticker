"""Registry duplicate-name collision guard (S7)."""

import pytest

from led_ticker.transitions import _TRANSITION_REGISTRY, register_transition
from led_ticker.widgets import _WIDGET_REGISTRY, register


def test_widget_registry_rejects_duplicate():
    """Second @register with same name must raise ValueError, not silently
    overwrite the first registration."""

    @register("_test_dup_widget")
    class First:
        pass

    with pytest.raises(ValueError, match="already registered"):

        @register("_test_dup_widget")
        class Second:
            pass

    _WIDGET_REGISTRY.pop("_test_dup_widget")


def test_transition_registry_rejects_duplicate():
    """Second @register_transition with same name must raise ValueError."""

    @register_transition("_test_dup_trans")
    class First:
        min_frames = 0

        def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
            return canvas

    with pytest.raises(ValueError, match="already registered"):

        @register_transition("_test_dup_trans")
        class Second:
            min_frames = 0

            def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
                return canvas

    _TRANSITION_REGISTRY.pop("_test_dup_trans")
