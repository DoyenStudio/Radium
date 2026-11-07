# coding=utf-8
"""Strict detached item snapshots containing only native NBT-safe values."""
from .values import integer_types, string_types
from .item_resource import (item_amount, item_resource, normalize_item,
                            _save_item_node, _read_item_node)


ITEM_SCHEMA = 1


def _read_integer(value):
    if not isinstance(value, string_types):
        raise ValueError("Item snapshot integers require decimal strings")
    result = item_amount(int(value))
    if str(result) != value:
        raise ValueError("Noncanonical item snapshot integer")
    return result


def _slots(handler):
    slots = tuple(handler.get_slots())
    for slot in slots:
        item_amount(slot)
    if len(set(slots)) != len(slots):
        raise ValueError("Item snapshot slots must be unique")
    return slots


def _resource_record(resource):
    resource = normalize_item(resource)
    return {"id": resource.item_id, "aux": str(resource.aux),
            "properties": _save_item_node(resource[2])}


def _read_resource(record):
    if (not isinstance(record, dict) or
            set(record) != set(("id", "aux", "properties"))):
        raise ValueError("Invalid item resource record")
    return item_resource(record["id"], _read_integer(record["aux"]),
                         _read_item_node(record["properties"]))


def _state(resource, amount):
    amount = item_amount(amount)
    if amount == 0:
        if resource is not None:
            raise ValueError("An empty item slot cannot retain a resource")
        return (None, 0)
    if resource is None:
        raise ValueError("A filled item slot must have a resource")
    return (normalize_item(resource), amount)


def save_item(handler):
    slots = {}
    for slot in _slots(handler):
        resource, amount = _state(handler.get_resource(slot),
                                  handler.get_amount(slot))
        slots[str(slot)] = {
            "resource": None if resource is None else _resource_record(resource),
            "amount": str(amount),
        }
    return {"schema": ITEM_SCHEMA, "slots": slots}


def read_items(data, handler):
    if (not isinstance(data, dict) or set(data) != set(("schema", "slots")) or
            isinstance(data["schema"], bool) or
            not isinstance(data["schema"], integer_types) or
            data["schema"] != ITEM_SCHEMA):
        raise ValueError("Invalid item snapshot schema")
    slots = _slots(handler)
    records = data["slots"]
    if (not isinstance(records, dict) or
            any(not isinstance(key, string_types) for key in records) or
            set(records) != set(str(slot) for slot in slots)):
        raise ValueError("Snapshot slots must exactly match configured slots")
    states = {}
    for slot in slots:
        record = records[str(slot)]
        if (not isinstance(record, dict) or
                set(record) != set(("resource", "amount"))):
            raise ValueError("Invalid item slot record")
        amount = _read_integer(record["amount"])
        resource = record["resource"]
        if resource is not None:
            resource = _read_resource(resource)
        resource, amount = _state(resource, amount)
        if resource is not None:
            # Restoration uses physical capacity and per-item stack limits,
            # independent of current insertion permissions or filters.
            capacity = item_amount(handler.storage_capacity(slot, resource))
            if amount > capacity:
                raise ValueError("Item snapshot exceeds configured storage capacity")
        states[slot] = (resource, amount)
    return states
