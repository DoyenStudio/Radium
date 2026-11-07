# coding=utf-8
from .transaction import TransactionManager, TransactionError, RecoveryError, Cell
from .energy import EnergyStorage, EnergyHandler, CombinedEnergyHandler, VoidingEnergyHandler
from .fluid import FluidStorage, FluidHandler
from .item import ItemStorage, ItemHandler
from .registry import ProviderRegistry, ENERGY, FLUID, ITEM
from .resource import fluid_resource, get_fluid_id, get_fluid_properties
from .item_resource import (item_resource, item_resource_from_stack, item_stack,
                            get_item_id, get_item_aux, get_item_properties)
from . import transfer, views, snapshot, item_views, item_transfer, item_snapshot


class TransferService(object):
    API_VERSION = (1, 3, 0)
    ENERGY = ENERGY
    FLUID = FLUID
    ITEM = ITEM
    TransactionError = TransactionError
    RecoveryError = RecoveryError

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

    def create_item_storage(self, capacities, stack_limit, saved=None, **kwargs):
        self.manager.assert_idle()
        storage = ItemStorage(self.manager, capacities, stack_limit, **kwargs)
        if saved is not None:
            states = item_snapshot.read_items(saved, storage)
            for slot, state in states.items():
                storage.cells[slot].state = state
        return storage

    def register_provider(self, capability, block_id, provider):
        return self.registry.register(capability, block_id, provider)

    def get_provider_revision(self, capability):
        """Changes only when the set of providers for this capability changes."""
        return self.registry.provider_revisions.get(capability, 0)

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
        from radium_scripts.radium.tests.item_test import run as run_items
        from radium_scripts.radium.tests.native_transaction_test import run as run_native
        from radium_scripts.radium.tests.quantized_test import run as run_quantized
        from radium_scripts.radium.tests.cauldron_test import run as run_cauldron
        from radium_scripts.radium.tests.native_item_codec_test import run as run_codec
        from radium_scripts.radium.tests.vanilla_rules_test import run as run_rules
        from radium_scripts.radium.tests.vanilla_backend_test import run as run_backend
        result = run()
        for runner in (run_items, run_native, run_quantized, run_cauldron, run_codec,
                       run_rules, run_backend):
            items = runner()
            result["passed"].extend(items["passed"])
            result["failed"].update(items["failed"])
            result["total"] += items["total"]
        result["ok"] = not result["failed"]
        return result

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
    create_item_handler = staticmethod(ItemHandler)
    item_view = staticmethod(item_views.item_view)
    move_item = staticmethod(item_transfer.move_item)
    distribute_item = staticmethod(item_transfer.distribute_item)
    insert_item_stacking = staticmethod(item_transfer.insert_item_stacking)
    save_item = staticmethod(item_snapshot.save_item)
    item_resource = staticmethod(item_resource)
    item_resource_from_stack = staticmethod(item_resource_from_stack)
    item_stack = staticmethod(item_stack)
    get_item_id = staticmethod(get_item_id)
    get_item_aux = staticmethod(get_item_aux)
    get_item_properties = staticmethod(get_item_properties)
