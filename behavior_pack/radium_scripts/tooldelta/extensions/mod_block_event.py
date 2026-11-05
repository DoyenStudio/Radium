# coding=utf-8

from ..events.client import (
    ModBlockEntityLoadedClientEvent,
    ModBlockEntityRemoveClientEvent,
    ModBlockEntityTickClientEvent,
)

# TYPE CHECKING
if 0>1:
    import typing

    CT = typing.TypeVar(
        "CT", bound=typing.Callable[[ModBlockEntityLoadedClientEvent], None]
    )
    RT = typing.TypeVar(
        "RT", bound=typing.Callable[[ModBlockEntityRemoveClientEvent], None]
    )
    TT = typing.TypeVar(
        "TT", bound=typing.Callable[[ModBlockEntityTickClientEvent], None]
    )
# TYPE CHECKING END

mod_block_loaded_cbs = {}  # type: dict[str, list[typing.Callable[[ModBlockEntityLoadedClientEvent], None]]]
mod_block_removed_cbs = {}  # type: dict[str, list[typing.Callable[[ModBlockEntityRemoveClientEvent], None]]]
mod_block_tick_cbs = {}  # type: dict[str, list[typing.Callable[[ModBlockEntityTickClientEvent], None]]]


def asModBlockLoadedListener(
    block_id,  # type: str
):
    def decorator(func):
        # type: (CT) -> CT
        mod_block_loaded_cbs.setdefault(block_id, []).append(func)
        return func

    return decorator


def asModBlockRemovedListener(
    block_id,  # type: str
):
    def decorator(func):
        # type: (RT) -> RT
        mod_block_removed_cbs.setdefault(block_id, []).append(func)
        return func

    return decorator


def asModBlockTickListener(
    block_id,  # type: str
):
    def decorator(func):
        # type: (TT) -> TT
        mod_block_tick_cbs.setdefault(block_id, []).append(func)
        return func

    return decorator


@ModBlockEntityLoadedClientEvent.Listen()
def _onModBlockLoaded(event):
    # type: (ModBlockEntityLoadedClientEvent) -> None
    cbs = mod_block_loaded_cbs.get(event.blockName)
    if cbs is None:
        return
    for cb in cbs:
        cb(event)


@ModBlockEntityRemoveClientEvent.Listen()
def _onModBlockRemoved(event):
    # type: (ModBlockEntityRemoveClientEvent) -> None
    cbs = mod_block_removed_cbs.get(event.blockName)
    if cbs is None:
        return
    for cb in cbs:
        cb(event)


@ModBlockEntityTickClientEvent.Listen()
def _onModBlockTick(event):
    # type: (ModBlockEntityTickClientEvent) -> None
    cbs = mod_block_tick_cbs.get(event.blockName)
    if cbs is None:
        return
    for cb in cbs:
        cb(event)
