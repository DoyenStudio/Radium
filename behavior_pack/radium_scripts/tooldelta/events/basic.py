# coding: utf-8


class BaseEvent(object):
    name = "Event"

    @classmethod
    def GetNamespace(cls):
        return None

    @classmethod
    def GetSystemName(cls):
        return None

    def marshal(self):  # type: () -> dict
        raise NotImplementedError

    @classmethod
    def unmarshal(
        cls,
        data,  # type: dict
    ):
        return cls()

    def broadcast(self):
        raise NotImplementedError("Not server or client event")


class ServerEvent(BaseEvent):
    name = "ServerEvent"

    @classmethod
    def Listen(cls, priority=0):
        """
        将以下的方法修饰为监听回调。

        Args:
            priority (int, optional): 优先级, 默认为 0
        """
        from .event_bus import GetMCServerEventBus

        return GetMCServerEventBus().ListenEvent(cls, priority, static=True)

    @classmethod
    def GetNamespace(cls):
        from mod.server.extraServerApi import GetEngineNamespace

        return GetEngineNamespace()

    @classmethod
    def GetSystemName(cls):
        from mod.server.extraServerApi import GetEngineSystemName

        return GetEngineSystemName()

    def broadcast(self):
        from .notify import ServerBroadcast

        return ServerBroadcast(self)


class ClientEvent(BaseEvent):
    name = "ClientEvent"

    @classmethod
    def Listen(cls, priority=0):
        """
        将以下的方法修饰为监听回调。

        Args:
            priority (int, optional): 优先级, 默认为 0
        """
        from .event_bus import GetMCClientEventBus

        return GetMCClientEventBus().ListenEvent(cls, priority, static=True)

    @classmethod
    def GetNamespace(cls):
        from mod.client.extraClientApi import GetEngineNamespace

        return GetEngineNamespace()

    @classmethod
    def GetSystemName(cls):
        from mod.client.extraClientApi import GetEngineSystemName

        return GetEngineSystemName()

    def broadcast(self):
        from .notify import ClientBroadcast

        return ClientBroadcast(self)


class CustomC2SEvent(ServerEvent):
    """
    表示一个由客户端发送的、需要被服务端监听的通信事件。
    """

    name = "CustomServerEvent"

    @classmethod
    def GetNamespace(cls):
        from ..internal import GetModName

        return GetModName()

    @classmethod
    def GetSystemName(cls):
        from ..internal import GetModClientEngineName

        return GetModClientEngineName()

    @classmethod
    def Listen(cls, priority=0):
        """
        将以下的方法修饰为监听回调。

        Args:
            priority (int, optional): 优先级, 默认为 0
        """
        from .event_bus import GetModServerEventBus

        return GetModServerEventBus().ListenEvent(cls, priority, static=True)

    def send(self):
        from .notify import NotifyToServer

        NotifyToServer(self)


class CustomS2CEvent(ClientEvent):
    """
    表示一个由服务端发送的、需要被客户端监听的通信事件。

    namespace 和 system_name 默认为本模组的命名空间和系统名。如要更改, 请修改类属性。
    """

    name = "CustomClientEvent"

    @classmethod
    def GetNamespace(cls):
        from ..internal import GetModName

        return GetModName()

    @classmethod
    def GetSystemName(cls):
        from ..internal import GetModServerEngineName

        return GetModServerEngineName()

    @classmethod
    def Listen(cls, priority=0):
        """
        将以下的方法修饰为监听回调。

        Args:
            priority (int, optional): 优先级, 默认为 0
        """
        from .event_bus import GetModClientEventBus

        return GetModClientEventBus().ListenEvent(cls, priority, static=True)

    def send(self, client_id):
        # type: (str) -> None
        from .notify import NotifyToClient

        NotifyToClient(client_id, self)

    def sendMulti(self, client_ids):
        # type: (list[str]) -> None
        from .notify import NotifyToClients

        NotifyToClients(client_ids, self)

    def sendAll(self):
        # type: () -> None
        from .notify import NotifyToAll

        NotifyToAll(self)
