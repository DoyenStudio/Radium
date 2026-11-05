from ..general import ClientInitCallback, ServerInitCallback
from ..events.client import UiInitFinishedEvent
from ..events.server import DelServerPlayerEvent
from ..events.basic import CustomC2SEvent

if 0>1:
    import typing

player_completely_loaded_cbs = []  # type: list[typing.Callable[[str], None]]
loaded_players = set()  # type: set[str]
loaded = False


class _PlayerCompletelyLoadedNotify(CustomC2SEvent):
    name = "td:PlayerCompletelyLoadedNotify"

    def __init__(self, player_id=""):
        self.player_id = player_id

    def marshal(self):
        return {}

    @classmethod
    def unmarshal(cls, data):
        return cls(data["__id__"])


def AddPlayerCompletelyLoadedServerCallback(cb):
    # type: (typing.Callable[[str], None]) -> None
    player_completely_loaded_cbs.append(cb)


@ClientInitCallback()
def onClientInited():
    @UiInitFinishedEvent.Listen()
    def onUiInitFinished(_):
        global loaded
        if loaded:
            return
        loaded = True
        _PlayerCompletelyLoadedNotify().send()


@ServerInitCallback()
def onServerInited():
    @_PlayerCompletelyLoadedNotify.Listen()
    def onPlayerCompletelyLoaded(event):
        # type: (_PlayerCompletelyLoadedNotify) -> None
        if event.player_id in loaded_players:
            return
        for cb in player_completely_loaded_cbs:
            cb(event.player_id)
        loaded_players.add(event.player_id)

    @DelServerPlayerEvent.Listen()
    def onDelPlayer(event):
        # type: (DelServerPlayerEvent) -> None
        loaded_players.discard(event.id)
