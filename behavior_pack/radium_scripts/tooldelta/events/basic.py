# coding=utf-8
from mod.server.extraServerApi import GetEngineNamespace, GetEngineSystemName


class ServerEvent(object):
    @classmethod
    def Listen(cls, system, listener):
        """Bind a system method to this native event. Radium only uses the signal."""
        system.ListenForEvent(GetEngineNamespace(), GetEngineSystemName(),
                              cls.name, system, listener)
