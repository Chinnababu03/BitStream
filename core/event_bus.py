"""
Centralized Event Bus for DownloadHub.

Decouples event producers (TorrentClient, YouTubeClient) from consumers (web layer).
All event routing, logging, and filtering happens here.
"""

import logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """All event types in the system."""
    # Torrent events
    TORRENT_ADDED = "torrent_added"
    TORRENT_REMOVED = "torrent_removed"
    TORRENT_UPDATED = "torrent_updated"
    TORRENT_PAUSED = "torrent_paused"
    TORRENT_RESUMED = "torrent_resumed"
    TORRENT_FINISHED = "torrent_finished"
    TORRENT_ERROR = "torrent_error"
    ALL_PAUSED = "all_paused"
    ALL_RESUMED = "all_resumed"

    # YouTube events
    YT_ADDED = "yt_added"
    YT_REMOVED = "yt_removed"
    YT_UPDATED = "yt_updated"
    YT_FINISHED = "yt_finished"
    YT_ERROR = "yt_error"

    # System events
    STARTED = "started"
    STOPPED = "stopped"
    ERROR = "error"
    METADATA_RECEIVED = "metadata_received"


@dataclass
class Event:
    """Represents an event with metadata."""
    type: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            'type': self.type,
            'data': self.data,
            'timestamp': self.timestamp.isoformat()
        }


# Type alias for event handlers
EventHandler = Callable[[str, dict], None]


class EventBus:
    """Centralized event bus for publishing and subscribing to events.

    This replaces the duplicated callback pattern in both TorrentClient and
    YouTubeClient, providing a single point for event routing, logging, and
    filtering.
    """

    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._global_handlers: List[EventHandler] = []
        self._event_log: List[Event] = []
        self._max_log_size: int = 1000

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe to a specific event type.

        Args:
            event_type: The event type to subscribe to (use EventType enum values).
            handler: The callback function to invoke when the event occurs.
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed to event '%s': %s", event_type, handler.__name__)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe to all events.

        Args:
            handler: The callback function to invoke for any event.
        """
        self._global_handlers.append(handler)
        logger.debug("Subscribed to all events: %s", handler.__name__)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe from a specific event type.

        Args:
            event_type: The event type to unsubscribe from.
            handler: The handler to remove.
        """
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]

    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish an event to all subscribers.

        Args:
            event_type: The event type to publish.
            data: The event data payload.
        """
        # Create event with the raw string type
        event = Event(type=event_type, data=data)

        # Log to event log (with rotation)
        self._event_log.append(event)
        if len(self._event_log) > self._max_log_size:
            self._event_log = self._event_log[-self._max_log_size:]

        # Notify specific handlers
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                handler(event_type, data)
            except Exception as e:
                logger.warning("Handler error for event '%s': %s", event_type, e)

        # Notify global handlers
        for handler in self._global_handlers:
            try:
                handler(event_type, data)
            except Exception as e:
                logger.warning("Global handler error for event '%s': %s", event_type, e)

    def get_recent_events(self, count: int = 100) -> List[Event]:
        """Get the most recent events from the log.

        Args:
            count: Maximum number of events to return.

        Returns:
            List of recent Event objects.
        """
        return self._event_log[-count:]

    def clear_log(self) -> None:
        """Clear the event log."""
        self._event_log.clear()

    def handler_count(self, event_type: Optional[str] = None) -> int:
        """Count registered handlers.

        Args:
            event_type: If provided, count handlers for this specific event.
                       If None, count all handlers.

        Returns:
            Number of registered handlers.
        """
        if event_type:
            return len(self._handlers.get(event_type, []))
        return sum(len(handlers) for handlers in self._handlers.values()) + len(self._global_handlers)


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance (singleton).

    Returns:
        The global EventBus instance.
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> None:
    """Reset the global event bus (useful for testing)."""
    global _event_bus
    _event_bus = None
