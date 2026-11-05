from . import _void

_void.Generic = _void.FakeGeneric
_void.TypeVar = _void.FakeTypeVar

from ._void import Generic, TypeVar

__all__ = ["Generic", "TypeVar"]
