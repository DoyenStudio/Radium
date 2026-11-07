# coding=utf-8
"""Transactional item movement and an explicit existing-stack-first helper."""
from .item_resource import normalize_item, item_amount
from .transaction import TransactionError
from .transfer import _distribute
from .values import integer_types


def distribute_item(source, targets, resource, amount, tx):
    resource = normalize_item(resource)
    amount = item_amount(amount)
    return _distribute(source, targets, amount, tx,
                       lambda handler, count, attempt: handler.extract(resource, count, attempt),
                       lambda handler, count, attempt: handler.insert(resource, count, attempt),
                       item_amount)


def move_item(source, target, resource, amount, tx):
    return distribute_item(source, (target,), resource, amount, tx)


def insert_item_stacking(handler, resource, amount, tx):
    """Fill matching nonempty slots before empty slots; return the accepted count."""
    resource = normalize_item(resource)
    amount = item_amount(amount)
    tx.check()
    if handler.manager is not tx.manager:
        raise TransactionError("Item handler belongs to a different manager")
    if amount == 0:
        return 0
    normalize = getattr(handler, "normalize_resource", None)
    if normalize is not None:
        if not callable(normalize):
            raise TransactionError("Item resource normalization must be callable")
        # A native endpoint can expose its lossless native representation before
        # the existing-stack comparison. Do not change ordinary item identities.
        with tx.manager.open(tx) as probe:
            resource = normalize_item(normalize(resource))
    with tx.manager.open(tx) as work:
        slots = tuple(handler.get_slots())
        if (any(isinstance(slot, bool) or not isinstance(slot, integer_types)
                or slot < 0 for slot in slots) or len(set(slots)) != len(slots)):
            raise TransactionError("Item handler returned invalid slot IDs")
        total = 0
        for empty in (False, True):
            for slot in slots:
                stored = item_amount(handler.get_amount(slot, work))
                if empty:
                    if stored != 0:
                        continue
                elif stored == 0 or handler.get_resource(slot, work) != resource:
                    continue
                with tx.manager.open(work) as attempt:
                    moved = item_amount(handler.insert(resource, amount - total, attempt, slot))
                    if moved > amount - total:
                        raise TransactionError("Handler exceeded requested item amount")
                    if moved:
                        attempt.commit()
                        total += moved
                if total == amount:
                    break
            if total == amount:
                break
        if total:
            work.commit()
        return total
