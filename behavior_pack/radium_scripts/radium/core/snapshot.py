# coding=utf-8
"""Detached NBT-safe snapshots. No engine I/O; caller reassigns bdata[key]."""
import struct
from .values import energy_amount, nbt_int, fluid_amount, string_types, integer_types, INFINITY
from .resource import save_resource, read_resource

BASE = 1000000000
SCHEMA = 1
FLUID_SCHEMA = 2


def save_energy(handler):
    # Arbitrary runtime FE integers are encoded as little-endian int32 limbs.
    amount = energy_amount(handler.get_amount())
    limbs = []
    while amount:
        amount, limb = divmod(amount, BASE)
        limbs.append(nbt_int(limb))
    return {"schema": SCHEMA, "limbs": limbs or [0]}


def read_energy(data):
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("Invalid energy snapshot schema")
    limbs = data.get("limbs")
    if not isinstance(limbs, list) or not limbs:
        raise ValueError("Energy limbs must be a nonempty int list")
    amount = 0
    for limb in reversed(limbs):
        value = nbt_int(limb)
        if isinstance(limb, float) or value >= BASE:
            raise ValueError("Invalid energy limb")
        amount = amount * BASE + value
    return amount


def save_fluid(handler):
    slots = {}
    for slot in handler.get_slots():
        amount = handler.get_amount(slot)
        infinite = amount == INFINITY
        slots[str(slot)] = {
            "resource": save_resource(handler.get_resource(slot)),
            # A hexadecimal string preserves the exact binary64 value through
            # native NBT, without relying on its default float tag precision.
            "amount": (0.0 if infinite else fluid_amount(amount)).hex(),
            "infinite": infinite,
        }
    return {"schema": FLUID_SCHEMA, "slots": slots}


def read_fluids(data, capacities):
    if (not isinstance(data, dict) or not isinstance(data.get("schema"), integer_types) or
            isinstance(data.get("schema"), bool) or
            data.get("schema") not in (SCHEMA, FLUID_SCHEMA)):
        raise ValueError("Invalid fluid snapshot schema")
    schema = data["schema"]
    records = data.get("slots")
    if not isinstance(records, dict) or set(records) != set(str(s) for s in capacities):
        raise ValueError("Snapshot slots must exactly match configured slots")
    states = {}
    for slot, capacity in capacities.items():
        record = records[str(slot)]
        if not isinstance(record, dict) or not isinstance(record.get("infinite"), bool):
            raise ValueError("Invalid fluid record")
        encoded = record.get("amount")
        if schema == FLUID_SCHEMA:
            if not isinstance(encoded, string_types):
                raise ValueError("Fluid schema 2 amounts require hexadecimal strings")
            amount = fluid_amount(float.fromhex(encoded))
            if amount.hex() != encoded:
                raise ValueError("Noncanonical fluid amount")
        else:
            amount = fluid_amount(encoded)
        raw_resource = record.get("resource")
        if schema == SCHEMA and raw_resource is not None and not isinstance(raw_resource, string_types):
            raise ValueError("Legacy fluid resources must be strings")
        fluid = read_resource(raw_resource)
        if record["infinite"]:
            if capacity != INFINITY or amount != 0:
                raise ValueError("Infinite fluid requires an infinite slot and zero sentinel")
            if fluid is None:
                raise ValueError("Infinite slot must have a resource")
            states[slot] = (fluid, INFINITY)
        elif amount > 0:
            if fluid is None:
                raise ValueError("Filled slot must have a resource")
            if capacity == INFINITY:
                raise ValueError("Fluid snapshot exceeds configured capacity")
            if amount > capacity:
                # Only accept the exact float32 rounding of this capacity from
                # schema 1. Larger/corrupt states and all schema 2 overflows fail.
                rounded = None
                if schema == SCHEMA:
                    try:
                        rounded = struct.unpack(">f", struct.pack(">f", capacity))[0]
                    except (OverflowError, struct.error):
                        pass
                if amount != rounded:
                    raise ValueError("Fluid snapshot exceeds configured capacity")
                amount = capacity
            states[slot] = (fluid, amount)
        else:
            if fluid is not None:
                raise ValueError("Empty slot must not retain a resource")
            states[slot] = (None, 0.0)
    return states
