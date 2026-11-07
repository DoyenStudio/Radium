# coding=utf-8
"""Quantized endpoint protocol regressions; run only in the game interpreter."""
import traceback
from radium_scripts.radium.core.service import TransferService
from radium_scripts.radium.core.transaction import TransactionError
from radium_scripts.radium.core.fluid import FluidHandler
from radium_scripts.radium.core.values import fluid_amount
from radium_scripts.radium.core.resource import normalize_fluid

WATER = "minecraft:water"
LAVA = "minecraft:lava"
LEVELS = (0, 167, 333, 500, 667, 833, 1000)


def service():
    return TransferService(lambda d, p: True, lambda d, p: "example:pot",
                           report=lambda message: None)


def expect(error, action):
    try:
        action()
    except error:
        return
    raise AssertionError("Expected %s" % error.__name__)


class QuantizedTank(FluidHandler):
    """Independent in-memory fixture using the same public endpoint protocol."""
    def __init__(self, api, amount=1000, resource=WATER, on_extract=None):
        self.levels = LEVELS if resource == WATER else (0, 1000)
        self.resource = resource
        self.on_extract = on_extract
        cell = api.create_cell((resource if amount else None, float(amount)))
        super(QuantizedTank, self).__init__({0: cell}, lambda slot: 1000)

    def extraction_candidates(self, resource, amount, tx, slots=None):
        tx.check()
        tx.guard(self.valid)
        current, stored = self._read(0, tx)
        if (slots is not None and 0 not in slots) or current != resource:
            return ()
        return tuple(stored - level for level in self.levels
                     if 0 < stored - level <= amount)

    def extract(self, resource, amount, tx, slot=None):
        resource = normalize_fluid(resource)
        amount = fluid_amount(amount)
        choices = self.extraction_candidates(resource, amount, tx,
                                              None if slot is None else (slot,))
        if not choices:
            return 0.0
        moved = super(QuantizedTank, self).extract(resource, choices[0], tx, slot)
        tx.record((self, "extract"), self.on_extract, moved)
        return moved

    def insert(self, resource, amount, tx, slot=None):
        resource = normalize_fluid(resource)
        amount = fluid_amount(amount)
        if resource != self.resource or slot not in (None, 0):
            return 0.0
        current, stored = self._read(0, tx)
        choices = [level - stored for level in self.levels
                   if 0 < level - stored <= amount]
        if not choices:
            return 0.0
        return super(QuantizedTank, self).insert(resource, max(choices), tx, slot)


def test_all_water_level_pairs_choose_largest_common_change():
    for source_amount in LEVELS:
        for target_amount in LEVELS:
            api = service()
            source = QuantizedTank(api, source_amount)
            target = QuantizedTank(api, target_amount)
            common = set(source_amount - n for n in LEVELS if n < source_amount)
            common.intersection_update(n - target_amount for n in LEVELS if n > target_amount)
            expected = max(common) if common else 0
            with api.open_transaction() as tx:
                assert api.move_fluid(source, target, WATER, 1000, tx) == expected
                tx.commit()
            assert source.get_amount(0) == source_amount - expected
            assert target.get_amount(0) == target_amount + expected


def test_partial_target_rounds_down_without_leaving_failed_attempts():
    api = service()
    source = QuantizedTank(api)
    target = api.create_fluid_storage({0: 600})
    with api.open_transaction() as tx:
        assert api.move_fluid(source, target, WATER, 1000, tx) == 500
        tx.commit()
    assert source.get_amount(0) == target.get_amount(0) == 500


def test_too_small_target_and_budget_return_zero():
    api = service()
    source = QuantizedTank(api)
    tiny = api.create_fluid_storage({0: 100})
    large = api.create_fluid_storage({0: 1000})
    with api.open_transaction() as tx:
        assert api.move_fluid(source, tiny, WATER, 1000, tx) == 0
        assert api.move_fluid(source, large, WATER, 166, tx) == 0
        assert tiny.get_amount(0, tx) == large.get_amount(0, tx) == 0
        tx.commit()
    assert source.get_amount(0) == 1000


def test_ordered_multiple_targets_and_aliases_share_one_quantum():
    api = service()
    source = QuantizedTank(api)
    first = api.create_fluid_storage({0: 100})
    second = api.create_fluid_storage({0: 67})
    with api.open_transaction() as tx:
        assert api.distribute_fluid(source, (source, first, first, second), WATER, 1000, tx) == 167
        tx.commit()
    assert source.get_amount(0) == 833
    assert first.get_amount(0) == 100 and second.get_amount(0) == 67


def test_lava_requires_complete_bucket_in_both_directions():
    for request, capacity, expected in ((999, 1000, 0), (1000, 1000, 1000),
                                         (1001, 1000, 1000), (1000, 999, 0)):
        api = service()
        source = QuantizedTank(api, resource=LAVA)
        target = api.create_fluid_storage({0: capacity})
        with api.open_transaction() as tx:
            assert api.move_fluid(source, target, LAVA, request, tx) == expected
            tx.commit()
        assert source.get_amount(0) == 1000 - expected
        assert target.get_amount(0) == expected
    api = service()
    source = api.create_fluid_storage({0: 1000})
    target = QuantizedTank(api, amount=0, resource=LAVA)
    with api.open_transaction() as tx:
        source.insert(LAVA, 1000, tx)
        assert api.move_fluid(source, target, LAVA, 500, tx) == 0
        assert api.move_fluid(source, target, LAVA, 1000, tx) == 1000
        tx.commit()
    assert target.get_amount(0) == 1000


def test_nested_abort_and_retries_emit_only_committed_effects():
    api = service()
    events = []
    source = QuantizedTank(api, on_extract=events.append)
    target = api.create_fluid_storage({0: 600})
    with api.open_transaction() as root:
        with api.open_transaction(root) as child:
            assert api.move_fluid(source, target, WATER, 1000, child) == 500
            child.commit()
        assert events == []
    assert source.get_amount(0) == 1000 and target.get_amount(0) == 0
    with api.open_transaction() as tx:
        assert api.move_fluid(source, target, WATER, 1000, tx) == 500
        tx.commit()
    assert events == [500]


def test_quote_probe_cannot_leave_staged_mutation_or_effects():
    api = service()
    events = []
    source = QuantizedTank(api, on_extract=events.append)
    target = api.create_fluid_storage({0: 1000})
    original_quote = source.extraction_candidates

    class QuotedSource(object):
        manager = source.manager
        storage_ids = source.storage_ids

        def extraction_candidates(self, resource, amount, tx):
            candidates = original_quote(resource, amount, tx)
            tx.write(source.cells[0], (None, 0.0))
            tx.record("bad_quote", events.append, 123)
            return candidates

        def extract(self, resource, amount, tx):
            return source.extract(resource, amount, tx)

    with api.open_transaction() as tx:
        assert api.move_fluid(QuotedSource(), target, WATER, 1000, tx) == 1000
        tx.commit()
    assert target.get_amount(0) == 1000 and events == [1000]


def test_invalid_candidates_are_transaction_errors_without_mutation():
    invalid = ([1000], (0,), (-1,), (167, 333), (500, 500), (1001,),
               (True,), (float("nan"),), (float("inf"),), ("500",))
    for candidates in invalid:
        api = service()
        source = QuantizedTank(api)
        target = api.create_fluid_storage({0: 1000})
        source.extraction_candidates = lambda r, n, t, values=candidates: values
        with api.open_transaction() as tx:
            expect(TransactionError, lambda: api.move_fluid(source, target, WATER, 1000, tx))
            assert source.get_amount(0, tx) == 1000 and target.get_amount(0, tx) == 0
            tx.commit()


def test_unfulfillable_candidate_is_not_treated_as_capacity_shortage():
    api = service()
    source = QuantizedTank(api)
    target = api.create_fluid_storage({0: 1000})
    source.extract = lambda r, n, t: 0.0
    with api.open_transaction() as tx:
        expect(TransactionError, lambda: api.move_fluid(source, target, WATER, 1000, tx))
        assert target.get_amount(0, tx) == 0
        tx.commit()


def test_views_and_query_proxies_preserve_candidate_permissions():
    api = service()
    source = QuantizedTank(api)
    api.register_provider(api.FLUID, "example:pot", lambda d, p, f: source)
    proxy = api.query(api.FLUID, 0, (0, 0, 0), 1)
    view = api.fluid_view(api.fluid_view(proxy, slots=(0,)))
    denied = api.fluid_view(view, output_slots=())
    target = api.create_fluid_storage({0: 1000})
    with api.open_transaction() as tx:
        assert proxy.extraction_candidates(WATER, 200, tx) == (167,)
        assert view.extraction_candidates(WATER, 1000, tx, slots=()) == ()
        assert denied.extraction_candidates(WATER, 1000, tx) == ()
        assert api.move_fluid(denied, target, WATER, 1000, tx) == 0
        assert api.move_fluid(view, target, WATER, 200, tx) == 167
        api.invalidate()
        expect(TransactionError, tx.commit)
    assert source.get_amount(0) == 1000 and target.get_amount(0) == 0


def test_view_candidates_guard_output_permissions_until_commit():
    api = service()
    source = QuantizedTank(api)
    view = api.fluid_view(source, slots=(0,))
    with api.open_transaction() as tx:
        assert view.extraction_candidates(WATER, 200, tx) == (167,)
        view.output_slots = ()
        expect(TransactionError, tx.commit)


def test_candidate_retry_does_not_assume_monotonic_target_acceptance():
    api = service()
    source = QuantizedTank(api)
    target = api.create_fluid_storage({0: 1000})

    class SelectiveTarget(object):
        manager = target.manager
        storage_ids = target.storage_ids

        def insert(self, resource, amount, tx):
            # First round accepts 100, but the later 333 candidate is feasible.
            accepted = 100 if amount == 1000 else (333 if amount == 333 else 0)
            return target.insert(resource, accepted, tx)

    with api.open_transaction() as tx:
        assert api.move_fluid(source, SelectiveTarget(), WATER, 1000, tx) == 333
        tx.commit()
    assert source.get_amount(0) == 667 and target.get_amount(0) == 333


def test_none_candidates_keep_ordinary_float_failure_contract():
    api = service()
    huge = float(2 ** 54)
    source = api.create_fluid_storage({0: huge})
    source.extraction_candidates = lambda r, n, t: None
    tiny = api.create_fluid_storage({0: 1})
    big = api.create_fluid_storage({0: huge})
    with api.open_transaction() as tx:
        source.insert(WATER, huge, tx)
        tx.commit()
    with api.open_transaction() as tx:
        expect(TransactionError, lambda: api.distribute_fluid(source, (tiny, big), WATER, huge, tx))
        assert tiny.get_amount(0, tx) == big.get_amount(0, tx) == 0
        tx.commit()
    assert source.get_amount(0) == huge


def test_narrowed_visible_slots_do_not_restore_bulk_extraction():
    for narrow_outputs in (False, True):
        api = service()
        source = api.create_fluid_storage({0: 1000, 1: 1000})
        target = api.create_fluid_storage({0: 1000})
        quoted_slots = []

        def candidates(resource, amount, tx, slots=None):
            selected = source.get_slots() if slots is None else slots
            quoted_slots.append(tuple(selected))
            available = sum(source.get_amount(slot, tx) for slot in selected)
            offered = min(amount, available)
            return (offered,) if offered else ()

        source.extraction_candidates = candidates
        with api.open_transaction() as tx:
            source.insert(WATER, 1000, tx, slot=0)
            source.insert(WATER, 1000, tx, slot=1)
            tx.commit()
        view = api.fluid_view(source)
        view.slots = (1,)
        if narrow_outputs:
            view.output_slots = (1,)
        with api.open_transaction() as tx:
            assert api.move_fluid(view, target, WATER, 1000, tx) == 1000
            tx.commit()
        assert quoted_slots == [(1,)]
        assert source.get_amount(0) == 1000 and source.get_amount(1) == 0
        assert target.get_amount(0) == 1000


def test_view_visibility_change_after_transfer_invalidates_commit():
    api = service()
    source = QuantizedTank(api)
    target = api.create_fluid_storage({0: 1000})
    view = api.fluid_view(source)
    with api.open_transaction() as tx:
        assert api.move_fluid(view, target, WATER, 167, tx) == 167
        view.slots = ()
        expect(TransactionError, tx.commit)
    assert source.get_amount(0) == 1000 and target.get_amount(0) == 0


def test_noncallable_candidates_remain_transaction_errors_through_wrappers():
    api = service()
    source = QuantizedTank(api)
    source.extraction_candidates = 7
    target = api.create_fluid_storage({0: 1000})
    api.register_provider(api.FLUID, "example:pot", lambda d, p, f: source)
    proxy = api.query(api.FLUID, 0, (0, 0, 0))
    wrappers = (source, proxy, api.fluid_view(source), api.fluid_view(proxy))
    with api.open_transaction() as tx:
        for handler in wrappers:
            expect(TransactionError, lambda h=handler:
                   api.move_fluid(h, target, WATER, 1000, tx))
        assert source.get_amount(0, tx) == 1000 and target.get_amount(0, tx) == 0
        tx.commit()


def run():
    cases = sorted((name, value) for name, value in globals().items()
                   if name.startswith("test_") and callable(value))
    passed, failed = [], {}
    for name, case in cases:
        try:
            case()
            passed.append(name)
        except Exception:
            failed[name] = traceback.format_exc()
    return {"passed": passed, "failed": failed, "total": len(cases), "ok": not failed}
