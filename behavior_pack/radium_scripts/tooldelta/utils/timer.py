# coding: utf-8
from ..internal import (
    inClientEnv,
    inServerEnv,
)
from ..general import ClientUninitCallback, ServerUninitCallback

# TYPE_CHECKING
if 0>1:
    import typing

    PT = typing.ParamSpec("PT")
# TYPE_CHECKING END

cTimerPool = set()  # type: set
sTimerPool = set()  # type: set


def ExecLater(t, func, *args, **kwargs):
    # type: (float, typing.Callable, typing.Any, typing.Any) -> None
    "执行延迟方法"
    if inServerEnv():
        from ..srv import CF, LEVEL_ID

        LaterFunc = CF.CreateGame(LEVEL_ID).AddTimer
    elif inClientEnv():
        from ..cli import CF, LEVEL_ID

        LaterFunc = CF.CreateGame(LEVEL_ID).AddTimer
    else:
        raise Exception("Not in client or server env")
    LaterFunc(t, func, *args, **kwargs)  # pyright: ignore[reportArgumentType]


def Delay(t):
    # type: (float) -> typing.Callable[[typing.Callable[PT, typing.Any]], typing.Callable[PT, typing.Any]]
    """
    将方法固定作为延时方法

    将延迟设置为 0 即下一 tick 执行。
    """

    def wrapper(func):
        # type: (typing.Callable[PT, typing.Any]) -> typing.Callable[PT, typing.Any]
        def inner(*args, **kwargs):
            ExecLater(t, func, *args, **kwargs)

        inner.__name__ = func.__module__ + "." + func.__name__
        return inner

    return wrapper


def Repeat(t):
    # type: (float) -> typing.Callable[[typing.Callable[PT, typing.Any]], typing.Callable[PT, typing.Any]]
    """
    将方法固定作为定时执行方法
    """

    def wrapper(func):
        # type: (typing.Callable[PT, typing.Any]) -> typing.Callable[PT, typing.Any]
        def inner(*args, **kwargs):
            if inClientEnv():
                from ..cli import CF, LEVEL_ID

                game = CF.CreateGame(LEVEL_ID)
                pool = cTimerPool
            elif inServerEnv():
                from ..srv import CF, LEVEL_ID

                game = CF.CreateGame(LEVEL_ID)
                pool = sTimerPool
            else:
                raise RuntimeError("Not in client or server env")
            timer = game.AddRepeatedTimer(t, func, *args, **kwargs)  # pyright: ignore[reportArgumentType]
            pool.add(timer)

        inner.__name__ = func.__module__ + "." + func.__name__
        return inner

    return wrapper


@ServerUninitCallback()
def onServerUninit():
    from ..srv import CF, LEVEL_ID

    game = CF.CreateGame(LEVEL_ID)
    for timer in sTimerPool:
        game.CancelTimer(timer)
    sTimerPool.clear()


@ClientUninitCallback()
def onClientUninit():
    from ..cli import CF, LEVEL_ID

    game = CF.CreateGame(LEVEL_ID)
    for timer in cTimerPool:
        game.CancelTimer(timer)
    cTimerPool.clear()


AsDelayFunc = Delay
AsTimerFunc = Repeat

__all__ = ["ExecLater", "Delay", "Repeat", "AsDelayFunc", "AsTimerFunc"]
