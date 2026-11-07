# coding=utf-8
"""Isolated participant fault tests; run only in the game's Python 2.7.13."""
import traceback
from radium_scripts.radium.core.transaction import (
    Cell, TransactionManager, TransactionError, RecoveryError)


def expect(error, action):
    try:
        action()
    except error as exc:
        return exc
    raise AssertionError("Expected %s" % error.__name__)


def manager():
    return TransactionManager(report=lambda message: None)


class Participant(object):
    """Separate memory and native dictionaries expose ordering and compensation."""
    def __init__(self, name, events):
        self.name = name
        self.events = events
        self.world = {}
        self.memory = {}
        self.fail_prepare = False
        self.fail_write = False
        self.fail_restore = False
        self.false_write = False
        self.false_restore = False
        self.hook = None

    def cell(self, mgr, key, value, **kwargs):
        self.world[key] = value
        self.memory[key] = value

        def apply(final):
            self.events.append(("memory", self.name, key, final))
            self.memory[key] = final

        cell = Cell(mgr, value, read=lambda: self.memory[key], apply=apply,
                    owner=self, participant=self, **kwargs)
        cell.native_key = key
        return cell

    def prepare(self, changes):
        self.events.append(("prepare", self.name))
        if self.hook is not None:
            self.hook("prepare")
        if self.fail_prepare:
            raise IOError("prepare failure")
        result = []
        for cell, original, final in changes:
            key = cell.native_key
            if self.world[key] != original:
                raise TransactionError("native snapshot changed")
            result.append((key, original, final))
        return tuple(result)

    def write(self, token):
        self.events.append(("write", self.name))
        for key, original, final in token:
            self.world[key] = final
        if self.hook is not None:
            self.hook("write")
        if self.fail_write:
            raise IOError("write failed after mutation")
        if self.false_write:
            return False
        assert all(self.world[key] == final for key, original, final in token)

    def restore(self, token):
        self.events.append(("restore", self.name))
        if self.hook is not None:
            self.hook("restore")
        if self.fail_restore:
            raise IOError("restore failure")
        for key, original, final in reversed(token):
            self.world[key] = original
        if self.false_restore:
            return False
        assert all(self.world[key] == original for key, original, final in token)


def operations(events):
    return [(entry[0], entry[1]) for entry in events if entry[0] != "memory"]


def test_native_abort_and_nested_commit_never_write():
    mgr = manager()
    events = []
    owner = Participant("a", events)
    cell = owner.cell(mgr, 0, 3)
    with mgr.open() as root:
        with mgr.open(root) as child:
            child.write(cell, 8)
            child.commit()
        assert root.read(cell) == 8
        assert cell.get() == 3 and owner.world[0] == 3 and not events
    assert cell.get() == 3 and owner.world[0] == 3 and not events


def test_native_all_prepare_then_memory_then_writes():
    mgr = manager()
    events = []
    a = Participant("a", events)
    b = Participant("b", events)
    ac = a.cell(mgr, 0, 4)
    bc = b.cell(mgr, 0, 0)
    with mgr.open() as tx:
        tx.write(ac, 1)
        tx.write(bc, 3)
        tx.commit()
    assert [entry[0] for entry in events] == [
        "prepare", "prepare", "memory", "memory", "write", "write"]
    assert ac.get() == a.world[0] == 1 and bc.get() == b.world[0] == 3
    assert ac.version == bc.version == 1 and not mgr.dirty


def test_native_same_owner_is_prepared_and_written_once():
    mgr = manager()
    events = []
    owner = Participant("a", events)
    a = owner.cell(mgr, 0, 5)
    b = owner.cell(mgr, 1, 0)
    with mgr.open() as root:
        root.write(a, 3)
        with mgr.open(root) as child:
            child.write(b, 2)
            child.commit()
        root.commit()
    assert operations(events) == [("prepare", "a"), ("write", "a")]
    assert owner.world == {0: 3, 1: 2}


def test_native_read_only_and_net_zero_changes_do_not_write():
    mgr = manager()
    events = []
    owner = Participant("a", events)
    cell = owner.cell(mgr, 0, 5)
    with mgr.open() as tx:
        assert tx.read(cell) == 5
        tx.write(cell, 8)
        tx.write(cell, 5)
        tx.commit()
    assert not events and cell.version == 0


def test_native_prepare_failure_prevents_every_application():
    mgr = manager()
    events = []
    a = Participant("a", events)
    b = Participant("b", events)
    ac = a.cell(mgr, 0, 4)
    bc = b.cell(mgr, 0, 0)
    b.fail_prepare = True
    with mgr.open() as tx:
        tx.write(ac, 1)
        tx.write(bc, 3)
        error = expect(TransactionError, tx.commit)
        assert not isinstance(error, RecoveryError) and tx.closed
    assert operations(events) == [("prepare", "a"), ("prepare", "b")]
    assert ac.get() == a.world[0] == 4 and bc.get() == b.world[0] == 0
    assert not mgr.faults and mgr.current is None


def test_native_snapshot_conflict_prevents_writes():
    mgr = manager()
    events = []
    owner = Participant("a", events)
    cell = owner.cell(mgr, 0, 5)
    with mgr.open() as tx:
        tx.write(cell, 2)
        owner.world[0] = 4
        expect(TransactionError, tx.commit)
    assert operations(events) == [("prepare", "a")]
    assert cell.get() == 5 and owner.world[0] == 4


def test_native_failed_writer_is_restored_before_prior_writers():
    mgr = manager()
    events = []
    a = Participant("a", events)
    b = Participant("b", events)
    ac = a.cell(mgr, 0, 5)
    bc = b.cell(mgr, 0, 0)
    b.fail_write = True
    with mgr.open() as tx:
        tx.write(ac, 2)
        tx.write(bc, 3)
        error = expect(TransactionError, tx.commit)
    assert not isinstance(error, RecoveryError)
    assert operations(events) == [("prepare", "a"), ("prepare", "b"),
        ("write", "a"), ("write", "b"), ("restore", "b"), ("restore", "a")]
    assert ac.get() == a.world[0] == 5 and bc.get() == b.world[0] == 0
    assert ac.version == bc.version == 0 and not mgr.faults
    b.fail_write = False
    with mgr.open() as retry:
        retry.write(ac, 2)
        retry.write(bc, 3)
        retry.commit()
    assert ac.get() == a.world[0] == 2 and bc.get() == b.world[0] == 3


def test_native_false_write_is_a_failure_and_is_compensated():
    mgr = manager()
    events = []
    owner = Participant("a", events)
    cell = owner.cell(mgr, 0, 5)
    owner.false_write = True
    with mgr.open() as tx:
        tx.write(cell, 1)
        error = expect(TransactionError, tx.commit)
    assert not isinstance(error, RecoveryError)
    assert cell.get() == owner.world[0] == 5
    assert operations(events)[-1] == ("restore", "a")


def test_native_memory_failure_never_calls_native_writers():
    mgr = manager()
    events = []
    owner = Participant("a", events)
    native = owner.cell(mgr, 0, 5)
    state = [0]

    def apply(value):
        state[0] = value
        if value == 3:
            raise IOError("memory apply failure")

    failing = Cell(mgr, 0, read=lambda: state[0], apply=apply)
    with mgr.open() as tx:
        tx.write(native, 2)
        tx.write(failing, 3)
        expect(TransactionError, tx.commit)
    assert operations(events) == [("prepare", "a")]
    assert native.get() == owner.world[0] == 5 and state[0] == 0


def test_native_compensation_failure_quarantines_all_touched_owners():
    mgr = manager()
    events = []
    a = Participant("a", events)
    b = Participant("b", events)
    ac = a.cell(mgr, 0, 5)
    bc = b.cell(mgr, 0, 0)
    sibling = a.cell(mgr, 1, 8)
    read_only = Cell(mgr, 7)
    plain = Cell(mgr, 3)
    unaffected = Cell(mgr, 6)
    b.fail_write = True
    b.fail_restore = True
    with mgr.open() as tx:
        tx.read(read_only)
        tx.write(plain, 2)
        tx.write(ac, 2)
        tx.write(bc, 3)
        error = expect(RecoveryError, tx.commit)
    assert error.fault_id in mgr.faults
    assert mgr.is_quarantined(participant=a) and mgr.is_quarantined(owner=b)
    for cell in (ac, bc, sibling, read_only, plain):
        expect(RecoveryError, cell.get)
        with mgr.open() as retry:
            expect(RecoveryError, lambda: retry.read(cell))
    assert a.world[0] == 5 and b.world[0] == 3
    assert a.memory[0] == 5 and b.memory[0] == 0 and plain.state == 3
    assert ac.version == bc.version == plain.version == 0
    with mgr.open() as tx:
        tx.write(unaffected, 9)
        tx.commit()
    assert unaffected.get() == 9


def test_native_restore_failure_does_not_skip_other_restores():
    mgr = manager()
    events = []
    a = Participant("a", events)
    b = Participant("b", events)
    ac = a.cell(mgr, 0, 5)
    bc = b.cell(mgr, 0, 0)
    b.fail_write = True
    b.fail_restore = True
    with mgr.open() as tx:
        tx.write(ac, 2)
        tx.write(bc, 3)
        expect(RecoveryError, tx.commit)
    assert operations(events)[-2:] == [("restore", "b"), ("restore", "a")]
    assert a.world[0] == 5 and a.memory[0] == 5 and b.memory[0] == 0


def test_native_false_restore_is_not_treated_as_success():
    mgr = manager()
    owner = Participant("a", [])
    cell = owner.cell(mgr, 0, 5)
    owner.fail_write = True
    owner.false_restore = True
    with mgr.open() as tx:
        tx.write(cell, 2)
        expect(RecoveryError, tx.commit)
    assert mgr.is_quarantined(cell=cell)


def test_native_memory_restore_failures_are_all_collected():
    mgr = manager()
    states = [0, 0, 0]
    restored = []

    def make(index):
        def apply(value):
            if value == 0:
                restored.append(index)
                if index in (0, 1):
                    raise IOError("restore %s" % index)
            states[index] = value
            if index == 2 and value == 1:
                raise IOError("apply failed")
        return Cell(mgr, 0, read=lambda: states[index], apply=apply)

    cells = tuple(make(index) for index in range(3))
    with mgr.open() as tx:
        for cell in cells:
            tx.write(cell, 1)
        error = expect(RecoveryError, tx.commit)
    assert restored == [2, 1, 0] and states[2] == 0
    assert len(mgr.faults[error.fault_id]["failures"]) >= 2
    assert all(mgr.is_quarantined(cell=cell) for cell in cells)


def test_native_silent_memory_restore_failure_is_detected():
    mgr = manager()
    state = [0]

    def apply(value):
        if value == 1:
            state[0] = 1
            raise IOError("failure after mutation")
        # A broken callback silently ignores restoration.

    cell = Cell(mgr, 0, read=lambda: state[0], apply=apply)
    with mgr.open() as tx:
        tx.write(cell, 1)
        expect(RecoveryError, tx.commit)
    assert mgr.is_quarantined(cell=cell) and state[0] == 1


def test_native_commit_and_restore_reject_public_reentry():
    mgr = manager()
    owner = Participant("a", [])
    cell = owner.cell(mgr, 0, 5)
    checked = []
    with mgr.open() as tx:
        def hook(phase):
            actions = (lambda: mgr.open(tx), lambda: tx.read(cell),
                       lambda: tx.write(cell, 4), tx.commit, tx.abort,
                       cell.get, lambda: cell.set(4), mgr.tick, mgr.flush)
            for action in actions:
                expect(TransactionError, action)
            assert mgr.current is tx and not tx.closed
            checked.append(phase)
        owner.hook = hook
        owner.fail_write = True
        tx.write(cell, 2)
        expect(TransactionError, tx.commit)
    assert checked == ["prepare", "write", "restore"]
    assert cell.get() == owner.world[0] == 5


def test_native_deferred_invalidation_runs_after_root_closes():
    mgr = manager()
    events = []
    owner = Participant("a", events)
    cell = owner.cell(mgr, 0, 5)

    def invalidated():
        assert mgr.current is None and not mgr.applying
        events.append(("invalidate", "a"))

    def hook(phase):
        if phase == "write":
            mgr.defer(invalidated)
            assert ("invalidate", "a") not in events

    owner.hook = hook
    with mgr.open() as tx:
        tx.write(cell, 2)
        tx.commit()
    assert operations(events)[-2:] == [("write", "a"), ("invalidate", "a")]
    assert not mgr.deferred


def test_native_deferred_invalidation_also_runs_after_failure():
    mgr = manager()
    owner = Participant("a", [])
    cell = owner.cell(mgr, 0, 5)
    called = []

    def invalidated():
        assert mgr.current is None and not mgr.applying
        called.append(True)

    owner.hook = lambda phase: mgr.defer(invalidated) if phase == "write" else None
    owner.fail_write = True
    with mgr.open() as tx:
        tx.write(cell, 2)
        expect(TransactionError, tx.commit)
    assert called == [True] and not mgr.deferred


def test_native_success_notifies_only_after_world_and_memory_commit():
    mgr = manager()
    events = []
    owner = Participant("a", events)
    callbacks = []
    holder = []

    def check(kind):
        assert mgr.current is None and not mgr.applying
        assert holder[0].get() == owner.world[0] == 2
        callbacks.append(kind)

    cell = owner.cell(mgr, 0, 5, persist=lambda: check("persist"),
                      changed=lambda changes: check("changed"))
    holder.append(cell)
    with mgr.open() as tx:
        tx.write(cell, 2)
        tx.record("effect", lambda count: check("effect"), 3)
        tx.commit()
    assert callbacks == ["persist", "changed", "effect"]


def test_native_failed_commit_never_persists_or_notifies():
    mgr = manager()
    owner = Participant("a", [])
    called = []
    cell = owner.cell(mgr, 0, 5, persist=lambda: called.append("persist"),
                      changed=lambda changes: called.append("changed"))
    owner.fail_write = True
    with mgr.open() as tx:
        tx.write(cell, 2)
        tx.record("effect", lambda count: called.append("effect"), 3)
        expect(TransactionError, tx.commit)
    mgr.tick()
    assert not called and not mgr.dirty and not mgr.notifications


def test_native_persist_retry_never_replays_native_write():
    mgr = manager()
    events = []
    owner = Participant("a", events)
    saved = []

    def persist():
        saved.append(owner.world[0])
        if len(saved) == 1:
            raise IOError("save failure")

    cell = owner.cell(mgr, 0, 5, persist=persist)
    with mgr.open() as tx:
        tx.write(cell, 2)
        tx.commit()
    assert owner in mgr.dirty and cell.get() == owner.world[0] == 2
    mgr.tick()
    assert saved == [2, 2] and not mgr.dirty
    assert operations(events) == [("prepare", "a"), ("write", "a")]


def test_native_quarantine_is_not_cleared_or_replayed_by_ticks():
    mgr = manager()
    events = []
    owner = Participant("a", events)
    cell = owner.cell(mgr, 0, 5)
    owner.fail_write = owner.fail_restore = True
    with mgr.open() as tx:
        tx.write(cell, 2)
        expect(RecoveryError, tx.commit)
    before = tuple(events)
    for unused in range(3):
        mgr.tick()
    assert tuple(events) == before and mgr.is_quarantined(cell=cell)


def test_native_participant_validation_and_immediate_set_rejection():
    mgr = manager()
    expect(TypeError, lambda: Cell(mgr, 0, participant=object()))
    owner = Participant("a", [])
    cell = owner.cell(mgr, 0, 5)
    expect(TransactionError, lambda: cell.set(1))
    assert cell.get() == owner.world[0] == 5


def test_native_later_writer_changes_earlier_owner_before_finish():
    mgr = manager()
    events = []
    a = Participant("a", events)
    b = Participant("b", events)
    ac = a.cell(mgr, 0, 5)
    bc = b.cell(mgr, 0, 0)
    # Match real adapters: Cell.read is authoritative native state, while apply
    # changes a separate memory mirror.
    ac.read = lambda: a.world[0]

    def changed_after_a_was_verified(phase):
        if phase == "write":
            a.world[0] = 9

    def refuse_external_overwrite(token):
        if a.world[0] != token[0][2]:
            raise TransactionError("external native change")
        a.world[0] = token[0][1]

    b.hook = changed_after_a_was_verified
    a.restore = refuse_external_overwrite
    with mgr.open() as tx:
        tx.write(ac, 2)
        tx.write(bc, 3)
        expect(RecoveryError, tx.commit)
    assert a.world[0] == 9 and b.world[0] == 0
    assert ac.version == bc.version == 0
    assert mgr.is_quarantined(cell=ac) and mgr.is_quarantined(cell=bc)


def test_native_silent_memory_apply_does_not_report_success():
    mgr = manager()
    state = [0]
    cell = Cell(mgr, 0, read=lambda: state[0], apply=lambda value: None)
    with mgr.open() as tx:
        tx.write(cell, 1)
        error = expect(TransactionError, tx.commit)
    assert not isinstance(error, RecoveryError)
    assert cell.get() == 0 and cell.version == 0 and not mgr.faults


def test_native_reporter_failure_never_changes_commit_or_recovery_result():
    def broken_report(message):
        raise IOError("diagnostic sink unavailable")

    mgr = TransactionManager(report=broken_report)
    saved, notified = [], []

    def persist():
        saved.append(True)
        if len(saved) == 1:
            raise IOError("temporary save failure")

    def changed(changes):
        notified.append(True)
        raise IOError("observer failure after commit")

    cell = Cell(mgr, 0, persist=persist, changed=changed)
    with mgr.open() as tx:
        tx.write(cell, 1)
        tx.commit()
    assert tx.closed and cell.get() == 1 and cell in mgr.dirty
    mgr.tick()
    assert len(saved) == 2 and len(notified) == 1 and not mgr.dirty
    assert len(mgr.report_failures) == 2

    owner = Participant("a", [])
    native = owner.cell(mgr, 0, 5)
    owner.fail_write = owner.fail_restore = True
    with mgr.open() as tx:
        tx.write(native, 2)
        error = expect(RecoveryError, tx.commit)
    assert tx.closed and mgr.current is None
    assert error.fault_id in mgr.faults and mgr.is_quarantined(cell=native)
    assert len(mgr.report_failures) == 3


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
