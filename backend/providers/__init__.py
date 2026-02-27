"""AI provider package for autopilot process spawning."""

from .base import AIProvider
from .claude import ClaudeProvider

REGISTRY: dict[str, type[AIProvider]] = {
    "claude": ClaudeProvider,
}


def get_provider(name: str) -> AIProvider:
    """Instantiate a provider by name.

    Args:
        name: Provider name (e.g. 'claude').

    Returns:
        An AIProvider instance.

    Raises:
        ValueError: If the provider name is not registered.
    """
    if name not in REGISTRY:
        available = ", ".join(sorted(REGISTRY.keys()))
        raise ValueError(f"Unknown provider '{name}'. Available providers: {available}")
    return REGISTRY[name]()
