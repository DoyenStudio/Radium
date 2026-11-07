# coding=utf-8
"""Exercise transfers between the external pipe addon's tank and a cauldron in-game."""
import traceback


def run():
    scope = {}
    path = 'D:/addon/transferlib/devtools/pipe_validation.py'
    exec(compile(open(path, 'rb').read(), path, 'exec'), scope)
    from skybluetech_scripts.skybluetech.server.machinery.core import pool
    api, results, failed = scope['API'], {}, {}
    for resource in ('minecraft:water', 'minecraft:lava'):
        for reverse in (False, True):
            label = resource + ('/tank_to_pot' if reverse else '/pot_to_tank')
            fixture = scope['Fixture'](fluid=True)
            tank_pos = fixture.source if reverse else fixture.target
            original = api.move_fluid
            calls = []
            def trace(source, target, fluid, amount, tx):
                moved = original(source, target, fluid, amount, tx)
                calls.append(moved)
                return moved
            old_budget = None
            try:
                names = ('skybluetech:tank_bronze', 'minecraft:cauldron') if reverse else (
                    'minecraft:cauldron', 'skybluetech:tank_bronze')
                network = fixture.build(*names)
                machine = pool.GetMachineWithoutCls(0, *tank_pos)
                old_budget = network.transfer_speed
                if resource == 'minecraft:lava':
                    network.transfer_speed = 1000
                if reverse:
                    ok, rest = machine.AddFluid(resource, 1000)
                    assert ok and rest == 0
                else:
                    with api.open_transaction() as tx:
                        assert fixture.port(fixture.source).insert(resource, 1000, tx) == 1000
                        tx.commit()
                api.move_fluid = trace
                for _ in range(4):
                    fixture.tick()
                pot_pos = fixture.target if reverse else fixture.source
                pot = fixture.port(pot_pos).get_amount(0)
                tank = machine.fluids[0].volume
                assert pot == (1000 if reverse else 0), (pot, tank, calls)
                assert tank == (0 if reverse else 1000), (pot, tank, calls)
                assert network.fluid_volume == 0 and calls and sum(calls) == 1000
                results[label] = {'pot': pot, 'tank': tank, 'radium_calls': len(calls),
                                  'budget': network.transfer_speed}
            except Exception:
                failed[label] = traceback.format_exc()
            finally:
                api.move_fluid = original
                if old_budget is not None:
                    fixture.network.transfer_speed = old_budget
                machine = pool.PopMachineStrict(0, *tank_pos)
                if machine is not None:
                    machine.handler.CallOnUnloadHandlers()
                fixture.cleanup()
    return {'ok': not failed, 'total': 4, 'passed': len(results), 'failed': failed,
            'details': results}
