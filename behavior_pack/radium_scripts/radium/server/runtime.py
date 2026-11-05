# coding=utf-8
import mod.server.extraServerApi as serverApi
from radium_scripts.tooldelta.srv import LEVEL_ID
from radium_scripts.tooldelta.general import ServerUninitCallback
from radium_scripts.tooldelta.events.server.world import (
    OnSimTickServerEvent, ChunkAcquireDiscardedServerEvent, ChunkLoadedServerEvent)
from radium_scripts.tooldelta.events.server.block import (
    BlockRemoveServerEvent, BlockNeighborChangedServerEvent, EntityPlaceBlockAfterServerEvent)

NAMESPACE = "radium"
COMPONENT = "transfer"
_component = None


def start():
    global _component
    if _component is not None:
        return
    path = "radium_scripts.radium.server.component.TransferComponent"
    if not serverApi.RegisterComponent(NAMESPACE, COMPONENT, path):
        raise RuntimeError("radium: component registration failed")
    _component = serverApi.CreateComponent(LEVEL_ID, NAMESPACE, COMPONENT)
    if _component is None:
        raise RuntimeError("radium: component creation failed")


@OnSimTickServerEvent.Listen()
def _on_tick(event):
    if _component is not None:
        _component.tick()


def _invalidate(event):
    if _component is not None:
        _component.invalidate()


# Separate wrappers: ToolDelta marks static listeners on the function object.
@BlockRemoveServerEvent.Listen()
def _on_remove(event):
    _invalidate(event)


@BlockNeighborChangedServerEvent.Listen()
def _on_neighbor(event):
    _invalidate(event)


@EntityPlaceBlockAfterServerEvent.Listen()
def _on_place(event):
    _invalidate(event)


@ChunkAcquireDiscardedServerEvent.Listen()
def _on_chunk_unloaded(event):
    _invalidate(event)


@ChunkLoadedServerEvent.Listen()
def _on_chunk_loaded(event):
    _invalidate(event)


@ServerUninitCallback()
def _on_stop():
    global _component
    if _component is not None:
        _component.tick()
        _component.invalidate()
        _component.registry.providers.clear()
        _component = None
