# coding=utf-8
"""Pure rule regressions, executed only by the game's Python interpreter."""
import traceback
from radium_scripts.radium.core.item_resource import item_resource
from radium_scripts.radium.vanilla import rules


def item(name, aux=0):
    return item_resource(name if ":" in name else "minecraft:" + name, aux)


def test_supported_profiles_and_non_container_exclusion():
    assert len(rules.CHESTS) == 10 and len(rules.SHULKERS) == 18
    assert len(rules.FURNACES) == 6 and len(rules.CAULDRONS) == 2
    for name in rules.CHESTS:
        assert rules.profile(name) == ("chest", 27)
    for name in rules.SHULKERS:
        assert rules.profile(name) == ("shulker", 27)
    for name in rules.FURNACES:
        assert rules.profile(name) == ("furnace", 3)
    for name in ("minecraft:ender_chest", "example:chest", "minecraft:stone"):
        assert rules.profile(name) is None and name not in rules.ITEM_BLOCKS
    assert not rules.CAULDRONS.intersection(rules.ITEM_BLOCKS)


def test_common_container_faces_have_complete_inventory():
    for kind, size in (("chest", 27), ("barrel", 27),
                       ("shulker", 27), ("hopper", 5), ("dispenser", 9), ("dropper", 9)):
        for face in (None, 0, 1, 2, 3, 4, 5):
            assert rules.ports(kind, face) == (tuple(range(size)), tuple(range(size)))
        assert rules.accepts(kind, size - 1, item("stone"))
        assert rules.allows_extract(kind, size - 1, item("stone"))
        assert not rules.accepts(kind, 54 if kind == "chest" else size, item("stone"))
        assert not rules.allows_extract(kind, -1, item("stone"))
    assert rules.accepts("chest", 53, item("stone"))
    assert rules.allows_extract("chest", 53, item("stone"))


def test_shulker_nesting_rejects_every_vanilla_encoding():
    for name in rules.SHULKERS:
        for aux in (0, 3, 15):
            resource = item(name, aux)
            assert not rules.accepts("shulker", 0, resource)
            assert rules.accepts("chest", 0, resource)
            assert rules.accepts("barrel", 26, resource)
    assert rules.accepts("shulker", 0, item("example:shulker_shell_material"))


def test_furnace_face_matrix_and_empty_bucket_exception():
    assert rules.ports("furnace", 1) == ((0,), ())
    assert rules.ports("furnace", 0) == ((), (2, 1))
    for face in (2, 3, 4, 5):
        assert rules.ports("furnace", face) == ((1,), ())
    assert rules.accepts("furnace", 0, item("diamond"))
    assert not rules.accepts("furnace", 2, item("iron_ingot"))
    assert not rules.accepts("furnace", 1, item("bucket"))
    assert rules.allows_extract("furnace", 1, item("bucket"))
    for resource in (item("bucket", 10), item("lava_bucket"), item("coal")):
        assert not rules.allows_extract("furnace", 1, resource)
    assert not rules.allows_extract("furnace", 0, item("iron_ore"))
    assert rules.allows_extract("furnace", 2, item("iron_ingot"))


def test_fuel_native_duration_and_explicit_block_fallback():
    assert rules.accepts("furnace", 1, item("example:pellet"), {"fuelDuration": 12.5})
    assert rules.accepts("furnace", 1, item("lava_bucket"), {"fuelDuration": 1000})
    for name in ("coal_block", "dried_kelp_block", "oak_planks", "spruce_log",
                 "stripped_cherry_wood", "mangrove_roots", "pale_oak_slab",
                 "bamboo_mosaic", "scaffolding", "bookshelf", "white_wool",
                 "red_carpet", "azalea", "barrel"):
        assert rules.accepts("furnace", 1, item(name), {"fuelDuration": 0}), name
    for name in ("example:oak_planks", "example:coal_block", "crimson_planks",
                 "warped_log", "stripped_crimson_stem", "nether_brick", "stone",
                 "copper_chest", "white_bed", "moss_carpet"):
        assert not rules.accepts("furnace", 1, item(name), {"fuelDuration": 0}), name


def test_legacy_fuels_use_aux_and_invalid_metadata_is_not_a_fuel():
    for name, aux in (("log", 15), ("log2", 1), ("planks", 5), ("wood", 13),
                       ("wooden_slab", 3), ("wool", 15), ("carpet", 1)):
        assert rules.accepts("furnace", 1, item(name, aux)), (name, aux)
    for name, aux in (("log2", 2), ("planks", 6), ("wood", 7), ("wool", 16)):
        assert not rules.accepts("furnace", 1, item(name, aux)), (name, aux)
    for invalid in (None, True, "10", float("inf"), float("nan"), -1):
        assert not rules.accepts("furnace", 1, item("example:fuel"), {"fuelDuration": invalid})


def test_brewing_face_matrix_keeps_reagent_bottles_out_of_bottom_output():
    assert rules.ports("brewing", 1) == ((0,), ())
    assert rules.ports("brewing", 0) == ((), (1, 2, 3))
    assert rules.ports("brewing", None) == ((0, 1, 2, 3, 4), (1, 2, 3))
    for face in (2, 3, 4, 5):
        assert rules.ports("brewing", face) == ((1, 2, 3, 4), ())
    for name in rules.BREWING_INGREDIENTS:
        assert rules.accepts("brewing", 0, item(name))
    for name in ("glass_bottle", "coal", "diamond", "example:ingredient"):
        assert not rules.accepts("brewing", 0, item(name))
    for slot in (1, 2, 3):
        for name in ("potion", "splash_potion", "lingering_potion", "glass_bottle"):
            assert rules.accepts("brewing", slot, item(name))
        assert not rules.accepts("brewing", slot, item("blaze_powder"))
    assert rules.accepts("brewing", 4, item("blaze_powder"))
    assert not rules.accepts("brewing", 4, item("coal"))
    assert not rules.allows_extract("brewing", 0, item("glass_bottle"))
    assert not rules.allows_extract("brewing", 0, item("nether_wart"))
    assert not rules.allows_extract("brewing", 4, item("blaze_powder"))


def test_unknown_kind_empty_resources_and_invalid_slots_are_denied():
    for kind in ("chest", "furnace", "brewing", "shulker", "unknown"):
        assert not rules.accepts(kind, 0, None)
        assert not rules.allows_extract(kind, 0, None)
        for slot in (True, -1, 100, 1.5):
            assert not rules.accepts(kind, slot, item("stone"))
            assert not rules.allows_extract(kind, slot, item("stone"))


def run():
    cases = sorted((name, value) for name, value in globals().items()
                   if name.startswith("test_") and callable(value))
    passed, failed = [], {}
    for name, case in cases:
        try:
            case()
            passed.append(name)
        except Exception:
            failed[name] = traceback.format_exc()
    return {"passed": passed, "failed": failed, "total": len(cases), "ok": not failed}
