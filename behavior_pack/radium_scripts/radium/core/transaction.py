# coding=utf-8
"""Synchronous, explicit transactions. No engine imports or persistence on abort."""
from collections import OrderedDict, deque
from threading import current_thread
import math
from .values import integer_types, string_types


def immutable_state(value):
    if isinstance(value, tuple):
        for part in value:
            immutable_state(part)
    elif value is not None and not isinstance(value, integer_types + string_types + (float, bool)):
        raise TypeError("Cell state must contain only immutable scalars and tuples")
    elif isinstance(value, float) and math.isnan(value):
        raise ValueError("Cell state must not contain NaN")
    return value


class TransactionError(RuntimeError):
    pass


class RecoveryError(TransactionError):
    """A failed commit could not be restored; its storage remains quarantined."""
    def __init__(self, message, fault_id=None):
        super(RecoveryError, self).__init__(message)
        self.fault_id = fault_id


class TransactionManager(object):
    def __init__(self, report=None):
        self.current = None
        self.epoch = 0
        self.thread = current_thread().ident
        self.report = report or self._report
        self.report_failures = deque(maxlen=16)
        self.dirty = OrderedDict()
        self.notifications = deque()
        self.dispatching = False
        self.persisting = False
        self.applying = False
        self.deferred = deque()
        self.faults = OrderedDict()
        self._fault_serial = 0
        self._quarantined_cells = {}
        self._quarantined_owners = {}
        self._quarantined_participants = {}

    @staticmethod
    def _report(message):
        print("[radium] " + message)

    def _log(self, message):
        # Diagnostic failures must not turn an already committed transfer into
        # an apparent failure, or hide the RecoveryError that isolates storage.
        try:
            self.report(message)
        except Exception as exc:
            self.report_failures.append((message, repr(exc)))

    def assert_thread(self):
        if current_thread().ident != self.thread:
            raise TransactionError("radium is server-thread only")

    def assert_idle(self):
        self.assert_access()
        if self.persisting:
            raise TransactionError("Persistence callbacks must not mutate resources")
        if self.current is not None:
            raise TransactionError("Use explicit handlers inside an open transaction")

    def assert_access(self):
        self.assert_thread()
        if self.applying:
            raise TransactionError("Resource access is forbidden during commit or recovery")

    def is_quarantined(self, cell=None, participant=None, owner=None):
        self.assert_thread()
        return bool((cell is not None and (
            cell in self._quarantined_cells or cell.owner in self._quarantined_owners or
            cell.participant in self._quarantined_participants)) or
            (participant is not None and participant in self._quarantined_participants) or
            (owner is not None and owner in self._quarantined_owners))

    def _check_cell(self, cell):
        fault_id = self._quarantined_cells.get(cell)
        if fault_id is None:
            fault_id = self._quarantined_owners.get(cell.owner)
        if fault_id is None:
            fault_id = self._quarantined_participants.get(cell.participant)
        if fault_id is not None:
            raise RecoveryError("Storage is quarantined by recovery fault %s" % fault_id,
                                fault_id)

    def defer(self, callback):
        """Defer internal invalidation until a committing root has closed."""
        self.assert_thread()
        if not callable(callback):
            raise TypeError("Deferred action must be callable")
        if self.applying:
            self.deferred.append(callback)
        else:
            callback()

    def _drain_deferred(self):
        if self.current is not None or self.applying:
            return
        while self.deferred:
            callback = self.deferred.popleft()
            try:
                callback()
            except Exception as exc:
                self._log("Deferred invalidation failed: %s" % exc)

    def _quarantine(self, entries, cause, failures):
        self._fault_serial += 1
        fault_id = self._fault_serial
        cells = []
        participants = []
        for cell, entry in entries.items():
            self._quarantined_cells[cell] = fault_id
            self._quarantined_owners[cell.owner] = fault_id
            cells.append((cell, entry[1], entry[2]))
            if cell.participant is not None:
                self._quarantined_participants[cell.participant] = fault_id
                if cell.participant not in participants:
                    participants.append(cell.participant)
        self.faults[fault_id] = {
            "cause": repr(cause), "failures": tuple(failures),
            "cells": tuple(cells), "participants": tuple(participants)}
        message = ("Recovery fault %s: %s; storage quarantined; manual reconciliation "
                   "is required before reload. Failures: %s" %
                   (fault_id, cause, "; ".join(failures)))
        self._log(message)
        return RecoveryError(message, fault_id)

    def open(self, parent=None):
        self.assert_access()
        if self.persisting or self.applying:
            raise TransactionError("Storage callbacks must not open transactions")
        if self.current is not parent:
            raise TransactionError("Pass the current transaction as parent")
        return Transaction(self, parent)

    def tick(self):
        self.assert_access()
        self.epoch += 1
        # A transaction must not survive a server tick, even if never committed.
        if self.current is not None:
            self._log("Aborting a transaction that crossed a tick")
            while self.current is not None:
                self.current.abort()
        self.flush()

    def flush(self):
        self.assert_idle()
        self.persisting = True
        try:
            for key, callback in list(self.dirty.items()):
                try:
                    callback()
                except Exception as exc:
                    self._log("Persistence remains dirty: %s" % exc)
                else:
                    self.dirty.pop(key, None)
        finally:
            self.persisting = False
        if self.dispatching:
            return
        self.dispatching = True
        try:
            while self.notifications:
                callback, args = self.notifications.popleft()
                try:
                    callback(*args)
                except Exception as exc:
                    # State is already committed. Never replay the transfer.
                    self._log("Post-commit notification failed: %s" % exc)
        finally:
            self.dispatching = False


class Cell(object):
    """Immutable state; apply updates memory only, without events.

    An optional internal participant prepares a detached token from immutable
    (cell, original, final) changes, then writes and verifies native state.
    restore(token) must verify the original native state or raise. None/True
    indicate completion; an explicit False is treated as a failure.
    """
    def __init__(self, manager, state, read=None, apply=None, persist=None,
                 changed=None, owner=None, valid=None, participant=None):
        for callback in (read, apply, persist, changed, valid):
            if callback is not None and not callable(callback):
                raise TypeError("Cell callbacks must be callable")
        if (read is None) != (apply is None):
            raise ValueError("External cells require both read and apply")
        if participant is not None:
            hash(participant)
            if not all(callable(getattr(participant, name, None))
                       for name in ("prepare", "write", "restore")):
                raise TypeError("Participants require prepare, write and restore methods")
        self.manager = manager
        self.state = immutable_state(state)
        self.read = read
        self.apply = apply
        self.persist = persist
        self.changed = changed
        self.owner = self if owner is None else owner
        hash(self.owner)
        self.valid = valid or (lambda: True)
        self.version = 0
        self.participant = participant

    def get(self):
        self.manager.assert_access()
        self.manager._check_cell(self)
        return self._get_unchecked()

    def _get_unchecked(self):
        return self.state if self.read is None else immutable_state(self.read())

    def _apply(self, state):
        if self.apply is not None:
            self.apply(state)
        else:
            self.state = state

    def set(self, state):
        """Legacy immediate write: persist, but do not synthesize business events."""
        self.manager.assert_idle()
        self.manager._check_cell(self)
        if self.participant is not None:
            raise TransactionError("Participant cells require an explicit transaction")
        immutable_state(state)
        if not self.valid():
            raise TransactionError("Storage is no longer available")
        if state == self.get():
            return
        self._apply(state)
        self.version += 1
        if self.persist is not None:
            self.manager.dirty[self.owner] = self.persist
            self.manager.flush()


class Transaction(object):
    def __init__(self, manager, parent):
        self.manager = manager
        self.parent = parent
        self.epoch = manager.epoch
        self.entries = OrderedDict()
        self.guards = []
        self.effects = OrderedDict()
        self.closed = False
        manager.current = self

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, exc_type, exc, traceback):
        if not self.closed:
            self.abort()
        return False

    def check(self):
        self.manager.assert_access()
        if self.closed or self.manager.current is not self:
            raise TransactionError("Transaction is closed or not current")
        if self.epoch != self.manager.epoch:
            raise TransactionError("Transaction crossed a tick")

    def read(self, cell):
        self.check()
        if cell.manager is not self.manager:
            raise TransactionError("Storage belongs to a different manager")
        self.manager._check_cell(cell)
        if cell not in self.entries:
            ancestor = self.parent
            entry = None
            while ancestor is not None:
                if cell in ancestor.entries:
                    entry = ancestor.entries[cell]
                    break
                ancestor = ancestor.parent
            if entry is None:
                state = cell.get()
                self.entries[cell] = [cell.version, state, state]
            else:
                self.entries[cell] = [entry[0], entry[1], entry[2]]
        return self.entries[cell][2]

    def write(self, cell, state):
        immutable_state(state)
        self.read(cell)
        self.entries[cell][2] = state

    def guard(self, predicate):
        self.check()
        if not predicate():
            raise TransactionError("Resource endpoint is no longer available")
        self.guards.append(predicate)

    def record(self, key, callback, amount):
        self.check()
        if callback is None or amount == 0:
            return
        previous = self.effects.get(key)
        self.effects[key] = (callback, amount + (previous[1] if previous else 0))

    def abort(self):
        self.manager.assert_access()
        if self.manager.current is not self:
            raise TransactionError("Close child transactions first")
        self.closed = True
        self.manager.current = self.parent
        self.manager._drain_deferred()

    def commit(self):
        self.check()
        if not all(guard() for guard in self.guards):
            raise TransactionError("Resource endpoint changed before commit")
        if self.parent is not None:
            for cell, entry in self.entries.items():
                self.parent.entries[cell] = entry
            self.parent.guards.extend(self.guards)
            for key, (callback, amount) in self.effects.items():
                previous = self.parent.effects.get(key)
                self.parent.effects[key] = (
                    callback, amount + (previous[1] if previous else 0))
            self.abort()
            return
        for cell, (version, original, final) in self.entries.items():
            self.manager._check_cell(cell)
            if not cell.valid() or cell.version != version or cell.get() != original:
                raise TransactionError("Resource storage changed before commit")
        changed = [(c, e[1], e[2]) for c, e in self.entries.items() if e[1] != e[2]]
        self._apply_root(changed)
        self._finish_root(changed)

    def _apply_root(self, changed):
        participants = OrderedDict()
        for cell, original, final in changed:
            if cell.participant is not None:
                participants.setdefault(cell.participant, []).append((cell, original, final))
        prepared = []
        applied = []
        attempted = []
        failure = None
        recovery_failures = []
        self.manager.applying = True
        try:
            for participant, changes in participants.items():
                prepared.append((participant, participant.prepare(tuple(changes))))
            for cell, original, final in changed:
                applied.append((cell, original))
                cell._apply(final)
            for participant, token in prepared:
                # A failing writer may already have changed its native owner.
                attempted.append((participant, token))
                if participant.write(token) is False:
                    raise TransactionError("Participant write returned False")
            # A later native writer can trigger synchronous engine events that
            # modify an earlier owner. Verify the complete final read set too.
            for cell, entry in self.entries.items():
                if cell._get_unchecked() != entry[2]:
                    raise TransactionError("Resource state changed during commit")
        except Exception as exc:
            failure = exc
            for participant, token in reversed(attempted):
                try:
                    if participant.restore(token) is False:
                        raise TransactionError("Participant restore returned False")
                except Exception as restore_exc:
                    recovery_failures.append("native %r: %s" % (participant, restore_exc))
            for cell, original in reversed(applied):
                try:
                    cell._apply(original)
                except Exception as restore_exc:
                    recovery_failures.append("memory %r: %s" % (cell.owner, restore_exc))
            for cell, original in applied:
                try:
                    if cell._get_unchecked() != original:
                        raise TransactionError("Restored state differs from its original")
                except Exception as restore_exc:
                    recovery_failures.append("verify %r: %s" % (cell.owner, restore_exc))
        finally:
            self.manager.applying = False
        if failure is not None:
            error = (self.manager._quarantine(self.entries, failure, recovery_failures)
                     if recovery_failures else TransactionError("Commit restored after failure: %s" % failure))
            self.abort()
            raise error

    def _finish_root(self, changed):
        groups = OrderedDict()
        for cell, original, final in changed:
            cell.version += 1
            if cell.persist is not None:
                self.manager.dirty[cell.owner] = cell.persist
            if cell.changed is not None:
                if cell.owner not in groups:
                    groups[cell.owner] = (cell.changed, [])
                groups[cell.owner][1].append((cell, original, final))
        self.abort()
        for callback, changes in groups.values():
            self.manager.notifications.append((callback, (changes,)))
        for callback, amount in self.effects.values():
            self.manager.notifications.append((callback, (amount,)))
        self.manager.flush()
