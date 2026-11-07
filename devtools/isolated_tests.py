# coding=utf-8
"""Run via MCDK execute_code in the GAME interpreter, never system Python."""
import os
import sys
import types

SOURCE = "D:/addon/transferlib/behavior_pack/radium_scripts/radium"


def load(prefix="_radium_validation"):
    for name in (prefix, prefix + ".core", prefix + ".vanilla", prefix + ".tests"):
        module = types.ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
    groups = (
        ("core", ("values", "transaction", "resource", "item_resource", "energy", "fluid",
                  "item", "snapshot", "item_snapshot", "registry", "transfer", "item_transfer",
                  "views", "item_views", "service")),
        ("vanilla", ("item_codec", "rules", "cauldron", "backend", "owner", "items", "registry")),
        ("tests", ("self_test", "item_test", "native_transaction_test", "quantized_test",
                   "cauldron_test", "native_item_codec_test", "vanilla_rules_test",
                   "vanilla_backend_test")))
    for group, names in groups:
        for name in names:
            path = os.path.join(SOURCE, group, name + ".py")
            full_name = prefix + "." + group + "." + name
            module = types.ModuleType(full_name)
            module.__file__ = path
            module.__package__ = prefix + "." + group
            sys.modules[full_name] = module
            setattr(sys.modules[module.__package__], name, module)
            with open(path, "rb") as source_file:
                source = source_file.read().replace("radium_scripts.radium", prefix)
            exec(compile(source, path, "exec"), module.__dict__)
    return sys.modules[prefix + ".core.service"]


def cleanup(prefix="_radium_validation"):
    for name in list(sys.modules):
        if name == prefix or name.startswith(prefix + "."):
            del sys.modules[name]


def run():
    try:
        service = load()
        api = service.TransferService(lambda d, p: True, lambda d, p: "example:block")
        result = api.run_self_tests()
        return {"ok": result["ok"], "passed": len(result["passed"]),
                "total": result["total"], "failed": result["failed"]}
    finally:
        cleanup()
