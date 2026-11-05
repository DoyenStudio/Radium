# radium development

- Independent optional NetEase Minecraft addon. Never modify the SkyBlueTech workspace as part of library-only work.
- Public discovery is serverApi.GetComponent(levelId, "radium", "transfer"). Do not require consumers to import radium scripts or declare a mandatory dependency.
- Python 2.7.13 compatible. Execute tests only in the game's interpreter. Do not run project code or compile .py files with system Python.
- Native Mod APIs and events must be verified from existing source or minecraft_mod_assistant documentation. Use the bundled radium_scripts.tooldelta event wrappers.
- Keep storage/transaction core independent of Minecraft and consumer addons. Host owns topology, tick frequency, priorities and machine lifecycle.
- Keep root commits atomic in memory, staged operations side-effect-free, and notifications after commit. Persistence errors retain dirty state; never replay committed transfers.
- Persist native dict/list data. No Python long or infinity in NBT; homogeneous lists, string keys, detached snapshots, assign updated data through bdata[key] = value.
- Preserve third-party source notices. Do not include addon.zip, caches or Studio metadata in version control.
