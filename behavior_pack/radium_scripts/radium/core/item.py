# coding=utf-8
"""Transaction-backed item slots; item limits are supplied by the host."""
from collections import OrderedDict
from .transaction import Cell, TransactionError
from .values import integer_types
from .item_resource import item_amount, normalize_item


def item_slot(slot):
    if isinstance(slot, bool) or not isinstance(slot, integer_types) or slot < 0:
        raise ValueError("Item slots must be nonnegative integers")
    return slot


class ItemHandler(object):
    def __init__(self, cells, capacity, stack_limit, input_slots=None,
                 output_slots=None, accepts=None, valid=None):
        if not cells:
            raise ValueError("Item handlers need at least one slot")
        for slot in cells:
            item_slot(slot)
        self.cells = OrderedDict(sorted(cells.items()))
        if len(set(self.cells.values())) != len(self.cells):
            raise ValueError("Each item slot needs a distinct cell")
        if any(cell.manager is not self.manager for cell in self.cells.values()):
            raise ValueError("All cells must belong to one manager")
        if not callable(capacity):
            raise TypeError("Item capacity must be a slot callback")
        if not callable(stack_limit):
            item_amount(stack_limit)
        for callback in (accepts, valid):
            if callback is not None and not callable(callback):
                raise TypeError("Item predicates must be callable")
        self.capacity = capacity
        self.stack_limit = stack_limit
        self.input_slots = tuple(self.cells) if input_slots is None else tuple(input_slots)
        self.output_slots = tuple(self.cells) if output_slots is None else tuple(output_slots)
        for selected in (self.input_slots, self.output_slots):
            for slot in selected:
                item_slot(slot)
            if len(set(selected)) != len(selected) or any(s not in cells for s in selected):
                raise ValueError("Slot filters must name unique existing slots")
        self.accepts = accepts or (lambda slot, resource: True)
        self.valid = valid or (lambda: True)

    @property
    def manager(self):
        return next(iter(self.cells.values())).manager

    @property
    def storage_ids(self):
        return frozenset(self.cells.values())

    def _check(self, tx=None):
        self.manager.assert_thread()
        if tx is not None:
            if tx.manager is not self.manager:
                raise TransactionError("Item handler belongs to a different manager")
            tx.guard(lambda: self.valid())
        elif not self.valid():
            raise TransactionError("Item handler is no longer available")

    def _slot(self, slot):
        item_slot(slot)
        if slot not in self.cells:
            raise KeyError(slot)

    def get_slots(self):
        self._check()
        return tuple(self.cells)

    def get_storage_ids(self, slots=None):
        self._check()
        selected = self.cells if slots is None else tuple(slots)
        for slot in selected:
            self._slot(slot)
        return frozenset(self.cells[slot] for slot in selected)

    def _read(self, slot, tx):
        self._check(tx)
        self._slot(slot)
        cell = self.cells[slot]
        resource, count = tx.read(cell) if tx is not None else cell.get()
        count = item_amount(count)
        if count == 0:
            if resource is not None:
                raise ValueError("Empty item slots must not retain a resource")
            return None, 0
        return normalize_item(resource), count

    def get_resource(self, slot, tx=None):
        return self._read(slot, tx)[0]

    def get_amount(self, slot, tx=None):
        return self._read(slot, tx)[1]

    def storage_capacity(self, slot, resource=None):
        """Physical limit, independent of automation direction or input filters."""
        self._check()
        self._slot(slot)
        capacity = item_amount(self.capacity(slot))
        if resource is None:
            return capacity
        resource = normalize_item(resource)
        limit = self.stack_limit(resource) if callable(self.stack_limit) else self.stack_limit
        return min(capacity, item_amount(limit))

    def get_capacity(self, slot, resource=None):
        self._slot(slot)
        if resource is not None and not self.is_valid(slot, resource):
            return 0
        return self.storage_capacity(slot, resource)

    def is_valid(self, slot, resource):
        self._check()
        self._slot(slot)
        resource = normalize_item(resource)
        return slot in self.input_slots and bool(self.accepts(slot, resource))

    def insert(self, resource, amount, tx, slot=None):
        resource = normalize_item(resource)
        amount = item_amount(amount)
        self._check(tx)
        if slot is not None:
            self._slot(slot)
        total = 0
        for index in self.input_slots if slot is None else (slot,):
            if total == amount:
                break
            if not self.is_valid(index, resource):
                continue
            current, stored = self._read(index, tx)
            if current is not None and current != resource:
                continue
            capacity = self.storage_capacity(index, resource)
            moved = min(amount - total, max(0, capacity - stored))
            if moved:
                tx.guard(lambda i=index, cap=capacity:
                         self.is_valid(i, resource) and self.storage_capacity(i, resource) == cap)
                tx.write(self.cells[index], (resource, stored + moved))
                total += moved
        return total

    def extract(self, resource, amount, tx, slot=None):
        resource = normalize_item(resource)
        amount = item_amount(amount)
        self._check(tx)
        if slot is not None:
            self._slot(slot)
        total = 0
        for index in self.output_slots if slot is None else (slot,):
            if total == amount:
                break
            if index not in self.output_slots:
                continue
            current, stored = self._read(index, tx)
            if current != resource:
                continue
            moved = min(amount - total, stored)
            if moved:
                tx.guard(lambda i=index: i in self.output_slots)
                remaining = stored - moved
                tx.write(self.cells[index], (resource, remaining) if remaining else (None, 0))
                total += moved
        return total


class ItemStorage(ItemHandler):
    def __init__(self, manager, capacities, stack_limit, persist=None, changed=None,
                 owner=None, input_slots=None, output_slots=None, accepts=None, valid=None):
        self.limits = dict((item_slot(slot), item_amount(capacity))
                           for slot, capacity in capacities.items())
        owner = self if owner is None else owner
        cells = dict((slot, Cell(manager, (None, 0), persist=persist, changed=changed,
                                 owner=owner, valid=valid)) for slot in self.limits)
        super(ItemStorage, self).__init__(cells, lambda slot: self.limits[slot],
                                          stack_limit, input_slots, output_slots, accepts, valid)
