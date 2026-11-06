# coding=utf-8
"""Invoke ONLY inside the game's Python 2.7.13 server interpreter."""
import traceback
import struct
from radium_scripts.radium.core.service import TransferService
from radium_scripts.radium.core.transaction import TransactionError
from radium_scripts.radium.core.values import INFINITY

WATER = "minecraft:water"
LAVA = "minecraft:lava"


def service():
    return TransferService(lambda d, p: True, lambda d, p: "example:machine",
                           report=lambda message: None)


def expect(error, action):
    try:
        action()
    except error:
        return
    raise AssertionError("Expected %s" % error.__name__)


def near(a, b):
    assert abs(a - b) < 1e-6, (a, b)


def test_explicit_commit_and_abort():
    api = service()
    store = api.create_energy_storage(100, 30)
    with api.open_transaction() as tx:
        assert store.insert(80, tx) == 70
        assert store.get_amount(tx) == 100
        assert store.get_amount() == 30
    assert store.get_amount() == 30
    with api.open_transaction() as tx:
        assert store.extract(40, tx) == 30
        tx.commit()
    assert store.get_amount() == 0


def test_nested_savepoints():
    api = service()
    store = api.create_energy_storage(100, 10)
    with api.open_transaction() as root:
        store.insert(20, root)
        with api.open_transaction(root) as child:
            store.insert(40, child)
        assert store.get_amount(root) == 30
        with api.open_transaction(root) as child:
            store.insert(5, child)
            child.commit()
        assert store.get_amount(root) == 35
    assert store.get_amount() == 10
    with api.open_transaction() as root:
        with api.open_transaction(root) as child:
            store.insert(1, child)
            child.commit()
        root.commit()
    assert store.get_amount() == 11


def test_cross_resource_recipe():
    api = service()
    energy = api.create_energy_storage(100, 20)
    tank = api.create_fluid_storage({0: 1000})
    with api.open_transaction() as tx:
        energy.extract(10, tx)
        tank.insert(WATER, 250, tx)
    assert energy.get_amount() == 20 and tank.get_amount(0) == 0
    with api.open_transaction() as tx:
        assert energy.extract(10, tx) == 10
        assert tank.insert(WATER, 250, tx) == 250
        tx.commit()
    assert energy.get_amount() == 10 and tank.get_amount(0) == 250


def test_ordered_distribution_and_aliases():
    api = service()
    source = api.create_energy_storage(100, 100)
    a = api.create_energy_storage(25)
    b = api.create_energy_storage(100)
    with api.open_transaction() as tx:
        assert api.distribute_energy(source, (source, a, a, b), 80, tx) == 80
        tx.commit()
    assert (source.get_amount(), a.get_amount(), b.get_amount()) == (20, 25, 55)


def test_limited_source_and_refused_target():
    api = service()
    source = api.create_energy_storage(100, 100)
    limited = api.create_energy_handler(source.cells, source.capacity, max_extract=30)
    small = api.create_energy_storage(10)
    full = api.create_energy_storage(10, 10)
    with api.open_transaction() as tx:
        assert api.distribute_energy(limited, (full, small), 80, tx) == 10
        tx.commit()
    assert source.get_amount() == 90
    assert small.get_amount() == 10


def test_transfer_rolls_back_when_source_changes_offer():
    api = service()
    source = api.create_energy_storage(100, 100)
    target = api.create_energy_storage(100)

    class BrokenOffer(object):
        manager = source.manager
        storage_ids = source.storage_ids
        count = 0

        def extract(self, amount, tx):
            self.count += 1
            return source.extract(amount if self.count == 1 else 0, tx)

    with api.open_transaction() as tx:
        expect(TransactionError, lambda: api.move_energy(BrokenOffer(), target, 50, tx))
        assert target.get_amount(tx) == 0
        tx.commit()
    assert source.get_amount() == 100 and target.get_amount() == 0


def test_combined_energy_aliases():
    api = service()
    a = api.create_energy_storage(20, 20)
    b = api.create_energy_storage(30, 30)
    combined = api.combine_energy((a, a, b))
    assert combined.get_amount() == 50 and combined.get_capacity() == 50
    with api.open_transaction() as tx:
        assert combined.extract(40, tx) == 40
        tx.commit()
    assert a.get_amount() == 0 and b.get_amount() == 10


def test_sparse_fluid_slots_and_views():
    api = service()
    tank = api.create_fluid_storage({2: 100, 9: 200})
    view = api.fluid_view(tank, (9,), output_slots=())
    with api.open_transaction() as tx:
        assert view.insert(WATER, 250, tx) == 200
        assert view.extract(WATER, 100, tx) == 0
        assert tank.insert(LAVA, 50, tx, slot=2) == 50
        tx.commit()
    assert tank.get_slots() == (2, 9)
    assert tank.get_resource(9) == WATER and tank.get_resource(2) == LAVA


def test_fluid_types_filters_and_fractional_transfer():
    api = service()
    source = api.create_fluid_storage({0: 1000})
    target = api.create_fluid_storage({0: 1000})
    filtered = api.create_fluid_handler(target.cells, target.capacity,
                                        accepts=lambda slot, fluid: fluid == WATER)
    with api.open_transaction() as tx:
        assert source.insert(WATER, 10.25, tx) == 10.25
        assert filtered.insert(LAVA, 5, tx) == 0
        tx.commit()
    with api.open_transaction() as tx:
        near(api.move_fluid(source, filtered, WATER, 0.125, tx), 0.125)
        tx.commit()
    near(source.get_amount(0) + target.get_amount(0), 10.25)
    with api.open_transaction() as tx:
        assert target.insert(LAVA, 10, tx) == 0
        tx.commit()


def test_two_slots_in_same_tank_can_transfer():
    api = service()
    tank = api.create_fluid_storage({0: 100, 5: 100})
    source = api.fluid_view(tank, (0,))
    target = api.fluid_view(tank, (5,))
    with api.open_transaction() as tx:
        source.insert(WATER, 50, tx)
        assert api.move_fluid(source, target, WATER, 20, tx) == 20
        tx.commit()
    assert tank.get_amount(0) == 30 and tank.get_amount(5) == 20


def test_creative_infinite_fluid():
    api = service()
    source = api.create_fluid_storage({0: INFINITY})
    target = api.create_fluid_storage({0: 500})
    with api.open_transaction() as tx:
        assert source.insert(WATER, 1, tx) == 1
        assert source.insert(WATER, 1, tx) == 0
        assert api.move_fluid(source, target, WATER, 500, tx) == 500
        tx.commit()
    assert source.get_amount(0) == INFINITY and target.get_amount(0) == 500
    saved = api.save_fluid(source)
    assert saved["schema"] == 2
    assert float.fromhex(saved["slots"]["0"]["amount"]) == 0
    restored = api.create_fluid_storage({0: INFINITY}, saved=saved)
    assert restored.get_amount(0) == INFINITY
    assert restored.get_resource(0) == WATER


def test_grouped_persistence_and_observers():
    api = service()
    calls = []
    owner = object()

    def persisted():
        calls.append(("save", energy.get_amount(), tank.get_amount(0)))

    def changed(changes):
        calls.append(("event", len(changes), energy.get_amount(), tank.get_amount(0)))

    energy = api.create_energy_storage(100, persist=persisted, changed=changed, owner=owner)
    tank = api.create_fluid_storage({0: 100}, persist=persisted, changed=changed, owner=owner)
    with api.open_transaction() as tx:
        energy.insert(10, tx)
        tank.insert(WATER, 20, tx)
        tx.commit()
    assert calls == [("save", 10, 20), ("event", 2, 10, 20)]


def test_persistence_failure_retries_without_replay():
    api = service()
    calls = []
    fail = [True]

    def persisted():
        calls.append("save")
        if fail[0]:
            raise IOError("intentional")

    store = api.create_energy_storage(100, persist=persisted,
                                       changed=lambda changes: calls.append("event"))
    with api.open_transaction() as tx:
        store.insert(20, tx)
        tx.commit()
    assert store.get_amount() == 20 and len(api.manager.dirty) == 1
    fail[0] = False
    api.tick()
    assert calls == ["save", "event", "save"] and not api.manager.dirty


def test_notification_failure_does_not_undo_commit():
    api = service()

    def fail(changes):
        raise RuntimeError("intentional")

    store = api.create_energy_storage(100, changed=fail)
    with api.open_transaction() as tx:
        store.insert(20, tx)
        tx.commit()
    assert store.get_amount() == 20 and not api.manager.notifications


def test_reentrant_notifications_are_queued():
    api = service()
    seen = []
    depth = [0]

    def on_changed(changes):
        depth[0] += 1
        assert depth[0] == 1
        seen.append(store.get_amount())
        if store.get_amount() == 1:
            with api.open_transaction() as inner:
                store.insert(1, inner)
                inner.commit()
        depth[0] -= 1

    store = api.create_energy_storage(100, changed=on_changed)
    with api.open_transaction() as tx:
        store.insert(1, tx)
        tx.commit()
    assert seen == [1, 2]


def test_external_write_conflict_and_immediate_guard():
    api = service()
    state = [5]
    cell = api.create_cell(5, read=lambda: state[0],
                           apply=lambda value: state.__setitem__(0, value))
    handler = api.create_energy_handler((cell,), lambda c: 100)
    with api.open_transaction() as tx:
        handler.insert(10, tx)
        expect(TransactionError, lambda: cell.set(1))
        state[0] = 7
        expect(TransactionError, tx.commit)
    assert state[0] == 7


def test_apply_failure_restores_all_memory():
    api = service()
    first = api.create_energy_storage(100)
    state = [0]

    def apply(value):
        state[0] = value
        if value == 10:
            raise RuntimeError("intentional")

    cell = api.create_cell(0, read=lambda: state[0], apply=apply)
    second = api.create_energy_handler((cell,), lambda c: 100)
    with api.open_transaction() as tx:
        first.insert(10, tx)
        second.insert(10, tx)
        expect(RuntimeError, tx.commit)
    assert first.get_amount() == 0 and state[0] == 0


def test_tick_thread_and_manager_guards():
    api = service()
    store = api.create_energy_storage(100)
    root = api.open_transaction()
    store.insert(10, root)
    child = api.open_transaction(root)
    store.insert(10, child)
    api.tick()
    assert root.closed and child.closed and store.get_amount() == 0
    expect(TransactionError, root.commit)
    other = service().create_energy_storage(10)
    with api.open_transaction() as tx:
        expect(TransactionError, lambda: other.insert(1, tx))
    thread = api.manager.thread
    api.manager.thread = object()
    try:
        expect(TransactionError, api.open_transaction)
    finally:
        api.manager.thread = thread


def test_configuration_changes_reject_commit():
    api = service()
    store = api.create_energy_storage(100)
    enabled = [True]
    handler = api.create_energy_handler(store.cells, store.capacity,
                                        can_insert=lambda: enabled[0])
    with api.open_transaction() as tx:
        handler.insert(10, tx)
        enabled[0] = False
        expect(TransactionError, tx.commit)
    assert store.get_amount() == 0


def test_capability_queries_and_invalidation():
    loaded = [True]
    name = ["example:machine"]
    api = TransferService(lambda d, p: loaded[0], lambda d, p: name[0])
    store = api.create_energy_storage(100)
    calls = []

    def provider(dimension, pos, face):
        calls.append((dimension, pos, face))
        return store if face in (None, 2) else None

    api.register_provider(api.ENERGY, "example:machine", provider)
    api.register_provider(api.ENERGY, "example:machine", provider)
    assert api.query(api.ENERGY, 0, (1, 2, 3), 4) is None
    handle = api.query(api.ENERGY, 0, (1, 2, 3), 2)
    with api.open_transaction() as tx:
        handle.insert(20, tx)
        api.invalidate()
        expect(TransactionError, tx.commit)
    assert store.get_amount() == 0
    expect(TransactionError, handle.get_amount)
    loaded[0] = False
    before = len(calls)
    assert api.query(api.ENERGY, 0, (1, 2, 3)) is None
    assert len(calls) == before
    loaded[0] = True
    handle = api.query(api.ENERGY, 0, (1, 2, 3), 2)
    name[0] = "minecraft:air"
    expect(TransactionError, handle.get_amount)
    assert api.unregister_provider(api.ENERGY, "example:machine", provider)


def test_large_energy_snapshot_roundtrip():
    api = service()
    amount = 10 ** 30 + 987654321
    store = api.create_energy_storage(amount, amount)
    saved = api.save_energy(store)
    assert all(type(n) is int and 0 <= n < 1000000000 for n in saved["limbs"])
    restored = api.create_energy_storage(amount, saved=saved)
    assert restored.get_amount() == amount
    saved["limbs"][0] = 0
    assert restored.get_amount() == amount


def test_fluid_snapshot_is_detached_and_strict():
    api = service()
    store = api.create_fluid_storage({3: 100})
    with api.open_transaction() as tx:
        store.insert(WATER, 33.5, tx)
        tx.commit()
    saved = api.save_fluid(store)
    restored = api.create_fluid_storage({3: 100}, saved=saved)
    saved["slots"]["3"]["amount"] = 1
    assert restored.get_amount(3) == 33.5
    expect(ValueError, lambda: api.create_fluid_storage({4: 100}, saved=saved))


def test_invalid_values_and_readonly_views():
    api = service()
    store = api.create_energy_storage(100)
    tank = api.create_fluid_storage({0: 100})
    with api.open_transaction() as tx:
        for amount in (-1, 1.5, float("nan"), float("inf")):
            expect(ValueError, lambda n=amount: store.insert(n, tx))
        expect(TypeError, lambda: store.insert(True, tx))
        expect(ValueError, lambda: tank.insert(WATER, float("inf"), tx))
        expect(ValueError, lambda: tank.insert("water", 1, tx))
        view = api.energy_view(store, can_insert=False, can_extract=False)
        assert view.insert(10, tx) == 0
        tx.commit()
    expect(TypeError, lambda: api.create_cell({"mutable": 1}))


def test_void_sink_effects_only_after_commit():
    api = service()
    source = api.create_energy_storage(100, 100)
    received = []
    sink = api.create_voiding_energy(on_insert=received.append)
    with api.open_transaction() as tx:
        assert api.move_energy(source, sink, 40, tx) == 40
    assert received == [] and source.get_amount() == 100
    with api.open_transaction() as tx:
        api.move_energy(source, sink, 40, tx)
        tx.commit()
    assert received == [40] and source.get_amount() == 60


def test_many_partial_transfers_conserve_resources():
    api = service()
    energy = [api.create_energy_storage(1000, n) for n in (800, 200, 0)]
    tanks = [api.create_fluid_storage({0: 1000}) for unused in range(3)]
    with api.open_transaction() as tx:
        tanks[0].insert(WATER, 537.125, tx)
        tx.commit()
    for index in range(90):
        source, target = index % 3, (index + 1) % 3
        with api.open_transaction() as tx:
            api.move_energy(energy[source], energy[target], index * 17 + 1, tx)
            api.move_fluid(tanks[source], tanks[target], WATER, index * 0.125 + 0.25, tx)
            tx.commit()
        assert sum(h.get_amount() for h in energy) == 1000
        near(sum(h.get_amount(0) for h in tanks), 537.125)


def test_scalar_energy_configuration_rechecked():
    for field, initial, replacement in (("can_insert", True, False),
                                         ("max_insert", 50, 5),
                                         ("can_extract", True, False),
                                         ("max_extract", 50, 5)):
        api = service()
        store = api.create_energy_storage(100, 50)
        setattr(store, field, initial)
        with api.open_transaction() as tx:
            operation = store.insert if "insert" in field else store.extract
            assert operation(20, tx) == 20
            setattr(store, field, replacement)
            expect(TransactionError, tx.commit)
        assert store.get_amount() == 50


def test_energy_views_follow_live_delegate_limits():
    api = service()
    store = api.create_energy_storage(100)
    store.max_insert = 40
    view = api.energy_view(api.energy_view(store), max_insert=30)
    store.max_insert = 5
    with api.open_transaction() as tx:
        assert view.insert(100, tx) == 5
        tx.commit()
    with api.open_transaction() as tx:
        assert view.insert(100, tx) == 5
        store.max_insert = 2
        expect(TransactionError, tx.commit)
    assert store.get_amount() == 5
    with api.open_transaction() as tx:
        assert view.insert(10, tx) == 2
        view.max_insert = 1
        expect(TransactionError, tx.commit)
    assert store.get_amount() == 5


def test_voiding_energy_view_preserves_semantics_and_effects():
    api = service()
    received = []
    source = api.create_energy_storage(100, 100)
    sink = api.energy_view(api.create_voiding_energy(received.append), max_insert=7)
    assert sink.get_capacity() == 0 and sink.get_amount() == 0
    with api.open_transaction() as tx:
        assert api.move_energy(source, sink, 20, tx) == 7
    assert received == [] and source.get_amount() == 100
    with api.open_transaction() as tx:
        assert api.move_energy(source, sink, 20, tx) == 7
        tx.commit()
    assert received == [7] and source.get_amount() == 93


def test_combined_and_queried_energy_can_be_wrapped():
    api = service()
    first = api.create_energy_storage(20, 20)
    second = api.create_energy_storage(30, 30)
    combined = api.combine_energy((first, second))
    api.register_provider(api.ENERGY, "example:machine", lambda d, p, f: combined)
    queried = api.query(api.ENERGY, 0, (1, 2, 3), 0)
    view = api.energy_view(queried, can_insert=False, max_extract=25)
    assert view.storage_ids == combined.storage_ids
    with api.open_transaction() as tx:
        assert view.insert(10, tx) == 0
        assert view.extract(40, tx) == 25
        tx.commit()
    assert first.get_amount() == 0 and second.get_amount() == 25
    with api.open_transaction() as tx:
        assert view.extract(1, tx) == 1
        api.invalidate()
        expect(TransactionError, tx.commit)
    assert second.get_amount() == 25
    expect(TransactionError, view.get_amount)


def test_custom_energy_view_uses_only_public_protocol():
    api = service()
    store = api.create_energy_storage(100)

    class Endpoint(object):
        manager = store.manager
        storage_ids = store.storage_ids

        def get_amount(self, tx=None):
            return store.get_amount(tx)

        def get_capacity(self):
            return store.get_capacity()

        def insert(self, amount, tx):
            return store.insert(amount, tx) if amount <= 3 else 0

        def extract(self, amount, tx):
            return 0

    view = api.energy_view(Endpoint())
    with api.open_transaction() as tx:
        assert view.insert(10, tx) == 0
        assert view.insert(3, tx) == 3
        assert view.extract(3, tx) == 0
        tx.commit()
    assert store.get_amount() == 3


def test_queried_fluid_slot_views_keep_independent_identities():
    api = service()
    tank = api.create_fluid_storage({2: 100, 9: 100})
    api.register_provider(api.FLUID, "example:machine", lambda d, p, f: tank)
    handle = api.query(api.FLUID, 0, (1, 2, 3), 0)
    source = api.fluid_view(handle, (2,))
    target = api.fluid_view(api.fluid_view(handle), (9,), output_slots=())
    assert not source.storage_ids.intersection(target.storage_ids)
    with api.open_transaction() as tx:
        assert source.insert(WATER, 50, tx) == 50
        assert api.move_fluid(source, target, WATER, 20, tx) == 20
        tx.commit()
    assert tank.get_amount(2) == 30 and tank.get_amount(9) == 20
    with api.open_transaction() as tx:
        assert source.extract(WATER, 1, tx) == 1
        api.invalidate()
        expect(TransactionError, tx.commit)
    assert tank.get_amount(2) == 30
    expect(TransactionError, source.get_slots)


def test_opaque_fluid_delegate_bulk_rules_and_conservative_identity():
    api = service()
    tank = api.create_fluid_storage({0: 100, 1: 100})

    class Endpoint(object):
        manager = tank.manager
        storage_ids = tank.storage_ids

        def get_slots(self):
            return tank.get_slots()

        def get_resource(self, slot, tx=None):
            return tank.get_resource(slot, tx)

        def get_amount(self, slot, tx=None):
            return tank.get_amount(slot, tx)

        def get_capacity(self, slot, fluid_id=None):
            return tank.get_capacity(slot, fluid_id)

        def is_valid(self, slot, fluid_id):
            return tank.is_valid(slot, fluid_id)

        def insert(self, fluid_id, amount, tx, slot=None):
            if fluid_id != WATER:
                return 0
            # Bulk calls have intentional reverse-slot routing.
            return tank.insert(fluid_id, amount, tx, 1 if slot is None else slot)

        def extract(self, fluid_id, amount, tx, slot=None):
            return tank.extract(fluid_id, amount, tx, slot)

    endpoint = Endpoint()
    view = api.fluid_view(endpoint)
    restricted = api.fluid_view(endpoint, (0,), output_slots=())
    assert restricted.storage_ids == endpoint.storage_ids
    with api.open_transaction() as tx:
        assert view.insert(LAVA, 10, tx) == 0
        assert view.insert(WATER, 10, tx) == 10
        assert restricted.insert(LAVA, 10, tx) == 0
        assert restricted.insert(WATER, 5, tx) == 5
        tx.commit()
    assert tank.get_amount(0) == 5 and tank.get_amount(1) == 10


def test_fluid_view_never_grants_delegate_permissions():
    api = service()
    tank = api.create_fluid_storage({0: 100})
    restricted = api.fluid_view(tank, input_slots=())
    outer = api.fluid_view(restricted, input_slots=(0,))
    with api.open_transaction() as tx:
        assert outer.insert(WATER, 10, tx) == 0
        tx.commit()
    assert tank.get_amount(0) == 0


def test_fluid_resource_identity_is_canonical_and_detached():
    api = service()
    properties = {"grade": 2, "recipe": [True, 1, 1.0, None, {"a": "b"}]}
    fluid = api.fluid_resource("example:solution", properties)
    equivalent = api.fluid_resource("example:solution", {
        "recipe": [True, 1, 1.0, None, {"a": "b"}], "grade": 2})
    assert fluid == equivalent and hash(fluid) == hash(equivalent)
    properties["recipe"][4]["a"] = "changed"
    detached = api.get_fluid_properties(fluid)
    detached["recipe"].append("changed")
    assert api.get_fluid_properties(fluid)["recipe"] == [True, 1, 1.0, None, {"a": "b"}]
    assert api.get_fluid_id(fluid) == "example:solution"
    assert api.fluid_resource(WATER, {}) == WATER
    assert api.get_fluid_properties(WATER) == {}
    assert api.fluid_resource(WATER, {"x": True}) != api.fluid_resource(WATER, {"x": 1})
    assert api.fluid_resource(WATER, {"x": 1}) != api.fluid_resource(WATER, {"x": 1.0})
    expect(TypeError, lambda: api.fluid_resource(WATER, []))
    expect(ValueError, lambda: api.fluid_resource(WATER, {"x": INFINITY}))


def test_fluid_variants_do_not_mix_and_survive_transfers():
    api = service()
    cold = api.fluid_resource(WATER, {"temperature": 280})
    hot = api.fluid_resource(WATER, {"temperature": 400})
    source = api.create_fluid_storage({0: 100})
    target = api.create_fluid_storage({0: 100})
    filtered = api.fluid_view(target, accepts=lambda s, r: r == cold)
    with api.open_transaction() as tx:
        assert source.insert(cold, 50, tx) == 50
        assert source.insert(hot, 1, tx) == 0
        assert source.extract(WATER, 1, tx) == 0
        assert filtered.insert(hot, 1, tx) == 0
        assert api.move_fluid(source, filtered, cold, 25, tx) == 25
        tx.commit()
    assert source.get_resource(0) == cold and target.get_resource(0) == cold
    assert source.get_amount(0) == target.get_amount(0) == 25


def test_fluid_view_filter_rechecked_at_commit():
    api = service()
    tank = api.create_fluid_storage({0: 100})
    enabled = [True]
    view = api.fluid_view(tank, accepts=lambda s, r: enabled[0])
    with api.open_transaction() as tx:
        assert view.insert(WATER, 10, tx) == 10
        enabled[0] = False
        expect(TransactionError, tx.commit)
    assert tank.get_amount(0) == 0


def test_fluid_schema_two_preserves_float_and_typed_properties():
    api = service()
    fluid = api.fluid_resource(WATER, {
        "large": 10 ** 40, "small": 0.1, "mixed": [True, 1, 1.0, None, "x"]})
    tank = api.create_fluid_storage({0: 1000.2, 2: INFINITY, 5: 10})
    with api.open_transaction() as tx:
        assert tank.insert(fluid, 1000.2, tx, 0) == 1000.2
        assert tank.insert(fluid, 1, tx, 2) == 1
        tx.commit()
    saved = api.save_fluid(tank)

    def check_native(value):
        if isinstance(value, dict):
            for key, child in value.items():
                assert isinstance(key, str)
                check_native(child)
        elif isinstance(value, list):
            assert not value or all(type(v) is type(value[0]) for v in value)
            for child in value:
                check_native(child)
        else:
            assert value is None or type(value) in (str, int, bool)

    check_native(saved)
    restored = api.create_fluid_storage({0: 1000.2, 2: INFINITY, 5: 10}, saved=saved)
    assert restored.get_amount(0) == 1000.2
    assert restored.get_amount(2) == INFINITY and restored.get_amount(5) == 0
    assert restored.get_resource(0) == fluid and restored.get_resource(2) == fluid
    saved["slots"]["0"]["resource"]["properties"]["value"]["large"]["value"] = "0"
    assert api.get_fluid_properties(restored.get_resource(0))["large"] == 10 ** 40


def test_legacy_float32_capacity_rounding_is_bounded():
    api = service()
    rounded = struct.unpack(">f", struct.pack(">f", 1000.2))[0]
    assert rounded > 1000.2
    saved = {"schema": 1, "slots": {"0": {
        "resource": WATER, "amount": rounded, "infinite": False}}}
    restored = api.create_fluid_storage({0: 1000.2}, saved=saved)
    assert restored.get_amount(0) == 1000.2
    saved["slots"]["0"]["amount"] = rounded + 0.001
    expect(ValueError, lambda: api.create_fluid_storage({0: 1000.2}, saved=saved))
    saved["schema"] = 2
    saved["slots"]["0"]["amount"] = rounded.hex()
    expect(ValueError, lambda: api.create_fluid_storage({0: 1000.2}, saved=saved))


def test_unrepresentable_fluid_deltas_do_not_create_or_destroy():
    api = service()
    huge = float(2 ** 54)
    source = api.create_fluid_storage({0: huge * 2})
    target = api.create_fluid_storage({0: 10})
    with api.open_transaction() as tx:
        assert source.insert(WATER, huge, tx) == huge
        tx.commit()
    with api.open_transaction() as tx:
        assert source.extract(WATER, 1, tx) == 0
        assert source.insert(WATER, 1, tx) == 0
        assert api.move_fluid(source, target, WATER, 1, tx) == 0
        tx.commit()
    assert source.get_amount(0) == huge and target.get_amount(0) == 0


def test_fluid_multi_slot_aggregation_does_not_hide_small_deltas():
    api = service()
    huge = float(2 ** 54)
    tank = api.create_fluid_storage({0: 1, 1: huge})
    with api.open_transaction() as tx:
        assert tank.insert(WATER, huge, tx) == 1
        tx.commit()
    assert tank.get_amount(0) == 1 and tank.get_amount(1) == 0


def test_fluid_distribution_rolls_back_unrepresentable_target_sum():
    api = service()
    huge = float(2 ** 54)
    source = api.create_fluid_storage({0: huge})
    tiny = api.create_fluid_storage({0: 1})
    big = api.create_fluid_storage({0: huge})
    with api.open_transaction() as tx:
        source.insert(WATER, huge, tx)
        tx.commit()
    with api.open_transaction() as tx:
        # The representable total is 1; the huge second insertion is discarded.
        # Source cannot supply exactly 1, so the entire move must roll back.
        expect(TransactionError, lambda: api.distribute_fluid(source, (tiny, big), WATER, huge, tx))
        assert tiny.get_amount(0, tx) == big.get_amount(0, tx) == 0
        tx.commit()
    assert source.get_amount(0) == huge


def test_fluid_rounding_reports_actual_quantity():
    api = service()
    tank = api.create_fluid_storage({0: 10})
    with api.open_transaction() as tx:
        tank.insert(WATER, 0.1, tx)
        before = tank.get_amount(0, tx)
        moved = tank.insert(WATER, 0.2, tx)
        assert 0 < moved <= 0.2
        assert tank.get_amount(0, tx) - before == moved
        tx.commit()
    before = tank.get_amount(0)
    tank.limits[0] = 0
    with api.open_transaction() as tx:
        assert tank.insert(WATER, 1, tx) == 0
        tx.commit()
    assert tank.get_amount(0) == before


def test_fluid_schema_two_rejects_corrupt_values():
    api = service()
    tank = api.create_fluid_storage({0: 10})
    with api.open_transaction() as tx:
        tank.insert(api.fluid_resource(WATER, {"grade": 1}), 1, tx)
        tx.commit()
    for invalid in (1.0, "inf", "nan", (-1.0).hex(), (11.0).hex()):
        saved = api.save_fluid(tank)
        saved["slots"]["0"]["amount"] = invalid
        expect(ValueError, lambda: api.create_fluid_storage({0: 10}, saved=saved))
    saved = api.save_fluid(tank)
    saved["slots"]["0"]["resource"]["properties"]["value"]["grade"] = {
        "type": "unknown", "value": "1"}
    expect(ValueError, lambda: api.create_fluid_storage({0: 10}, saved=saved))


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
