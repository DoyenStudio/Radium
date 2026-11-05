# coding: utf-8
from ..basic import ServerEvent


class ClientLoadAddonsFinishServerEvent(ServerEvent):
    name = "ClientLoadAddonsFinishServerEvent"

    def __init__(
        self,
        playerId,  # type: str
    ):
        self.playerId = playerId
        """ 玩家id """

    @classmethod
    def unmarshal(cls, data):
        return cls(
            playerId=data["playerId"],
        )

    def marshal(self):
        # type: () -> dict
        return {
            "playerId": self.playerId,
        }

class LoadServerAddonScriptsAfter(ServerEvent):
    name = "LoadServerAddonScriptsAfter"

    def __init__(self):
        pass

    @classmethod
    def unmarshal(cls, _):
        return cls()

    def marshal(self):
        return {}

class AddServerPlayerEvent(ServerEvent):
    name = "AddServerPlayerEvent"

    def __init__(
        self,
        id,  # type: str
        isTransfer,  # type: bool
        isReconnect,  # type: bool
        isPeUser,  # type: bool
        transferParam,  # type: str
        uid,  # type: int
        proxyId,  # type: int
    ):
        self.id = id
        """ 玩家id """
        self.isTransfer = isTransfer
        """ 是否是切服时进入服务器，仅用于Apollo。如果是True，则表示切服时加入服务器，若是False，则表示登录进入网络游戏 """
        self.isReconnect = isReconnect
        """ 是否是断线重连，仅用于Apollo。如果是True，则表示本次登录是断线重连，若是False，则表示本次是正常登录或者转服 """
        self.isPeUser = isPeUser
        """ 是否从手机端登录，仅用于Apollo。如果是True，则表示本次登录是从手机端登录，若是False，则表示本次登录是从PC端登录 """
        self.transferParam = transferParam
        """ 切服传入参数，仅用于Apollo。调用【TransferToOtherServer】或【TransferToOtherServerById】传入的切服参数 """
        self.uid = uid
        """ 仅用于Apollo，玩家的netease uid，玩家的唯一标识 """
        self.proxyId = proxyId
        """ 仅用于Apollo，当前客户端连接的proxy服务器id """

    @classmethod
    def unmarshal(cls, data):
        return cls(
            id=data["id"],
            isTransfer=data.get("isTransfer", False),
            isReconnect=data.get("isReconnect", False),
            isPeUser=data.get("isPeUser", False),
            transferParam=data.get("transferParam", ""),
            uid=data.get("uid", 0),
            proxyId=data.get("proxyId", 0),
        )

    def marshal(self):
        # type: () -> dict
        return {
            "id": self.id,
            "isTransfer": self.isTransfer,
            "isReconnect": self.isReconnect,
            "isPeUser": self.isPeUser,
            "transferParam": self.transferParam,
            "uid": self.uid,
            "proxyId": self.proxyId,
        }


class DelServerPlayerEvent(ServerEvent):
    name = "DelServerPlayerEvent"

    id = ""  # type: str
    """玩家id"""
    isTransfer = False  # type: bool
    """是否是切服时退出服务器，仅用于Apollo。如果是True，则表示切服时退出服务器；若是False，则表示退出网络游戏"""
    uid = 0  # type: int
    """玩家的netease uid，玩家的唯一标识"""

    @classmethod
    def unmarshal(cls, data):
        # type: (dict) -> DelServerPlayerEvent
        instance = cls()
        instance.id = data["id"]
        instance.isTransfer = data["isTransfer"]
        instance.uid = data["uid"]
        return instance


class ChunkAcquireDiscardedServerEvent(ServerEvent):
    name = "ChunkAcquireDiscardedServerEvent"

    dimension = 0  # type: int
    """ 区块所在维度 """
    chunkPosX = 0  # type: int
    """ 区块的x坐标，对应方块X坐标区间为[x * 16, x * 16 + 15] """
    chunkPosZ = 0  # type: int
    """ 区块的z坐标，对应方块Z坐标区间为[z * 16, z * 16 + 15] """
    entities = []  # type: list[str]
    """ 随区块卸载而从世界移除的实体id的列表。注意事件触发时已经无法获取到这些实体的信息，仅供脚本资源回收用。 """
    blockEntities = []  # type: list[dict]
    """ 随区块卸载而从世界移除的自定义方块实体的坐标的列表，列表元素dict包含posX，posY，posZ三个int表示自定义方块实体的坐标，blockName表示方块的identifier，包含命名空间及名称。注意事件触发时已经无法获取到这些方块实体的信息，仅供脚本资源回收用。 """

    @classmethod
    def unmarshal(cls, data):
        # type: (dict) -> ChunkAcquireDiscardedServerEvent
        instance = cls()
        instance.dimension = data["dimension"]
        instance.chunkPosX = data["chunkPosX"]
        instance.chunkPosZ = data["chunkPosZ"]
        instance.entities = data["entities"]
        instance.blockEntities = data["blockEntities"]
        return instance

    def marshal(self):
        # type: () -> dict
        return {
            "dimension": self.dimension,
            "chunkPosX": self.chunkPosX,
            "chunkPosZ": self.chunkPosZ,
            "entities": self.entities,
            "blockEntities": self.blockEntities,
        }


class ChunkLoadedServerEvent(ServerEvent):
    name = "ChunkLoadedServerEvent"

    dimension = 0  # type: int
    """ 区块所在维度 """
    chunkPosX = 0  # type: int
    """ 区块的x坐标，对应方块X坐标区间为[x * 16, x * 16 + 15] """
    chunkPosZ = 0  # type: int
    """ 区块的z坐标，对应方块Z坐标区间为[z * 16, z * 16 + 15] """
    blockEntities = []  # type: list[dict]
    """ 随区块加载而加载进世界的自定义方块实体的坐标的列表，列表元素dict包含posX，posY，posZ三个int表示自定义方块实体的坐标，blockName表示方块的identifier，包含命名空间及名称 """

    @classmethod
    def unmarshal(cls, data):
        # type: (dict) -> ChunkLoadedServerEvent
        instance = cls()
        instance.dimension = data["dimension"]
        instance.chunkPosX = data["chunkPosX"]
        instance.chunkPosZ = data["chunkPosZ"]
        instance.blockEntities = data["blockEntities"]
        return instance

    def marshal(self):
        # type: () -> dict
        return {
            "dimension": self.dimension,
            "chunkPosX": self.chunkPosX,
            "chunkPosZ": self.chunkPosZ,
            "blockEntities": self.blockEntities,
        }


class OnSimTickServerEvent(ServerEvent):
    name = "OnSimTickServerEvent"

    def __init__(self):
        pass

    @classmethod
    def unmarshal(cls, data):
        return cls()

    def marshal(self):
        return {}


class NewOnEntityAreaEvent(ServerEvent):
    name = "NewOnEntityAreaEvent"

    def __init__(
        self,
        name,  # type: str
        enteredEntities,  # type: list[str]
        leftEntities,  # type: list[str]
    ):
        self.name = name
        """ 注册感应区域名称 """
        self.enteredEntities = enteredEntities
        """ 进入该感应区域的实体id列表 """
        self.leftEntities = leftEntities
        """ 离开该感应区域的实体id列表 """

    @classmethod
    def unmarshal(cls, data):
        return cls(
            name=data["name"],
            enteredEntities=data["enteredEntities"],
            leftEntities=data["leftEntities"],
        )

    def marshal(self):
        # type: () -> dict
        return {
            "name": self.name,
            "enteredEntities": self.enteredEntities,
            "leftEntities": self.leftEntities,
        }


class OnContainerFillLoottableServerEvent(ServerEvent):
    name = "OnContainerFillLoottableServerEvent"

    def __init__(
        self,
        loottable,  # type: str
        playerId,  # type: str
        itemList,  # type: list
        dirty,  # type: bool
        _orig,  # type: dict
    ):
        self.loottable = loottable
        """ 奖励箱子所读取的loottable的json路径 """
        self.playerId = playerId
        """ 打开奖励箱子的玩家的playerId """
        self.itemList = itemList
        """ 掉落物品列表，每个元素为一个itemDict，格式可参考物品信息字典 """
        self.dirty = dirty
        """ 默认为False，如果需要修改掉落列表需将该值设为True """
        self._orig = _orig

    @classmethod
    def unmarshal(cls, data):
        return cls(
            loottable=data["loottable"],
            playerId=data["playerId"],
            itemList=data["itemList"],
            dirty=data["dirty"],
            _orig=data,
        )

    def marshal(self):
        # type: () -> dict
        return {
            "loottable": self.loottable,
            "playerId": self.playerId,
            "itemList": self.itemList,
            "dirty": self.dirty,
        }

    def SetDirty(self):
        self.dirty = self._orig["dirty"] = True


class OnScriptTickServer(ServerEvent):
    name = "OnScriptTickServer"

    def __init__(self):
        pass

    @classmethod
    def unmarshal(cls, data=None):
        return cls()

    def marshal(self):
        return {}
