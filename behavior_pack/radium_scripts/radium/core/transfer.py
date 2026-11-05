# coding=utf-8
"""Explicit ordered scheduling; never owns a network or schedules game ticks."""
from .transaction import TransactionError
from .values import energy_amount, fluid_amount, exact_fluid_sum
from .resource import normalize_fluid


def _distribute(source, targets, amount, tx, extract, insert, validate=energy_amount):
    tx.check()
    if source.manager is not tx.manager:
        raise TransactionError("Source belongs to a different manager")
    targets = tuple(targets)
    if any(target.manager is not tx.manager for target in targets):
        raise TransactionError("Target belongs to a different manager")
    # Probe in an aborted child. No persistent writes or notifications.
    with tx.manager.open(tx) as probe:
        offered = validate(extract(source, amount, probe))
    if offered < 0 or offered > amount:
        raise TransactionError("Handler returned an invalid extraction amount")
    if offered <= 0:
        return 0
    with tx.manager.open(tx) as work:
        remaining = offered
        moved = 0.0 if validate is fluid_amount else 0
        seen = set(source.storage_ids)
        for target in targets:
            # Shared controller ports and overlapping combined handlers are aliases.
            if seen.intersection(target.storage_ids):
                continue
            seen.update(target.storage_ids)
            with tx.manager.open(work) as attempt:
                accepted = validate(insert(target, remaining, attempt))
                if accepted < 0 or accepted > remaining:
                    raise TransactionError("Handler returned an invalid insertion amount")
                total = (exact_fluid_sum(moved, accepted) if validate is fluid_amount
                         else moved + accepted)
                if total is None or total > offered:
                    continue
                attempt.commit()
                moved = total
                remaining = offered - moved
            if moved == offered:
                break
        if moved > 0:
            taken = validate(extract(source, moved, work))
            if taken != moved:
                raise TransactionError("Source changed its offer during transfer")
            work.commit()
        return moved


def distribute_energy(source, targets, amount, tx):
    amount = energy_amount(amount)
    return _distribute(source, targets, amount, tx,
                       lambda h, n, t: h.extract(n, t),
                       lambda h, n, t: h.insert(n, t))


def move_energy(source, target, amount, tx):
    return distribute_energy(source, (target,), amount, tx)


def distribute_fluid(source, targets, fluid_id, amount, tx):
    fluid_id = normalize_fluid(fluid_id)
    amount = fluid_amount(amount)
    return _distribute(source, targets, amount, tx,
                       lambda h, n, t: h.extract(fluid_id, n, t),
                       lambda h, n, t: h.insert(fluid_id, n, t), fluid_amount)


def move_fluid(source, target, fluid_id, amount, tx):
    return distribute_fluid(source, (target,), fluid_id, amount, tx)
