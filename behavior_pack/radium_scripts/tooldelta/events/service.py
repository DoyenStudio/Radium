# coding=utf-8
from .._typing import Generic, TypeVar
from .basic import BaseEvent
from .event_bus import EventBus

EventT = TypeVar("EventT", bound=BaseEvent)


if 0>1:
    import typing

    CallT = TypeVar("CallT", bound=typing.Callable)

_ATTR_EVENT_LISTENER = "_tdbind_event_listen"


class EventListenerService(object):
    def __init__(self, event_bus):
        # type: (EventBus) -> None
        self._event_bus = event_bus
        self._bind_listen_events = []  # type: list[tuple[type[BaseEvent], typing.Callable[[BaseEvent], None], int]]
        self._listen_service_enabled = False
        self._process_bind_listeners()

    @classmethod
    def Listen(
        cls,
        event,  # type: type[EventT]
        priority=0,
    ):

        def wrapper(func):
            # type: (CallT) -> CallT
            former = getattr(func, _ATTR_EVENT_LISTENER, [])
            former.append((event, priority))
            setattr(func, _ATTR_EVENT_LISTENER, former)
            return func

        return wrapper

    def enable_listeners(self):
        self._listen_service_enabled = True
        for event, listener, priority in self._bind_listen_events:
            self._event_bus._dyn_listen(event, listener, priority)

    def disable_listeners(self):
        self._listen_service_enabled = False
        for event, listener, priority in self._bind_listen_events:
            self._event_bus._dyn_unlisten(event, listener, priority)

    def _process_bind_listeners(self):
        for key in dir(self):
            attr = getattr(self, key)
            if hasattr(attr, _ATTR_EVENT_LISTENER):
                events = getattr(attr, _ATTR_EVENT_LISTENER)
                for event, priority in events:
                    self._bind_listen_events.append((event, attr, priority))

    def __del__(self):
        self.disable_listeners()
