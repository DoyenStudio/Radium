# coding=utf-8

from ..basic import ServerEvent


class AddEntityServerEvent(ServerEvent):
    name = "AddEntityServerEvent"

    def __init__(
        self,
        id,  # type: str
        posX,  # type: float
        posY,  # type: float
        posZ,  # type: float
        dimensionId,  # type: int
        isBaby,  # type: bool
        engineTypeStr,  # type: str
        itemName="",  # type: str
        auxValue=0,  # type: int
    ):
        self.id = id
        self.posX = posX
        self.posY = posY
        self.posZ = posZ
        self.dimensionId = dimensionId
        self.isBaby = isBaby
        self.engineTypeStr = engineTypeStr
        self.itemName = itemName
        self.auxValue = auxValue

    @classmethod
    def unmarshal(cls, data):
        # type: (dict) -> AddEntityServerEvent
        return cls(
            id=data["id"],
            posX=data["posX"],
            posY=data["posY"],
            posZ=data["posZ"],
            dimensionId=data["dimensionId"],
            isBaby=data["isBaby"],
            engineTypeStr=data["engineTypeStr"],
            itemName=data.get("itemName", ""),
            auxValue=data.get("auxValue", 0),
        )

    def marshal(self):
        # type: () -> dict
        return {
            "id": self.id,
            "posX": self.posX,
            "posY": self.posY,
            "posZ": self.posZ,
            "dimensionId": self.dimensionId,
            "isBaby": self.isBaby,
            "engineTypeStr": self.engineTypeStr,
            "itemName": self.itemName,
            "auxValue": self.auxValue,
        }


class EntityDieLoottableAfterServerEvent(ServerEvent):
    name = "EntityDieLoottableAfterServerEvent"

    dieEntityId = "" # type: str
    """ 死亡实体的entityId """
    attacker = "" # type: str
    """ 伤害来源的entityId """
    itemList = [] # type: list[dict]
    """ 掉落物品列表，每个元素为一个itemDict，格式可参考物品信息字典 """
    itemEntityIdList = [] # type: list[str]
    """ 掉落物品entityId列表 """

    @classmethod
    def unmarshal(cls, data):
        # type: (dict) -> EntityDieLoottableAfterServerEvent
        instance = cls()
        instance.dieEntityId = data["dieEntityId"]
        instance.attacker = data["attacker"]
        instance.itemList = data["itemList"]
        instance.itemEntityIdList = data["itemEntityIdList"]
        return instance

    def marshal(self):
        # type: () -> dict
        return {
            "dieEntityId": self.dieEntityId,
            "attacker": self.attacker,
            "itemList": self.itemList,
            "itemEntityIdList": self.itemEntityIdList,
        }
