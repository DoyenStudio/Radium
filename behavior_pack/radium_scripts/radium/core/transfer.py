# coding=utf-8
"""Explicit ordered scheduling; never owns a network or schedules game ticks."""
from .transaction import TransactionError
from .values import energy_amount, fluid_amount, exact_fluid_sum
from .resource import normalize_fluid


def _candidates(values, amount):
    if values is None:
        return None
    if not isinstance(values, tuple):
        raise TransactionError("Extraction candidates must be a finite tuple")
    result = []
    previous = None
    for value in values:
        try:
            value = fluid_amount(value)
        except (TypeError, ValueError, OverflowError):
            raise TransactionError("Invalid extraction candidate")
        if value <= 0 or value > amount or (previous is not None and value >= previous):
            raise TransactionError("Extraction candidates must be positive and decreasing")
        result.append(value)
        previous = value
    return tuple(result)


def _distribute(source, targets, amount, tx, extract, insert, validate=energy_amount,
                quote=None):
    tx.check()
    if source.manager is not tx.manager:
        raise TransactionError("Source belongs to a different manager")
    targets = tuple(targets)
    if any(target.manager is not tx.manager for target in targets):
        raise TransactionError("Target belongs to a different manager")
    candidates = None
    if quote is not None:
        # Even a misbehaving quote cannot leave staged writes or notifications.
        with tx.manager.open(tx) as probe:
            candidates = _candidates(quote(amount, probe), amount)
    if candidates is None:
        with tx.manager.open(tx) as probe:
            offered = validate(extract(source, amount, probe))
        if offered < 0 or offered > amount:
            raise TransactionError("Handler returned an invalid extraction amount")
        if offered <= 0:
            return 0
        return _distribute_attempt(source, targets, offered, tx, extract, insert, validate)
    allowed = frozenset(candidates)
    for offered in candidates:
        with tx.manager.open(tx) as probe:
            taken = validate(extract(source, offered, probe))
        if taken != offered:
            raise TransactionError("Source cannot fulfill its extraction candidate")
        moved = _distribute_attempt(source, targets, offered, tx, extract, insert,
                                    validate, allowed)
        if moved:
            return moved
    return 0.0


def _distribute_attempt(source, targets, offered, tx, extract, insert, validate,
                        allowed=None):
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
        if allowed is not None and moved not in allowed:
            return 0.0
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
    method = getattr(source, "extraction_candidates", None)
    if method is not None and not callable(method):
        raise TransactionError("Extraction candidates must be callable")
    quote = (None if method is None else
             lambda n, t: method(fluid_id, n, t))
    return _distribute(source, targets, amount, tx,
                       lambda h, n, t: h.extract(fluid_id, n, t),
                       lambda h, n, t: h.insert(fluid_id, n, t), fluid_amount, quote)


def move_fluid(source, target, fluid_id, amount, tx):
    return distribute_fluid(source, (target,), fluid_id, amount, tx)
