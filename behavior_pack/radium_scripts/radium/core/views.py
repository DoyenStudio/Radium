# coding=utf-8
"""Restrict public endpoint protocols by delegation, without rebuilding storage."""
from .transaction import TransactionError
from .values import energy_amount, fluid_amount, exact_fluid_sum
from .resource import normalize_fluid


def _value(value):
    return value() if callable(value) else value


class EndpointView(object):
    def __init__(self, handler, valid):
        self.handler = handler
        self.valid = valid or (lambda: True)

    @property
    def manager(self):
        return self.handler.manager

    @property
    def storage_ids(self):
        return self.handler.storage_ids

    def _check(self, tx=None):
        self.manager.assert_thread()
        if tx is not None:
            if tx.manager is not self.manager:
                raise TransactionError("View belongs to a different manager")
            tx.guard(lambda: self.valid())
        elif not self.valid():
            raise TransactionError("View is no longer available")


class EnergyView(EndpointView):
    def __init__(self, handler, can_insert=True, can_extract=True, valid=None,
                 max_insert=None, max_extract=None):
        super(EnergyView, self).__init__(handler, valid)
        self.can_insert = can_insert
        self.can_extract = can_extract
        self.max_insert = max_insert
        self.max_extract = max_extract

    def get_amount(self, tx=None):
        self._check(tx)
        return self.handler.get_amount(tx)

    def get_capacity(self):
        self._check()
        return self.handler.get_capacity()

    def _transfer(self, amount, tx, inserting):
        amount = energy_amount(amount)
        self._check(tx)
        allowed = lambda: _value(self.can_insert if inserting else self.can_extract)
        if not allowed():
            return 0
        tx.guard(lambda: bool(allowed()))
        limit_field = lambda: _value(self.max_insert if inserting else self.max_extract)
        limit = limit_field()
        tx.guard(lambda: limit_field() == limit)
        if limit is not None:
            amount = min(amount, energy_amount(limit))
        return (self.handler.insert(amount, tx) if inserting
                else self.handler.extract(amount, tx))

    def insert(self, amount, tx):
        return self._transfer(amount, tx, True)

    def extract(self, amount, tx):
        return self._transfer(amount, tx, False)


class FluidView(EndpointView):
    def __init__(self, handler, slots=None, input_slots=None, output_slots=None,
                 valid=None, accepts=None):
        super(FluidView, self).__init__(handler, valid)
        available = tuple(handler.get_slots())
        self.slots = available if slots is None else tuple(slots)
        if (len(set(self.slots)) != len(self.slots) or
                any(s not in available for s in self.slots)):
            raise ValueError("A view must name unique existing slots")
        self.input_slots = self.slots if input_slots is None else tuple(input_slots)
        self.output_slots = self.slots if output_slots is None else tuple(output_slots)
        for selected in (self.input_slots, self.output_slots):
            if len(set(selected)) != len(selected) or any(s not in self.slots for s in selected):
                raise ValueError("Slot filters must name unique visible slots")
        self.bulk_insert = slots is None and input_slots is None
        self.bulk_extract = slots is None and output_slots is None
        self.accepts = accepts

    def get_storage_ids(self, slots=None):
        selected = self.slots if slots is None else tuple(slots)
        if any(s not in self.slots for s in selected):
            raise ValueError("Unknown view slot")
        method = getattr(self.handler, "get_storage_ids", None)
        # Opaque endpoints conservatively retain their entire identity set.
        return method(selected) if method is not None else self.handler.storage_ids

    @property
    def storage_ids(self):
        return self.get_storage_ids()

    def get_slots(self):
        self._check()
        return self.slots

    def _slot(self, slot):
        if slot not in self.slots:
            raise KeyError(slot)

    def get_resource(self, slot, tx=None):
        self._check(tx)
        self._slot(slot)
        return self.handler.get_resource(slot, tx)

    def get_amount(self, slot, tx=None):
        self._check(tx)
        self._slot(slot)
        return self.handler.get_amount(slot, tx)

    def get_capacity(self, slot, fluid_id=None):
        self._check()
        self._slot(slot)
        if fluid_id is not None:
            fluid_id = normalize_fluid(fluid_id)
            if not self.is_valid(slot, fluid_id):
                return 0.0
        return self.handler.get_capacity(slot, fluid_id)

    def is_valid(self, slot, fluid_id):
        self._check()
        fluid_id = normalize_fluid(fluid_id)
        return (slot in self.input_slots and
                (self.accepts is None or self.accepts(slot, fluid_id)) and
                self.handler.is_valid(slot, fluid_id))

    def _transfer(self, fluid_id, amount, tx, slot, inserting):
        fluid_id = normalize_fluid(fluid_id)
        amount = fluid_amount(amount)
        self._check(tx)
        selected = self.input_slots if inserting else self.output_slots
        if slot is not None and slot not in selected:
            return 0.0
        bulk = self.bulk_insert if inserting else self.bulk_extract
        operation = self.handler.insert if inserting else self.handler.extract
        if slot is None and bulk and (not inserting or self.accepts is None):
            tx.guard(lambda: (self.bulk_insert if inserting else self.bulk_extract)
                     and (self.input_slots if inserting else self.output_slots) == selected
                     and (not inserting or self.accepts is None))
            return operation(fluid_id, amount, tx)
        total = 0.0
        for index in selected if slot is None else (slot,):
            if inserting and not self.is_valid(index, fluid_id):
                continue
            # Discard delegate state/effects too if the sum cannot be represented.
            with tx.manager.open(tx) as attempt:
                attempt.guard(lambda i=index: i in (
                    self.input_slots if inserting else self.output_slots))
                if inserting:
                    attempt.guard(lambda i=index: self.is_valid(i, fluid_id))
                moved = fluid_amount(operation(fluid_id, amount - total, attempt, index))
                if moved > amount - total:
                    raise TransactionError("Delegate exceeded requested fluid amount")
                combined = exact_fluid_sum(total, moved)
                if combined is None or combined > amount:
                    continue
                attempt.commit()
                total = combined
            if total == amount:
                break
        return total

    def insert(self, fluid_id, amount, tx, slot=None):
        return self._transfer(fluid_id, amount, tx, slot, True)

    def extract(self, fluid_id, amount, tx, slot=None):
        return self._transfer(fluid_id, amount, tx, slot, False)


def energy_view(handler, can_insert=True, can_extract=True, valid=None,
                max_insert=None, max_extract=None):
    return EnergyView(handler, can_insert, can_extract, valid, max_insert, max_extract)


def fluid_view(handler, slots=None, input_slots=None, output_slots=None, valid=None,
               accepts=None):
    return FluidView(handler, slots, input_slots, output_slots, valid, accepts)
