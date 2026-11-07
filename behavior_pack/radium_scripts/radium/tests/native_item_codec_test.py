# coding=utf-8
"""Native item boundary regressions; run only in the game's Python 2.7.13."""
import traceback
from ..core.item_resource import item_resource
from ..vanilla.item_codec import (canonical, decode_stack, decode_entry,
                                  encode_entry, api_stack)


def atom(kind, value):
    return {"__type__": kind, "__value__": value}


def basic(item_id, aux):
    return {"maxDurability": 1561 if item_id == "minecraft:diamond_sword" else 0}


def expect(error, callback):
    try:
        callback()
    except error:
        return
    raise AssertionError("Expected %r" % (error,))


def sword_entry():
    return {"Count": atom(1, 1), "Slot": atom(1, 0),
            "Name": atom(8, "minecraft:diamond_sword"), "Damage": atom(2, 0),
            "WasPickedUp": atom(1, 0),
            "tag": {"ItemExtraID": atom(8, "radium-probe"),
                    "ench": [{"lvl": atom(2, 2), "id": atom(2, 9),
                              "modEnchant": atom(8, "")}],
                    "ItemCustomTips": atom(8, "probe"),
                    "Damage": atom(3, 1438),
                    "display": {"Name": atom(8, "probe name")}},
            "CanDestroy": [atom(8, "minecraft:stone")]}


def test_plain_native_defaults_do_not_create_distinct_resource():
    stack = {"newItemName": "minecraft:stone", "newAuxValue": 0, "count": 7,
             "itemName": "minecraft:stone", "auxValue": 0,
             "itemId": 1, "isDiggerItem": False, "modId": 0, "modItemId": 0,
             "showInHand": True, "enchantData": [], "modEnchantData": [],
             "durability": 0, "extraId": "", "customTips": "", "userData": {},
             "canDestroy": [], "canPlaceOn": []}
    resource, count = decode_stack(stack, basic)
    assert resource == item_resource("minecraft:stone") and count == 7
    assert api_stack(resource, 7) == {
        "newItemName": "minecraft:stone", "newAuxValue": 0, "count": 7}
    assert decode_entry(encode_entry(resource, 7, 26)) == (resource, 7, 26)


def test_current_api_aliases_win_over_legacy_flattening_names():
    resource, count = decode_stack({
        "newItemName": "minecraft:white_wool", "newAuxValue": 0,
        "itemName": "minecraft:wool", "auxValue": 0, "count": 1})
    assert resource == item_resource("minecraft:white_wool") and count == 1


def test_real_sword_sample_roundtrips_nbt_and_convenience_fields():
    entry = sword_entry()
    saved, count, slot = decode_entry(entry)
    properties = {"userData": {"display": {"Name": atom(8, "probe name")}},
                  "extraId": "radium-probe", "customTips": "probe",
                  "enchantData": [(9, 2)], "durability": 123,
                  "canDestroy": ["minecraft:stone"]}
    original = item_resource("minecraft:diamond_sword", 0, properties)
    assert canonical(original, basic) == saved
    assert original.properties == properties  # Core identity remains untouched.
    assert encode_entry(saved, count, slot) == entry
    raw = api_stack(saved, 1)
    raw.update({"durability": 123, "enchantData": [(9, 2)],
                "modEnchantData": [], "extraId": "radium-probe",
                "customTips": "probe", "isDiggerItem": True})
    assert decode_stack(raw, basic) == (saved, 1)


def test_detached_snapshots_do_not_share_nested_tag_or_restrictions():
    entry = sword_entry()
    resource, count, slot = decode_entry(entry)
    entry["tag"]["display"]["Name"]["__value__"] = "changed"
    output = encode_entry(resource, 1, 0)
    assert output["tag"]["display"]["Name"]["__value__"] == "probe name"
    output["tag"]["ench"][0]["lvl"]["__value__"] = 9
    stack = api_stack(resource, 1)
    stack["canDestroy"].append("minecraft:dirt")
    assert encode_entry(resource, 1, 0) == sword_entry()


def test_template_preserves_original_native_fields_for_count_only_edit():
    original = encode_entry(item_resource("minecraft:stone"), 4, 3)
    original["WasPickedUp"] = atom(1, 1)
    original["tag"] = {"Damage": atom(3, 0)}
    original["CanDestroy"] = []
    resource, count, slot = decode_entry(original)
    assert resource == item_resource("minecraft:stone")
    result = encode_entry(resource, 3, 3, template=original)
    assert result["tag"] == original["tag"]
    assert result["CanDestroy"] == [] and result["WasPickedUp"] == atom(1, 1)
    assert result["Count"] == atom(1, 3) and original["Count"] == atom(1, 4)
    other = encode_entry(item_resource("minecraft:dirt"), 1, 3, template=original)
    assert "tag" not in other and other["WasPickedUp"] == atom(1, 0)


def test_known_tag_types_and_unrelated_custom_metadata_are_preserved():
    tag = {"byte": atom(1, -1), "short": atom(2, 12), "int": atom(3, 34),
           "long": atom(4, 100), "float": atom(5, 1.25), "double": atom(6, 2.5),
           "bytes": atom(7, [-1, 0, 127]), "text": atom(8, "value"),
           "list": atom(9, [atom(2, 1), atom(2, 2)]),
           "compound": atom(10, {"value": atom(8, "nested")}),
           "ints": atom(11, [-2147483648, 2147483647]),
           "Items": [{"Count": atom(1, 3), "Name": atom(8, "minecraft:stone")}]}
    resource = item_resource("minecraft:shulker_box", 0, {"userData": tag})
    assert canonical(resource) == resource
    assert decode_entry(encode_entry(resource, 1, 0))[0] == resource


def test_restrictions_stay_outside_tag_and_readback_expansion_is_detectable():
    resource = item_resource("minecraft:stone", 0, {
        "canDestroy": ["minecraft:stone"], "canPlaceOn": ["minecraft:dirt"]})
    entry = encode_entry(resource, 2, 0)
    assert "tag" not in entry
    assert entry["CanDestroy"] == [atom(8, "minecraft:stone")]
    assert entry["CanPlaceOn"] == [atom(8, "minecraft:dirt")]
    assert decode_entry(entry)[0] == resource
    expanded = api_stack(resource, 2)
    expanded["canDestroy"].append("minecraft:granite")
    assert decode_stack(expanded)[0] != resource


def test_conflicting_convenience_fields_cannot_overwrite_native_tag():
    for field, native, value in (("extraId", "ItemExtraID", "other"),
                                 ("customTips", "ItemCustomTips", "other")):
        resource = item_resource("minecraft:stone", 0, {
            "userData": {native: atom(8, "original")}, field: value})
        expect(ValueError, lambda: canonical(resource, basic))
    resource = item_resource("minecraft:diamond_sword", 0, {
        "userData": {"Damage": atom(3, 100)}, "durability": 123})
    expect(ValueError, lambda: canonical(resource, basic))
    resource = item_resource("minecraft:diamond_sword", 0, {
        "userData": sword_entry()["tag"], "enchantData": [(9, 3)]})
    expect(ValueError, lambda: canonical(resource, basic))


def test_custom_enchantments_preserve_verified_tag_but_do_not_guess_encoding():
    tag = {"ench": [{"lvl": atom(2, 2), "modEnchant": atom(8, "example:ench")}]}
    resource = item_resource("minecraft:diamond_sword", 0, {
        "userData": tag, "modEnchantData": [("example:ench", 2)]})
    saved = canonical(resource)
    assert saved.properties == {"userData": tag}
    assert decode_entry(encode_entry(saved, 1, 0))[0] == saved
    unknown = item_resource("minecraft:diamond_sword", 0, {
        "modEnchantData": [("example:ench", 2)]})
    expect(ValueError, lambda: canonical(unknown))


def test_remaining_durability_conversion_and_default_zero_damage():
    full = item_resource("minecraft:diamond_sword", 0, {"durability": 1561})
    assert canonical(full, basic) == item_resource("minecraft:diamond_sword")
    broken = canonical(item_resource("minecraft:diamond_sword", 0,
                                    {"durability": 0}), basic)
    assert broken.properties["userData"]["Damage"] == atom(3, 1561)
    expect(ValueError, lambda: canonical(full))
    expect(ValueError, lambda: canonical(item_resource(
        "minecraft:diamond_sword", 0, {"durability": 1562}), basic))


def test_native_block_palette_requires_reconstructible_states_and_keeps_template():
    entry = encode_entry(item_resource("minecraft:stone"), 4, 0)
    entry["Block"] = {"name": atom(8, "minecraft:stone"), "val": atom(2, 0),
                      "version": atom(3, 18168865), "states": {}}
    verified = lambda name, aux: {"maxDurability": 0, "_radium_block_states": {}}
    resource, count, slot = decode_entry(entry, verified)
    assert resource == item_resource("minecraft:stone")
    expect(ValueError, lambda: decode_entry(entry))
    expect(ValueError, lambda: decode_entry(entry, basic))
    saved = encode_entry(resource, 3, 0, template=entry, basic_info=verified)
    assert saved["Block"] == entry["Block"] and saved["Count"] == atom(1, 3)
    saved["Block"]["version"]["__value__"] = 1
    assert entry["Block"]["version"]["__value__"] == 18168865
    for key, value in (("name", atom(8, "minecraft:dirt")), ("val", atom(2, 2)),
                       ("unknown", atom(3, 1))):
        broken = dict(entry, Block=dict(entry["Block"], **{key: value}))
        expect(ValueError, lambda: decode_entry(broken, verified))


def test_native_block_nonempty_states_must_match_native_aux_lookup_exactly():
    entry = encode_entry(item_resource("minecraft:oak_stairs", 3), 1, 0)
    entry["Block"] = {"name": atom(8, "minecraft:oak_stairs"), "val": atom(2, 3),
                      "version": atom(3, 18168865),
                      "states": {"weirdo_direction": atom(3, 3),
                                 "upside_down_bit": atom(1, 0)}}
    expected = {"weirdo_direction": 3, "upside_down_bit": False}
    verified = lambda name, aux: {"maxDurability": 0, "_radium_block_states": expected}
    assert decode_entry(entry, verified)[0] == item_resource("minecraft:oak_stairs", 3)
    expected["weirdo_direction"] = 2
    expect(ValueError, lambda: decode_entry(entry, verified))
    expected["weirdo_direction"] = 3
    expected["additional_state"] = 0
    expect(ValueError, lambda: decode_entry(entry, verified))


def test_unknown_fields_and_malformed_or_unsafe_nbt_are_rejected():
    expect(ValueError, lambda: canonical(item_resource("minecraft:stone", 0,
                                                        {"unknown": "lost"})))
    entry = encode_entry(item_resource("minecraft:stone"), 1, 0)
    entry["UnrecognizedData"] = atom(8, "must not disappear")
    expect(ValueError, lambda: decode_entry(entry))
    bad_tags = ({"raw": 3}, {"wrong": {"__type__": 3}},
                {"mixed": [atom(2, 1), atom(3, 2)]},
                {"overflow": atom(3, 2147483648)},
                {"overflow": atom(4, 2147483648)},
                {"overflow": atom(5, 1e100)},
                {"bad": atom(6, float("inf"))},
                {"bad": atom(1, True)}, {"bad": atom(12, [])})
    for tag in bad_tags:
        expect((TypeError, ValueError), lambda: canonical(item_resource(
            "minecraft:stone", 0, {"userData": tag})))
    expect(ValueError, lambda: decode_stack({"newItemName": "minecraft:stone",
        "newAuxValue": 0, "count": 1, "unknown": "data"}))


def test_empty_and_numeric_boundaries_are_explicit():
    assert decode_stack(None) == (None, 0)
    assert decode_stack({}) == (None, 0)
    assert decode_stack({"count": 0}) == (None, 0)
    assert encode_entry(None, 0, 0) is None and api_stack(None, 0) == {}
    for count in (True, -1, 128, 1.0):
        expect((TypeError, ValueError), lambda: api_stack("minecraft:stone", count))
    for slot in (True, -1, 128, 1.0):
        expect((TypeError, ValueError), lambda: encode_entry("minecraft:stone", 1, slot))


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
