# coding=utf-8
from ..core.transaction import RecoveryError
from .backend import Engine, ItemBackend, CauldronBackend, UnsupportedContainer
from .owner import NativeOwner
from .items import NativeItemHandler
from .cauldron import CauldronHandler
from . import rules


class VanillaRegistry(object):
    def __init__(self, service, factory, level_id):
        self.service = service
        self.engine = Engine(factory, level_id)
        self.owners = {}
        self.blocked = set()
        self.reported = set()
        for name in sorted(rules.ITEM_BLOCKS):
            service.register_provider(service.ITEM, name, self.item_provider)
        for name in sorted(rules.CAULDRONS):
            service.register_provider(service.FLUID, name, self.fluid_provider)

    def invalidate(self):
        for owner in self.owners.values():
            if self.service.manager.is_quarantined(participant=owner):
                self.blocked.update((owner.backend.dimension, p) for p in owner.backend.positions)
            owner.alive = False
        self.owners.clear()

    def _owner(self, capability, dimension, pos):
        self.service.manager.assert_access()
        for cached in self.owners.values():
            if self.service.manager.is_quarantined(participant=cached):
                self.blocked.update((cached.backend.dimension, p) for p in cached.backend.positions)
        if (dimension, pos) in self.blocked:
            raise RecoveryError("Native container is quarantined; manual reconciliation required")
        cls = ItemBackend if capability == self.service.ITEM else CauldronBackend
        try:
            backend = cls(self.engine, dimension, pos)
            if any((dimension, p) in self.blocked for p in backend.positions):
                raise RecoveryError("A paired native container is quarantined")
            key = (capability, dimension, backend.positions)
            owner = self.owners.get(key)
            if owner is not None:
                if self.service.manager.is_quarantined(participant=owner):
                    self.blocked.update((dimension, p) for p in backend.positions)
                    raise RecoveryError("Native container is quarantined")
                old_identity = getattr(owner.backend, "identity", None)
                if old_identity == getattr(backend, "identity", None) and owner.alive:
                    return owner
                owner.alive = False
            size = backend.size if capability == self.service.ITEM else 1
            for previous in self.owners.values():
                if (previous.backend.dimension == dimension and
                        set(previous.backend.positions).intersection(backend.positions)):
                    previous.alive = False
            owner = NativeOwner(self.service.manager, backend, size)
            self.owners[key] = owner
            return owner
        except UnsupportedContainer as exc:
            key = (dimension, pos, str(exc))
            if key not in self.reported:
                self.reported.add(key)
                self.service.manager.report("Vanilla port unavailable at %r: %s" % ((dimension, pos), exc))
            return None

    def item_provider(self, dimension, pos, face):
        owner = self._owner(self.service.ITEM, dimension, pos)
        return NativeItemHandler(owner, face) if owner is not None else None

    def fluid_provider(self, dimension, pos, face):
        owner = self._owner(self.service.FLUID, dimension, pos)
        return CauldronHandler(owner.cells[0], owner.valid) if owner is not None else None
