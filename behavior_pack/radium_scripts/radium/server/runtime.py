# coding=utf-8
import mod.server.extraServerApi as serverApi
from radium_scripts.tooldelta.srv import LEVEL_ID
from radium_scripts.tooldelta.events.server.world import (
    OnSimTickServerEvent, ChunkAcquireDiscardedServerEvent, ChunkLoadedServerEvent)
from radium_scripts.tooldelta.events.server.block import (
    BlockRemoveServerEvent, BlockNeighborChangedServerEvent, EntityPlaceBlockAfterServerEvent)


class RadiumServer(serverApi.GetServerSystemCls()):
    def __init__(self, namespace, name):
        super(RadiumServer, self).__init__(namespace, name)
        path = "radium_scripts.radium.server.component.TransferComponent"
        if not serverApi.RegisterComponent(namespace, "transfer", path):
            raise RuntimeError("radium: component registration failed")
        self.component = serverApi.CreateComponent(LEVEL_ID, namespace, "transfer")
        if self.component is None:
            raise RuntimeError("radium: component creation failed")

        OnSimTickServerEvent.Listen(self, self._on_tick)
        for event in (BlockRemoveServerEvent, BlockNeighborChangedServerEvent,
                      EntityPlaceBlockAfterServerEvent, ChunkAcquireDiscardedServerEvent,
                      ChunkLoadedServerEvent):
            event.Listen(self, self._invalidate)

    def _on_tick(self, event):
        if self.component is not None:
            self.component.tick()

    def _invalidate(self, event):
        if self.component is not None:
            self.component.invalidate()

    def Destroy(self):
        if self.component is not None:
            self.component.tick()
            self.component.invalidate()
            self.component.registry.providers.clear()
            self.component = None
