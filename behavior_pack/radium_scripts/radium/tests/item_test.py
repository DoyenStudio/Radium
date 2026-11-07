# coding=utf-8
"""Isolated item regressions; execute only in the game's Python 2.7.13."""
import math
import traceback
from radium_scripts.radium.core.service import TransferService
from radium_scripts.radium.core.transaction import TransactionError
from radium_scripts.radium.core.values import integer_types, string_types


def service():
    return TransferService(lambda d, p: True, lambda d, p: "example:machine",
                           report=lambda message: None)


def expect(errors, action):
    try:
        action()
    except errors:
        return
    raise AssertionError("Expected %r" % (errors,))


def seed(api, handler, resource, amount, slot=None):
    with api.open_transaction() as tx:
        assert handler.insert(resource, amount, tx, slot) == amount
        tx.commit()


def assert_native_snapshot(value):
    if isinstance(value, dict):
        assert all(isinstance(key, string_types) for key in value)
        for child in value.values():
            assert_native_snapshot(child)
    elif isinstance(value, list):
        assert not value or all(type(child) is type(value[0]) for child in value)
        for child in value:
            assert_native_snapshot(child)
    elif isinstance(value, bool) or value is None or isinstance(value, string_types):
        return
    elif isinstance(value, integer_types):
        assert type(value) is int and -2147483648 <= value <= 2147483647
    elif isinstance(value, float):
        assert not math.isnan(value) and not math.isinf(value)
    else:
        raise AssertionError("Non-native snapshot value: %r" % (value,))


def test_item_identity_detaches_metadata_and_ignores_count():
    api = service()
    stack = {"newItemName": "example:part", "newAuxValue": 3, "count": 2,
             "userData": {"nested": [True, 1, 1.0, None, {"mode": "a"}]},
             "durability": 17, "customTips": "kept"}
    resource = api.item_resource_from_stack(stack)
    other = dict(stack, count=30)
    assert resource == api.item_resource_from_stack(other)
    assert hash(resource) == hash(api.item_resource_from_stack(other))
    assert api.get_item_id(resource) == "example:part"
    assert api.get_item_aux(resource) == 3
    stack["userData"]["nested"][4]["mode"] = "changed"
    properties = api.get_item_properties(resource)
    assert properties["userData"]["nested"][4]["mode"] == "a"
    properties["userData"]["nested"].append("changed")
    restored = api.item_stack(resource, 7)
    assert restored["count"] == 7 and restored["durability"] == 17
    assert restored["customTips"] == "kept"
    assert restored["userData"]["nested"] == [True, 1, 1.0, None, {"mode": "a"}]
    assert resource != api.item_resource("example:part", 4, api.get_item_properties(resource))
    assert api.item_resource("example:part", properties={"value": 1}) != api.item_resource(
        "example:part", properties={"value": True})


def test_item_stack_aliases_and_empty_boundaries():
    api = service()
    old = {"itemName": "example:part", "auxValue": 2, "count": 4,
           "userData": {"custom": "value"}}
    new = {"newItemName": "example:part", "newAuxValue": 2, "count": 4,
           "userData": {"custom": "value"}}
    assert api.item_resource_from_stack(old) == api.item_resource_from_stack(new)
    assert api.item_stack(api.item_resource_from_stack(old), 4) == new
    assert api.item_resource_from_stack(None) is None
    assert api.item_resource_from_stack({}) is None
    assert api.item_resource_from_stack(dict(new, count=0)) is None
    assert api.item_stack(api.item_resource("example:part"), 0) is None
    for broken in (dict(new, itemName="example:other"),
                   dict(new, auxValue=9), dict(new, newItemName="minecraft:air")):
        expect((TypeError, ValueError), lambda value=broken: api.item_resource_from_stack(value))
    expect((TypeError, ValueError), lambda: api.item_stack(None, 1))
    expect((TypeError, ValueError), lambda: api.item_resource("example:part", properties={"count": 1}))


def test_item_native_enchantment_tuples_survive_snapshot():
    api = service()
    stack = {"newItemName": "example:tool", "newAuxValue": 0, "count": 1,
             "enchantData": [(9, 3), (15, 1)],
             "modEnchantData": [("example:custom", 2)]}
    item = api.item_resource_from_stack(stack)
    store = api.create_item_storage({0: 1}, 1)
    seed(api, store, item, 1)
    saved = api.save_item(store)
    assert_native_snapshot(saved)
    restored = api.create_item_storage({0: 1}, 1, saved=saved)
    assert api.item_stack(restored.get_resource(0), 1) == stack
    returned = api.item_stack(restored.get_resource(0), 1)
    returned["enchantData"].append((1, 1))
    assert api.item_stack(item, 1) == stack


def test_item_counts_reject_fractional_bool_and_nonfinite_values():
    api = service()
    item = api.item_resource("example:part")
    store = api.create_item_storage({0: 64}, 64)
    with api.open_transaction() as tx:
        for bad in (True, False, -1, 1.0, 0.25, float("inf"), float("nan"), "1"):
            expect((TypeError, ValueError), lambda value=bad: store.insert(item, value, tx))
            expect((TypeError, ValueError), lambda value=bad: store.extract(item, value, tx))
        assert store.get_amount(0, tx) == 0
        tx.commit()
    expect((TypeError, ValueError), lambda: api.create_item_storage({0: 64}, 1.5))


def test_item_nested_abort_keeps_committed_state_unchanged():
    api = service()
    item = api.item_resource("example:part")
    store = api.create_item_storage({0: 64}, 64)
    seed(api, store, item, 5)
    with api.open_transaction() as root:
        store.insert(item, 10, root)
        with api.open_transaction(root) as child:
            store.extract(item, 12, child)
        assert store.get_amount(0, root) == 15
        with api.open_transaction(root) as child:
            store.insert(item, 3, child)
            child.commit()
        assert store.get_amount(0, root) == 18
        assert store.get_amount(0) == 5
    assert store.get_amount(0) == 5
    with api.open_transaction() as tx:
        assert store.extract(item, 100, tx) == 5
        tx.commit()
    assert store.get_amount(0) == 0 and store.get_resource(0) is None


def test_item_partial_transfer_preserves_full_identity_and_remainder():
    api = service()
    tagged = api.item_resource("example:part", 2, {"userData": {"grade": 3}})
    different = api.item_resource("example:part", 2, {"userData": {"grade": 4}})
    source = api.create_item_storage({0: 64}, 64)
    target = api.create_item_storage({0: 10}, 64)
    seed(api, source, tagged, 20)
    seed(api, target, tagged, 8)
    with api.open_transaction() as tx:
        assert target.insert(different, 2, tx) == 0
        assert source.extract(different, 2, tx) == 0
        assert api.move_item(source, target, tagged, 20, tx) == 2
        tx.commit()
    assert source.get_amount(0) == 18 and target.get_amount(0) == 10
    assert source.get_resource(0) == target.get_resource(0) == tagged


def test_item_resource_stack_limits_and_slot_capacity_both_apply():
    api = service()
    tool = api.item_resource("example:tool")
    pearl = api.item_resource("example:pearl")
    limits = lambda resource: 1 if api.get_item_id(resource) == "example:tool" else 16
    store = api.create_item_storage({2: 64, 9: 12}, limits)
    assert store.get_capacity(2, tool) == 1
    assert store.get_capacity(2, pearl) == 16
    assert store.get_capacity(9, pearl) == 12
    with api.open_transaction() as tx:
        assert store.insert(tool, 4, tx, slot=2) == 1
        assert store.insert(pearl, 20, tx, slot=9) == 12
        tx.commit()
    assert (store.get_amount(2), store.get_amount(9)) == (1, 12)


def test_item_sparse_slots_side_views_and_filters():
    api = service()
    item = api.item_resource("example:part")
    rejected = api.item_resource("example:other")
    store = api.create_item_storage({2: 64, 9: 64}, 64)
    inlet = api.item_view(store, (2,), output_slots=(), accepts=lambda slot, r: r == item)
    outlet = api.item_view(store, (9,), input_slots=())
    assert inlet.get_slots() == (2,)
    with api.open_transaction() as tx:
        assert inlet.insert(rejected, 1, tx) == 0
        assert inlet.insert(item, 10, tx) == 10
        assert inlet.extract(item, 1, tx) == 0
        assert outlet.insert(item, 1, tx) == 0
        assert store.insert(item, 4, tx, slot=9) == 4
        assert outlet.extract(item, 3, tx) == 3
        tx.commit()
    assert (store.get_amount(2), store.get_amount(9)) == (10, 1)


def test_item_disjoint_slots_share_storage_without_alias_duplication():
    api = service()
    item = api.item_resource("example:part")
    store = api.create_item_storage({2: 64, 9: 64}, 64)
    source = api.item_view(store, (2,))
    target = api.item_view(store, (9,))
    seed(api, source, item, 20)
    with api.open_transaction() as tx:
        assert api.move_item(source, api.item_view(source), item, 5, tx) == 0
        assert api.move_item(source, target, item, 7, tx) == 7
        tx.commit()
    assert (store.get_amount(2), store.get_amount(9)) == (13, 7)


def test_item_distribution_respects_order_and_duplicate_ports():
    api = service()
    item = api.item_resource("example:part")
    source = api.create_item_storage({0: 64}, 64)
    first = api.create_item_storage({0: 4}, 64)
    second = api.create_item_storage({0: 64}, 64)
    seed(api, source, item, 30)
    with api.open_transaction() as tx:
        assert api.distribute_item(source, (source, first, api.item_view(first), second),
                                   item, 20, tx) == 20
        tx.commit()
    assert (source.get_amount(0), first.get_amount(0), second.get_amount(0)) == (10, 4, 16)


def test_item_filter_capacity_and_stack_limit_changes_reject_commit():
    api = service()
    item = api.item_resource("example:part")
    allowed = [True]
    maximum = [16]
    store = api.create_item_storage({0: 64}, lambda resource: maximum[0])
    view = api.item_view(store, accepts=lambda slot, resource: allowed[0])
    with api.open_transaction() as tx:
        view.insert(item, 5, tx)
        allowed[0] = False
        expect(TransactionError, tx.commit)
    assert store.get_amount(0) == 0
    allowed[0] = True
    with api.open_transaction() as tx:
        store.insert(item, 5, tx)
        maximum[0] = 2
        expect(TransactionError, tx.commit)
    maximum[0] = 16
    with api.open_transaction() as tx:
        store.insert(item, 5, tx)
        store.limits[0] = 3
        expect(TransactionError, tx.commit)
    assert store.get_amount(0) == 0


def test_item_provider_faces_and_stale_queries():
    api = service()
    item = api.item_resource("example:part")
    store = api.create_item_storage({0: 64}, 64)
    inlet = api.item_view(store, output_slots=())
    provider = lambda dimension, pos, face: inlet if face == 0 else None
    api.register_provider(api.ITEM, "example:machine", provider)
    assert api.query(api.ITEM, 0, (0, 0, 0), 1) is None
    handle = api.query(api.ITEM, 0, (0, 0, 0), 0)
    seed(api, handle, item, 2)
    with api.open_transaction() as tx:
        assert handle.extract(item, 2, tx) == 0
        tx.commit()
    api.invalidate()
    expect(TransactionError, lambda: handle.get_amount(0))
    fresh = api.query(api.ITEM, 0, (0, 0, 0), 0)
    with api.open_transaction() as tx:
        fresh.insert(item, 1, tx)
        api.invalidate()
        expect(TransactionError, tx.commit)
    assert store.get_amount(0) == 2
    assert api.unregister_provider(api.ITEM, "example:machine", provider)
    assert api.query(api.ITEM, 0, (0, 0, 0), 0) is None


def test_item_and_fluid_recipe_commits_once_per_owner():
    api = service()
    item = api.item_resource("example:part")
    calls = []
    owner = object()

    def persisted():
        calls.append(("save", store.get_amount(0), tank.get_amount(0)))

    def changed(changes):
        calls.append(("changed", len(changes), store.get_amount(0), tank.get_amount(0)))

    store = api.create_item_storage({0: 64}, 64, persist=persisted, changed=changed, owner=owner)
    tank = api.create_fluid_storage({0: 1000}, persist=persisted, changed=changed, owner=owner)
    with api.open_transaction() as tx:
        store.insert(item, 3, tx)
        tank.insert("minecraft:water", 250, tx)
    assert not calls and store.get_amount(0) == tank.get_amount(0) == 0
    with api.open_transaction() as tx:
        assert store.insert(item, 3, tx) == 3
        assert tank.insert("minecraft:water", 250, tx) == 250
        tx.commit()
    assert calls == [("save", 3, 250), ("changed", 2, 3, 250)]


def test_item_external_cell_conflict_aborts_all_participants():
    api = service()
    item = api.item_resource("example:part")
    state = [(item, 10)]
    cell = api.create_cell(state[0], read=lambda: state[0],
                           apply=lambda value: state.__setitem__(0, value))
    source = api.create_item_handler({0: cell}, lambda slot: 64, 64)
    target = api.create_item_storage({0: 64}, 64)
    with api.open_transaction() as tx:
        assert api.move_item(source, target, item, 5, tx) == 5
        state[0] = (item, 7)
        expect(TransactionError, tx.commit)
    assert state[0] == (item, 7) and target.get_amount(0) == 0


def test_item_failed_persistence_retries_without_replaying_transfer():
    api = service()
    item = api.item_resource("example:part")
    failing = [True]
    calls = []

    def persisted():
        calls.append("save")
        if failing[0]:
            raise IOError("intentional item persistence failure")

    source = api.create_item_storage({0: 64}, 64)
    target = api.create_item_storage({0: 64}, 64, persist=persisted,
                                    changed=lambda changes: calls.append("changed"))
    seed(api, source, item, 10)
    with api.open_transaction() as tx:
        assert api.move_item(source, target, item, 6, tx) == 6
        tx.commit()
    assert calls == ["save", "changed"] and len(api.manager.dirty) == 1
    failing[0] = False
    api.tick()
    assert calls == ["save", "changed", "save"] and not api.manager.dirty
    assert (source.get_amount(0), target.get_amount(0)) == (4, 6)


def test_item_failed_memory_apply_restores_source_and_target():
    api = service()
    item = api.item_resource("example:part")
    state = [(None, 0)]

    def apply(value):
        state[0] = value
        if value[1] == 5:
            raise RuntimeError("intentional item memory apply failure")

    cell = api.create_cell(state[0], read=lambda: state[0], apply=apply)
    target = api.create_item_handler({0: cell}, lambda slot: 64, 64)
    source = api.create_item_storage({0: 64}, 64)
    seed(api, source, item, 10)
    with api.open_transaction() as tx:
        assert api.move_item(source, target, item, 5, tx) == 5
        expect(RuntimeError, tx.commit)
    assert source.get_amount(0) == 10 and state[0] == (None, 0)


def test_item_snapshot_preserves_large_counts_and_typed_metadata():
    api = service()
    huge = 10 ** 30
    item = api.item_resource("example:part", 6, {"userData": {
        "big": huge, "fraction": 0.1, "mixed": [True, 1, "a", None, {"b": 2}]}})
    store = api.create_item_storage({2: huge, 9: 1}, huge)
    seed(api, store, item, huge, 2)
    saved = api.save_item(store)
    assert_native_snapshot(saved)
    restored = api.create_item_storage({2: huge, 9: 1}, huge, saved=saved)
    assert restored.get_amount(2) == huge and restored.get_resource(2) == item
    assert restored.get_amount(9) == 0 and restored.get_resource(9) is None
    saved["slots"]["2"]["amount"] = "1"
    saved["slots"]["2"]["resource"]["id"] = "example:other"
    assert restored.get_amount(2) == huge and restored.get_resource(2) == item
    assert store.get_amount(2) == huge and store.get_resource(2) == item


def test_item_snapshot_rejects_corruption_and_overfull_stacks():
    api = service()
    item = api.item_resource("example:part")
    store = api.create_item_storage({0: 64}, 64)
    seed(api, store, item, 10)
    for invalid in (True, 1, 1.0, "01", "-1", "1.0", "65", "0"):
        saved = api.save_item(store)
        saved["slots"]["0"]["amount"] = invalid
        expect((TypeError, ValueError), lambda data=saved: api.create_item_storage({0: 64}, 64, saved=data))
    saved = api.save_item(store)
    saved["slots"]["0"]["resource"] = None
    expect((TypeError, ValueError), lambda: api.create_item_storage({0: 64}, 64, saved=saved))
    saved = api.save_item(store)
    expect((TypeError, ValueError), lambda: api.create_item_storage({1: 64}, 64, saved=saved))
    expect((TypeError, ValueError), lambda: api.create_item_storage({0: 64}, 1, saved=saved))
    for schema in (True, 1.0, "1", 2):
        broken = dict(saved, schema=schema)
        expect((TypeError, ValueError), lambda data=broken: api.create_item_storage({0: 64}, 64, saved=data))


def test_item_restore_keeps_output_inventory_when_input_is_disabled():
    api = service()
    item = api.item_resource("example:part")
    source = api.create_item_storage({0: 64}, 64)
    seed(api, source, item, 10)
    saved = api.save_item(source)
    restored = api.create_item_storage({0: 64}, 64, saved=saved, input_slots=())
    assert restored.get_amount(0) == 10
    assert restored.get_capacity(0, item) == 0
    with api.open_transaction() as tx:
        assert restored.insert(item, 1, tx) == 0
        assert restored.extract(item, 3, tx) == 3
        tx.commit()
    assert restored.get_amount(0) == 7


def test_item_view_preserves_opaque_bulk_delegate_and_storage_identity():
    api = service()
    item = api.item_resource("example:part")
    base = api.create_item_storage({0: 64, 1: 64}, 64)

    class Endpoint(object):
        manager = base.manager
        storage_ids = base.storage_ids

        def get_slots(self):
            return base.get_slots()

        def get_resource(self, slot, tx=None):
            return base.get_resource(slot, tx)

        def get_amount(self, slot, tx=None):
            return base.get_amount(slot, tx)

        def get_capacity(self, slot, resource=None):
            return base.get_capacity(slot, resource)

        def is_valid(self, slot, resource):
            return slot == 1 and base.is_valid(slot, resource)

        def insert(self, resource, amount, tx, slot=None):
            if slot == 0:
                return 0
            return base.insert(resource, min(amount, 2), tx, 1)

        def extract(self, resource, amount, tx, slot=None):
            return base.extract(resource, amount, tx, slot)

    endpoint = Endpoint()
    whole = api.item_view(endpoint)
    first = api.item_view(endpoint, (0,))
    second = api.item_view(endpoint, (1,))
    with api.open_transaction() as tx:
        assert whole.insert(item, 5, tx) == 2
        assert first.insert(item, 5, tx) == 0
        assert api.move_item(second, first, item, 1, tx) == 0
        tx.commit()
    assert (base.get_amount(0), base.get_amount(1)) == (0, 2)
    assert first.storage_ids == second.storage_ids == base.storage_ids


def test_item_nested_views_cannot_restore_forbidden_permissions():
    api = service()
    item = api.item_resource("example:part")
    store = api.create_item_storage({0: 64}, 64)
    restricted = api.item_view(store, input_slots=())
    outer = api.item_view(restricted, input_slots=(0,))
    assert not outer.is_valid(0, item)
    with api.open_transaction() as tx:
        assert outer.insert(item, 1, tx) == 0
        tx.commit()
    assert store.get_amount(0) == 0


def test_item_stacking_helper_fills_existing_stack_before_empty_slots():
    api = service()
    item = api.item_resource("example:part")
    other = api.item_resource("example:part", properties={"userData": {"variant": 2}})
    store = api.create_item_storage({0: 64, 1: 64, 2: 64}, 64)
    seed(api, store, item, 60, 2)
    seed(api, store, other, 10, 1)
    with api.open_transaction() as tx:
        assert api.insert_item_stacking(store, item, 8, tx) == 8
        assert (store.get_amount(0, tx), store.get_amount(1, tx), store.get_amount(2, tx)) == (4, 10, 64)
    assert (store.get_amount(0), store.get_amount(1), store.get_amount(2)) == (0, 10, 60)
    with api.open_transaction() as tx:
        assert api.insert_item_stacking(store, item, 8, tx) == 8
        tx.commit()
    assert (store.get_amount(0), store.get_amount(1), store.get_amount(2)) == (4, 10, 64)


def test_item_source_offer_mismatch_rolls_back_target():
    api = service()
    item = api.item_resource("example:part")
    source = api.create_item_storage({0: 64}, 64)
    target = api.create_item_storage({0: 64}, 64)
    seed(api, source, item, 10)

    class ChangedOffer(object):
        manager = source.manager
        storage_ids = source.storage_ids
        calls = 0

        def extract(self, resource, amount, tx):
            self.calls += 1
            return source.extract(resource, amount if self.calls == 1 else 0, tx)

    with api.open_transaction() as tx:
        expect(TransactionError, lambda: api.move_item(ChangedOffer(), target, item, 5, tx))
        assert target.get_amount(0, tx) == 0
        tx.commit()
    assert source.get_amount(0) == 10 and target.get_amount(0) == 0


def test_item_transfers_conserve_integer_counts_across_many_rounds():
    api = service()
    item = api.item_resource("example:part")
    stores = [api.create_item_storage({0: 64, 5: 64}, 64) for unused in range(3)]
    seed(api, stores[0], item, 100)
    for index in range(40):
        with api.open_transaction() as tx:
            api.move_item(stores[index % 3], stores[(index + 1) % 3], item, index + 1, tx)
            if index % 4:
                tx.commit()
        assert sum(store.get_amount(slot) for store in stores for slot in store.get_slots()) == 100


def test_item_transactions_reject_foreign_manager_and_cross_tick():
    api = service()
    item = api.item_resource("example:part")
    store = api.create_item_storage({0: 64}, 64)
    foreign = service().create_item_storage({0: 64}, 64)
    with api.open_transaction() as tx:
        expect(TransactionError, lambda: foreign.insert(item, 1, tx))
    root = api.open_transaction()
    store.insert(item, 3, root)
    api.tick()
    assert root.closed and store.get_amount(0) == 0
    expect(TransactionError, root.commit)


def test_item_invalid_delegate_results_cannot_leak_into_parent_commit():
    # The stacking path first succeeds in slot 0, then fails in slot 1;
    # rollback must cover both attempts, including queued business callbacks.
    for stacking in (False, True):
        for invalid in ("excess", -1, 1.0, True):
            api = service()
            item = api.item_resource("example:part")
            events = []
            base = api.create_item_storage(
                {0: 1, 1: 64}, 64, changed=lambda changes: events.append("changed"))
            survivor = api.create_item_storage({0: 1}, 1)

            class BadEndpoint(object):
                manager = base.manager
                storage_ids = base.storage_ids

                def get_slots(self):
                    return base.get_slots()

                def get_resource(self, slot, tx=None):
                    return base.get_resource(slot, tx)

                def get_amount(self, slot, tx=None):
                    return base.get_amount(slot, tx)

                def insert(self, resource, amount, tx, slot=None):
                    actual = base.insert(resource, amount, tx, slot)
                    tx.record("bad-endpoint", lambda count: events.append(count), actual)
                    if slot == 0:
                        return actual
                    return amount + 1 if invalid == "excess" else invalid

            endpoint = BadEndpoint()
            view = api.item_view(endpoint)
            with api.open_transaction() as tx:
                assert survivor.insert(item, 1, tx) == 1
                if stacking:
                    operation = lambda: api.insert_item_stacking(endpoint, item, 3, tx)
                else:
                    operation = lambda: view.insert(item, 3, tx)
                expect((TypeError, ValueError, TransactionError), operation)
                assert base.get_amount(0, tx) == base.get_amount(1, tx) == 0
                assert survivor.get_amount(0, tx) == 1
                tx.commit()
            assert base.get_amount(0) == base.get_amount(1) == 0
            assert survivor.get_amount(0) == 1 and not events


def test_item_save_after_capacity_shrink_keeps_inventory_without_truncation():
    api = service()
    item = api.item_resource("example:part", 2, {"userData": {"grade": 3}})
    maximum = [64]
    store = api.create_item_storage({0: 64}, lambda resource: maximum[0])
    seed(api, store, item, 40)
    store.limits[0] = 10
    maximum[0] = 5
    saved = api.save_item(store)
    assert saved["slots"]["0"]["amount"] == "40"
    assert store.get_amount(0) == 40 and store.get_resource(0) == item
    assert_native_snapshot(saved)
    expect(ValueError, lambda: api.create_item_storage({0: 10}, 64, saved=saved))
    expect(ValueError, lambda: api.create_item_storage({0: 64}, 5, saved=saved))
    restored = api.create_item_storage({0: 64}, 64, saved=saved)
    assert restored.get_amount(0) == 40 and restored.get_resource(0) == item


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
