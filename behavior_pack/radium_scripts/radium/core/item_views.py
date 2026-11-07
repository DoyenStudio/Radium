# coding=utf-8
"""Item endpoint restrictions that retain the delegate's storage semantics."""
from .item_resource import normalize_item, item_amount
from .transaction import TransactionError
from .values import integer_types
from .views import EndpointView


def _slots(selected, available):
    selected = tuple(selected)
    if (any(isinstance(slot, bool) or not isinstance(slot, integer_types)
            or slot < 0 for slot in selected) or
            len(set(selected)) != len(selected) or
            any(slot not in available for slot in selected)):
        raise ValueError("Slot filters must name unique existing slots")
    return selected


class ItemView(EndpointView):
    def __init__(self, handler, slots=None, input_slots=None, output_slots=None,
                 valid=None, accepts=None):
        super(ItemView, self).__init__(handler, valid)
        available = tuple(handler.get_slots())
        self.slots = _slots(available if slots is None else slots, available)
        self.input_slots = _slots(
            self.slots if input_slots is None else input_slots, self.slots)
        self.output_slots = _slots(
            self.slots if output_slots is None else output_slots, self.slots)
        self.bulk_insert = slots is None and input_slots is None
        self.bulk_extract = slots is None and output_slots is None
        self.accepts = accepts

    def normalize_resource(self, resource):
        self.manager.assert_access()
        self._check()
        resource = normalize_item(resource)
        method = getattr(self.handler, "normalize_resource", None)
        if method is None:
            return resource
        if not callable(method):
            raise TransactionError("Item resource normalization must be callable")
        return normalize_item(method(resource))

    def get_storage_ids(self, slots=None):
        self._check()
        selected = self.slots if slots is None else _slots(slots, self.slots)
        method = getattr(self.handler, "get_storage_ids", None)
        # Opaque endpoints retain every identity rather than inventing sub-stores.
        return method(selected) if method is not None else self.handler.storage_ids

    @property
    def storage_ids(self):
        return self.get_storage_ids()

    def get_slots(self):
        self._check()
        self.handler.get_slots()
        return self.slots

    def _slot(self, slot):
        if isinstance(slot, bool) or not isinstance(slot, integer_types) or slot not in self.slots:
            raise KeyError(slot)

    def get_resource(self, slot, tx=None):
        self._check(tx)
        self._slot(slot)
        return self.handler.get_resource(slot, tx)

    def get_amount(self, slot, tx=None):
        self._check(tx)
        self._slot(slot)
        return self.handler.get_amount(slot, tx)

    def get_capacity(self, slot, resource=None):
        self._check()
        self._slot(slot)
        if resource is not None:
            resource = normalize_item(resource)
            if not self.is_valid(slot, resource):
                return 0
        return self.handler.get_capacity(slot, resource)

    def is_valid(self, slot, resource):
        self._check()
        resource = normalize_item(resource)
        return (not isinstance(slot, bool) and isinstance(slot, integer_types)
                and slot in self.slots and slot in self.input_slots
                and (self.accepts is None or self.accepts(slot, resource))
                and self.handler.is_valid(slot, resource))

    def _transfer(self, resource, amount, tx, slot, inserting):
        resource = normalize_item(resource)
        amount = item_amount(amount)
        self._check(tx)
        selected = tuple(self.input_slots if inserting else self.output_slots)
        visible = tuple(self.slots)
        if slot is not None:
            if isinstance(slot, bool) or not isinstance(slot, integer_types):
                raise ValueError("Item slot must be an integer")
            if slot not in visible or slot not in selected:
                return 0
        if amount == 0:
            return 0
        bulk = ((self.bulk_insert if inserting else self.bulk_extract)
                and selected == visible and visible == tuple(self.handler.get_slots()))
        operation = self.handler.insert if inserting else self.handler.extract
        with tx.manager.open(tx) as work:
            work.guard(lambda: tuple(self.slots) == visible and tuple(
                self.input_slots if inserting else self.output_slots) == selected)
            if slot is None and bulk and (not inserting or self.accepts is None):
                work.guard(lambda: (self.bulk_insert if inserting else self.bulk_extract)
                           and tuple(self.handler.get_slots()) == visible
                           and (not inserting or self.accepts is None))
                moved = item_amount(operation(resource, amount, work))
                if moved > amount:
                    raise TransactionError("Delegate exceeded requested item amount")
                if moved:
                    work.commit()
                return moved
            total = 0
            for index in selected if slot is None else (slot,):
                if index not in visible or (inserting and not self.is_valid(index, resource)):
                    continue
                with tx.manager.open(work) as attempt:
                    attempt.guard(lambda i=index: i in self.slots and i in (
                        self.input_slots if inserting else self.output_slots))
                    if inserting:
                        attempt.guard(lambda i=index: self.is_valid(i, resource))
                    moved = item_amount(operation(resource, amount - total, attempt, index))
                    if moved > amount - total:
                        raise TransactionError("Delegate exceeded requested item amount")
                    if moved:
                        attempt.commit()
                        total += moved
                if total == amount:
                    break
            if total:
                work.commit()
            return total

    def insert(self, resource, amount, tx, slot=None):
        return self._transfer(resource, amount, tx, slot, True)

    def extract(self, resource, amount, tx, slot=None):
        return self._transfer(resource, amount, tx, slot, False)


def item_view(handler, slots=None, input_slots=None, output_slots=None,
              valid=None, accepts=None):
    return ItemView(handler, slots, input_slots, output_slots, valid, accepts)
