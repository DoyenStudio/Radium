# coding=utf-8
from .transaction import TransactionError
from .values import integer_types, resource_id
from .item_resource import normalize_item

ENERGY = "radium:energy"
FLUID = "radium:fluid"
ITEM = "radium:item"


class ProviderRegistry(object):
    """Providers only expose already-loaded endpoints; no block entity creation."""
    def __init__(self, manager, is_loaded, block_name):
        self.manager = manager
        self.is_loaded = is_loaded
        self.block_name = block_name
        self.providers = {}
        self.provider_revisions = {}
        self.generation = 0

    def register(self, capability, block_id, provider):
        self.manager.assert_idle()
        if capability not in (ENERGY, FLUID, ITEM):
            raise ValueError("Unsupported capability")
        resource_id(block_id)
        if not callable(provider):
            raise TypeError("Provider must be callable")
        key = (capability, block_id)
        previous = self.providers.get(key)
        if previous is not None and previous != provider:
            raise ValueError("A different provider is already registered for %r" % (key,))
        if previous is None:
            self.providers[key] = provider
            self.provider_revisions[capability] = self.provider_revisions.get(capability, 0) + 1

    def unregister(self, capability, block_id, provider):
        self.manager.assert_idle()
        key = (capability, block_id)
        if self.providers.get(key) == provider:
            del self.providers[key]
            self.provider_revisions[capability] += 1
            self.invalidate()
            return True
        return False

    def invalidate(self):
        # Global generation is intentional: no strong-reference block cache.
        self.manager.defer(self._invalidate_now)

    def _invalidate_now(self):
        self.generation += 1

    def query(self, capability, dimension, pos, face=None):
        self.manager.assert_access()
        if capability not in (ENERGY, FLUID, ITEM):
            raise ValueError("Unsupported capability")
        pos = tuple(pos)
        if (len(pos) != 3 or any(isinstance(v, bool) or not isinstance(v, integer_types)
                                 for v in pos) or isinstance(dimension, bool)
                or not isinstance(dimension, integer_types)):
            raise ValueError("Use integer dimension and block coordinates")
        if face is not None and (isinstance(face, bool) or
                                 not isinstance(face, integer_types) or face not in range(6)):
            raise ValueError("Face must be an absolute target face 0..5 or None")
        if not self.is_loaded(dimension, pos):
            return None
        name = self.block_name(dimension, pos)
        provider = self.providers.get((capability, name))
        if provider is None:
            return None
        generation = self.generation
        handler = provider(dimension, pos, face)
        if handler is None:
            return None
        if handler.manager is not self.manager:
            raise TransactionError("Provider returned an endpoint from a different service")

        def valid():
            return (self.generation == generation and
                    self.providers.get((capability, name)) == provider and
                    self.is_loaded(dimension, pos) and
                    self.block_name(dimension, pos) == name)

        cls = {ENERGY: GuardedEnergy, FLUID: GuardedFluid, ITEM: GuardedItem}[capability]
        return cls(handler, valid)


class GuardedHandler(object):
    def __init__(self, handler, valid):
        self.handler = handler
        self.valid = valid

    @property
    def manager(self):
        return self.handler.manager

    @property
    def storage_ids(self):
        return self.handler.storage_ids

    def check(self, tx=None):
        self.manager.assert_access()
        if tx is not None:
            tx.guard(self.valid)
        elif not self.valid():
            raise TransactionError("Stale capability handle; query it again")


class GuardedEnergy(GuardedHandler):
    def get_amount(self, tx=None):
        self.check(tx)
        return self.handler.get_amount(tx)

    def get_capacity(self):
        self.check()
        return self.handler.get_capacity()

    def insert(self, amount, tx):
        self.check(tx)
        return self.handler.insert(amount, tx)

    def extract(self, amount, tx):
        self.check(tx)
        return self.handler.extract(amount, tx)


class GuardedFluid(GuardedHandler):
    def extraction_candidates(self, resource, amount, tx, slots=None):
        self.check(tx)
        method = getattr(self.handler, "extraction_candidates", None)
        if method is None:
            return None
        if not callable(method):
            raise TransactionError("Extraction candidates must be callable")
        return method(resource, amount, tx, slots)

    def get_storage_ids(self, slots=None):
        self.check()
        method = getattr(self.handler, "get_storage_ids", None)
        return method(slots) if method is not None else self.handler.storage_ids

    def get_slots(self):
        self.check()
        return self.handler.get_slots()

    def get_resource(self, slot, tx=None):
        self.check(tx)
        return self.handler.get_resource(slot, tx)

    def get_amount(self, slot, tx=None):
        self.check(tx)
        return self.handler.get_amount(slot, tx)

    def get_capacity(self, slot, fluid_id=None):
        self.check()
        return self.handler.get_capacity(slot, fluid_id)

    def is_valid(self, slot, fluid_id):
        self.check()
        return self.handler.is_valid(slot, fluid_id)

    def insert(self, fluid_id, amount, tx, slot=None):
        self.check(tx)
        return self.handler.insert(fluid_id, amount, tx, slot)

    def extract(self, fluid_id, amount, tx, slot=None):
        self.check(tx)
        return self.handler.extract(fluid_id, amount, tx, slot)


class GuardedItem(GuardedHandler):
    def normalize_resource(self, resource):
        self.check()
        resource = normalize_item(resource)
        method = getattr(self.handler, "normalize_resource", None)
        if method is None:
            return resource
        if not callable(method):
            raise TransactionError("Item resource normalization must be callable")
        return normalize_item(method(resource))

    def get_storage_ids(self, slots=None):
        self.check()
        method = getattr(self.handler, "get_storage_ids", None)
        return method(slots) if method is not None else self.handler.storage_ids

    def get_slots(self):
        self.check()
        return self.handler.get_slots()

    def get_resource(self, slot, tx=None):
        self.check(tx)
        return self.handler.get_resource(slot, tx)

    def get_amount(self, slot, tx=None):
        self.check(tx)
        return self.handler.get_amount(slot, tx)

    def get_capacity(self, slot, resource=None):
        self.check()
        return self.handler.get_capacity(slot, resource)

    def is_valid(self, slot, resource):
        self.check()
        return self.handler.is_valid(slot, resource)

    def insert(self, resource, amount, tx, slot=None):
        self.check(tx)
        return self.handler.insert(resource, amount, tx, slot)

    def extract(self, resource, amount, tx, slot=None):
        self.check(tx)
        return self.handler.extract(resource, amount, tx, slot)
