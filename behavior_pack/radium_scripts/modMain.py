# coding=utf-8
from radium_scripts.tooldelta.mod_main import ToolDeltaMod, RegisterMod


@RegisterMod()
class Radium(ToolDeltaMod):
    name = "radium"
    version = (1, 1, 0)

    def OnServerInited(self):
        from radium_scripts.radium.server.runtime import start
        start()
