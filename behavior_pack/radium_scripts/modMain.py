# coding=utf-8
from mod.common.mod import Mod


@Mod.Binding(name="radium", version="1.3.0")
class Radium(object):
    @Mod.InitServer()
    def init_server(self):
        import mod.server.extraServerApi as serverApi
        serverApi.RegisterSystem("radium", "radium.TDServer",
                                 "radium_scripts.radium.server.runtime.RadiumServer")
