# coding=utf-8
import math
import struct

try:
    integer_types = (int, long)
    string_types = (str, unicode)
except NameError:
    integer_types = (int,)
    string_types = (str,)

EPSILON = 1e-6
INFINITY = float("inf")


def energy_amount(value):
    if isinstance(value, bool) or not isinstance(value, integer_types + (float,)):
        raise TypeError("FE must be a non-negative integer")
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value) or value != int(value):
            raise ValueError("Fractional or non-finite FE is not supported")
    if value < 0:
        raise ValueError("FE must be non-negative")
    return int(value)


def fluid_amount(value):
    if isinstance(value, bool) or not isinstance(value, integer_types + (float,)):
        raise TypeError("Fluid amount must be numeric")
    value = float(value)
    if math.isnan(value) or math.isinf(value) or value < 0:
        raise ValueError("Fluid transfer amount must be finite and non-negative")
    return value


def exact_fluid_sum(a, b):
    """Return a+b only when its float represents the exact sum of both floats."""
    result = a + b
    if math.isinf(result):
        return None
    an, ad = float(a).as_integer_ratio()
    bn, bd = float(b).as_integer_ratio()
    rn, rd = result.as_integer_ratio()
    return result if (an * bd + bn * ad) * rd == rn * ad * bd else None


def fluid_delta(stored, requested, inserting, capacity=None):
    """A finite update must report its exact representable delta, never a quote."""
    if requested <= 0:
        return stored, 0.0
    final = (min(capacity, stored + requested) if inserting else stored - requested)
    # Rounding can overshoot the requested amount. Try the adjacent float toward
    # the original state; otherwise leave this slot untouched.
    for attempt in range(2):
        moved = abs(final - stored)
        if (0 < moved <= requested and
                exact_fluid_sum(stored, moved if inserting else -moved) == final):
            return final, moved
        if final == stored:
            break
        bits = struct.unpack(">Q", struct.pack(">d", final))[0]
        bits += -1 if inserting else 1
        final = struct.unpack(">d", struct.pack(">Q", bits))[0]
    return stored, 0.0


def resource_id(value):
    if (not isinstance(value, string_types) or value.count(":") != 1 or
            not all(value.split(":")) or any(c.isspace() for c in value)):
        raise ValueError("Resource ID must use namespace:name")
    return value


def nbt_int(value):
    value = energy_amount(value)
    if value > 2147483647:
        raise OverflowError("FE scalar does not fit signed int32 NBT")
    return int(value)
