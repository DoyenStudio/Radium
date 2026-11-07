# coding=utf-8
"""Lossless, detached item conversion at the native-container boundary only."""
import math
from ..core.item_resource import item_resource, normalize_item
from ..core.resource import _text
from ..core.values import integer_types, string_types


_TYPE = "__type__"
_VALUE = "__value__"
_DERIVED = frozenset(("itemId", "isDiggerItem", "modId", "modItemId",
                      "showInHand"))
_PROPERTIES = frozenset(("userData", "canDestroy", "canPlaceOn", "extraId",
                         "customTips", "enchantData", "modEnchantData",
                         "durability"))
_ENTRY_KEYS = frozenset(("Name", "Damage", "Count", "Slot", "WasPickedUp",
                         "tag", "CanDestroy", "CanPlaceOn", "Block"))
_STACK_KEYS = frozenset(("itemName", "newItemName", "auxValue", "newAuxValue",
                         "count"))


def _integer(value, minimum=0, maximum=2147483647):
    if isinstance(value, bool) or not isinstance(value, integer_types):
        raise TypeError("Native item integer expected")
    if value < minimum or value > maximum:
        raise ValueError("Native item integer is outside its supported range")
    return int(value)


def _atom(kind, value):
    return {_TYPE: kind, _VALUE: value}


def _kind(value):
    if isinstance(value, dict):
        return value.get(_TYPE, 10)
    if isinstance(value, list):
        return 9
    raise TypeError("Expected a typed NBT value")


def _copy_list(values):
    if not isinstance(values, list):
        raise TypeError("NBT list expected")
    if values and any(_kind(value) != _kind(values[0]) for value in values):
        raise ValueError("NBT lists must be homogeneous")
    return [_copy_nbt(value) for value in values]


def _copy_nbt(value):
    """Preserve NBT widths, reject unsupported shapes and unsafe Python values."""
    if isinstance(value, list):
        return _copy_list(value)
    if not isinstance(value, dict):
        raise TypeError("Untyped NBT scalar is not supported")
    if _TYPE not in value:
        result = {}
        for key, child in value.items():
            if not isinstance(key, string_types):
                raise TypeError("NBT compound keys must be strings")
            key = _text(key)
            if key in result:
                raise ValueError("Duplicate NBT compound key")
            result[key] = _copy_nbt(child)
        return result
    if set(value) != set((_TYPE, _VALUE)):
        raise ValueError("Malformed typed NBT value")
    kind = _integer(value[_TYPE], 1, 11)
    raw = value[_VALUE]
    if kind in (1, 2, 3, 4):
        bounds = {1: (-128, 127), 2: (-32768, 32767),
                  3: (-2147483648, 2147483647),
                  4: (-2147483648, 2147483647)}
        raw = _integer(raw, *bounds[kind])
    elif kind in (5, 6):
        if isinstance(raw, bool) or not isinstance(raw, (float,) + integer_types):
            raise TypeError("NBT floating-point value expected")
        raw = float(raw)
        if math.isnan(raw) or math.isinf(raw):
            raise ValueError("Non-finite NBT value")
        if kind == 5 and abs(raw) > 3.4028234663852886e38:
            raise ValueError("NBT float would overflow its native width")
    elif kind == 8:
        if not isinstance(raw, string_types):
            raise TypeError("NBT string expected")
        raw = _text(raw)
    elif kind == 9:
        raw = _copy_list(raw)
    elif kind == 10:
        if not isinstance(raw, dict) or _TYPE in raw:
            raise TypeError("NBT compound expected")
        raw = _copy_nbt(raw)
    else:
        if not isinstance(raw, list):
            raise TypeError("NBT array expected")
        bounds = (-128, 127) if kind == 7 else (-2147483648, 2147483647)
        raw = [_integer(entry, *bounds) for entry in raw]
    return _atom(kind, raw)


def _read_atom(value, kind):
    copied = _copy_nbt(value)
    if not isinstance(copied, dict) or copied.get(_TYPE) != kind:
        raise ValueError("Unexpected NBT value type")
    return copied[_VALUE]


def _strings(values):
    if not isinstance(values, (list, tuple)):
        raise TypeError("Item block restrictions must be a sequence")
    if any(not isinstance(value, string_types) for value in values):
        raise TypeError("Item block restrictions must contain strings")
    return [_text(value) for value in values]


def _merge(tag, name, value):
    if name in tag and tag[name] != value:
        raise ValueError("Conflicting item property and userData: " + name)
    tag[name] = value


def _enchantments(values, custom):
    if not isinstance(values, (list, tuple)):
        raise TypeError("Enchantments must be a sequence")
    result = []
    for pair in values:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("Invalid enchantment pair")
        key, level = pair
        if custom:
            if not isinstance(key, string_types) or not key:
                raise ValueError("Custom enchantment identifier expected")
            key = _text(key)
        else:
            key = _integer(key, 0, 32767)
        result.append((key, _integer(level, 0, 32767)))
    if len(set(key for key, level in result)) != len(result):
        raise ValueError("Duplicate enchantment identifier")
    return result


def _existing_enchantments(tag):
    normal, custom = [], []
    entries = tag.get("ench", [])
    if not isinstance(entries, list):
        raise ValueError("Unsupported enchantment NBT shape")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Unsupported enchantment entry")
        level = _read_atom(entry.get("lvl"), 2)
        name = _read_atom(entry["modEnchant"], 8) if "modEnchant" in entry else ""
        if name:
            custom.append((name, level))
        else:
            normal.append((_read_atom(entry.get("id"), 2), level))
    return normal, custom


def _merge_enchantments(tag, properties):
    normal = properties.get("enchantData")
    custom = properties.get("modEnchantData")
    normal = _enchantments([] if normal is None else normal, False)
    custom = _enchantments([] if custom is None else custom, True)
    if not normal and not custom:
        return
    if "ench" in tag:
        saved_normal, saved_custom = _existing_enchantments(tag)
        if normal and sorted(normal) != sorted(saved_normal):
            raise ValueError("Conflicting native enchantments")
        if custom and sorted(custom) != sorted(saved_custom):
            raise ValueError("Conflicting custom enchantments")
        return
    if custom:
        raise ValueError("Custom enchantment encoding requires verified native userData")
    tag["ench"] = [{"id": _atom(2, key), "lvl": _atom(2, level),
                    "modEnchant": _atom(8, "")} for key, level in normal]


def canonical(resource, basic_info=None):
    """Normalize writable native identity without changing core ItemResource rules.

    basic_info, when needed, is callable(item_id, aux) -> GetItemBasicInfo dict.
    Conflicting convenience fields and NBT are rejected instead of overwritten.
    """
    resource = normalize_item(resource)
    _integer(resource.aux, 0, 32767)
    properties = resource.properties
    if set(properties) - _PROPERTIES - _DERIVED:
        raise ValueError("Unsupported native item properties")
    tag = properties.get("userData")
    if tag is None:
        tag = {}
    if not isinstance(tag, dict) or _TYPE in tag:
        raise TypeError("Item userData must be an NBT compound")
    tag = _copy_nbt(tag)
    for field, native in (("extraId", "ItemExtraID"),
                          ("customTips", "ItemCustomTips")):
        value = properties.get(field)
        if value is not None:
            if not isinstance(value, string_types):
                raise TypeError("Native item text property must be a string")
            if value:
                _merge(tag, native, _atom(8, _text(value)))
    _merge_enchantments(tag, properties)
    durability = properties.get("durability")
    if durability is not None:
        durability = _integer(durability)
        if basic_info is None or not callable(basic_info):
            raise ValueError("Durability conversion requires item basic information")
        basic = basic_info(resource.item_id, resource.aux)
        if not isinstance(basic, dict) or "maxDurability" not in basic:
            raise ValueError("Missing maximum item durability")
        maximum = _integer(basic["maxDurability"])
        if durability > maximum:
            raise ValueError("Remaining durability exceeds maximum")
        if maximum:
            _merge(tag, "Damage", _atom(3, maximum - durability))
        elif durability:
            raise ValueError("Non-durable item has durability")
    # Native tools may materialize their default zero damage on a write.
    if tag.get("Damage") == _atom(3, 0):
        del tag["Damage"]
    result = {"userData": tag} if tag else {}
    for field in ("canDestroy", "canPlaceOn"):
        if field in properties and properties[field] is not None:
            values = _strings(properties[field])
            if values:
                result[field] = values
    return item_resource(resource.item_id, resource.aux, result)


def decode_stack(stack, basic_info=None):
    """Return (canonical resource, count); known API-only fields are discarded."""
    if stack is None or stack == {}:
        return None, 0
    if not isinstance(stack, dict):
        raise TypeError("Native item stack must be a dictionary")
    if set(stack) - _STACK_KEYS - _PROPERTIES - _DERIVED:
        raise ValueError("Unsupported native stack fields")
    count = _integer(stack.get("count"), 0, 127)
    if count == 0:
        return None, 0
    # Current names supersede legacy aliases, which may refer to pre-flattening IDs.
    name = stack.get("newItemName", stack.get("itemName"))
    aux = stack.get("newAuxValue", stack.get("auxValue", 0))
    properties = dict((key, value) for key, value in stack.items()
                      if key not in _STACK_KEYS)
    return canonical(item_resource(name, aux, properties), basic_info), count


decode_api_stack = decode_stack


def _validate_block(block, name, aux, basic_info):
    """Drop only a palette description the engine can exactly reconstruct.

    Engine.basic_info supplies _radium_block_states using the documented native
    GetBlockStatesFromAuxValue query. The original palette stays in templates.
    """
    if (not isinstance(block, dict) or
            set(block) != set(("name", "val", "version", "states"))):
        raise ValueError("Unsupported native item Block palette")
    if _read_atom(block["name"], 8) != name or _read_atom(block["val"], 2) != aux:
        raise ValueError("Native Block palette disagrees with item identity")
    _integer(_read_atom(block["version"], 3))
    states = block["states"]
    if not isinstance(states, dict) or _TYPE in states:
        raise ValueError("Unsupported native Block states")
    if basic_info is None or not callable(basic_info):
        raise ValueError("Block palette conversion requires verified native states")
    basic = basic_info(name, aux)
    if not isinstance(basic, dict) or not isinstance(basic.get("_radium_block_states"), dict):
        raise ValueError("Native block states are unavailable for this item")
    expected = basic["_radium_block_states"]
    if set(states) != set(expected):
        raise ValueError("Native Block states cannot be reconstructed from item aux")
    for key, node in states.items():
        kind = _kind(node)
        if kind not in (1, 3, 8):
            raise ValueError("Unsupported native Block state type")
        value = _read_atom(node, kind)
        target = expected[key]
        if kind == 8:
            if not isinstance(target, string_types) or value != _text(target):
                raise ValueError("Native Block string state differs from item aux")
        elif (not isinstance(target, integer_types + (bool,)) or value != target):
            raise ValueError("Native Block numeric state differs from item aux")


def decode_entry(entry, basic_info=None):
    """Return (canonical resource, count, physical slot) from typed item NBT."""
    if not isinstance(entry, dict) or set(entry) - _ENTRY_KEYS:
        raise ValueError("Unsupported native item entry fields")
    entry = _copy_nbt(entry)
    slot = _integer(_read_atom(entry.get("Slot"), 1), 0, 127)
    count = _integer(_read_atom(entry.get("Count"), 1), 0, 127)
    if "WasPickedUp" in entry:
        _integer(_read_atom(entry["WasPickedUp"], 1), 0, 1)
    if not count:
        return None, 0, slot
    name = _read_atom(entry.get("Name"), 8)
    aux = _integer(_read_atom(entry.get("Damage"), 2), 0, 32767)
    if "Block" in entry:
        _validate_block(entry["Block"], name, aux, basic_info)
    properties = {}
    if "tag" in entry:
        properties["userData"] = entry["tag"]
    for native, field in (("CanDestroy", "canDestroy"), ("CanPlaceOn", "canPlaceOn")):
        if native in entry:
            if not isinstance(entry[native], list):
                raise ValueError("Unsupported block restriction NBT")
            properties[field] = [_read_atom(value, 8) for value in entry[native]]
    return canonical(item_resource(name, aux, properties), basic_info), count, slot


def encode_entry(resource, count, slot, template=None, basic_info=None):
    """Encode one physical slot, retaining exact template fields for count edits.

    Empty slots return None and must be omitted from the block entity's Items list.
    A template is reused only when its canonical item identity matches.
    """
    count = _integer(count, 0, 127)
    slot = _integer(slot, 0, 127)
    if not count:
        return None
    resource = canonical(resource, basic_info)
    if template is not None:
        previous, ignored_count, ignored_slot = decode_entry(template, basic_info)
        if previous == resource:
            result = _copy_nbt(template)
            result["Count"] = _atom(1, count)
            result["Slot"] = _atom(1, slot)
            return result
    result = {"Name": _atom(8, resource.item_id),
              "Damage": _atom(2, resource.aux), "Count": _atom(1, count),
              "Slot": _atom(1, slot), "WasPickedUp": _atom(1, 0)}
    properties = resource.properties
    if properties.get("userData"):
        result["tag"] = _copy_nbt(properties["userData"])
    for field, native in (("canDestroy", "CanDestroy"), ("canPlaceOn", "CanPlaceOn")):
        if properties.get(field):
            result[native] = [_atom(8, value) for value in properties[field]]
    return result


def api_stack(resource, count, basic_info=None):
    """Return a detached native API stack. Empty slots use the documented {}."""
    count = _integer(count, 0, 127)
    if not count:
        return {}
    resource = canonical(resource, basic_info)
    result = resource.properties
    result.update({"newItemName": resource.item_id, "newAuxValue": resource.aux,
                   "count": count})
    return result
