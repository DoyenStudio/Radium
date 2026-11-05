# coding=utf-8
"""Immutable fluid identities; tagged property trees preserve scalar types."""
import math
from .values import integer_types, string_types, resource_id


def _text(value):
    if not isinstance(value, string_types):
        raise TypeError("Property keys and text must be strings")
    # Normalize unicode and UTF-8 str to the same cross-addon identity on Py2.
    return value.encode("utf-8") if not isinstance(value, str) else value


def _freeze(value):
    if value is None:
        return ("none", "")
    if isinstance(value, bool):
        return ("bool", "1" if value else "0")
    if isinstance(value, integer_types):
        return ("int", str(value))
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("Fluid properties must be finite")
        return ("float", (0.0 if value == 0 else value).hex())
    if isinstance(value, string_types):
        return ("str", _text(value))
    if isinstance(value, list):
        return ("list", tuple(_freeze(v) for v in value))
    if isinstance(value, dict):
        pairs = sorted((_text(k), _freeze(v)) for k, v in value.items())
        if len(set(k for k, v in pairs)) != len(pairs):
            raise ValueError("Duplicate normalized property key")
        return ("dict", tuple(pairs))
    raise TypeError("Fluid properties require native scalars, dicts and lists")


def _thaw(node):
    kind, value = node
    if kind == "none":
        return None
    if kind == "bool":
        return value == "1"
    if kind == "int":
        return int(value)
    if kind == "float":
        return float.fromhex(value)
    if kind == "str":
        return value
    if kind == "list":
        return [_thaw(v) for v in value]
    return dict((k, _thaw(v)) for k, v in value)


class FluidResource(tuple):
    __slots__ = ()

    def __new__(cls, fluid_id, properties):
        resource_id(fluid_id)
        if not isinstance(properties, dict):
            raise TypeError("Fluid properties must be a dict")
        return tuple.__new__(cls, (_text(fluid_id), _freeze(properties)))

    @property
    def fluid_id(self):
        return self[0]

    @property
    def properties(self):
        return _thaw(self[1])


def fluid_resource(fluid_id, properties=None):
    """No-property resources stay strings, preserving the v1 plain-ID protocol."""
    resource_id(fluid_id)
    if properties is not None and not isinstance(properties, dict):
        raise TypeError("Fluid properties must be a dict")
    return FluidResource(fluid_id, properties) if properties else _text(fluid_id)


def normalize_fluid(value):
    if isinstance(value, FluidResource):
        # Canonicalize a directly constructed empty-property instance too.
        return value if value[1][1] else value.fluid_id
    return fluid_resource(value)


def get_fluid_id(value):
    value = normalize_fluid(value)
    return value.fluid_id if isinstance(value, FluidResource) else value


def get_fluid_properties(value):
    value = normalize_fluid(value)
    return value.properties if isinstance(value, FluidResource) else {}


def _save_node(node):
    kind, value = node
    if kind == "dict":
        value = dict((k, _save_node(v)) for k, v in value)
    elif kind == "list":
        value = [_save_node(v) for v in value]
    return {"type": kind, "value": value}


def _read_node(record):
    if not isinstance(record, dict) or set(record) != set(("type", "value")):
        raise ValueError("Invalid fluid property record")
    kind, value = record["type"], record["value"]
    if kind == "dict" and isinstance(value, dict):
        return dict((_text(k), _read_node(v)) for k, v in value.items())
    if kind == "list" and isinstance(value, list):
        return [_read_node(v) for v in value]
    if not isinstance(value, string_types):
        raise ValueError("Invalid fluid property scalar")
    if kind == "none" and value == "":
        return None
    if kind == "bool" and value in ("0", "1"):
        return value == "1"
    if kind == "str":
        return value
    if kind == "int":
        result = int(value)
        if str(result) == value:
            return result
    if kind == "float":
        result = float.fromhex(value)
        if not math.isnan(result) and not math.isinf(result) and result.hex() == value:
            return result
    raise ValueError("Invalid fluid property encoding")


def save_resource(value):
    if value is None:
        return None
    value = normalize_fluid(value)
    if isinstance(value, FluidResource):
        return {"id": value.fluid_id, "properties": _save_node(value[1])}
    return value


def read_resource(value):
    if value is None or isinstance(value, string_types):
        return None if value is None else normalize_fluid(value)
    if not isinstance(value, dict) or set(value) != set(("id", "properties")):
        raise ValueError("Invalid fluid resource record")
    return fluid_resource(value["id"], _read_node(value["properties"]))
