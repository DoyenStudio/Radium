# coding=utf-8
from .transaction import Cell, TransactionError
from .values import energy_amount


class EnergyHandler(object):
    def __init__(self, cells, capacity, can_insert=True, can_extract=True,
                 max_insert=None, max_extract=None, valid=None,
                 on_insert=None, on_extract=None, owner=None):
        self.cells = tuple(cells)
        if not self.cells or len(set(self.cells)) != len(self.cells):
            raise ValueError("Energy handlers need nonempty, unique cells")
        if any(c.manager is not self.cells[0].manager for c in self.cells):
            raise ValueError("All cells must belong to one manager")
        self.capacity = capacity
        self.can_insert = can_insert
        self.can_extract = can_extract
        self.max_insert = max_insert
        self.max_extract = max_extract
        self.valid = valid or (lambda: True)
        self.on_insert = on_insert
        self.on_extract = on_extract
        self.owner = self if owner is None else owner

    @property
    def manager(self):
        return self.cells[0].manager

    @property
    def storage_ids(self):
        return frozenset(self.cells)

    @staticmethod
    def _value(value):
        return value() if callable(value) else value

    def get_amount(self, tx=None):
        return sum(tx.read(c) if tx else c.get() for c in self.cells)

    def get_capacity(self):
        return sum(self.capacity(c) for c in self.cells)

    def _transfer(self, amount, tx, inserting):
        amount = energy_amount(amount)
        if tx.manager is not self.manager:
            raise TransactionError("Handler belongs to a different manager")
        tx.guard(self.valid)
        allowed = lambda: self._value(self.can_insert if inserting else self.can_extract)
        if not allowed():
            return 0
        tx.guard(lambda: bool(allowed()))
        limit_field = lambda: self._value(self.max_insert if inserting else self.max_extract)
        limit = limit_field()
        tx.guard(lambda: limit_field() == limit)
        remaining = amount if limit is None else min(amount, energy_amount(limit))
        total = 0
        for cell in self.cells:
            stored = energy_amount(tx.read(cell))
            capacity = energy_amount(self.capacity(cell))
            tx.guard(lambda c=cell, cap=capacity: self.capacity(c) == cap)
            available = max(0, capacity - stored) if inserting else stored
            moved = min(remaining, available)
            if moved:
                tx.write(cell, stored + moved if inserting else stored - moved)
                total += moved
                remaining -= moved
            if remaining == 0:
                break
        callback = self.on_insert if inserting else self.on_extract
        tx.record((self.owner, "in" if inserting else "out"), callback, total)
        return total

    def insert(self, amount, tx):
        return self._transfer(amount, tx, True)

    def extract(self, amount, tx):
        return self._transfer(amount, tx, False)


class EnergyStorage(EnergyHandler):
    def __init__(self, manager, capacity, amount=0, persist=None, changed=None, owner=None):
        capacity = energy_amount(capacity)
        amount = energy_amount(amount)
        if amount > capacity:
            raise ValueError("Initial energy exceeds capacity")
        self.cell = Cell(manager, amount, persist=persist, changed=changed, owner=owner)
        super(EnergyStorage, self).__init__((self.cell,), lambda _: capacity)


class CombinedEnergyHandler(object):
    def __init__(self, handlers, valid=None):
        self.handlers = tuple(handlers)
        if not self.handlers:
            raise ValueError("Combined handler must not be empty")
        if any(h.manager is not self.handlers[0].manager for h in self.handlers):
            raise ValueError("All handlers must belong to one manager")
        self.valid = valid or (lambda: True)

    @property
    def manager(self):
        return self.handlers[0].manager

    @property
    def storage_ids(self):
        return frozenset(c for h in self.handlers for c in h.storage_ids)

    def get_amount(self, tx=None):
        seen = set()
        total = 0
        for handler in self.handlers:
            if seen.intersection(handler.storage_ids):
                continue
            total += handler.get_amount(tx)
            seen.update(handler.storage_ids)
        return total

    def get_capacity(self):
        seen = set()
        total = 0
        for handler in self.handlers:
            if seen.intersection(handler.storage_ids):
                continue
            total += handler.get_capacity()
            seen.update(handler.storage_ids)
        return total

    def _transfer(self, amount, tx, inserting):
        amount = energy_amount(amount)
        remaining = amount
        if tx.manager is not self.manager:
            raise TransactionError("Handler belongs to a different manager")
        tx.guard(self.valid)
        seen = set()
        for handler in self.handlers:
            if seen.intersection(handler.storage_ids):
                continue
            seen.update(handler.storage_ids)
            remaining -= (handler.insert(remaining, tx) if inserting
                          else handler.extract(remaining, tx))
            if remaining == 0:
                break
        return amount - remaining

    def insert(self, amount, tx):
        return self._transfer(amount, tx, True)

    def extract(self, amount, tx):
        return self._transfer(amount, tx, False)


class VoidingEnergyHandler(EnergyHandler):
    def __init__(self, manager, on_insert=None, valid=None):
        self.counter = Cell(manager, 0)
        super(VoidingEnergyHandler, self).__init__(
            (self.counter,), lambda _: 0, can_extract=False,
            on_insert=on_insert, valid=valid)

    def get_amount(self, tx=None):
        return 0

    def insert(self, amount, tx):
        amount = energy_amount(amount)
        if tx.manager is not self.manager:
            raise TransactionError("Handler belongs to a different manager")
        tx.guard(self.valid)
        tx.record((self.owner, "in"), self.on_insert, amount)
        return amount
