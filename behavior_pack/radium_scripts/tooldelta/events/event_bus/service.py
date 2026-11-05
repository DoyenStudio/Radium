# coding=utf-8
from .event_bus import EventBus

try:
    import typing

    from ._types import SystemLike

    SystemT = typing.TypeVar("SystemT", bound="SystemLike")

except ImportError:
    pass

event_buses = {}  # type: dict[tuple[str, str, str], EventBus]


def GetEventBus(namespace, system_name, system):
    # type: (str, str, SystemT) -> EventBus[SystemT]
    k = (namespace, system_name, system.__class__.__name__)
    cached = event_buses.get(k)
    if cached is None:
        cached = event_buses[k] = EventBus(system, namespace, system_name)
    return cached


def GetMCServerEventBus():
    from mod.server.extraServerApi import GetEngineNamespace, GetEngineSystemName

    from ...internal import GetServer

    return GetEventBus(GetEngineNamespace(), GetEngineSystemName(), GetServer())


def GetMCClientEventBus():
    from mod.client.extraClientApi import GetEngineNamespace, GetEngineSystemName

    from ...internal import GetClient

    return GetEventBus(GetEngineNamespace(), GetEngineSystemName(), GetClient())

def GetModServerEventBus():
    from ...internal import GetModName, GetModServerEngineName, GetServer

    return GetEventBus(GetModName(), GetModServerEngineName(), GetServer())


def GetModClientEventBus():
    from ...internal import GetClient, GetModClientEngineName, GetModName

    return GetEventBus(GetModName(), GetModClientEngineName(), GetClient())
