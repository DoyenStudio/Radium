# coding=utf-8
from ..core.item import ItemHandler
from ..core.item_resource import item_amount
from . import item_codec, rules


class NativeItemHandler(ItemHandler):
    def __init__(self, owner, face):
        self.owner = owner
        self.kind = owner.backend.kind
        self.basic_info = owner.backend.engine.basic_info
        inputs, outputs = rules.ports(self.kind, face)
        if self.kind not in ("furnace", "brewing"):
            inputs = outputs = tuple(owner.cells)
        super(NativeItemHandler, self).__init__(owner.cells,
            lambda slot: 1 if self.kind == "brewing" and slot in (1, 2, 3) else 64,
            lambda resource: self.basic_info(resource.item_id, resource.aux)["maxStackSize"],
            inputs, outputs, self._accepts, owner.valid)

    def _accepts(self, slot, resource):
        return rules.accepts(self.kind, slot, resource, self.basic_info(resource.item_id, resource.aux))

    def normalize_resource(self, resource):
        self.manager.assert_access()
        self._check()
        return item_codec.canonical(resource, self.basic_info)

    def is_valid(self, slot, resource):
        resource = item_codec.canonical(resource, self.basic_info)
        return super(NativeItemHandler, self).is_valid(slot, resource)

    def insert(self, resource, amount, tx, slot=None):
        resource = item_codec.canonical(resource, self.basic_info)
        return super(NativeItemHandler, self).insert(resource, amount, tx, slot)

    def extract(self, resource, amount, tx, slot=None):
        resource = item_codec.canonical(resource, self.basic_info)
        amount = item_amount(amount)
        self._check(tx)
        if slot is not None:
            self._slot(slot)
        total = 0
        for index in self.output_slots if slot is None else (slot,):
            if index not in self.output_slots or not rules.allows_extract(self.kind, index, resource):
                continue
            tx.guard(lambda i=index: rules.allows_extract(self.kind, i, resource))
            total += super(NativeItemHandler, self).extract(resource, amount - total, tx, index)
            if total == amount:
                break
        return total
