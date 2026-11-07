# coding=utf-8
"""Explicit native hopper comparison; load only in the game's server interpreter."""
import traceback
import mod.server.extraServerApi as serverApi

CF = serverApi.GetEngineCompFactory()
LEVEL = serverApi.GetLevelId()
BLOCKS = CF.CreateBlockInfo(LEVEL)
ITEMS = CF.CreateItem(LEVEL)
GAME = CF.CreateGame(LEVEL)
TARGET = (-22, 100, 12)
REGION = (TARGET, (-22, 99, 12), (-23, 100, 12), (-22, 101, 12))
CASES = (
    ("furnace_top_dirt", "furnace", "top", "dirt", 0),
    ("furnace_side_planks", "furnace", "side", "oak_planks", 0),
    ("furnace_side_coal_block", "furnace", "side", "coal_block", 0),
    ("furnace_side_crimson", "furnace", "side", "crimson_planks", 0),
    ("furnace_side_bucket", "furnace", "side", "bucket", 0),
    ("furnace_bottom_bucket", "furnace", "bottom", "bucket", 1),
    ("brewing_bottom_residual_bottle", "brewing_stand", "bottom", "glass_bottle", 0),
    ("brewing_bottom_potion", "brewing_stand", "bottom", "potion", 1),
    ("brewing_side_glass_bottle", "brewing_stand", "side", "glass_bottle", 0),
    ("brewing_side_blaze", "brewing_stand", "side", "blaze_powder", 0),
    ("brewing_top_wart", "brewing_stand", "top", "nether_wart", 0))
results = []
done = False
owned = set()


def atom(kind, val):
    return {"__type__": kind, "__value__": val}


def clear():
    for pos in tuple(owned):
        block = BLOCKS.GetBlockNew(pos, 0)
        if block and block["name"] != "minecraft:air":
            data = BLOCKS.GetBlockEntityData(0, pos)
            if data is not None and "Items" in data:
                data["Items"] = []
                BLOCKS.SetBlockEntityData(0, pos, data)
            BLOCKS.SetBlockNew(pos, {"name": "minecraft:air", "aux": 0}, 0, 0, True, False)
        owned.discard(pos)


def place(pos, name, aux=0):
    owned.add(pos)
    BLOCKS.SetBlockNew(pos, {"name": "minecraft:" + name, "aux": aux}, 0, 0, True, False)


def start(index=0):
    global done
    if index == len(CASES):
        done = True
        return
    try:
        assert all(BLOCKS.GetBlockNew(p, 0)["name"] == "minecraft:air" for p in REGION)
        label, block, direction, item, slot = CASES[index]
        hopper = {"top": (-22, 101, 12), "side": (-23, 100, 12),
                  "bottom": (-22, 99, 12)}[direction]
        if direction != "bottom":
            place((-22, 99, 12), "stone")
        place(TARGET, block)
        place(hopper, "hopper", 5 if direction == "side" else 0)
        if direction == "bottom":
            data = BLOCKS.GetBlockEntityData(0, TARGET)
            data["Items"] = [{"Name": atom(8, "minecraft:" + item), "Count": atom(1, 1),
                              "Slot": atom(1, slot), "Damage": atom(2, 0)}]
            assert BLOCKS.SetBlockEntityData(0, TARGET, data)
        else:
            assert ITEMS.SpawnItemToContainer({"newItemName": "minecraft:" + item,
                                              "newAuxValue": 0, "count": 1}, 0, hopper, 0)
        GAME.AddTimer(1.0, finish, index, hopper)
    except Exception:
        results.append({"case": CASES[index][0], "error": traceback.format_exc()})
        clear()
        done = True


def finish(index, hopper):
    global done
    try:
        data = BLOCKS.GetBlockEntityData(0, TARGET)
        inventory = [(entry["Slot"]["__value__"], entry["Name"]["__value__"],
                      entry["Count"]["__value__"]) for entry in data["Items"]]
        extracted = [ITEMS.GetContainerItem(hopper, slot, 0, True) for slot in range(5)]
        results.append({"case": CASES[index][0], "target": inventory,
                        "hopper": [(s["newItemName"], s["count"]) for s in extracted if s]})
    except Exception:
        results.append({"case": CASES[index][0], "error": traceback.format_exc()})
        done = True
    finally:
        clear()
    if not done:
        start(index + 1)
