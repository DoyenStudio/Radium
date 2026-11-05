# coding=utf-8
from ..._typing import Generic, TypeVar
from ..basic import BaseEvent

EventT = TypeVar("EventT", bound=BaseEvent)
T = TypeVar("T")
SystemT = TypeVar("SystemT", bound="SystemLike")

try:
    import typing  # noqa # type: ignore

    from ._types import SystemLike

except ImportError:
    pass


class EventBus(Generic[SystemT]):
    def __init__(self, system, namespace, system_name):
        # type: (SystemLike, str, str) -> None
        self.system = system
        self.namespace = namespace
        self.system_name = system_name
        self.event_listeners = {}  # type: dict[int, dict[type[BaseEvent], list[typing.Callable[..., None]]]]
        self.system_event_listeners = {}  # type: dict[int, dict[type[BaseEvent], typing.Callable[[dict], None]]]

    def AddEventListener(self, event, listener, priority=0, static=False):
        # type: (type[EventT], typing.Callable[[EventT], None], int, bool) -> None
        """
        监听客户端事件。

        Args:
            event (type[Event]): 事件类
            listener ((T) -> None): 事件监听器
            priority (int): 优先级
        """
        if static:
            if hasattr(listener, "_td_static"):
                return
            listener._td_static = True
        self._dyn_listen(event, listener, priority)

    def RemoveEventListener(self, event, listener, priority=0):
        # type: (type[EventT], typing.Callable[[EventT], None], int) -> None
        """
        取消监听服务端事件。

        Args:
            event (type[Event]): 事件类
            listener ((T) -> None): 事件监听器
            priority (int): 优先级
        """
        self._dyn_unlisten(event, listener, priority)

    def ListenEvent(self, event, priority, static=False):
        # type: (type[EventT], int, bool) -> typing.Callable[[typing.Callable[[EventT], None]], typing.Callable[[EventT], None]]
        """
        监听客户端事件, 作为装饰器使用。

        Args:
            event (type[Event]): 事件类
        """

        def wrapper(func):
            # type: (typing.Callable[[EventT], None]) -> typing.Callable[[EventT], None]
            self.AddEventListener(event, func, priority, static)
            return func

        return wrapper

    def _dyn_listen(self, event, listener, priority=0):
        # type: (type[EventT], typing.Callable[[EventT], None], int) -> None
        if (
            priority not in self.event_listeners
            or event not in self.event_listeners[priority]
        ):

            def event_bus_handler(*args):
                # type: (dict) -> None
                event_ins = event.unmarshal(*args)
                for cb in self.event_listeners[priority][event]:
                    cb(event_ins)

            event_bus_handler.__name__ = (
                "tdevent_handler_"
                + event.__module__
                + "."
                + event.__name__
                + str(priority)
            )
            self.system_event_listeners.setdefault(priority, {})[event] = (
                event_bus_handler
            )
            self._add_sys_event_listener(event, event_bus_handler, priority)
        listeners = self.event_listeners.setdefault(priority, {}).setdefault(event, [])
        listeners.append(listener)

    def _dyn_unlisten(self, event, listener, priority=0):
        # type: (type[EventT], typing.Callable[[EventT], None], int) -> None
        if (
            priority not in self.event_listeners
            or event not in self.event_listeners[priority]
        ):
            return
        self.event_listeners[priority][event].remove(listener)
        # not GC now

    def _add_sys_event_listener(self, event, listener, priority=0):
        # type: (type[EventT], typing.Callable[[dict], None], int) -> None
        setattr(self.system, listener.__name__, listener)
        self.system.ListenForEvent(
            event.GetNamespace() or self.namespace,
            event.GetSystemName() or self.system_name,
            event.name,
            self.system,
            listener,
            priority,
        )

    def _del_sys_event_listener(self, event, listener, priority=0):
        # type: (type[EventT], typing.Callable[[dict], None], int) -> None
        if hasattr(self.system, listener.__name__):
            delattr(self.system, listener.__name__)
        self.system.UnListenForEvent(
            self.namespace,
            self.system_name,
            event.name,
            self.system,
            listener,
            priority,
        )
