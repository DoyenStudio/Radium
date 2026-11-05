# coding=utf-8

from ..basic import ClientEvent


class DimensionChangeClientEvent(ClientEvent):
    name = "DimensionChangeClientEvent"

    def __init__(
        self,
        playerId,  # type: str
        fromDimensionId,  # type: int
        toDimensionId,  # type: int
        fromX,  # type: float
        fromY,  # type: float
        
        fromZ,  # type: float
        toX,  # type: float
        toY,  # type: float
        toZ,  # type: float
    ):
        self.playerId = playerId
        """ 玩家实体id """
        self.fromDimensionId = fromDimensionId
        """ 维度改变前的维度 """
        self.toDimensionId = toDimensionId
        """ 维度改变后的维度 """
        self.fromX = fromX
        """ 改变前的位置x """
        self.fromY = fromY
        """ 改变前的位置Y """
        self.fromZ = fromZ
        """ 改变前的位置Z """
        self.toX = toX
        """ 改变后的位置x """
        self.toY = toY
        """ 改变后的位置Y """
        self.toZ = toZ
        """ 改变后的位置Z """

    @classmethod
    def unmarshal(cls, data):
        return cls(
            playerId=data["playerId"],
            fromDimensionId=data["fromDimensionId"],
            toDimensionId=data["toDimensionId"],
            fromX=data["fromX"],
            fromY=data["fromY"],
            fromZ=data["fromZ"],
            toX=data["toX"],
            toY=data["toY"],
            toZ=data["toZ"],
        )

    def marshal(self):
        # type: () -> dict
        return {
            "playerId": self.playerId,
            "fromDimensionId": self.fromDimensionId,
            "toDimensionId": self.toDimensionId,
            "fromX": self.fromX,
            "fromY": self.fromY,
            "fromZ": self.fromZ,
            "toX": self.toX,
            "toY": self.toY,
            "toZ": self.toZ,
        }


class OnScriptTickClient(ClientEvent):
    name = "OnScriptTickClient"

    def __init__(self):
        pass

    @classmethod
    def unmarshal(cls, data=None):
        return cls()

    def marshal(self):
        return {}


class GameRenderTickEvent(ClientEvent):
    name = "GameRenderTickEvent"

    def __init__(self):
        pass

    @classmethod
    def unmarshal(cls, data=None):
        return cls()

    def marshal(self):
        return {}


class LoadClientAddonScriptsAfter(ClientEvent):
    name = "LoadClientAddonScriptsAfter"

    def __init__(self):
        pass

    @classmethod
    def unmarshal(cls, _):
        return cls()

    def marshal(self):
        return {}
