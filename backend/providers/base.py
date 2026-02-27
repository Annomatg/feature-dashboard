"""Abstract base class for AI providers."""

import subprocess
from abc import ABC, abstractmethod


class AIProvider(ABC):
    """Abstract interface for spawning AI provider processes for autopilot."""

    @abstractmethod
    def spawn_process(self, feature, settings: dict, working_dir: str) -> subprocess.Popen:
        """Spawn an AI process for the given feature and return the Popen handle.

        Args:
            feature:     Feature ORM object (id, category, name, description, steps, model).
            settings:    Settings dict with provider-specific configuration.
            working_dir: Working directory for the spawned process.

        Returns:
            subprocess.Popen handle for the spawned process.
        """
        ...

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the canonical name of this provider (e.g. 'claude')."""
        ...
