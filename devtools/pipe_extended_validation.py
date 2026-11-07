# coding=utf-8
"""Real SBT scheduler and paired-container checks; GAME Python 2.7.13 only.

run_sync() exercises the actual callback synchronously for paired chests.
run_async() observes enabled networks through SBT's normal OnSimTick scheduler;
it never invokes a network tick itself. Poll the report until done=True before
reloading the world or using the shared test area for another fixture.
"""
import json
import os
import sys
import time
import traceback
import types
from weakref import WeakValueDictionary


SOURCE = "D:/addon/transferlib/devtools/pipe_validation.py"
REPORT = "D:/addon/transferlib/.cache/pipe_extended_validation.json"
ACTIVE = "_radium_pipe_extended_active"
WATER = "minecraft:water"
LAVA = "minecraft:lava"


def _base():
    module = types.ModuleType("_radium_pipe_extended_base")
    with open(SOURCE, "rb") as source:
        exec(compile(source.read(), SOURCE, "exec"), module.__dict__)
    return module


def _assert_idle():
    if ACTIVE in sys.modules:
        raise RuntimeError("Extended pipe validation is already running")


def _region_empty(base):
    chunks = base.CF.CreateChunkSource(base.LEVEL)
    for x in range(-24, -16):
        for y in range(99, 103):
            for z in range(10, 17):
                pos = (x, y, z)
                assert chunks.CheckChunkState(0, pos), ("Unloaded fixture area", pos)
                assert base.BLOCKS.GetBlockNew(pos, 0)["name"] == "minecraft:air", pos


class Trace(object):
    """Pass all calls through unchanged; record only this network's call scope."""
    def __init__(self, base, fixture):
        self.base, self.fixture = base, fixture
        self.active = False
        self.ticks = 0
        self.calls = []
        self.tick_stamps = []
        self.old_tick = fixture.logic.on_network_tick
        self.attribute = "move_fluid" if fixture.fluid else "move_item"
        self.old_move = getattr(base.API, self.attribute)

        def network_tick(network):
            if network is not fixture.network:
                return self.old_tick(network)
            self.ticks += 1
            self.tick_stamps.append(fixture.logic._tick_counter)
            self.active = True
            try:
                return self.old_tick(network)
            finally:
                self.active = False

        def move(source, target, resource, amount, tx):
            moved = self.old_move(source, target, resource, amount, tx)
            if self.active:
                self.calls.append({"tick": self.ticks, "requested": amount, "moved": moved})
            return moved

        self.tick_wrapper, self.move_wrapper = network_tick, move
        fixture.logic.on_network_tick = network_tick
        setattr(base.API, self.attribute, move)

    def close(self):
        if self.fixture.logic.on_network_tick is self.tick_wrapper:
            self.fixture.logic.on_network_tick = self.old_tick
        if getattr(self.base.API, self.attribute) is self.move_wrapper:
            setattr(self.base.API, self.attribute, self.old_move)


def _reverse(fixture):
    old_inputs = tuple(fixture.network.group_inputs)
    old_outputs = tuple(fixture.network.group_outputs)
    for access in old_outputs:
        assert fixture.logic.SetAccessPointIOMode(access, 1)
        access.io_mode = 1
    for access in old_inputs:
        assert fixture.logic.SetAccessPointIOMode(access, 2)
        access.io_mode = 2
    # Item networks cache sorted lists by length; reversing preserves the length.
    if hasattr(fixture.network, "_sorted_inputs"):
        fixture.network._sorted_inputs = fixture.network._sorted_outputs = None


def _register(base, fixture, inputs, outputs, nodes):
    logic = fixture.logic
    for node in nodes:
        assert logic.nodes_pool.get(0, {}).get(node) is None, ("Existing pipe network", node)
    for access in inputs | outputs:
        assert (0, access.x, access.y, access.z, access.access_facing) not in logic.access_points_pool
    network = logic.network_cls(0, inputs, outputs, nodes, fixture.pipe_name)
    network.enabled = False
    fixture.network = network
    for node in nodes:
        logic.nodes_pool.setdefault(0, WeakValueDictionary())[node] = network
    logic.networks_pool.add(network)
    for access in inputs | outputs:
        logic.access_points_pool[(0, access.x, access.y, access.z, access.access_facing)] = access
    logic.apply_network_to_pool(network)
    base.API.invalidate()


def _build_double(base, fixture, name):
    fixture.source, fixture.target = (-23, 100, 12), (-22, 100, 12)
    pipes = ((-23, 100, 13), (-22, 100, 13))
    states = base.CF.CreateBlockState(base.LEVEL)
    aux = states.GetBlockAuxValueFromStates(name, {"minecraft:cardinal_direction": "north"})
    assert aux >= 0
    for pos in (fixture.source, fixture.target) + pipes:
        fixture.place((pos[0], 99, pos[2]), "minecraft:stone")
    for pos in (fixture.source, fixture.target):
        assert base.BLOCKS.GetBlockNew(pos, 0)["name"] == "minecraft:air"
        fixture.placed.append(pos)
        assert base.BLOCKS.SetBlockNew(pos, {"name": name, "aux": aux}, 0, 0, True, True)
    for pos in pipes:
        fixture.place(pos, fixture.pipe_name)
    assert tuple(base.BLOCKS.GetChestPairedPosition(fixture.source, 0)) == fixture.target
    output = fixture.logic.access_point_cls(0, pipes[0][0], 100, pipes[0][2], 2, 2)
    target = fixture.logic.access_point_cls(0, pipes[1][0], 100, pipes[1][2], 2, 1)
    assert output.target_pos == fixture.source and target.target_pos == fixture.target
    _register(base, fixture, set((target,)), set((output,)), set(pipes))


def paired_chest_case(base, name):
    fixture = base.Fixture()
    trace = None
    try:
        _region_empty(base)
        _build_double(base, fixture, name)
        left, right = fixture.port(fixture.source), fixture.port(fixture.target)
        assert left.get_slots() == right.get_slots() == tuple(range(54))
        assert left.storage_ids == right.storage_ids
        stone = base.API.item_resource("minecraft:stone")
        coal = base.API.item_resource("minecraft:coal")
        with base.API.open_transaction() as tx:
            assert left.insert(stone, 31, tx, 53) == 31
            assert left.insert(coal, 7, tx, 0) == 7
            tx.commit()
        before = base.API.save_item(left)
        trace = Trace(base, fixture)
        for unused in range(3):
            fixture.logic.on_network_tick(fixture.network)
        _reverse(fixture)
        for unused in range(3):
            fixture.logic.on_network_tick(fixture.network)
        assert base.API.save_item(left) == before == base.API.save_item(right)
        assert trace.calls and not any(call["moved"] for call in trace.calls), trace.calls
        return {"ticks": trace.ticks, "radium_calls": len(trace.calls),
                "moved": 0, "slots": 54, "both_directions": True}
    finally:
        if trace is not None:
            trace.close()
        fixture.cleanup()
        _region_empty(base)


def run_sync():
    _assert_idle()
    base = _base()
    result = {"ok": False, "passed": [], "failed": {}, "details": {}, "cleaned": True}
    for name in ("minecraft:chest", "minecraft:waxed_copper_chest"):
        try:
            result["details"][name] = paired_chest_case(base, name)
            result["passed"].append(name)
        except Exception:
            result["failed"][name] = traceback.format_exc()
            try:
                _region_empty(base)
            except Exception:
                result["cleaned"] = False
                break
    result["ok"] = not result["failed"]
    return result


class ScheduledCase(object):
    def __init__(self, base, label, resource, pipe_name, budget):
        self.base, self.label, self.resource = base, label, resource
        self.fixture = base.Fixture(fluid=resource is not None)
        self.fixture.pipe_name = pipe_name
        self.expected_budget = budget
        self.original_budget = None
        self.trace = None
        self.phase = 0
        self.phase_started = 0
        self.observations = []
        self.deadline = time.time() + 30.0
        self.phases = (("items", 6, 0, 15, False, budget),) if resource is None else (
            (("forward", 10, 0, 1000, False, budget),
             ("reverse", 10, 1000, 0, True, budget)) if resource == WATER else
            (("normal_forward_blocked", 4, 1000, 0, False, budget),
             ("1000_forward", 4, 0, 1000, False, 1000),
             ("normal_reverse_blocked", 4, 0, 1000, True, budget),
             ("1000_reverse", 4, 1000, 0, False, 1000)))

    def start(self):
        _region_empty(self.base)
        self.fixture.build("minecraft:cauldron" if self.resource else "minecraft:barrel",
                           "minecraft:cauldron" if self.resource else "minecraft:barrel")
        self.original_budget = self.fixture.network.transfer_speed
        assert self.original_budget == self.expected_budget, self.original_budget
        if self.resource is None:
            self.fixture.seed(self.fixture.source, ((0, "minecraft:stone", 0, 15),))
        else:
            # Roofs keep rain from adding water while scheduler ticks are observed.
            for pos in (self.fixture.source, self.fixture.target):
                self.fixture.place((pos[0], 102, pos[2]), "minecraft:stone")
            with self.base.API.open_transaction() as tx:
                assert self.fixture.port(self.fixture.source).insert(self.resource, 1000, tx) == 1000
                tx.commit()
        self.trace = Trace(self.base, self.fixture)
        self._begin_phase()

    def _begin_phase(self):
        network = self.fixture.network
        network.enabled = False
        label, ticks, source, target, reverse, budget = self.phases[self.phase]
        if reverse:
            _reverse(self.fixture)
        network.transfer_speed = budget
        self.phase_started = self.trace.ticks
        self.deadline = time.time() + 20.0
        network.enabled = True

    def amounts(self):
        left, right = self.fixture.port(self.fixture.source), self.fixture.port(self.fixture.target)
        if self.resource:
            return left.get_amount(0), right.get_amount(0), self.fixture.network.fluid_volume
        return (sum(left.get_amount(slot) for slot in left.get_slots()),
                sum(right.get_amount(slot) for slot in right.get_slots()), 0)

    def poll(self):
        assert self.fixture.network in self.fixture.logic.networks_pool, "Fixture network was replaced"
        assert all(self.fixture.logic.nodes_pool[0].get(node) is self.fixture.network
                   for node in self.fixture.network.nodes)
        values = self.amounts()
        assert sum(values) == (1000 if self.resource else 15), ("Conservation", values)
        assert time.time() < self.deadline, ("No scheduler progress", self.trace.ticks, self.label)
        label, ticks, source, target, reverse, budget = self.phases[self.phase]
        if self.trace.ticks - self.phase_started < ticks:
            return False
        assert values == (source, target, 0), (label, values, self.trace.calls)
        self.observations.append({"phase": label, "amounts": values, "budget": budget,
                                  "scheduler_ticks": self.trace.ticks - self.phase_started})
        self.phase += 1
        if self.phase == len(self.phases):
            assert self.trace.calls, "Actual scheduler never called radium"
            stamps = self.trace.tick_stamps
            assert len(stamps) > 1 and all(b - a == 5 for a, b in zip(stamps, stamps[1:])), stamps
            return True
        self._begin_phase()
        return False

    def summary(self):
        return {"phases": self.observations, "radium_calls": len(self.trace.calls),
                "scheduler_ticks": self.trace.ticks, "scheduler_sim_ticks": self.trace.tick_stamps,
                "calls": self.trace.calls, "original_budget": self.original_budget}

    def close(self):
        if self.fixture.network is not None:
            self.fixture.network.enabled = False
            if self.original_budget is not None:
                self.fixture.network.transfer_speed = self.original_budget
                assert self.fixture.network.transfer_speed == self.original_budget
        if self.trace is not None:
            self.trace.close()
        self.fixture.cleanup()
        _region_empty(self.base)


def run_async(subset=None, report_path=REPORT):
    """Start automatic scheduler acceptance; no manual tick calls in this entry."""
    _assert_idle()
    report_path = os.path.abspath(report_path)
    cache = os.path.abspath("D:/addon/transferlib/.cache")
    assert os.path.normcase(os.path.dirname(report_path)) == os.path.normcase(cache)
    assert report_path.lower().endswith(".json")
    if not os.path.isdir(cache):
        os.makedirs(cache)
    base = _base()
    marker = types.ModuleType(ACTIVE)
    sys.modules[ACTIVE] = marker
    progress = {"done": False, "completed": 0, "total": 0, "passed": [], "failed": {},
                "details": {}, "cleaned": True, "running": None, "ok": False}
    marker.progress = progress
    specs = (("items/steel", None, "skybluetech:item_transport_cable_steel", 5),
             ("water/300", WATER, "skybluetech:pipe_cupronickel", 300),
             ("water/500", WATER, "skybluetech:pipe_ultraheatinum", 500),
             ("lava/300", LAVA, "skybluetech:pipe_cupronickel", 300),
             ("lava/500", LAVA, "skybluetech:pipe_ultraheatinum", 500))
    prefixes = (subset,) if isinstance(subset, basestring) else tuple(subset or ())
    selected = [spec for spec in specs if not prefixes or any(spec[0].startswith(p) for p in prefixes)]
    progress["total"] = len(selected)
    current = [None]
    game = base.CF.CreateGame(base.LEVEL)

    def publish():
        with open(report_path, "wb") as output:
            output.write(json.dumps(progress, ensure_ascii=True, indent=2))

    def finish():
        progress["done"] = True
        progress["running"] = None
        progress["ok"] = not progress["failed"] and progress["cleaned"]
        sys.modules.pop(ACTIVE, None)
        publish()

    def close_current():
        if current[0] is not None:
            try:
                current[0].close()
            except Exception:
                progress["failed"][current[0].label + "/cleanup"] = traceback.format_exc()
                progress["cleaned"] = False
            current[0] = None

    def step():
        if progress["done"]:
            return
        try:
            if current[0] is None:
                if progress["completed"] == len(selected):
                    finish()
                    return
                current[0] = ScheduledCase(base, *selected[progress["completed"]])
                progress["running"] = current[0].label
                current[0].start()
            if current[0].poll():
                label = current[0].label
                progress["details"][label] = current[0].summary()
                progress["passed"].append(label)
                close_current()
                progress["details"][label]["budget_restored"] = progress["cleaned"]
                progress["completed"] += 1
                if not progress["cleaned"]:
                    finish()
                    return
            publish()
            game.AddTimer(0.1, step)
        except Exception:
            label = progress["running"] or "setup"
            progress["failed"][label] = traceback.format_exc()
            close_current()
            progress["completed"] += 1
            if not progress["cleaned"]:
                finish()
                return
            publish()
            game.AddTimer(0.1, step)

    if not selected:
        progress["failed"]["setup"] = "No matching scheduler cases"
        finish()
    else:
        try:
            publish()
            game.AddTimer(0, step)
        except Exception:
            sys.modules.pop(ACTIVE, None)
            raise
    return dict(progress, report_path=report_path)
