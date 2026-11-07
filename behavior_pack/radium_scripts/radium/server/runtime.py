# coding=utf-8
import mod.server.extraServerApi as serverApi
from radium_scripts.tooldelta.srv import CF, LEVEL_ID
from radium_scripts.tooldelta.events.server.command import CustomCommandTriggerServerEvent
from radium_scripts.tooldelta.events.server.world import (
    OnSimTickServerEvent, ChunkAcquireDiscardedServerEvent, ChunkLoadedServerEvent)
from radium_scripts.tooldelta.events.server.block import (
    BlockRemoveServerEvent, BlockNeighborChangedServerEvent, EntityPlaceBlockAfterServerEvent)

CAULDRON_SETTING = "radium:cauldron_interact"


class RadiumServer(serverApi.GetServerSystemCls()):
    def __init__(self, namespace, name):
        super(RadiumServer, self).__init__(namespace, name)
        path = "radium_scripts.radium.server.component.TransferComponent"
        if not serverApi.RegisterComponent(namespace, "transfer", path):
            raise RuntimeError("radium: component registration failed")
        self.component = serverApi.CreateComponent(LEVEL_ID, namespace, "transfer")
        if self.component is None:
            raise RuntimeError("radium: component creation failed")

        self.settings = CF.CreateExtraData(LEVEL_ID)
        if self.settings.GetExtraData(CAULDRON_SETTING) == 1:
            self.component.vanilla.set_cauldron_interact(True)
        CustomCommandTriggerServerEvent.Listen(self, self._on_command)
        OnSimTickServerEvent.Listen(self, self._on_tick)
        for event in (BlockRemoveServerEvent, BlockNeighborChangedServerEvent,
                      EntityPlaceBlockAfterServerEvent, ChunkAcquireDiscardedServerEvent,
                      ChunkLoadedServerEvent):
            event.Listen(self, self._invalidate)

    def _save_cauldron_setting(self):
        enabled = self.component.vanilla.cauldron_interact
        if not self.settings.SetExtraData(CAULDRON_SETTING, int(enabled), True):
            raise RuntimeError("radium: could not save cauldron_interact")

    def _on_command(self, event):
        if event.get("command") != "radium" or self.component is None:
            return
        args = [arg.get("value") for arg in event["args"]]
        if args == ["version"]:
            version = ".".join(map(str, self.component.API_VERSION))
            event["return_msg_key"] = "radium API %s" % version
            return
        if (len(args) != 3 or args[0] != "function" or args[1] not in ("enable", "disable")
                or args[2] != "cauldron_interact"):
            event["return_failed"] = True
            event["return_msg_key"] = "用法：/radium function <enable|disable> cauldron_interact"
            return
        enabled = args[1] == "enable"
        vanilla = self.component.vanilla
        if enabled != vanilla.cauldron_interact:
            try:
                vanilla.set_cauldron_interact(enabled)
            except (ValueError, self.component.TransactionError) as exc:
                event["return_failed"] = True
                event["return_msg_key"] = "切换 cauldron_interact 失败：%s" % exc
                return
            self.component.manager.dirty[CAULDRON_SETTING] = self._save_cauldron_setting
        event["return_msg_key"] = "cauldron_interact 已启用" if enabled else "cauldron_interact 已禁用"

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
