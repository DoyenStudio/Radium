# coding=utf-8
from ..basic import ServerEvent


class BlockNeighborChangedServerEvent(ServerEvent):
    name = "BlockNeighborChangedServerEvent"


class BlockRemoveServerEvent(ServerEvent):
    name = "BlockRemoveServerEvent"

    @classmethod
    def AddExtraBlocks(cls, blocks):
        from ...srv import CF, LEVEL_ID

        for block in blocks:
            CF.CreateBlockInfo(LEVEL_ID).ListenOnBlockRemoveEvent(block, True)


class EntityPlaceBlockAfterServerEvent(ServerEvent):
    name = "EntityPlaceBlockAfterServerEvent"
