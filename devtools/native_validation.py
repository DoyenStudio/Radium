# coding=utf-8
"""Explicit real-world acceptance checks; GAME Python 2.7.13 only.

Run with MCDK execute_code after reviewing the fixed, empty test area. This script
places and removes temporary blocks. It never reloads the game or the live addon.
run("ordinary"), run("double/minecraft:chest"), run("cauldron") select prefixes;
run(["furnace", "brewing", "metadata"]) selects several groups. Each invocation
runs synchronously; these tests do not claim natural processing across game ticks.
"""
import sys
import os
import json
import traceback
import types


HELPER = "D:/addon/transferlib/devtools/isolated_tests.py"
PREFIX = "_radium_native_validation"
DIMENSION = 0
FIRST = (-23, 100, 12)
SECOND = (-20, 100, 12)
THIRD = (-18, 100, 12)
WATER = "minecraft:water"
LAVA = "minecraft:lava"
LEVELS = (0, 167, 333, 500, 667, 833, 1000)


def atom(kind, value):
    return {"__type__": kind, "__value__": value}


def region():
    return ((x, y, z) for x in range(-24, -16)
            for y in range(99, 103) for z in range(10, 17))


def assert_empty(blocks, chunks):
    for pos in region():
        assert chunks.CheckChunkState(DIMENSION, pos), ("Unloaded test area", pos)
        block = blocks.GetBlockNew(pos, DIMENSION)
        assert block and block["name"] == "minecraft:air", ("Test area is occupied", pos, block)


class Fixture(object):
    def __init__(self, service_module, factory, level_id):
        self.blocks = factory.CreateBlockInfo(level_id)
        self.chunks = factory.CreateChunkSource(level_id)
        self.items = factory.CreateItem(level_id)
        self.states = factory.CreateBlockState(level_id)
        self.placed = []
        self.reports = []
        self.api = service_module.TransferService(
            lambda d, p: self.chunks.CheckChunkState(d, p), self.block_name,
            report=self.reports.append)
        registry_module = sys.modules[PREFIX + ".vanilla.registry"]
        self.registry = registry_module.VanillaRegistry(self.api, factory, level_id)
        self.registry.set_cauldron_interact(True)
        self.codec = sys.modules[PREFIX + ".vanilla.item_codec"]
        self.rules = sys.modules[PREFIX + ".vanilla.rules"]
        self.engine = self.registry.engine

    def block_name(self, dimension, pos):
        data = self.blocks.GetBlockNew(pos, dimension)
        return data.get("name") if data else None

    def _place(self, pos, name, aux=0, neighbors=False):
        assert pos in set(region()), ("Outside test area", pos)
        assert self.block_name(DIMENSION, pos) == "minecraft:air", ("Occupied", pos)
        # Record before calling the setter: a failing write may still mutate.
        self.placed.append((pos, name))
        ok = self.blocks.SetBlockNew(pos, {"name": name, "aux": aux},
                                     0, DIMENSION, True, neighbors)
        observed = self.blocks.GetBlockNew(pos, DIMENSION)
        assert ok and observed and observed["name"] != "minecraft:air", (name, pos, observed)
        if name in self.rules.SHULKERS:
            assert observed["name"] in self.rules.SHULKERS, observed
        else:
            assert observed["name"] == name, (name, observed)
        return observed

    def place(self, name, pos=FIRST, aux=0, neighbors=False):
        self._place((pos[0], pos[1] - 1, pos[2]), "minecraft:stone")
        return self._place(pos, name, aux, neighbors)

    def port(self, pos=FIRST, face=None, fluid=False):
        handler = self.api.query(self.api.FLUID if fluid else self.api.ITEM,
                                 DIMENSION, pos, face)
        assert handler is not None, ("Missing native port", pos, face, self.reports)
        return handler

    def resource(self, name, aux=0, properties=None):
        return self.codec.canonical(self.api.item_resource(name, aux, properties),
                                    self.engine.basic_info)

    def seed_nbt(self, pos, slots):
        data = self.blocks.GetBlockEntityData(DIMENSION, pos)
        assert isinstance(data, dict)
        data["Items"] = [self.codec.encode_entry(resource, count, slot,
                         basic_info=self.engine.basic_info)
                         for slot, resource, count in slots if count]
        assert self.blocks.SetBlockEntityData(DIMENSION, pos, data)
        self.registry.invalidate()
        self.api.invalidate()

    def set_liquid(self, resource, level):
        assert self.states.SetBlockStates(FIRST, {
            "cauldron_liquid": "lava" if resource == LAVA else "water",
            "fill_level": level}, DIMENSION)
        self.registry.invalidate()
        self.api.invalidate()

    def cleanup(self):
        errors = []
        self.registry.invalidate()
        self.api.invalidate()
        # Clear all inventories before destroying either half of any paired chest.
        for pos, name in reversed(self.placed):
            try:
                current = self.block_name(DIMENSION, pos)
                allowed = self.rules.SHULKERS if name in self.rules.SHULKERS else (name,)
                if name in self.rules.FURNACES:
                    base = name.replace("minecraft:lit_", "minecraft:")
                    allowed = (base, base.replace("minecraft:", "minecraft:lit_"))
                assert current == "minecraft:air" or current in allowed, (
                    "Refusing to remove an unexpected block", pos, name, current)
                if current != "minecraft:air" and name != "minecraft:stone":
                    data = self.blocks.GetBlockEntityData(DIMENSION, pos)
                    if data and "Items" in data:
                        size = self.items.GetContainerSize(pos, DIMENSION)
                        if size > 0:
                            # The native NBT setter may address only the lead
                            # half after a saved double chest has been loaded.
                            for slot in range(size):
                                if self.items.GetContainerItem(pos, slot, DIMENSION, True):
                                    assert self.items.SpawnItemToContainer({}, slot, pos, DIMENSION)
                        else:
                            data["Items"] = []
                            assert self.blocks.SetBlockEntityData(DIMENSION, pos, data)
                        assert not self.blocks.GetBlockEntityData(DIMENSION, pos).get("Items")
            except Exception:
                errors.append(traceback.format_exc())
        if errors:
            raise AssertionError("Inventory cleanup failed; blocks retained:\n" + "\n".join(errors))
        for pos, name in reversed(self.placed):
            try:
                if self.block_name(DIMENSION, pos) != "minecraft:air":
                    assert self.blocks.SetBlockNew(pos, {"name": "minecraft:air", "aux": 0},
                                                   0, DIMENSION, True, False)
                assert self.block_name(DIMENSION, pos) == "minecraft:air"
            except Exception:
                errors.append(traceback.format_exc())
        if errors:
            raise AssertionError("Block cleanup failed:\n" + "\n".join(errors))


def ordinary(fixture, name):
    observed = fixture.place(name)
    size = fixture.rules.profile(observed["name"])[1]
    assert fixture.items.GetContainerSize(FIRST, DIMENSION) == size
    handler = fixture.port()
    assert handler.get_slots() == tuple(range(size))
    for face in range(6):
        other = fixture.port(face=face)
        assert other.storage_ids == handler.storage_ids
        assert other.get_slots() == handler.get_slots()
    item = fixture.resource("minecraft:stone")
    with fixture.api.open_transaction() as tx:
        assert handler.insert(item, 7, tx, size - 1) == 7
        assert fixture.codec.decode_stack(fixture.items.GetContainerItem(
            FIRST, size - 1, DIMENSION, True), fixture.engine.basic_info) == (None, 0)
        tx.commit()
    actual = fixture.codec.decode_stack(fixture.items.GetContainerItem(
        FIRST, size - 1, DIMENSION, True), fixture.engine.basic_info)
    assert actual == (item, 7), actual
    with fixture.api.open_transaction() as tx:
        assert handler.extract(item, 7, tx, size - 1) == 7
        tx.commit()
    assert handler.get_amount(size - 1) == 0
    # Exercise every physical slot, then overwrite cleared slots with distinct
    # stack limits. No native writes occur before the root commits.
    with fixture.api.open_transaction() as tx:
        for slot in range(size):
            assert handler.insert(item, slot + 1, tx, slot) == slot + 1
        tx.commit()
    for slot in range(size):
        assert fixture.codec.decode_stack(fixture.items.GetContainerItem(
            FIRST, slot, DIMENSION, True), fixture.engine.basic_info) == (item, slot + 1)
    with fixture.api.open_transaction() as tx:
        for slot in range(size):
            assert handler.extract(item, slot + 1, tx, slot) == slot + 1
        tx.commit()
    snowball = fixture.resource("minecraft:snowball")
    sword = fixture.resource("minecraft:diamond_sword")
    with fixture.api.open_transaction() as tx:
        assert handler.insert(item, 65, tx, 0) == 64
        assert handler.insert(snowball, 17, tx, size - 1) == 16
        assert handler.insert(sword, 2, tx, 1) == 1
        tx.commit()
    assert handler.get_amount(0) == 64 and handler.get_amount(size - 1) == 16
    assert handler.get_amount(1) == 1
    return {"block": observed, "capacity": size}


def double_chest(fixture, name, facing, reverse):
    direction = {2: "north", 3: "south", 4: "west", 5: "east"}[facing]
    aux = fixture.states.GetBlockAuxValueFromStates(
        name, {"minecraft:cardinal_direction": direction})
    assert isinstance(aux, (int, long)) and aux >= 0, (name, direction, aux)
    offset = (1, 0, 0) if facing in (2, 3) else (0, 0, 1)
    paired = tuple(FIRST[index] + offset[index] for index in range(3))
    order = (paired, FIRST) if reverse else (FIRST, paired)
    for pos in order:
        fixture.place(name, pos, aux, True)
        assert fixture.states.GetBlockStates(pos, DIMENSION).get(
            "minecraft:cardinal_direction") == direction
    assert tuple(fixture.blocks.GetChestPairedPosition(FIRST, DIMENSION)) == paired
    assert tuple(fixture.blocks.GetChestPairedPosition(paired, DIMENSION)) == FIRST
    for pos in (FIRST, paired):
        assert fixture.items.GetContainerSize(pos, DIMENSION) == 54
    left, right = fixture.port(), fixture.port(paired)
    assert left.storage_ids == right.storage_ids
    assert left.get_slots() == right.get_slots() == tuple(range(54))
    item = fixture.resource("minecraft:stone")
    with fixture.api.open_transaction() as tx:
        for slot in range(54):
            assert left.insert(item, slot + 1, tx, slot) == slot + 1
        tx.commit()
    anchor = min(FIRST, paired)
    for slot in range(54):
        assert left.get_amount(slot) == right.get_amount(slot) == slot + 1
        assert fixture.codec.decode_stack(fixture.items.GetContainerItem(
            anchor, slot, DIMENSION, True), fixture.engine.basic_info) == (item, slot + 1)
    with fixture.api.open_transaction() as tx:
        for slot in range(54):
            assert right.extract(item, slot + 1, tx, slot) == slot + 1
        tx.commit()
    assert all(left.get_amount(slot) == 0 for slot in range(54))


def furnace(fixture, name):
    fixture.place(name)
    item = fixture.resource("minecraft:iron_ore")
    fuel = fixture.resource("minecraft:coal")
    output = fixture.resource("minecraft:iron_ingot")
    bucket = fixture.resource("minecraft:bucket")
    top, bottom = fixture.port(face=1), fixture.port(face=0)
    with fixture.api.open_transaction() as tx:
        assert top.insert(item, 3, tx) == 3
        assert top.get_amount(0, tx) == 3 and top.get_amount(1, tx) == 0
        assert top.extract(item, 3, tx) == 0
        assert bottom.insert(item, 1, tx) == 0
        tx.commit()
    for face in (2, 3, 4, 5):
        side = fixture.port(face=face)
        with fixture.api.open_transaction() as tx:
            assert side.insert(item, 1, tx) == 0
            assert side.insert(bucket, 1, tx) == 0
            assert side.insert(fuel, 1, tx) == 1
            assert side.extract(fuel, 1, tx) == 0
            assert side.get_amount(1, tx) == 1
        assert side.get_amount(1) == 0
    with fixture.api.open_transaction() as tx:
        assert fixture.port(face=2).insert(fuel, 2, tx) == 2
        tx.commit()
    fixture.seed_nbt(FIRST, ((0, item, 3), (1, fuel, 2), (2, output, 4)))
    with fixture.api.open_transaction() as tx:
        bottom = fixture.port(face=0)
        assert bottom.extract(fuel, 2, tx) == 0
        assert bottom.extract(output, 4, tx) == 4
        tx.commit()
    fixture.seed_nbt(FIRST, ((1, bucket, 1),))
    with fixture.api.open_transaction() as tx:
        assert fixture.port(face=0).extract(bucket, 1, tx) == 1
        tx.commit()


def brewing(fixture):
    fixture.place("minecraft:brewing_stand")
    reagent = fixture.resource("minecraft:nether_wart")
    fuel = fixture.resource("minecraft:blaze_powder")
    bottle = fixture.resource("minecraft:potion", 0)
    glass = fixture.resource("minecraft:glass_bottle")
    stone = fixture.resource("minecraft:stone")
    top = fixture.port(face=1)
    with fixture.api.open_transaction() as tx:
        assert top.insert(reagent, 2, tx) == 2
        assert top.get_amount(0, tx) == 2
        assert top.insert(bottle, 1, tx) == 0
        assert top.extract(reagent, 1, tx) == 0
        tx.commit()
    for face in (2, 3, 4, 5):
        side = fixture.port(face=face)
        with fixture.api.open_transaction() as tx:
            assert side.insert(reagent, 1, tx) == 0
            assert side.insert(stone, 1, tx) == 0
            assert side.insert(bottle, 4, tx) == 3
            assert all(side.get_amount(slot, tx) == 1 for slot in (1, 2, 3))
            assert side.insert(fuel, 2, tx) == 2
            assert side.get_amount(4, tx) == 2
            assert side.extract(bottle, 1, tx) == 0
    with fixture.api.open_transaction() as tx:
        side = fixture.port(face=2)
        assert side.insert(bottle, 3, tx) == 3
        assert side.insert(fuel, 2, tx) == 2
        tx.commit()
    with fixture.api.open_transaction() as tx:
        bottom = fixture.port(face=0)
        assert bottom.insert(bottle, 1, tx) == 0
        assert bottom.extract(reagent, 2, tx) == 0
        assert bottom.extract(fuel, 2, tx) == 0
        assert bottom.extract(bottle, 3, tx) == 3
        tx.commit()
    fixture.seed_nbt(FIRST, ((0, glass, 1),))
    bottom = fixture.port(face=0)
    with fixture.api.open_transaction() as tx:
        assert bottom.extract(glass, 1, tx) == 0
        tx.commit()
    assert bottom.get_resource(0) == glass and bottom.get_amount(0) == 1
    assert fixture.port().get_amount(0) == 1


def water_transition(fixture, start, end):
    fixture.place("minecraft:cauldron", aux=start)
    handler = fixture.port(fluid=True)
    assert handler.get_amount(0) == LEVELS[start]
    assert handler.get_capacity(0) == 1000.0
    for face in range(6):
        assert fixture.port(face=face, fluid=True).storage_ids == handler.storage_ids
    delta = abs(LEVELS[end] - LEVELS[start])
    with fixture.api.open_transaction() as tx:
        operation = handler.insert if end >= start else handler.extract
        assert operation(WATER, delta, tx) == delta
        assert handler.get_amount(0, tx) == LEVELS[end]
        assert fixture.states.GetBlockStates(FIRST, DIMENSION)["fill_level"] == start
        tx.commit()
    states = fixture.states.GetBlockStates(FIRST, DIMENSION)
    assert states["cauldron_liquid"] == "water" and states["fill_level"] == end, states
    assert handler.get_amount(0) == LEVELS[end]


def lava_transition(fixture):
    fixture.place("minecraft:cauldron")
    handler = fixture.port(fluid=True)
    with fixture.api.open_transaction() as tx:
        assert handler.insert(LAVA, 999, tx) == 0
        assert handler.insert(LAVA, 1001, tx) == 1000
        tx.commit()
    states = fixture.states.GetBlockStates(FIRST, DIMENSION)
    assert states["cauldron_liquid"] == "lava" and states["fill_level"] == 6
    with fixture.api.open_transaction() as tx:
        assert handler.extract(LAVA, 999, tx) == 0
        assert handler.insert(WATER, 1000, tx) == 0
        assert handler.extract(LAVA, 1000, tx) == 1000
        tx.commit()
    assert fixture.states.GetBlockStates(FIRST, DIMENSION)["fill_level"] == 0
    fixture.set_liquid(LAVA, 3)
    assert fixture.api.query(fixture.api.FLUID, DIMENSION, FIRST) is None


def metadata_resource(fixture, kind):
    if kind == "sword":
        return fixture.resource("minecraft:diamond_sword", 0, {
            "durability": 123, "enchantData": [(9, 2)],
            "extraId": "radium-native-validation", "customTips": "metadata roundtrip",
            "userData": {"display": {"Name": atom(8, "radium validation sword")}}})
    if kind == "filled_shulker":
        entry = fixture.codec.encode_entry(fixture.resource("minecraft:stone"), 7, 0,
                                            basic_info=fixture.engine.basic_info)
        return fixture.resource("minecraft:undyed_shulker_box", 0, {"userData": {"Items": [entry]}})
    # This checks arbitrary typed bundle metadata, not native filled-bundle content.
    return fixture.resource("minecraft:bundle", 0, {"userData": {
        "radium_validation_marker": atom(8, "bundle userdata preserved")}})


def metadata_roundtrip(fixture, kind, native_nbt):
    fixture.place("minecraft:barrel")
    fixture.place("minecraft:barrel", SECOND)
    resource = metadata_resource(fixture, kind)
    source, target = fixture.port(), fixture.port(SECOND)
    with fixture.api.open_transaction() as tx:
        assert source.insert(resource, 1, tx) == 1
        tx.commit()
    assert source.get_resource(0) == resource
    if native_nbt:
        fixture.place("minecraft:furnace", THIRD)
        furnace_top = fixture.port(THIRD, 1)
        with fixture.api.open_transaction() as tx:
            assert fixture.api.move_item(source, furnace_top, resource, 1, tx) == 1
            tx.commit()
        assert furnace_top.get_resource(0) == resource
        # Native processing is deliberately not simulated. Move the exact stored
        # item to output via test setup, then exercise the real bottom wrapper.
        fixture.seed_nbt(THIRD, ((2, resource, 1),))
        source, target = fixture.port(THIRD, 0), fixture.port(SECOND)
    with fixture.api.open_transaction() as tx:
        assert fixture.api.move_item(source, target, resource, 1, tx) == 1
        tx.commit()
    assert target.get_resource(0) == resource and target.get_amount(0) == 1
    decoded = fixture.codec.decode_stack(fixture.items.GetContainerItem(
        SECOND, 0, DIMENSION, True), fixture.engine.basic_info)
    assert decoded == (resource, 1), (kind, decoded, resource)


def metadata_unknown_fields(fixture):
    fixture.place("minecraft:barrel")
    fixture.place("minecraft:furnace", SECOND)
    resource = fixture.api.item_resource("minecraft:stone", 0,
                                         {"unsupported_native_metadata": "must not vanish"})
    for pos, face in ((FIRST, None), (SECOND, 1)):
        handler = fixture.port(pos, face)
        before = fixture.blocks.GetBlockEntityData(DIMENSION, pos)
        with fixture.api.open_transaction() as tx:
            try:
                handler.insert(resource, 1, tx)
            except ValueError:
                pass
            else:
                raise AssertionError("Unknown native item fields were accepted")
            tx.commit()
        assert fixture.blocks.GetBlockEntityData(DIMENSION, pos) == before


def cases(rules):
    ordinary_names = rules.CHESTS | rules.SHULKERS | frozenset((
        "minecraft:barrel", "minecraft:hopper", "minecraft:dispenser", "minecraft:dropper"))
    result = [("ordinary/" + name, ordinary, (name,)) for name in sorted(ordinary_names)]
    for name in sorted(rules.CHESTS):
        for facing in (2, 3, 4, 5):
            for reverse in (False, True):
                result.append(("double/%s/facing_%d/reverse_%d" % (name, facing, reverse),
                               double_chest, (name, facing, reverse)))
    result.extend(("furnace/" + name, furnace, (name,)) for name in sorted(rules.FURNACES))
    result.append(("brewing/faces_and_slots", brewing, ()))
    for start in range(7):
        for end in range(7):
            result.append(("cauldron/water/%d_to_%d" % (start, end), water_transition, (start, end)))
    result.append(("cauldron/lava_bucket", lava_transition, ()))
    for kind in ("sword", "filled_shulker", "bundle_marker"):
        for native_nbt in (False, True):
            result.append(("metadata/%s/%s" % (kind, "nbt" if native_nbt else "api"),
                           metadata_roundtrip, (kind, native_nbt)))
    result.append(("metadata/unknown_fields", metadata_unknown_fields, ()))
    return result


def run(subset=None):
    _assert_not_running()
    helper = types.ModuleType("_radium_native_validation_helper")
    with open(HELPER, "rb") as source_file:
        exec(compile(source_file.read(), HELPER, "exec"), helper.__dict__)
    passed, failed, details = [], {}, {}
    selected, cleaned = [], True
    try:
        service_module = helper.load(PREFIX)
        import mod.server.extraServerApi as serverApi
        factory, level_id = serverApi.GetEngineCompFactory(), serverApi.GetLevelId()
        blocks, chunks = factory.CreateBlockInfo(level_id), factory.CreateChunkSource(level_id)
        assert_empty(blocks, chunks)
        prefixes = (subset,) if isinstance(subset, basestring) else tuple(subset or ())
        selected = [case for case in cases(sys.modules[PREFIX + ".vanilla.rules"])
                    if not prefixes or any(case[0].startswith(prefix) for prefix in prefixes)]
        assert selected, ("No matching validation cases", subset)
        for name, callback, args in selected:
            fixture = Fixture(service_module, factory, level_id)
            try:
                result = callback(fixture, *args)
                if result is not None:
                    details[name] = result
                passed.append(name)
            except Exception:
                failed[name] = traceback.format_exc()
                if fixture.reports:
                    details[name] = {"reports": fixture.reports}
            finally:
                try:
                    fixture.cleanup()
                    assert_empty(blocks, chunks)
                except Exception:
                    failed[name + "/cleanup"] = traceback.format_exc()
                    cleaned = False
            if not cleaned:
                break
    except Exception:
        failed["setup"] = traceback.format_exc()
    finally:
        helper.cleanup(PREFIX)
    return {"ok": not failed, "passed": passed, "failed": failed, "details": details,
            "total": len(selected), "executed": len(passed) + len([name for name in failed
            if name != "setup" and not name.endswith("/cleanup")]), "cleaned": cleaned}


def _assert_not_running():
    module = sys.modules.get(PREFIX)
    if module is not None and getattr(module, "_native_validation_running", False):
        raise RuntimeError("A native validation run is already active")


def _report_path(path):
    cache = os.path.abspath("D:/addon/transferlib/.cache")
    target = os.path.abspath(path)
    if (os.path.normcase(os.path.dirname(target)) != os.path.normcase(cache) or
            os.path.splitext(target)[1].lower() != ".json"):
        raise ValueError("Validation reports must be JSON files directly inside " + cache)
    if not os.path.isdir(cache):
        os.makedirs(cache)
    return target


def run_async(subset, report_path):
    """Run one complete case per AddTimer(0) callback; poll the JSON report.

    Every case, including its cleanup, stays within a synchronous callback. Game
    ticks occur only while the fixed test area is empty between cases. The caller
    must wait for done=True before starting another validation run.
    """
    _assert_not_running()
    report_path = _report_path(report_path)
    helper = types.ModuleType("_radium_native_validation_helper")
    with open(HELPER, "rb") as source_file:
        exec(compile(source_file.read(), HELPER, "exec"), helper.__dict__)
    progress = {"done": False, "completed": 0, "total": 0, "passed": [],
                "failed": {}, "details": {}, "cleaned": True, "ok": False,
                "running": None, "report_path": report_path}

    def publish():
        with open(report_path, "wb") as report:
            report.write(json.dumps(progress, ensure_ascii=True, indent=2))

    def finish():
        progress["done"] = True
        progress["running"] = None
        progress["ok"] = (not progress["failed"] and progress["cleaned"] and
                          progress["completed"] == progress["total"])
        try:
            helper.cleanup(PREFIX)
        finally:
            publish()

    try:
        service_module = helper.load(PREFIX)
        sys.modules[PREFIX]._native_validation_running = True
        import mod.server.extraServerApi as serverApi
        factory, level_id = serverApi.GetEngineCompFactory(), serverApi.GetLevelId()
        blocks, chunks = factory.CreateBlockInfo(level_id), factory.CreateChunkSource(level_id)
        game = factory.CreateGame(level_id)
        assert_empty(blocks, chunks)
        prefixes = (subset,) if isinstance(subset, basestring) else tuple(subset or ())
        selected = [case for case in cases(sys.modules[PREFIX + ".vanilla.rules"])
                    if not prefixes or any(case[0].startswith(prefix) for prefix in prefixes)]
        assert selected, ("No matching validation cases", subset)
        progress["total"] = len(selected)

        def step():
            if progress["done"]:
                return
            fixture = None
            name = "between_cases"
            try:
                # Another actor may have occupied the area during the yielded frame.
                assert_empty(blocks, chunks)
                name, callback, args = selected[progress["completed"]]
                progress["running"] = name
                publish()
                fixture = Fixture(service_module, factory, level_id)
                try:
                    result = callback(fixture, *args)
                    if result is not None:
                        progress["details"][name] = result
                    progress["passed"].append(name)
                except Exception:
                    progress["failed"][name] = traceback.format_exc()
                    if fixture.reports:
                        progress["details"][name] = {"reports": fixture.reports}
                finally:
                    try:
                        fixture.cleanup()
                        assert_empty(blocks, chunks)
                    except Exception:
                        progress["failed"][name + "/cleanup"] = traceback.format_exc()
                        progress["cleaned"] = False
                progress["completed"] += 1
                progress["running"] = None
                if not progress["cleaned"] or progress["completed"] == progress["total"]:
                    finish()
                    return
                publish()
                game.AddTimer(0, step)
            except Exception:
                progress["failed"][name + "/runner"] = traceback.format_exc()
                # All mutation is inside the inner case's try/finally. Failures
                # before Fixture creation have nothing belonging to us to remove.
                finish()

        publish()
        game.AddTimer(0, step)
    except Exception:
        progress["failed"]["setup"] = traceback.format_exc()
        finish()
    return dict(progress)
