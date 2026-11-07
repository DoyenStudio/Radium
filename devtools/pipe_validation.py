# coding=utf-8
"""Real SkyBlueTech pipe classes and world blocks; GAME interpreter only."""
import traceback
from weakref import WeakValueDictionary
import mod.server.extraServerApi as serverApi
from radium_scripts.radium.vanilla import item_codec
from skybluetech_scripts.skybluetech.server import transferlib
from skybluetech_scripts.skybluetech.server.transmitters.item_pipe import logic as item_logic
from skybluetech_scripts.skybluetech.server.transmitters.fluid_pipe import logic as fluid_logic

CF = serverApi.GetEngineCompFactory()
LEVEL = serverApi.GetLevelId()
BLOCKS = CF.CreateBlockInfo(LEVEL)
ITEMS = CF.CreateItem(LEVEL)
API = serverApi.GetComponent(LEVEL, "radium", "transfer")


class Fixture(object):
    def __init__(self, fluid=False, shape="side"):
        assert API.API_VERSION >= (1, 3, 0) and transferlib.api is API
        self.module = fluid_logic if fluid else item_logic
        self.logic = self.module.logic_module
        self.fluid = fluid
        self.pipe_name = "skybluetech:pipe_ultraheatinum" if fluid else "skybluetech:item_transport_cable_steel"
        self.network = None
        self.placed = []
        self.pipe = (-22, 100, 12)
        self.source, self.target = (-23, 100, 12), (-21, 100, 12)
        self.source_facing, self.target_facing = 4, 5
        if shape == "top":
            self.source, self.pipe, self.target = (-23, 101, 12), (-22, 101, 12), (-22, 100, 12)
            self.target_facing = 0
        elif shape == "bottom":
            self.source = (-22, 101, 12)
            self.source_facing = 1

    def place(self, pos, name):
        assert BLOCKS.GetBlockNew(pos, 0)["name"] == "minecraft:air", ("Occupied fixture", pos)
        self.placed.append(pos)
        assert BLOCKS.SetBlockNew(pos, {"name": name, "aux": 0}, 0, 0, True, False)

    def build(self, source_name, target_name):
        for pos in (self.source, self.pipe, self.target):
            support = (pos[0], pos[1] - 1, pos[2])
            if support not in (self.source, self.pipe, self.target) and support not in self.placed:
                self.place(support, "minecraft:stone")
        self.place(self.source, source_name)
        self.place(self.target, target_name)
        self.place(self.pipe, self.pipe_name)
        API.invalidate()
        output = self.logic.access_point_cls(0, self.pipe[0], self.pipe[1], self.pipe[2], self.source_facing, 2)
        target = self.logic.access_point_cls(0, self.pipe[0], self.pipe[1], self.pipe[2], self.target_facing, 1)
        network = self.logic.network_cls(0, set((target,)), set((output,)), set((self.pipe,)), self.pipe_name)
        network.enabled = False
        self.network = network
        assert self.logic.nodes_pool.get(0, {}).get(self.pipe) is None
        self.logic.nodes_pool.setdefault(0, WeakValueDictionary())[self.pipe] = network
        self.logic.networks_pool.add(network)
        for ap in (output, target):
            self.logic.access_points_pool[(0, ap.x, ap.y, ap.z, ap.access_facing)] = ap
        self.logic.apply_network_to_pool(network)
        return network

    def seed(self, pos, stacks):
        data = BLOCKS.GetBlockEntityData(0, pos)
        data["Items"] = [item_codec.encode_entry(API.item_resource(name, aux), count, slot,
                          basic_info=API.vanilla.engine.basic_info)
                          for slot, name, aux, count in stacks]
        assert BLOCKS.SetBlockEntityData(0, pos, data)
        API.invalidate()

    def port(self, pos):
        return API.query(API.FLUID if self.fluid else API.ITEM, 0, pos, None)

    def tick(self):
        # This is the exact callback used by SkyBlueTech's normal five-tick scheduler.
        self.module.onNetworkTick(self.network)

    def cleanup(self):
        if self.network is not None:
            self.network.enabled = False
            self.logic.delete_network(self.network)
        for pos in reversed(self.placed):
            data = BLOCKS.GetBlockEntityData(0, pos)
            if data is not None and "Items" in data:
                data["Items"] = []
                assert BLOCKS.SetBlockEntityData(0, pos, data)
        for pos in reversed(self.placed):
            assert BLOCKS.SetBlockNew(pos, {"name": "minecraft:air", "aux": 0}, 0, 0, True, False)
        API.invalidate()


def item_case(source_name, target_name, shape, stacks, slot, expected, expected_id):
    fixture = Fixture(shape=shape)
    try:
        fixture.build(source_name, target_name)
        fixture.seed(fixture.source, stacks)
        calls = []
        original = API.move_item
        def traced(source, target, resource, amount, tx):
            moved = original(source, target, resource, amount, tx)
            calls.append(moved)
            return moved
        API.move_item = traced
        try:
            fixture.tick()
        finally:
            API.move_item = original
        port = fixture.port(fixture.target)
        assert port.get_amount(slot) == expected, (target_name, port.get_amount(slot), calls)
        if expected:
            assert port.get_resource(slot).item_id == expected_id
        assert calls and sum(calls) == expected, ("Not a successful radium pipe path", calls)
        return {"moved": sum(calls), "radium_calls": len(calls)}
    finally:
        fixture.cleanup()


def fluid_case(resource, budget, expected):
    fixture = Fixture(fluid=True)
    try:
        network = fixture.build("minecraft:cauldron", "minecraft:cauldron")
        original_budget = network.transfer_speed
        if budget is not None:
            network.transfer_speed = budget
        try:
            with API.open_transaction() as tx:
                assert fixture.port(fixture.source).insert(resource, 1000, tx) == 1000
                tx.commit()
            calls = []
            original = API.move_fluid
            def traced(source, target, fluid, amount, tx):
                moved = original(source, target, fluid, amount, tx)
                calls.append(moved)
                return moved
            API.move_fluid = traced
            try:
                fixture.tick()
                fixture.tick()
                fixture.tick()
            finally:
                API.move_fluid = original
            source = fixture.port(fixture.source).get_amount(0)
            target = fixture.port(fixture.target).get_amount(0)
            assert source + target + network.fluid_volume == 1000
            assert target == expected, (source, target, network.fluid_volume, calls)
            assert calls, "Pipe did not use radium"
            return {"source": source, "target": target, "buffer": network.fluid_volume,
                    "budget": network.transfer_speed, "radium_calls": len(calls)}
        finally:
            network.transfer_speed = original_budget
    finally:
        fixture.cleanup()


def run():
    results, failed = {}, {}
    normal = ("chest", "trapped_chest", "barrel", "copper_chest", "waxed_oxidized_copper_chest",
              "undyed_shulker_box", "red_shulker_box", "hopper", "dispenser", "dropper")
    cases = [("ordinary/" + name, ("minecraft:barrel", "minecraft:" + name, "side",
              ((0, "minecraft:stone", 0, 8),), 0, 5, "minecraft:stone")) for name in normal]
    for name in ("furnace", "smoker", "blast_furnace"):
        full = "minecraft:" + name
        cases.extend((
            (name + "/top", ("minecraft:barrel", full, "top", ((0,"minecraft:iron_ore",0,5),),0,5,"minecraft:iron_ore")),
            (name + "/fuel", ("minecraft:barrel", full, "side", ((0,"minecraft:coal",0,5),),1,5,"minecraft:coal")),
            (name + "/bottom", (full,"minecraft:barrel","bottom",((2,"minecraft:iron_ingot",0,5),),0,5,"minecraft:iron_ingot")),
            (name + "/bucket", (full,"minecraft:barrel","bottom",((1,"minecraft:bucket",0,1),),0,1,"minecraft:bucket"))))
    cases.extend((
        ("brewing/reagent", ("minecraft:barrel","minecraft:brewing_stand","top",((0,"minecraft:nether_wart",0,5),),0,5,"minecraft:nether_wart")),
        ("brewing/fuel", ("minecraft:barrel","minecraft:brewing_stand","side",((0,"minecraft:blaze_powder",0,5),),4,5,"minecraft:blaze_powder")),
        ("brewing/bottle", ("minecraft:barrel","minecraft:brewing_stand","side",((0,"minecraft:potion",0,1),),1,1,"minecraft:potion")),
        ("brewing/output", ("minecraft:brewing_stand","minecraft:barrel","bottom",((1,"minecraft:potion",0,1),),0,1,"minecraft:potion"))))
    for label, args in cases:
        try:
            results[label] = item_case(*args)
        except Exception:
            failed[label] = traceback.format_exc()
    for label, resource, budget, expected in (
            ("water/normal", "minecraft:water", None, 1000),
            ("lava/normal", "minecraft:lava", None, 0),
            ("lava/1000", "minecraft:lava", 1000, 1000)):
        try:
            results[label] = fluid_case(resource, budget, expected)
        except Exception:
            failed[label] = traceback.format_exc()
    return {"ok": not failed, "passed": len(results), "total": len(cases) + 3,
            "failed": failed, "details": results}
