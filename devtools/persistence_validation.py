# coding=utf-8
"""Two-phase native persistence acceptance fixture; GAME Python 2.7.13 only.

1. Call seed() in the reviewed, empty native_validation test area.
2. Save and fully reload the world using the game's normal lifecycle.
3. Load this script again and call verify_and_cleanup().

This script does not save or reload the world itself. Successful seed intentionally
leaves its blocks in place. The JSON manifest survives Python/module reloads.
Unknown filled-bundle NBT is never synthesized: optionally provide a real native
GetContainerItem(..., True) bundle stack captured from a player-filled bundle.
"""
import json
import os
import sys
import time
import traceback
import types


BASE = "D:/addon/transferlib"
NATIVE_SCRIPT = BASE + "/devtools/native_validation.py"
REPORT = BASE + "/.cache/persistence_fixture.json"
PREFIX = "_radium_persistence_validation"
DIMENSION = 0
CHEST = (-23, 100, 11)
COPPER_LEFT = (-23, 100, 14)
COPPER_RIGHT = (-22, 100, 14)
WATER_POS = (-20, 100, 14)
LAVA_POS = (-18, 100, 14)
COPPER_NAME = "minecraft:waxed_copper_chest"
CONTAINERS = ((CHEST, "minecraft:chest"), (COPPER_LEFT, COPPER_NAME),
              (COPPER_RIGHT, COPPER_NAME), (WATER_POS, "minecraft:cauldron"),
              (LAVA_POS, "minecraft:cauldron"))
ROOFS = ((WATER_POS[0], 102, WATER_POS[2]), (LAVA_POS[0], 102, LAVA_POS[2]))


def _write(data):
    directory = os.path.dirname(REPORT)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    with open(REPORT, "wb") as output:
        output.write(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True))


def _read():
    with open(REPORT, "rb") as source:
        return json.load(source)


def _load():
    native = types.ModuleType("_radium_persistence_native_helper")
    with open(NATIVE_SCRIPT, "rb") as source:
        exec(compile(source.read(), NATIVE_SCRIPT, "exec"), native.__dict__)
    # Refuse to replace modules used by an active asynchronous acceptance run.
    native._assert_not_running()
    native.PREFIX = PREFIX
    native._assert_not_running()
    helper = types.ModuleType("_radium_persistence_loader")
    with open(native.HELPER, "rb") as source:
        exec(compile(source.read(), native.HELPER, "exec"), helper.__dict__)
    try:
        service = helper.load(PREFIX)
        import mod.server.extraServerApi as serverApi
        factory, level_id = serverApi.GetEngineCompFactory(), serverApi.GetLevelId()
        fixture = native.Fixture(service, factory, level_id)
    except Exception:
        helper.cleanup(PREFIX)
        raise
    return native, helper, fixture


def _planned_blocks():
    result = []
    for pos, name in CONTAINERS:
        result.append(((pos[0], pos[1] - 1, pos[2]), "minecraft:stone"))
        result.append((pos, name))
    result.extend((pos, "minecraft:stone") for pos in ROOFS)
    return result


def _serialized_placed(placed):
    return [{"pos": list(pos), "name": name} for pos, name in placed]


def _validate_manifest(data):
    assert isinstance(data, dict) and data.get("schema") == 1
    assert data.get("dimension") == DIMENSION
    allowed = dict(_planned_blocks())
    seen = set()
    for block in data.get("placed", []):
        pos = tuple(block["pos"])
        assert pos not in seen and allowed.get(pos) == block["name"], block
        seen.add(pos)
    assert seen, "Manifest contains no fixture blocks"
    for record in data.get("records", []):
        pos = tuple(record["pos"])
        assert pos in seen and record["block"]["name"] == allowed[pos], record


def _nbt(fixture, pos):
    data = fixture.blocks.GetBlockEntityData(DIMENSION, pos)
    if data is None:
        return None
    data = fixture.codec._copy_nbt(data)
    # Native slot writes materialize this transient flag. The actual pairing is
    # separately recorded and verified, matching ItemBackend.capture's treatment.
    data.pop("forceunpair", None)
    return data


def _capture(fixture, pos, name):
    record = {"pos": list(pos), "block": fixture.blocks.GetBlockNew(pos, DIMENSION),
              "states": fixture.states.GetBlockStates(pos, DIMENSION),
              "nbt": _nbt(fixture, pos)}
    if name in fixture.rules.ITEM_BLOCKS:
        handler = fixture.port(pos)
        record["kind"] = "item"
        record["snapshot"] = fixture.api.save_item(handler)
        record["capacity"] = fixture.items.GetContainerSize(pos, DIMENSION)
        paired = fixture.blocks.GetChestPairedPosition(pos, DIMENSION)
        record["paired"] = list(paired) if paired else None
    elif name in fixture.rules.CAULDRONS:
        handler = fixture.port(pos, fluid=True)
        record["kind"] = "fluid"
        record["snapshot"] = fixture.api.save_fluid(handler)
        record["capacity"] = handler.get_capacity(0)
    else:
        record["kind"] = "support"
    return record


def _full_shulker(fixture):
    stone = fixture.resource("minecraft:stone")
    entries = [fixture.codec.encode_entry(stone, 64, slot,
               basic_info=fixture.engine.basic_info) for slot in range(27)]
    return fixture.resource("minecraft:undyed_shulker_box", 0,
                            {"userData": {"Items": entries}})


def _real_bundle(fixture, native_stack):
    resource, count = fixture.codec.decode_stack(native_stack, fixture.engine.basic_info)
    assert resource is not None and count == 1 and resource.item_id == "minecraft:bundle"
    tag = resource.properties.get("userData", {})
    contents = tag.get("storage_item_component_content")
    weight = tag.get("bundle_weight", {})
    assert isinstance(contents, list) and len(contents) == 64, "Real bundle content sample required"
    assert (weight.get("__type__") == 3 and weight.get("__value__", 0) > 0), (
        "A genuinely filled native bundle sample is required")
    return resource


def seed(bundle_stack=None):
    """Leave a durable fixture and manifest; optional bundle_stack is a real sample."""
    if os.path.isfile(REPORT):
        previous = _read()
        if previous.get("placed") and not previous.get("cleaned", False):
            raise RuntimeError("A persistence fixture still exists; verify_and_cleanup first")
    native, helper, fixture = _load()
    manifest = {"schema": 1, "dimension": DIMENSION, "status": "preparing",
                "created_at_unix": time.time(), "report_path": REPORT,
                "placed": [], "records": [], "failed": {}, "cleaned": False,
                "ignored_nbt_keys": ["forceunpair"],
                "filled_bundle": "not tested: no verified native filled-bundle sample supplied"}
    success = False
    try:
        native.assert_empty(fixture.blocks, fixture.chunks)
        _write(manifest)
        copper_aux = fixture.states.GetBlockAuxValueFromStates(
            COPPER_NAME, {"minecraft:cardinal_direction": "north"})
        assert copper_aux >= 0
        for pos, name in CONTAINERS:
            fixture.place(name, pos, copper_aux if name == COPPER_NAME else 0,
                          name == COPPER_NAME)
            manifest["placed"] = _serialized_placed(fixture.placed)
            _write(manifest)
        for pos in ROOFS:
            fixture._place(pos, "minecraft:stone")
        manifest["placed"] = _serialized_placed(fixture.placed)
        _write(manifest)
        assert tuple(fixture.blocks.GetChestPairedPosition(COPPER_LEFT, DIMENSION)) == COPPER_RIGHT
        chest, copper = fixture.port(CHEST), fixture.port(COPPER_LEFT)
        assert len(chest.get_slots()) == 27 and len(copper.get_slots()) == 54
        sword = native.metadata_resource(fixture, "sword")
        shulker = _full_shulker(fixture)
        stone = fixture.resource("minecraft:stone")
        bundle = _real_bundle(fixture, bundle_stack) if bundle_stack is not None else None
        with fixture.api.open_transaction() as tx:
            assert chest.insert(sword, 1, tx, 0) == 1
            assert chest.insert(shulker, 1, tx, 1) == 1
            if bundle is not None:
                assert chest.insert(bundle, 1, tx, 2) == 1
                manifest["filled_bundle"] = "included: caller-supplied verified native sample"
            for slot in range(54):
                assert copper.insert(stone, slot + 1, tx, slot) == slot + 1
            tx.commit()
        assert chest.get_resource(0) == sword and chest.get_resource(1) == shulker
        if bundle is not None:
            assert chest.get_resource(2) == bundle
        assert copper.storage_ids == fixture.port(COPPER_RIGHT).storage_ids
        water, lava = fixture.port(WATER_POS, fluid=True), fixture.port(LAVA_POS, fluid=True)
        with fixture.api.open_transaction() as tx:
            assert water.insert(native.WATER, 667, tx) == 667
            assert lava.insert(native.LAVA, 1000, tx) == 1000
            tx.commit()
        manifest["records"] = [_capture(fixture, pos, name) for pos, name in fixture.placed]
        manifest["status"] = "seeded"
        manifest["ok"] = True
        manifest["next_action"] = "Save and fully reload the world, then call verify_and_cleanup()"
        _write(manifest)
        success = True
    except Exception:
        manifest["status"] = "seed_failed"
        manifest["ok"] = False
        manifest["failed"]["seed"] = traceback.format_exc()
    finally:
        try:
            if not success:
                manifest["placed"] = _serialized_placed(fixture.placed)
                try:
                    fixture.cleanup()
                    native.assert_empty(fixture.blocks, fixture.chunks)
                    manifest["cleaned"] = True
                except Exception:
                    manifest["failed"]["cleanup"] = traceback.format_exc()
                _write(manifest)
        finally:
            helper.cleanup(PREFIX)
    result = {key: manifest[key] for key in (
        "status", "ok", "failed", "cleaned", "filled_bundle", "report_path")}
    result["next_action"] = manifest.get("next_action")
    result["placed_count"] = len(manifest["placed"])
    return result


def verify_and_cleanup():
    """After the caller reloads the world, compare all snapshots and restore air."""
    manifest = _read()
    _validate_manifest(manifest)
    if manifest.get("cleaned"):
        return {"ok": False, "cleaned": True, "failed": {"setup": "Fixture already cleaned"}}
    native, helper, fixture = _load()
    fixture.placed = [(tuple(block["pos"]), block["name"]) for block in manifest["placed"]]
    result = {"ok": False, "passed": [], "failed": {}, "cleaned": False,
              "filled_bundle": manifest.get("filled_bundle"),
              "reload": "Caller must have performed a full world reload before verification"}
    try:
        # Check only known fixture blocks. Never remove unrelated blocks that may
        # have appeared elsewhere in the test area during the reload.
        for expected in manifest.get("records", []):
            pos = tuple(expected["pos"])
            label = "%s@%s" % (expected["block"]["name"], pos)
            try:
                assert fixture.chunks.CheckChunkState(DIMENSION, pos), "Fixture chunk is unloaded"
                actual = _capture(fixture, pos, expected["block"]["name"])
                for field in expected:
                    assert actual.get(field) == expected[field], (
                        field, "expected", expected[field], "actual", actual.get(field))
                result["passed"].append(label)
            except Exception:
                result["failed"][label] = traceback.format_exc()
        if not manifest.get("records"):
            result["failed"]["snapshot"] = "No successful seed snapshot exists"
    finally:
        try:
            fixture.cleanup()
            native.assert_empty(fixture.blocks, fixture.chunks)
            result["cleaned"] = True
        except Exception:
            result["failed"]["cleanup"] = traceback.format_exc()
        helper.cleanup(PREFIX)
        result["ok"] = not result["failed"] and result["cleaned"]
        manifest["status"] = "verified" if result["ok"] else "verification_failed"
        manifest["ok"] = result["ok"]
        manifest["cleaned"] = result["cleaned"]
        manifest["verification"] = result
        _write(manifest)
    return result
