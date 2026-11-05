from collections.abc import Callable
from typing import Any, Protocol

class SystemLike(Protocol):
    def ListenForEvent(
        self,
        namespace: str,
        systemName: str,
        eventName: str,
        instance: SystemLike,
        func: Callable[..., Any],
        priority: int = 0,
    ) -> None: ...
    def UnListenForEvent(
        self,
        namespace: str,
        systemName: str,
        eventName: str,
        instance: SystemLike,
        func: Callable[..., Any],
        priority: int = 0,
    ) -> None: ...
    def UnListenAllEvents(self) -> None: ...
    def BroadcastEvent(self, eventName: str, eventData: dict) -> None: ...
