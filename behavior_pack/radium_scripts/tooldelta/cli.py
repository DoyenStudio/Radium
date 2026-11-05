# coding=utf-8
from mod.client.extraClientApi import GetLevelId, GetEngineCompFactory

CF = GetEngineCompFactory()
LEVEL_ID = GetLevelId()

__all__ = ["CF", "LEVEL_ID"]
