# coding=utf-8
"""Immutable item identities, separated from stack counts and engine objects."""
from .values import integer_types, string_types, resource_id
from .resource import _text, _freeze, _thaw, _save_node, _read_node


_STACK_FIELDS = frozenset(("newItemName", "itemName", "newAuxValue",
                           "auxValue", "count"))


def item_amount(value):
    """Counts and auxiliary values are exact integers, never bools or floats."""
    if isinstance(value, bool) or not isinstance(value, integer_types):
        raise TypeError("Item amount must be a non-negative integer")
    if value < 0:
        raise ValueError("Item amount must be non-negative")
    return int(value)


def _freeze_item(value):
    # Native enchantment entries use tuples. Preserve that distinction without
    # extending the established fluid-property contract.
    if isinstance(value, (list, tuple)):
        kind = "tuple" if isinstance(value, tuple) else "list"
        return (kind, tuple(_freeze_item(entry) for entry in value))
    if isinstance(value, dict):
        pairs = sorted((_text(key), _freeze_item(entry))
                       for key, entry in value.items())
        if len(set(key for key, entry in pairs)) != len(pairs):
            raise ValueError("Duplicate normalized item property key")
        return ("dict", tuple(pairs))
    return _freeze(value)


def _thaw_item(node):
    kind, value = node
    if kind == "tuple":
        return tuple(_thaw_item(entry) for entry in value)
    if kind == "list":
        return [_thaw_item(entry) for entry in value]
    if kind == "dict":
        return dict((key, _thaw_item(entry)) for key, entry in value)
    return _thaw(node)


def _save_item_node(node):
    kind, value = node
    if kind == "dict":
        return {"type": kind, "value": dict(
            (key, _save_item_node(entry)) for key, entry in value)}
    if kind in ("list", "tuple"):
        return {"type": kind, "value": [_save_item_node(entry)
                                        for entry in value]}
    return _save_node(node)


def _read_item_node(record):
    if (not isinstance(record, dict) or
            set(record) != set(("type", "value"))):
        raise ValueError("Invalid item property record")
    kind, value = record["type"], record["value"]
    if not isinstance(kind, string_types):
        raise ValueError("Invalid item property type")
    if kind == "dict":
        if not isinstance(value, dict):
            raise ValueError("Invalid item property dictionary")
        result = {}
        for key, entry in value.items():
            key = _text(key)
            if key in result:
                raise ValueError("Duplicate normalized item property key")
            result[key] = _read_item_node(entry)
        return result
    if kind in ("list", "tuple"):
        if not isinstance(value, list):
            raise ValueError("Invalid item property sequence")
        result = [_read_item_node(entry) for entry in value]
        return tuple(result) if kind == "tuple" else result
    return _read_node(record)


class ItemResource(tuple):
    __slots__ = ()

    def __new__(cls, item_id, aux=0, properties=None):
        resource_id(item_id)
        item_id = _text(item_id)
        if item_id == "minecraft:air":
            raise ValueError("Air is not a stored item resource")
        aux = item_amount(aux)
        if properties is None:
            properties = {}
        if not isinstance(properties, dict):
            raise TypeError("Item properties must be a dict")
        if any(_text(key) in _STACK_FIELDS for key in properties):
            raise ValueError("Item properties cannot contain stack identity or count")
        return tuple.__new__(cls, (item_id, aux, _freeze_item(properties)))

    @property
    def item_id(self):
        return self[0]

    @property
    def aux(self):
        return self[1]

    @property
    def properties(self):
        return _thaw_item(self[2])


def item_resource(item_id, aux=0, properties=None):
    return ItemResource(item_id, aux, properties)


def normalize_item(value):
    return value if isinstance(value, ItemResource) else item_resource(value)


def get_item_id(value):
    return normalize_item(value).item_id


def get_item_aux(value):
    return normalize_item(value).aux


def get_item_properties(value):
    return normalize_item(value).properties


def _alias(stack, current, legacy, default, normalize):
    if current in stack and legacy in stack:
        value = normalize(stack[current])
        if value != normalize(stack[legacy]):
            raise ValueError("Conflicting item aliases: %s and %s" %
                             (current, legacy))
        return value
    if current in stack:
        return normalize(stack[current])
    if legacy in stack:
        return normalize(stack[legacy])
    return default


def item_resource_from_stack(stack):
    """Copy a native item dictionary's identity; a zero count yields None."""
    if stack is None:
        return None
    if not isinstance(stack, dict):
        raise TypeError("An item stack must be a dict or None")
    if not stack:
        return None
    count = item_amount(stack.get("count"))
    item_id = _alias(stack, "newItemName", "itemName", None, _text)
    aux = _alias(stack, "newAuxValue", "auxValue", 0, item_amount)
    if count == 0:
        return None
    properties = dict((key, value) for key, value in stack.items()
                      if _text(key) not in _STACK_FIELDS)
    return item_resource(item_id, aux, properties)


def item_stack(resource, count=1):
    """Return a detached native stack; None represents a zero-sized stack."""
    count = item_amount(count)
    if count == 0:
        return None
    resource = normalize_item(resource)
    result = resource.properties
    result.update({"newItemName": resource.item_id,
                   "newAuxValue": resource.aux, "count": count})
    return result
