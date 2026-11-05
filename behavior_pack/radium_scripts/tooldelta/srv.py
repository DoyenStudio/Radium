# coding=utf-8
from mod.server.extraServerApi import GetLevelId, GetEngineCompFactory

CF = GetEngineCompFactory()
LEVEL_ID = GetLevelId()

__all__ = ["CF", "LEVEL_ID"]
