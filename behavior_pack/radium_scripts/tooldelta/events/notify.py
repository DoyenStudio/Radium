# coding=utf-8
from mod_log import logger
from ..internal import GetClient, GetServer
from .basic import BaseEvent, CustomC2SEvent, CustomS2CEvent

if 0 > 1:  # noqa: PLR0133
    import typing

    ET = typing.TypeVar("ET", bound="BaseEvent")


class _ModRuntime:
    _client_systems = {}
    _server_systems = {}

    @classmethod
    def GetServerSystem(cls, namespace, system_name):
        system = cls._server_systems.get((namespace, system_name))
        if system is None:
            from mod.server.extraServerApi import GetServerSystemCls, GetSystem

            system = GetSystem(namespace, system_name)
            if system is None:
                # 引擎命名空间的 system 查不到(GetSystem 拿不到引擎自己), 直接造一个
                # 同 (namespace, systemName) 的实例: BroadcastEvent 只投给注册在
                # 「广播方自身 (namespace, systemName)」上的监听器
                system = GetServerSystemCls()(namespace, system_name)
            cls._server_systems[(namespace, system_name)] = system
        return system

    @classmethod
    def GetClientSystem(cls, namespace, system_name):
        system = cls._client_systems.get((namespace, system_name))
        if system is None:
            from mod.client.extraClientApi import GetClientSystemCls, GetSystem

            system = GetSystem(namespace, system_name)
            if system is None:
                system = GetClientSystemCls()(namespace, system_name)
            cls._client_systems[(namespace, system_name)] = system
        return system


def NotifyToServer(event):
    # type: (CustomC2SEvent) -> None
    GetClient().NotifyToServer(event.name, event.marshal())


def NotifyToClient(targetId, event):
    # type: (str, CustomS2CEvent) -> None
    GetServer().NotifyToClient(targetId, event.name, event.marshal())


def NotifyToClients(targetIds, event):
    # type: (list[str], CustomS2CEvent) -> None
    GetServer().NotifyToMultiClients(targetIds, event.name, event.marshal())


def NotifyToAll(event):
    # type: (CustomS2CEvent) -> None
    GetServer().BroadcastToAllClient(event.name, event.marshal())


def ServerBroadcast(event):
    # type: (ET) -> ET
    event_dct = event.marshal()
    system = _ModRuntime.GetServerSystem(event.GetNamespace(), event.GetSystemName())
    if system is not None:
        system.BroadcastEvent(event.name, event_dct)
    else:
        logger.error(
            "Broadcast: system not found: %s:%s" % (event.GetNamespace(), event.GetSystemName())
        )
    return event.unmarshal(event_dct)


def ClientBroadcast(event):
    # type: (ET) -> ET
    event_dct = event.marshal()
    system = _ModRuntime.GetClientSystem(event.GetNamespace(), event.GetSystemName())
    if system is not None:
        system.BroadcastEvent(event.name, event_dct)
    else:
        logger.error(
            "Broadcast: system not found: %s:%s" % (event.GetNamespace(), event.GetSystemName())
        )
    return event.unmarshal(event_dct)
