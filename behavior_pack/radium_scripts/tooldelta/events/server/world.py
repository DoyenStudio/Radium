# coding=utf-8
from ..basic import ServerEvent


class ChunkAcquireDiscardedServerEvent(ServerEvent):
    name = "ChunkAcquireDiscardedServerEvent"


class ChunkLoadedServerEvent(ServerEvent):
    name = "ChunkLoadedServerEvent"


class OnSimTickServerEvent(ServerEvent):
    name = "OnSimTickServerEvent"
