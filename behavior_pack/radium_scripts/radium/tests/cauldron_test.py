# coding=utf-8
"""Isolated cauldron tests; execute only in the game's Python 2.7.13."""
import traceback
from radium_scripts.radium.core.service import TransferService
from radium_scripts.radium.core.transaction import Cell, TransactionError, TransactionManager
from radium_scripts.radium.core.resource import fluid_resource
from radium_scripts.radium.vanilla.cauldron import CauldronHandler, WATER, LAVA, LEVEL_AMOUNTS


def expect(errors, action):
    try:
        action()
    except errors:
        return
    raise AssertionError("Expected %r" % (errors,))


def cauldron(manager, level=0, resource=WATER, **kwargs):
    state = (resource, level) if level else (None, 0)
    return CauldronHandler(Cell(manager, state), **kwargs)


def test_cauldron_water_all_level_transitions_are_exact_and_abortable():
    manager = TransactionManager()
    for start in range(7):
        for end in range(7):
            handler = cauldron(manager, start)
            original = handler.cell.get()
            requested = abs(LEVEL_AMOUNTS[end] - LEVEL_AMOUNTS[start])
            with manager.open() as tx:
                operation = handler.insert if end >= start else handler.extract
                assert operation(WATER, requested, tx) == requested
                assert handler.get_amount(0, tx) == LEVEL_AMOUNTS[end]
                assert handler.get_resource(0, tx) == (WATER if end else None)
                assert handler.cell.get() == original
            assert handler.cell.get() == original


def test_cauldron_water_each_quantum_totals_exactly_one_bucket():
    manager = TransactionManager()
    handler = cauldron(manager)
    inserted = extracted = 0.0
    for level in range(1, 7):
        delta = LEVEL_AMOUNTS[level] - LEVEL_AMOUNTS[level - 1]
        with manager.open() as tx:
            assert handler.insert(WATER, delta - 0.25, tx) == 0.0
            inserted += handler.insert(WATER, delta, tx)
            tx.commit()
        assert handler.get_amount(0) == LEVEL_AMOUNTS[level]
    for level in range(6, 0, -1):
        delta = LEVEL_AMOUNTS[level] - LEVEL_AMOUNTS[level - 1]
        with manager.open() as tx:
            assert handler.extract(WATER, delta - 0.25, tx) == 0.0
            extracted += handler.extract(WATER, delta, tx)
            tx.commit()
    assert inserted == extracted == 1000.0
    assert handler.cell.get() == (None, 0)


def test_cauldron_partial_requests_choose_largest_reachable_level():
    manager = TransactionManager()
    handler = cauldron(manager)
    with manager.open() as tx:
        assert handler.insert(WATER, 600.0, tx) == 500.0
        assert handler.insert(WATER, 499.0, tx) == 333.0
        assert handler.get_amount(0, tx) == 833.0
        assert handler.extract(WATER, 332.0, tx) == 166.0
        assert handler.get_amount(0, tx) == 667.0
        assert handler.extract(WATER, 9999.0, tx) == 667.0
        tx.commit()
    assert handler.get_amount(0) == 0.0


def test_cauldron_lava_requires_full_bucket_in_both_directions():
    manager = TransactionManager()
    handler = cauldron(manager)
    with manager.open() as tx:
        assert handler.insert(LAVA, 999.0, tx) == 0.0
        assert handler.insert(LAVA, 1001.0, tx) == 1000.0
        assert handler.insert(LAVA, 1000.0, tx) == 0.0
        assert handler.get_amount(0, tx) == 1000.0
        assert handler.extraction_candidates(LAVA, 999.0, tx) == ()
        assert handler.extraction_candidates(LAVA, 1001.0, tx) == (1000.0,)
        assert handler.extract(LAVA, 999.0, tx) == 0.0
        assert handler.extract(LAVA, 1000.0, tx) == 1000.0
        assert handler.cell.get() == (None, 0)
        tx.commit()
    assert handler.cell.get() == (None, 0)


def test_cauldron_does_not_mix_liquids_or_accept_resource_properties():
    manager = TransactionManager()
    handler = cauldron(manager, 3)
    dyed = fluid_resource(WATER, {"color": "red"})
    assert not handler.is_valid(0, dyed)
    assert handler.get_capacity(0, dyed) == 0.0
    assert handler.is_valid(0, WATER) and handler.is_valid(0, LAVA)
    with manager.open() as tx:
        for resource in (dyed, "example:oil", LAVA):
            assert handler.insert(resource, 1000.0, tx) == 0.0
            assert handler.extract(resource, 1000.0, tx) == 0.0
            assert handler.extraction_candidates(resource, 1000.0, tx) == ()
        assert handler.extract(WATER, 1000.0, tx) == 500.0
        assert handler.insert(LAVA, 1000.0, tx) == 1000.0
        assert handler.insert(WATER, 1000.0, tx) == 0.0
        tx.commit()
    assert handler.cell.get() == (LAVA, 6)


def test_cauldron_candidate_quantities_are_complete_ordered_and_read_only():
    manager = TransactionManager()
    for level in range(7):
        handler = cauldron(manager, level)
        for requested in (0.0, 100.0, 166.0, 167.0, 500.0, 999.0, 1000.0, 1200.0):
            with manager.open() as tx:
                expected = tuple(float(LEVEL_AMOUNTS[level] - LEVEL_AMOUNTS[end])
                                 for end in range(level)
                                 if LEVEL_AMOUNTS[level] - LEVEL_AMOUNTS[end] <= requested)
                before = handler.cell.get()
                assert handler.extraction_candidates(WATER, requested, tx) == expected
                assert handler.extraction_candidates(WATER, requested, tx, (0,)) == expected
                assert handler.extraction_candidates(WATER, requested, tx, ()) == ()
                assert handler.extraction_candidates(WATER, requested, tx, (1,)) == ()
                assert handler.cell.get() == before
                assert handler.get_amount(0, tx) == LEVEL_AMOUNTS[level]
                assert not tx.effects


def test_cauldron_single_slot_identity_survives_multiple_views():
    api = TransferService(lambda d, p: True, lambda d, p: "minecraft:cauldron")
    handler = cauldron(api.manager, 6)
    assert handler.get_slots() == (0,)
    assert handler.get_capacity(0) == 1000.0
    assert handler.get_storage_ids(()) == frozenset()
    assert handler.storage_ids == frozenset((handler.cell,))
    assert handler.get_storage_ids((0,)) == handler.storage_ids
    assert not handler.is_valid(1, WATER)
    expect(KeyError, lambda: handler.get_amount(1))
    expect(KeyError, lambda: handler.get_capacity(1))
    left = api.fluid_view(handler)
    right = api.fluid_view(handler, (0,))
    assert left.storage_ids == right.storage_ids == handler.storage_ids
    with api.open_transaction() as tx:
        assert handler.insert(WATER, 1000, tx, 1) == 0.0
        assert handler.extract(WATER, 1000, tx, 1) == 0.0
        assert api.move_fluid(left, right, WATER, 1000, tx) == 0.0
        tx.commit()
    assert handler.get_amount(0) == 1000.0


def test_cauldron_nested_abort_does_not_publish_level_changes():
    manager = TransactionManager()
    handler = cauldron(manager, 6)
    with manager.open() as tx:
        with manager.open(tx) as child:
            assert handler.extract(WATER, 500.0, child) == 500.0
            child.commit()
        assert handler.get_amount(0, tx) == 500.0
        with manager.open(tx) as abandoned:
            assert handler.extract(WATER, 500.0, abandoned) == 500.0
        assert handler.get_amount(0, tx) == 500.0
        assert handler.cell.get() == (WATER, 6)
    assert handler.cell.get() == (WATER, 6)


def test_cauldron_invalid_native_states_are_rejected_without_coercion():
    manager = TransactionManager()
    for state in ((None, 1), (WATER, 0), (WATER, -1), (WATER, 7),
                  (WATER, True), (WATER, 1.0), (LAVA, 3), ("example:oil", 6),
                  (fluid_resource(WATER, {"potion": True}), 2), (WATER,), None):
        handler = CauldronHandler(Cell(manager, state))
        expect(TransactionError, lambda: handler.get_amount(0))
        with manager.open() as tx:
            expect(TransactionError, lambda: handler.extract(WATER, 1000.0, tx))
        assert handler.cell.get() == state


def test_cauldron_amount_validation_and_manager_ownership():
    manager = TransactionManager()
    handler = cauldron(manager, 6)
    with manager.open() as tx:
        for amount in (-1, True, False, float("inf"), float("nan"), "1000"):
            expect((TypeError, ValueError), lambda: handler.insert(WATER, amount, tx))
            expect((TypeError, ValueError), lambda: handler.extract(WATER, amount, tx))
            expect((TypeError, ValueError), lambda: handler.extraction_candidates(WATER, amount, tx))
        assert handler.get_amount(0, tx) == 1000.0
    other = TransactionManager()
    with other.open() as tx:
        expect(TransactionError, lambda: handler.extract(WATER, 1000.0, tx))
        expect(TransactionError, lambda: handler.extraction_candidates(WATER, 1000.0, tx))


def test_cauldron_lifecycle_change_and_external_content_conflict_abort():
    manager = TransactionManager()
    available = [True]
    handler = cauldron(manager, 6, valid=lambda: available[0])
    with manager.open() as tx:
        assert handler.extract(WATER, 500.0, tx) == 500.0
        available[0] = False
        expect(TransactionError, tx.commit)
    assert handler.cell.get() == (WATER, 6)
    expect(TransactionError, lambda: handler.get_amount(0))
    available[0] = True
    with manager.open() as tx:
        assert handler.extract(WATER, 500.0, tx) == 500.0
        handler.cell.state = (LAVA, 6)
        expect(TransactionError, tx.commit)
    assert handler.cell.get() == (LAVA, 6)


def run():
    cases = sorted((name, value) for name, value in globals().items()
                   if name.startswith("test_") and callable(value))
    passed = []
    failed = {}
    for name, case in cases:
        try:
            case()
            passed.append(name)
        except Exception:
            failed[name] = traceback.format_exc()
    return {"passed": passed, "failed": failed, "total": len(cases), "ok": not failed}
