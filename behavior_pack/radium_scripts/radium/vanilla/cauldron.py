# coding=utf-8
"""Single-slot, level-quantized cauldrons; native I/O belongs to the owner."""
from ..core.resource import normalize_fluid
from ..core.transaction import TransactionError
from ..core.values import fluid_amount, integer_types


WATER = "minecraft:water"
LAVA = "minecraft:lava"
LEVEL_AMOUNTS = (0, 167, 333, 500, 667, 833, 1000)


class CauldronHandler(object):
    """The owner's Cell contains (resource, level), never fractional levels."""
    def __init__(self, cell, valid=None):
        if valid is not None and not callable(valid):
            raise TypeError("Cauldron validity must be callable")
        self.cell = cell
        self.cells = {0: cell}
        self.valid = valid or (lambda: True)

    @property
    def manager(self):
        return self.cell.manager

    @property
    def storage_ids(self):
        return self.get_storage_ids()

    def _check(self, tx=None):
        self.manager.assert_thread()
        if tx is not None:
            if tx.manager is not self.manager:
                raise TransactionError("Handler belongs to a different manager")
            tx.guard(self.valid)
        elif not self.valid():
            raise TransactionError("Cauldron is no longer available")

    def get_storage_ids(self, slots=None):
        self._check()
        return frozenset(self.cells[s] for s in ((0,) if slots is None else slots))

    def get_slots(self):
        self._check()
        return (0,)

    def _read(self, slot, tx=None):
        self._check(tx)
        cell = self.cells[slot]
        state = tx.read(cell) if tx is not None else cell.get()
        if not isinstance(state, tuple) or len(state) != 2:
            raise TransactionError("Invalid cauldron state")
        resource, level = state
        if (isinstance(level, bool) or not isinstance(level, integer_types) or
                level < 0 or level > 6 or
                (level == 0 and resource is not None) or
                (level > 0 and resource not in (WATER, LAVA)) or
                (resource == LAVA and level != 6)):
            raise TransactionError("Unsupported cauldron contents")
        return resource, level

    def get_resource(self, slot, tx=None):
        return self._read(slot, tx)[0]

    def get_amount(self, slot, tx=None):
        return float(LEVEL_AMOUNTS[self._read(slot, tx)[1]])

    def get_capacity(self, slot, fluid_id=None):
        self._check()
        if slot not in self.cells:
            raise KeyError(slot)
        return 1000.0 if fluid_id is None or self.is_valid(slot, fluid_id) else 0.0

    def is_valid(self, slot, fluid_id):
        self._check()
        fluid_id = normalize_fluid(fluid_id)
        return slot == 0 and fluid_id in (WATER, LAVA)

    @staticmethod
    def _changes(resource, level, amount, inserting):
        # Descending moved amounts make both transfer and candidate lookup bounded.
        if resource == LAVA:
            levels = (6,) if inserting and level == 0 else ((0,) if not inserting else ())
        else:
            levels = range(6, level, -1) if inserting else range(level)
        current = LEVEL_AMOUNTS[level]
        return tuple((float(abs(LEVEL_AMOUNTS[target] - current)), target)
                     for target in levels
                     if 0 < abs(LEVEL_AMOUNTS[target] - current) <= amount)

    def _transfer(self, fluid_id, amount, tx, slot, inserting):
        fluid_id = normalize_fluid(fluid_id)
        amount = fluid_amount(amount)
        self._check(tx)
        if slot not in (None, 0) or fluid_id not in (WATER, LAVA):
            return 0.0
        resource, level = self._read(0, tx)
        if (inserting and resource is not None and resource != fluid_id or
                not inserting and resource != fluid_id):
            return 0.0
        changes = self._changes(fluid_id, level, amount, inserting)
        if not changes:
            return 0.0
        moved, target = changes[0]
        tx.write(self.cell, (fluid_id, target) if target else (None, 0))
        return moved

    def insert(self, fluid_id, amount, tx, slot=None):
        return self._transfer(fluid_id, amount, tx, slot, True)

    def extract(self, fluid_id, amount, tx, slot=None):
        return self._transfer(fluid_id, amount, tx, slot, False)

    def extraction_candidates(self, resource, amount, tx, slots=None):
        """All positive legal extraction quantities, largest first, without writes."""
        resource = normalize_fluid(resource)
        amount = fluid_amount(amount)
        self._check(tx)
        if slots is not None and 0 not in slots:
            return ()
        current, level = self._read(0, tx)
        if current != resource or resource not in (WATER, LAVA):
            return ()
        return tuple(moved for moved, target in self._changes(resource, level, amount, False))
