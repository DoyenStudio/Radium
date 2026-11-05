# coding=utf-8
from .transaction import TransactionManager, TransactionError, Cell
from .energy import EnergyStorage, EnergyHandler, CombinedEnergyHandler, VoidingEnergyHandler
from .fluid import FluidStorage, FluidHandler
from .registry import ProviderRegistry, ENERGY, FLUID
from .resource import fluid_resource, get_fluid_id, get_fluid_properties
from . import transfer, views, snapshot


class TransferService(object):
    API_VERSION = (1, 1, 0)
    ENERGY = ENERGY
    FLUID = FLUID
    TransactionError = TransactionError

    def __init__(self, is_loaded, block_name, report=None):
        self.manager = TransactionManager(report)
        self.registry = ProviderRegistry(self.manager, is_loaded, block_name)

    def open_transaction(self, parent=None):
        return self.manager.open(parent)

    def create_cell(self, state, **kwargs):
        self.manager.assert_idle()
        return Cell(self.manager, state, **kwargs)

    def create_energy_storage(self, capacity, amount=0, saved=None, **kwargs):
        self.manager.assert_idle()
        if saved is not None:
            amount = snapshot.read_energy(saved)
        return EnergyStorage(self.manager, capacity, amount, **kwargs)

    def create_fluid_storage(self, capacities, saved=None, **kwargs):
        self.manager.assert_idle()
        storage = FluidStorage(self.manager, capacities, **kwargs)
        if saved is not None:
            states = snapshot.read_fluids(saved, storage.limits)
            for slot, state in states.items():
                storage.cells[slot].state = state
        return storage

    def create_voiding_energy(self, on_insert=None, valid=None):
        self.manager.assert_idle()
        return VoidingEnergyHandler(self.manager, on_insert, valid)

    def register_provider(self, capability, block_id, provider):
        return self.registry.register(capability, block_id, provider)

    def unregister_provider(self, capability, block_id, provider):
        return self.registry.unregister(capability, block_id, provider)

    def query(self, capability, dimension, pos, face=None):
        return self.registry.query(capability, dimension, pos, face)

    def invalidate(self):
        """Call on controller rebind, face/filter changes or custom resource unload."""
        self.registry.invalidate()

    def flush(self):
        self.manager.flush()

    def tick(self):
        self.manager.tick()

    def run_self_tests(self):
        self.manager.assert_idle()
        from radium_scripts.radium.tests.self_test import run
        return run()

    create_energy_handler = staticmethod(EnergyHandler)
    create_fluid_handler = staticmethod(FluidHandler)
    combine_energy = staticmethod(CombinedEnergyHandler)
    energy_view = staticmethod(views.energy_view)
    fluid_view = staticmethod(views.fluid_view)
    move_energy = staticmethod(transfer.move_energy)
    move_fluid = staticmethod(transfer.move_fluid)
    distribute_energy = staticmethod(transfer.distribute_energy)
    distribute_fluid = staticmethod(transfer.distribute_fluid)
    save_energy = staticmethod(snapshot.save_energy)
    save_fluid = staticmethod(snapshot.save_fluid)
    fluid_resource = staticmethod(fluid_resource)
    get_fluid_id = staticmethod(get_fluid_id)
    get_fluid_properties = staticmethod(get_fluid_properties)
