# coding=utf-8
"""Inject a return failure AFTER a real native write, then verify compensation.

Only the isolated validation engine is wrapped; global Minecraft/SBT APIs are
never replaced. Run in the game's interpreter, using the empty fixture region.
"""
import types


class FailAfterWrite(object):
    def __init__(self, delegate, method, failure):
        self.delegate, self.method, self.failure = delegate, method, failure
        self.calls = 0

    def __getattr__(self, name):
        original = getattr(self.delegate, name)
        if name != self.method:
            return original
        def wrapped(*args):
            result = original(*args)
            self.calls += 1
            return False if self.calls == self.failure else result
        return wrapped


def run():
    native = types.ModuleType('_radium_native_failure_helper')
    path = 'D:/addon/transferlib/devtools/native_validation.py'
    exec(compile(open(path, 'rb').read(), path, 'exec'), native.__dict__)

    def failure(fixture, name, paired=False):
        aux = 0
        if paired:
            aux = fixture.states.GetBlockAuxValueFromStates(
                name, {'minecraft:cardinal_direction': 'north'})
        fixture.place(name, aux=aux, neighbors=paired)
        if paired:
            fixture.place(name, (-22, 100, 12), aux, True)
        fluid = name == 'minecraft:cauldron'
        handler = fixture.port(fluid=fluid)
        save = fixture.api.save_fluid if fluid else fixture.api.save_item
        before = save(handler)
        owner = next(iter(fixture.registry.owners.values()))
        native_before = owner.backend.capture()
        if fluid:
            proxy = FailAfterWrite(fixture.engine.states, 'SetBlockStates', 1)
            fixture.engine.states = proxy
        elif name in ('minecraft:furnace', 'minecraft:brewing_stand'):
            proxy = FailAfterWrite(fixture.engine.blocks, 'SetBlockEntityData', 1)
            fixture.engine.blocks = proxy
        else:
            proxy = FailAfterWrite(fixture.engine.items, 'SpawnItemToContainer', 2)
            fixture.engine.items = proxy
        caught = None
        try:
            with fixture.api.open_transaction() as tx:
                if fluid:
                    assert handler.insert('minecraft:water', 1000, tx) == 1000
                elif name == 'minecraft:furnace':
                    assert handler.insert('minecraft:iron_ore', 3, tx, 0) == 3
                    assert handler.insert('minecraft:coal', 2, tx, 1) == 2
                elif name == 'minecraft:brewing_stand':
                    assert handler.insert('minecraft:nether_wart', 3, tx, 0) == 3
                    assert handler.insert('minecraft:blaze_powder', 2, tx, 4) == 2
                else:
                    assert handler.insert('minecraft:stone', 7, tx, 0) == 7
                    assert handler.insert('minecraft:stone', 8, tx, handler.get_slots()[-1]) == 8
                tx.commit()
        except fixture.api.TransactionError as exc:
            caught = exc
        assert caught is not None and not isinstance(caught, fixture.api.RecoveryError), repr(caught)
        assert save(handler) == before
        assert owner.backend.capture() == native_before
        assert not fixture.api.manager.faults
        assert proxy.calls >= (4 if proxy.failure == 2 else 2), proxy.calls
        return {'native_calls': proxy.calls, 'restored': True, 'error': type(caught).__name__}

    def external_conflict(fixture):
        fixture.place('minecraft:barrel')
        handler = fixture.port()
        caught = None
        try:
            with fixture.api.open_transaction() as tx:
                assert handler.insert('minecraft:stone', 1, tx, 0) == 1
                assert fixture.items.SpawnItemToContainer(
                    {'newItemName': 'minecraft:stone', 'newAuxValue': 0, 'count': 9},
                    0, native.FIRST, 0)
                tx.commit()
        except fixture.api.TransactionError as exc:
            caught = exc
        assert caught is not None and handler.get_amount(0) == 9
        return {'external_amount_preserved': 9}

    def pairing_lifecycle(fixture):
        name = 'minecraft:waxed_copper_chest'
        aux = fixture.states.GetBlockAuxValueFromStates(
            name, {'minecraft:cardinal_direction': 'north'})
        fixture.place(name, aux=aux, neighbors=True)
        old = fixture.port()
        other = (-22, 100, 12)
        caught = None
        try:
            with fixture.api.open_transaction() as tx:
                assert old.insert('minecraft:stone', 5, tx) == 5
                fixture.place(name, other, aux, True)
                tx.commit()
        except fixture.api.TransactionError as exc:
            caught = exc
        assert caught is not None
        paired = fixture.port()
        assert len(paired.get_slots()) == 54 and all(paired.get_amount(s) == 0 for s in paired.get_slots())
        caught = None
        try:
            with fixture.api.open_transaction() as tx:
                assert paired.insert('minecraft:stone', 5, tx, 53) == 5
                assert fixture.blocks.SetBlockNew(other, {'name': 'minecraft:air', 'aux': 0},
                                                  0, 0, True, True)
                tx.commit()
        except fixture.api.TransactionError as exc:
            caught = exc
        assert caught is not None
        single = fixture.port()
        assert len(single.get_slots()) == 27 and all(single.get_amount(s) == 0 for s in single.get_slots())
        assert old.storage_ids != single.storage_ids
        return {'merge_and_split_reject_old_commit': True}

    selected = [('failure/' + name, failure, ('minecraft:' + name, False))
                for name in ('barrel', 'chest', 'furnace', 'brewing_stand', 'cauldron')]
    selected.append(('failure/copper_double', failure, ('minecraft:waxed_copper_chest', True)))
    selected.append(('external/native_slot_change', external_conflict, ()))
    selected.append(('lifecycle/pair_merge_split', pairing_lifecycle, ()))
    native.cases = lambda rules: selected
    return native.run()
