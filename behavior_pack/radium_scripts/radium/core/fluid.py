# coding=utf-8
from collections import OrderedDict
from .transaction import Cell, TransactionError
from .values import INFINITY, fluid_amount, integer_types, fluid_delta, exact_fluid_sum
from .resource import normalize_fluid


class FluidHandler(object):
    """Sparse slot IDs; amounts in mB. Storage cells hold (resource_id, amount)."""
    def __init__(self, cells, capacity, input_slots=None, output_slots=None,
                 accepts=None, valid=None):
        if not cells or any(isinstance(s, bool) or not isinstance(s, integer_types)
                            or s < 0 for s in cells):
            raise ValueError("Fluid handlers need nonempty, nonnegative integer slots")
        self.cells = OrderedDict(sorted(cells.items()))
        if len(set(self.cells.values())) != len(self.cells):
            raise ValueError("Each fluid slot needs a distinct cell")
        if any(c.manager is not self.manager for c in self.cells.values()):
            raise ValueError("All cells must belong to one manager")
        self.capacity = capacity
        self.input_slots = tuple(self.cells) if input_slots is None else tuple(input_slots)
        self.output_slots = tuple(self.cells) if output_slots is None else tuple(output_slots)
        for slots in (self.input_slots, self.output_slots):
            if len(set(slots)) != len(slots) or any(s not in cells for s in slots):
                raise ValueError("Slot filters must name unique existing slots")
        self.accepts = accepts or (lambda slot, fluid: True)
        self.valid = valid or (lambda: True)

    @property
    def manager(self):
        return next(iter(self.cells.values())).manager

    @property
    def storage_ids(self):
        return frozenset(self.cells.values())

    def get_storage_ids(self, slots=None):
        return frozenset(self.cells[s] for s in (self.cells if slots is None else slots))

    def get_slots(self):
        return tuple(self.cells)

    def _read(self, slot, tx):
        cell = self.cells[slot]
        return tx.read(cell) if tx else cell.get()

    def get_resource(self, slot, tx=None):
        resource, amount = self._read(slot, tx)
        return resource if amount > 0 else None

    def get_amount(self, slot, tx=None):
        return self._read(slot, tx)[1]

    def get_capacity(self, slot, fluid_id=None):
        if fluid_id is not None and not self.is_valid(slot, fluid_id):
            return 0.0
        return self.capacity(slot)

    def is_valid(self, slot, fluid_id):
        fluid_id = normalize_fluid(fluid_id)
        return slot in self.input_slots and self.accepts(slot, fluid_id)

    def insert(self, fluid_id, amount, tx, slot=None):
        fluid_id = normalize_fluid(fluid_id)
        amount = fluid_amount(amount)
        total = 0.0
        if tx.manager is not self.manager:
            raise TransactionError("Handler belongs to a different manager")
        tx.guard(self.valid)
        slots = self.input_slots if slot is None else (slot,)
        for index in slots:
            if index not in self.cells or not self.is_valid(index, fluid_id):
                continue
            current, stored = self._read(index, tx)
            if stored > 0 and current != fluid_id:
                continue
            capacity = self.capacity(index)
            if capacity != INFINITY:
                capacity = fluid_amount(capacity)
            tx.guard(lambda i=index, cap=capacity:
                     self.capacity(i) == cap and self.is_valid(i, fluid_id))
            if capacity == INFINITY:
                if current is None and amount > total:
                    # Explicit creative supply: first insertion configures its type.
                    tx.write(self.cells[index], (fluid_id, INFINITY))
                    return amount
                continue
            stored = fluid_amount(stored)
            requested = min(amount - total, max(0.0, capacity - stored))
            final, moved = fluid_delta(stored, requested, True, capacity)
            combined = exact_fluid_sum(total, moved)
            if combined is None or combined > amount:
                continue
            if moved > 0:
                tx.write(self.cells[index], (fluid_id, final))
                total = combined
            if total == amount:
                break
        return total

    def extract(self, fluid_id, amount, tx, slot=None):
        fluid_id = normalize_fluid(fluid_id)
        amount = fluid_amount(amount)
        total = 0.0
        if tx.manager is not self.manager:
            raise TransactionError("Handler belongs to a different manager")
        tx.guard(self.valid)
        slots = self.output_slots if slot is None else (slot,)
        for index in slots:
            if index not in self.cells or index not in self.output_slots:
                continue
            current, stored = self._read(index, tx)
            if current != fluid_id or stored <= 0:
                continue
            tx.guard(lambda i=index: i in self.output_slots)
            if stored == INFINITY:
                return amount
            stored = fluid_amount(stored)
            rest, moved = fluid_delta(stored, min(stored, amount - total), False)
            combined = exact_fluid_sum(total, moved)
            if combined is None or combined > amount:
                continue
            if moved > 0:
                tx.write(self.cells[index], (None, 0.0) if rest <= 0
                         else (current, rest))
                total = combined
            if total == amount:
                break
        return total


class FluidStorage(FluidHandler):
    def __init__(self, manager, capacities, persist=None, changed=None, owner=None):
        self.limits = {}
        for slot, capacity in capacities.items():
            self.limits[slot] = (INFINITY if capacity == INFINITY
                                 else fluid_amount(capacity))
        cells = dict((slot, Cell(manager, (None, 0.0), persist=persist,
                                changed=changed, owner=self if owner is None else owner)) for slot in self.limits)
        super(FluidStorage, self).__init__(cells, lambda slot: self.limits[slot])
