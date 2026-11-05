# coding=utf-8
import mod.server.extraServerApi as serverApi
from radium_scripts.tooldelta.srv import CF, LEVEL_ID
from radium_scripts.tooldelta.events.server.block import BlockRemoveServerEvent
from radium_scripts.radium.core.service import TransferService

ComponentBase = serverApi.GetComponentCls()


class TransferComponent(ComponentBase, TransferService):
    def __init__(self, entity_id):
        ComponentBase.__init__(self, entity_id)
        TransferService.__init__(self, self._is_loaded, self._block_name)

    @staticmethod
    def _is_loaded(dimension, pos):
        return CF.CreateChunkSource(LEVEL_ID).CheckChunkState(dimension, pos)

    @staticmethod
    def _block_name(dimension, pos):
        block = CF.CreateBlockInfo(LEVEL_ID).GetBlockNew(pos, dimension)
        return block.get("name") if block else None

    def register_provider(self, capability, block_id, provider):
        TransferService.register_provider(self, capability, block_id, provider)
        # Native removal events need explicit registration for custom blocks.
        BlockRemoveServerEvent.AddExtraBlocks(set((block_id,)))
