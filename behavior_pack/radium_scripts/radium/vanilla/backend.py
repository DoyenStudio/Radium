# coding=utf-8
"""Verified ModSDK reads and synchronous writes; no scheduling or persistence."""
from copy import deepcopy
from ..core.transaction import TransactionError
from . import item_codec, rules


def value(record, key, default=None):
    node = record.get(key, default)
    return node.get("__value__", default) if isinstance(node, dict) else node


class UnsupportedContainer(TransactionError):
    pass


class Engine(object):
    def __init__(self, factory, level_id):
        self.blocks = factory.CreateBlockInfo(level_id)
        self.items = factory.CreateItem(level_id)
        self.states = factory.CreateBlockState(level_id)
        self.chunks = factory.CreateChunkSource(level_id)
        self._basic = {}

    def basic_info(self, name, aux=0):
        key = (name, aux)
        if key not in self._basic:
            data = self.items.GetItemBasicInfo(name, aux)
            if not data:
                raise UnsupportedContainer("Unknown item %r" % (key,))
            if data.get("itemType") == "block":
                data["_radium_block_states"] = self.states.GetBlockStatesFromAuxValue(name, aux)
            self._basic[key] = data
        return self._basic[key]

    def block(self, dimension, pos):
        if not self.chunks.CheckChunkState(dimension, pos):
            raise TransactionError("Native block chunk is not loaded")
        block = self.blocks.GetBlockNew(pos, dimension)
        if not block:
            raise TransactionError("Native block is unavailable")
        return block

    def nbt(self, dimension, pos):
        data = self.blocks.GetBlockEntityData(dimension, pos)
        if not isinstance(data, dict):
            raise UnsupportedContainer("Native block entity is unavailable")
        if value(data, "LootTable", ""):
            raise UnsupportedContainer("Unopened loot is owned by the game")
        try:
            return item_codec._copy_nbt(data)
        except (TypeError, ValueError) as exc:
            raise UnsupportedContainer("Native NBT cannot be restored safely: %s" % exc)


class ItemBackend(object):
    def __init__(self, engine, dimension, pos):
        self.engine = engine
        self.dimension = dimension
        block = engine.block(dimension, pos)
        profile = rules.profile(block["name"])
        if profile is None:
            raise UnsupportedContainer("Unsupported native item container")
        self.kind, self.size = profile
        paired = (engine.blocks.GetChestPairedPosition(pos, dimension)
                  if block["name"] in rules.CHESTS else None)
        self.positions = tuple(sorted((pos, tuple(paired)))) if paired else (pos,)
        self.anchor = self.positions[0]
        self.api_slots = self.kind not in ("furnace", "brewing")
        if paired:
            self.size = 54
        self.identity = self._identity()
        for position in self.positions:
            self._validate_entries(engine.nbt(dimension, position))

    def _validate_entries(self, data):
        entries = data.get("Items", [])
        if not isinstance(entries, list):
            raise UnsupportedContainer("Unknown native inventory format")
        # Paired chests expose 54 API slots, but each block entity still owns
        # only physical slots 0..26. Never accept hidden or duplicate entries.
        capacity = 27 if len(self.positions) == 2 else self.size
        seen = set()
        for entry in entries:
            try:
                resource, count, slot = item_codec.decode_entry(entry, self.engine.basic_info)
            except (TypeError, ValueError) as exc:
                raise UnsupportedContainer("Native item cannot be restored losslessly: %s" % exc)
            if slot in seen or not 0 <= slot < capacity:
                raise UnsupportedContainer("Invalid or duplicate physical inventory slot")
            seen.add(slot)

    def _identity(self):
        result = []
        for position in self.positions:
            block = self.engine.block(self.dimension, position)
            profile = rules.profile(block["name"])
            if profile is None:
                raise TransactionError("Native container was replaced")
            kind, size = profile
            if kind != self.kind:
                raise TransactionError("Native container type changed")
            pair = (self.engine.blocks.GetChestPairedPosition(position, self.dimension)
                    if block["name"] in rules.CHESTS else None)
            expected = (self.positions[1] if position == self.positions[0]
                        else self.positions[0]) if len(self.positions) == 2 else None
            if (tuple(pair) if pair else None) != expected:
                raise TransactionError("Native chest pairing changed")
            if self.api_slots:
                size = self.engine.items.GetContainerSize(position, self.dimension)
                if size != self.size:
                    raise UnsupportedContainer("Native container capacity is unavailable")
            name = block["name"]
            if name in rules.FURNACES and name.startswith("minecraft:lit_"):
                # The engine can toggle burning state synchronously while an
                # inventory NBT write is applied. It remains the same furnace.
                name = "minecraft:" + name[len("minecraft:lit_"):]
            result.append((position, name, block.get("aux", 0), size))
        return tuple(result)

    def check(self):
        if self._identity() != self.identity:
            raise TransactionError("Native container identity changed")

    def _decode_nbt(self, data):
        slots = [(None, 0)] * self.size
        seen = set()
        entries = data.get("Items", [])
        if not isinstance(entries, list):
            raise UnsupportedContainer("Unknown native inventory format")
        for entry in entries:
            try:
                resource, count, slot = item_codec.decode_entry(entry, self.engine.basic_info)
            except (TypeError, ValueError) as exc:
                raise UnsupportedContainer("Native item cannot be represented losslessly: %s" % exc)
            if slot in seen or slot not in range(self.size):
                raise UnsupportedContainer("Invalid native inventory slot")
            seen.add(slot)
            slots[slot] = (resource, count)
        return tuple(slots)

    def read_slot(self, slot):
        self.check()
        if self.api_slots:
            for position in self.positions:
                self.engine.nbt(self.dimension, position)
            return self._decode_api_slot(slot)
        return self._decode_nbt(self.engine.nbt(self.dimension, self.anchor))[slot]

    def _decode_api_slot(self, slot):
        try:
            return item_codec.decode_stack(self.engine.items.GetContainerItem(
                self.anchor, slot, self.dimension, True), self.engine.basic_info)
        except (TypeError, ValueError) as exc:
            raise UnsupportedContainer("Native item cannot be represented losslessly: %s" % exc)

    def capture(self):
        self.check()
        data = tuple(self.engine.nbt(self.dimension, p) for p in self.positions)
        # The native slot setter adds this bookkeeping flag even to single
        # barrels/shulkers. Actual pairing is independently guarded by _identity.
        for record in data:
            self._validate_entries(record)
            record.pop("forceunpair", None)
        if self.api_slots:
            slots = tuple(self._decode_api_slot(slot) for slot in range(self.size))
        else:
            slots = self._decode_nbt(data[0])
        return {"slots": slots, "nbt": data}

    def write_slots(self, before, final, touched, token):
        self.check()
        if self.capture() != before:
            raise TransactionError("Native inventory changed before write")
        if self.api_slots:
            expected = list(before["slots"])
            for slot in touched:
                self.check()
                if self.capture() != token["observed"]:
                    raise TransactionError("Native inventory changed during write")
                resource, count = final[slot]
                stack = item_codec.api_stack(resource, count, self.engine.basic_info)
                token["attempted"] = True
                ok = self.engine.items.SpawnItemToContainer(
                    stack, slot, self.anchor, self.dimension)
                expected[slot] = final[slot]
                observed = self.capture()
                if observed["slots"] not in (token["observed"]["slots"], tuple(expected)):
                    raise TransactionError("Uncertain native write; refusing blind compensation")
                self._check_metadata(before, observed)
                token["observed"] = observed
                if not ok or observed["slots"] != tuple(expected):
                    raise TransactionError("Native slot write failed verification")
        else:
            data = deepcopy(before["nbt"][0])
            templates = dict((value(entry, "Slot"), entry) for entry in data.get("Items", []))
            entries = []
            for slot, (resource, count) in enumerate(final):
                if slot not in touched and slot in templates:
                    entries.append(templates[slot])
                elif count:
                    entries.append(item_codec.encode_entry(resource, count, slot,
                                   templates.get(slot), self.engine.basic_info))
            data["Items"] = entries
            token["attempted"] = True
            ok = self.engine.blocks.SetBlockEntityData(self.dimension, self.anchor, data)
            observed = self.capture()
            if observed["slots"] not in (before["slots"], final):
                raise TransactionError("Uncertain native NBT write")
            self._check_metadata(before, observed)
            token["observed"] = observed
            if not ok or observed["slots"] != final:
                raise TransactionError("Native NBT write failed verification")

    @staticmethod
    def _check_metadata(before, observed):
        for old, new in zip(before["nbt"], observed["nbt"]):
            if dict((k, v) for k, v in old.items() if k != "Items") != dict(
                    (k, v) for k, v in new.items() if k != "Items"):
                raise TransactionError("Native write changed unrelated block data")

    def restore(self, token):
        self.check()
        if not token["attempted"]:
            return
        current = self.capture()
        if current == token["before"]:
            return
        if current != token["observed"]:
            raise TransactionError("Refusing to overwrite an external inventory change")
        if self.api_slots:
            self._restore_api_slots(token)
            return
        # Restore the complete native before-image, including metadata not exposed
        # as automation resources. Never schedule this as a future persist retry.
        for index, position in enumerate(self.positions):
            self.check()
            data = token["before"]["nbt"][index]
            current_half = self.engine.nbt(self.dimension, position)
            current_half.pop("forceunpair", None)
            if current_half == data:
                continue
            if current_half != token["observed"]["nbt"][index]:
                raise TransactionError("Paired inventory changed during restoration")
            if not self.engine.blocks.SetBlockEntityData(self.dimension, position, deepcopy(data)):
                raise TransactionError("Native inventory restoration failed")
        if self.capture() != token["before"]:
            raise TransactionError("Native inventory restoration did not match")

    def _restore_api_slots(self, token):
        # SetBlockEntityData may address only the lead half of a paired chest.
        # Restore through the same verified global-slot API used for its writes.
        before = token["before"]
        observed = token["observed"]
        expected = list(observed["slots"])
        for slot in reversed(token["touched"]):
            self.check()
            if self.capture() != observed:
                raise TransactionError("Native inventory changed during restoration")
            if expected[slot] == before["slots"][slot]:
                continue
            resource, count = before["slots"][slot]
            stack = item_codec.api_stack(resource, count, self.engine.basic_info)
            ok = self.engine.items.SpawnItemToContainer(
                stack, slot, self.anchor, self.dimension)
            expected[slot] = before["slots"][slot]
            restored = self.capture()
            self._check_metadata(before, restored)
            if not ok or restored["slots"] != tuple(expected):
                raise TransactionError("Native slot restoration failed verification")
            observed = restored
            token["observed"] = restored
        # Equal resource counts alone do not prove that per-item flags or native
        # palettes were restored. Never fall back to an unsafe whole-NBT write.
        if self.capture() != before:
            raise TransactionError("Native slot restoration did not match the before-image")


class CauldronBackend(object):
    def __init__(self, engine, dimension, pos):
        self.engine, self.dimension, self.anchor = engine, dimension, pos
        self.positions = (pos,)
        self.capture()

    def capture(self):
        block = self.engine.block(self.dimension, self.anchor)
        if block["name"] not in rules.CAULDRONS:
            raise TransactionError("Cauldron was replaced")
        data = self.engine.nbt(self.dimension, self.anchor)
        states = self.engine.states.GetBlockStates(self.anchor, self.dimension)
        if not states or value(data, "id") != "Cauldron":
            raise UnsupportedContainer("Unknown cauldron state")
        if (value(data, "PotionId", -2) != -1 or value(data, "PotionType", -2) != -1
                or "CustomColor" in data or data.get("Items")):
            raise UnsupportedContainer("Only ordinary water and lava are supported")
        level = states.get("fill_level")
        liquid = states.get("cauldron_liquid")
        if level not in range(7) or liquid not in ("water", "lava"):
            raise UnsupportedContainer("Unknown cauldron liquid")
        if liquid == "lava" and level not in (0, 6):
            raise UnsupportedContainer("Partial lava cauldron is not supported")
        state = ("minecraft:" + liquid, level) if level else (None, 0)
        return {"slots": (state,), "nbt": (data,), "states": deepcopy(states),
                "block": block}

    def read_slot(self, slot):
        return self.capture()["slots"][0]

    def check(self):
        self.capture()

    def write_slots(self, before, final, touched, token):
        if self.capture() != before:
            raise TransactionError("Cauldron changed before write")
        resource, level = final[0]
        states = deepcopy(before["states"])
        states.update({"cauldron_liquid": "lava" if resource == "minecraft:lava" else "water",
                       "fill_level": level})
        token["attempted"] = True
        ok = self.engine.states.SetBlockStates(self.anchor, states, self.dimension)
        observed = self.capture()
        if (observed["nbt"] != before["nbt"] or
                observed["states"] not in (before["states"], states)):
            raise TransactionError("Uncertain cauldron write; refusing blind compensation")
        token["observed"] = observed
        if not ok or observed["slots"] != final:
            raise TransactionError("Cauldron write failed verification")

    def restore(self, token):
        if not token["attempted"]:
            return
        current = self.capture()
        if current == token["before"]:
            return
        if current != token["observed"]:
            raise TransactionError("Refusing to overwrite an external cauldron change")
        if not self.engine.states.SetBlockStates(self.anchor, token["before"]["states"], self.dimension):
            raise TransactionError("Cauldron restoration failed")
        if self.capture() != token["before"]:
            raise TransactionError("Cauldron restoration did not match")
