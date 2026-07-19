"""
Dependency Injection Container for DownloadHub.

Provides factory functions to create and wire up all application components.
This replaces module-level instantiation and sys.path hacks.
"""

from core.config import Settings, load_settings
from core.event_bus import EventBus, get_event_bus
from core.download_manager import DownloadManager


class AppContainer:
    """Dependency injection container for the application.

    Creates and holds references to all major components, wired together
    through proper dependencies instead of module-level globals.
    """

    def __init__(self, settings: Settings = None, event_bus: EventBus = None):
        self.settings = settings or load_settings()
        self.event_bus = event_bus or get_event_bus()
        self.download_manager = DownloadManager(
            settings=self.settings,
            event_bus=self.event_bus
        )

    def start(self) -> None:
        """Start all services."""
        self.download_manager.start()

    def stop(self) -> None:
        """Stop all services."""
        self.download_manager.stop()


def create_container(settings: Settings = None, event_bus: EventBus = None) -> AppContainer:
    """Factory function to create a fully-wired AppContainer.

    Args:
        settings: Optional settings override (for testing).
        event_bus: Optional event bus override (for testing).

    Returns:
        A ready-to-use AppContainer instance.
    """
    return AppContainer(settings=settings, event_bus=event_bus)
