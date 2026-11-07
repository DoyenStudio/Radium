# radium 1.3.0 第三方模组接口文档

适用于网易我的世界服务端 Python 2.7.13。管道、电缆等运输模组通过 `query` 查找端口，通过 `move_*` 或 `distribute_*` 搬运资源。机器模组通过 `register_provider` 告诉其他模组，哪个方块的哪一面能存取物品、FE 或流体。一个模组可以同时承担两种角色。

## 快速接入

### 在使用方获取组件

```python
import mod.server.extraServerApi as serverApi

def get_transfer_api():
    api = serverApi.GetComponent(serverApi.GetLevelId(), "radium", "transfer")
    if api is None or api.API_VERSION[0] != 1:
        return None
    return api
```

将这段代码放在使用方的服务端脚本中。用到传输功能时再获取组件；返回 `None` 时跳过联动，保留模组自身的运行流程，下次使用时可再次获取。使用方无需导入 radium 脚本、创建组件或在 manifest 中声明强制依赖。

### 运输模组：从下方机器向上方机器输送 FE

```python
def push_up(dimension, source_pos):
    api = get_transfer_api()
    if api is None:
        return 0
    x, y, z = source_pos
    try:
        source = api.query(api.ENERGY, dimension, source_pos, face=1)
        target = api.query(api.ENERGY, dimension, (x, y + 1, z), face=0)
        if source is None or target is None:
            return 0
        with api.open_transaction() as tx:
            moved = api.move_energy(source, target, 200, tx)
            tx.commit()
        return moved
    except api.TransactionError as exc:
        recovery_error = getattr(api, "RecoveryError", None)
        if recovery_error is not None and isinstance(exc, recovery_error):
            # 原值无法确认恢复：交给宿主报告并停止相关库存的调度。
            raise
        # 端口可能已卸载或重绑，交给宿主下一轮重新查询。
        return 0
```

由运输模组在自己的调度中调用 `push_up`。两个面编号分别相对于各自被查询的方块。若上方机器只能接收 60 FE，提交后源端只扣 60 FE，函数返回 60。搬运流体时，两端都查 `api.FLUID`，然后调用例如 `api.move_fluid(source, target, "minecraft:water", 250, tx)`，返回量以 mB 计。

### 机器模组：向其他模组开放电池端口

```python
def register_battery(api, loaded_batteries):
    def provider(dimension, pos, face):
        battery = loaded_batteries.get((dimension, pos))
        if battery is None:
            return None
        if face == 0:
            return battery.input_port
        if face == 1:
            return battery.output_port
        return None

    api.register_provider(api.ENERGY, "example:battery", provider)
    return provider
```

1. 在取得兼容组件后，为自己的实际方块 ID 注册一次 provider，并保存返回的回调引用。`loaded_batteries` 是宿主管理的已加载机器字典，键为 `(维度整数, (x, y, z))`。
2. 在机器加载时创建或恢复它的 `battery.energy`。用 `api.energy_view(battery.energy, can_extract=False)` 创建 `input_port`，用 `api.energy_view(battery.energy, can_insert=False)` 创建 `output_port`，再将机器加入字典。上下两面共享这份储量。
3. 单台机器卸载时，从字典移除该实例并调用 `api.invalidate()`，让已有查询结果失效。同类其他机器继续使用已注册的 provider。停用整类方块的联动时，用保存的回调调用 `api.unregister_provider(api.ENERGY, "example:battery", provider)`。

带存档的机器可参考[完整宿主示例](../examples/third_party_machine.py)，其中包含服务发现、稀疏流体槽、FE 与流体的原子配方、存档回调和卸载处理。

## 服务发现与生命周期

通过 `serverApi.GetComponent(levelId, "radium", "transfer")` 获取服务端组件。使用方检查 `None` 与 `API_VERSION[0]`，不导入库的脚本包。所有调用必须在该组件所属的服务端线程执行。

组件属性：`API_VERSION=(1,3,0)`、`ENERGY="radium:energy"`、`FLUID="radium:fluid"`、`ITEM="radium:item"`、`TransactionError`、`RecoveryError`。流体身份接口要求 `API_VERSION >= (1, 1, 0)`，物品能力要求 `API_VERSION >= (1, 2, 0)`；原版容器、量化候选协议、可选物品规范化协议和 `RecoveryError` 自 1.3.0 提供。

服务的每个模拟 tick 只执行两项维护：中止跨 tick 未关闭的事务，重试脏持久化回调。没有自动资源调度。退出世界时执行最后一次维护并清理 provider 引用。

## 存储和端点

能量统一使用 FE。所有能量端点的储量、容量、存取量、传输返回量、每次调用限额及 `on_insert/on_extract` 回调数量均以 FE 计；自定义端点也须遵守这一约定。库不提供其他能量单位、单位选择或换算分支。能量快照保存 FE 整数值，沿用现有格式和数值，无需迁移。

| 方法 | 返回 / 用途 |
| --- | --- |
| `create_energy_storage(capacity, amount=0, saved=None, persist=None, changed=None, owner=None)` | 单 Cell FE 存储；saved 非 None 时从快照恢复 |
| `create_fluid_storage(capacities, saved=None, persist=None, changed=None, owner=None)` | capacities 为非空的整数槽位 → 容量字典；初始为空 |
| `create_cell(state, read=None, apply=None, persist=None, changed=None, owner=None, valid=None)` | 为现有缓存创建事务 Cell；state 只能是不可变标量或元组 |
| `create_energy_handler(cells, capacity, can_insert=True, can_extract=True, max_insert=None, max_extract=None, valid=None, on_insert=None, on_extract=None, owner=None)` | `cells` 是同一组件下非空、无重复的 FE Cell 序列，每个 Cell 保存整数储量；`capacity(cell)` 返回该 Cell 的容量 |
| `create_fluid_handler(cells, capacity, input_slots=None, output_slots=None, accepts=None, valid=None)` | `cells` 将非负整数槽位映射到同一组件下各自独立的 Cell，每个 Cell 保存 `(resource, amount)`；`capacity(slot)` 返回槽容量 |
| `combine_energy(handlers, valid=None)` | 按给定顺序调用多个能源端点 |
| `create_voiding_energy(on_insert=None, valid=None)` | 接受任意有限非负 FE；无储量、无提取；提交后统计 |
| `energy_view(handler, can_insert=True, can_extract=True, valid=None, max_insert=None, max_extract=None)` | 委托原端点，附加方向和每次调用限额 |
| `fluid_view(handler, slots=None, input_slots=None, output_slots=None, valid=None, accepts=None)` | 委托原端点，附加可见槽位、方向和资源过滤 |
| `fluid_resource(fluid_id, properties=None)` | 创建不可变流体身份；无属性时仍返回字符串 |
| `get_fluid_id(resource)` / `get_fluid_properties(resource)` | 取得基础 ID / 脱离身份对象的属性副本 |

视图可包装原始存储、query 保护代理、组合能源 handler、其他视图和遵守公开协议的自定义端点。它们调用原端点的存取方法，不重新构造存储算法，因此保留虚空接收、自定义存取规则、失效检查与提交后回调。多层视图只能收紧权限；外层声明输入槽也不能使内层已禁用的输入恢复。能源限额随原端点更新，附加限额不会放宽原端点限制。

能源视图的方向参数可为布尔值或无参函数，限额可为非负整数、无参函数或 None。方向、限额字段的替换和函数返回值在提交时重验。流体视图的 `accepts(slot, resource)` 是额外过滤，提交时重验。视图的 `valid()` 只提供额外生命周期限制。

未限制流体槽位且未增加插入资源过滤时，无槽位调用原样委托，保留端点的批量调度规则。显式限制槽位或添加资源过滤时，按视图顺序调用原端点的单槽方法；每次调用仍受原端点约束。只支持整体处理的自定义端点必须拒绝不支持的单槽操作。

FE handler 方法：`get_amount(tx=None)`、`get_capacity()`、`insert(amount, tx)`、`extract(amount, tx)`。数量必须是非负整数，允许值为整数的有限 float 作为兼容输入；拒绝 bool、小数、负数、NaN 与无穷。运行时可使用 Python long，但不得直接持久化。

FE handler 选项：`can_insert/can_extract` 为布尔值或无参函数，`max_insert/max_extract` 为非负整数、无参函数或 None，`valid()` 检查生命周期，`on_insert(actual)/on_extract(actual)` 在最终提交后调用。限额是**每次 handler 调用的限额**，不是每 tick 或每事务的全局预算。方向、容量及限额在提交时重验。

流体端点的方法如下。读取储量或流体身份时，显式传入当前 `tx` 可看到本层暂存的修改，省略时读取已提交状态。FE 的 `get_amount` 也遵循这个规则。

| 方法 | 返回值及用法 |
| --- | --- |
| `get_slots()` | 可见槽位序号；遍历返回的序号即可处理稀疏槽位 |
| `get_resource(slot, tx=None)` | 该槽的完整流体身份，空槽返回 `None` |
| `get_amount(slot, tx=None)` | 该槽的储量（mB），空槽返回 `0.0` |
| `get_capacity(slot, fluid_id=None)` | 该槽总容量（mB）；传入身份时，输入规则拒绝该身份则返回 `0.0` |
| `is_valid(slot, fluid_id)` | 输入方向及过滤规则是否允许该身份；实际能装多少还取决于槽内流体和剩余容量 |
| `insert(fluid_id, amount, tx, slot=None)` | 本次实际接收的 mB 数；指定槽位时只尝试该槽 |
| `extract(fluid_id, amount, tx, slot=None)` | 本次实际提取的 mB 数；指定槽位时只尝试该槽 |

流体 handler 选项：`input_slots/output_slots` 为无重复的已有槽位，None 表示全部，空元组表示禁用该方向；`accepts(slot, resource)` 是入槽过滤函数；`valid()` 检查生命周期。参数名为 `fluid_id` 的流体方法均接受字符串 ID 或 `fluid_resource` 返回的身份。数量为非负有限浮点 mB，空槽为 `(None, 0.0)`，不混液。槽位序号可以不连续。跨槽按配置顺序操作。

只有容量明确为 `float("inf")` 的槽位是创造模式无限源：首次正量插入配置完整流体身份，随后拒绝插入，提取不减少储量。这是显式的非守恒设施。

有限槽仍使用双精度浮点 mB，不强制量化为整数。库检查实际储量变化能否精确表示，并只报告该实际数量；舍入时可少接收，无法表示正变化时返回 0。例如 `2**54 mB` 的有限罐无法提取 `1 mB`，不会向目标凭空提供该数量。跨槽、跨目标累加无法精确表示时跳过相应操作；最终源端提取量与接收总量必须严格相等，否则抛 TransactionError 并放弃该次转移子事务。普通调用方仍须使用返回值决定是否满足配方。

## 流体身份与属性

```python
coolant = api.fluid_resource("example:coolant", {
    "grade": 2,
    "components": {"example:additive": 0.125},
})
view = api.fluid_view(tank, accepts=lambda slot, resource:
                      api.get_fluid_id(resource) == "example:coolant")
with api.open_transaction() as tx:
    received = view.insert(coolant, 250, tx)
    tx.commit()
```

身份由基础 `namespace:name` 和完整属性组成；属性键顺序不影响相等与哈希。同 ID 不同属性不能混合或相互提取；字符串只匹配无属性流体。需要按基础类型过滤时调用 `get_fluid_id`，需要精确匹配时比较完整身份。

属性根节点必须为 dict，支持嵌套 dict/list、字符串、整数（含运行时 long）、有限 float、bool 和 None。键必须为字符串，unicode 规范化为 UTF-8 str。整数、浮点数与布尔值保留类型区别。创建身份时深度冻结，`.properties` / `get_fluid_properties` 返回深拷贝；调用方修改输入属性或返回副本不会改变已有身份。身份本身是可哈希的不可变元组对象，可安全放入 Cell。无需导入库中的类。

## 自定义端点公开协议

端点必须提供属于当前组件的 `manager`、稳定的 `storage_ids` 身份集合，以及上述能源或流体公开方法；包装器不要求暴露 `cells`、容量回调或内部方向字段。每个真实存储必须使用同一身份标记，不能为别名重新生成标记。所有存取必须遵守传入的事务，支持放弃与嵌套模拟，生命周期和业务限制必须由端点自行 guard；不能在模拟中调用旧的立即写入接口或发送通知。

流体端点可额外实现 `get_storage_ids(slots=None)`，返回所选槽位对应的稳定身份集合。内置存储、查询代理和流体视图支持该方法，因此同罐分槽视图仍能互转。未实现时，任何子视图保守保留原端点整个 `storage_ids` 集合；这种端点的同源分槽互转会被消重跳过，避免错误推断独立性。

### 可选的量化提取协议（自 1.3.0 起）

流体端点可以实现 `extraction_candidates(resource, amount, tx, slots=None)`。它只读取当前事务中的状态，不修改资源、不通知、不写世界；`slots=None` 表示全部允许输出的槽，空序列表示没有槽。返回值为：

- `None`：不使用量化协商，沿用既有的模拟源端、分配目标、精确扣源算法。
- `()`：在本次请求和槽位限制下，没有可提取数量。
- 有限 tuple：严格递减、无重复的正数候选，均有限且不超过 `amount`；每项都必须能在同一事务状态下被精确提取。

`move_fluid` / `distribute_fluid` 在可放弃子事务内探测候选，按候选从大到小尝试原有目标顺序及别名消重。目标实际接收总量也是合法候选时，精确扣源并保留本轮；否则放弃整轮，包括暂存状态和通知，再尝试下一候选。没有共同数量时返回 0。非法候选、无法兑现的报价仍抛 `TransactionError`；未实现协议或返回 None 的普通端点保持原有错误语义。

查询代理转发该方法，流体视图把指定槽与自身输出槽取交集，不扩大底层权限。候选不是跨 tick 预算，也不形成资源预留；宿主仍需检查实际返回量。

## 事务

`open_transaction(parent=None)` 立即创建并成为当前事务。使用 with 块，必须显式 `commit()`。有当前事务时必须显式传入该事务作为 parent，禁止隐式加入。子事务提交不修改真实存储；子事务放弃保留父层状态；父层放弃也丢弃所有已合并子层。

```python
with api.open_transaction() as root:
    with api.open_transaction(root) as attempt:
        if api.move_energy(source, target, 100, attempt) == 100:
            attempt.commit()
    # 这里还可操作流体；最后一起提交。
    root.commit()
```

`tx.read(cell)` 读取本层暂存值；`tx.write(cell, immutable_value)` 暂存修改；`tx.guard(predicate)` 立即及提交时核验端点；`tx.abort()` 关闭本层。同一 Cell 的外部缓存、版本或有效性在根提交前发生变化会抛出 TransactionError。事务不得跨 tick、线程或服务实例。

`cell.set(value)` 是适配旧调用的立即写入口，仅在无事务时可用，触发持久化但不合成业务通知。不要在事务内调用旧 AddPower/AddFluid 等直接修改方法，也不要直接写 cells/state。

### 提交顺序

1. 校验全部 guard、Cell 版本、外部原值与生命周期；为原生参与者准备脱离原引用的前像和目标像。
2. 将所有修改应用到可恢复内存，再逐个写入原生参与者并回读核验；最后复核整个事务的最终状态。
3. 全部成功后更新版本，按 owner 合并脏持久化，关闭事务。
4. 执行 persist，再执行合并后的 changed 与统计回调。只有根事务产生原生写入。

回调约定：

- `read()` 返回不可变快照；`apply(value)` **仅更新内存**，必须支持恢复原值，不执行 NBT/事件/网络发送，也不得开启事务。这两个参数必须成对提供。
- `persist()` 写当前最终快照，只做持久化；不得修改资源或开启事务。失败时抛异常（原生接口返回 False 时由适配方转为异常），库记录日志并留待下个 tick 重试。
- `changed(changes)` 收到 `[(cell, original, final), ...]`，此时所有资源均已提交。它可标记 UI 待同步，也可开启新事务；通知用队列排出，不递归进入通知。
- 同一逻辑所有者的所有 Cell 使用同一个可哈希 owner、同一 persist 和同一 changed 回调，以便跨 FE/流体合并一次。
- 统计回调按 handler owner 和 in/out 合并。通知异常会记录日志，但不回滚已提交资源，也不重放转移。

这里只保证单线程内存事务，不保证多方块 NBT 写盘的崩溃原子性。持久化失败或 UI 回调失败后，不可重试整个已提交交易。脏状态保留在 `api.manager.dirty` 中，可在调试时观察；卸载前调用 `flush()` 并确认真实保存行为。

### 原生提交失败与隔离

vanilla 使用内部 `prepare / write / restore` 参与者衔接原生 API，不把原生库存写入塞进 `Cell.apply` 或可重试的 `persist`。提交失败时，逆序补偿所有尝试过的原生写入（包括失败的写入者），再恢复并核验内存。普通容器通过容器 API 逐槽写入和补偿，双箱使用同一个访问基准；炉和酿造台保留 NBT 后端，不把普通双箱的补偿改走整份 NBT 回写。确认完整恢复时抛普通 `TransactionError`，宿主可重新查询后尝试新的事务。

若任何恢复无法确认，库抛 `RecoveryError`（继承 `TransactionError`，携带 `fault_id`），报告诊断并隔离该根事务涉及的全部 Cell、owner 和原生参与者。所有面均不可继续使用；换一个查询代理、下个 tick 或触发失效都不会自动解封。宿主应先处理 `RecoveryError`，停止相关库存调度，人工核对并修复后再重载服务；不能把它当成普通容量不足或自动重试信号。重载本身不等于已经修复资源差额。

原生补偿不保证引擎级跨容器绝对原子，也不提供崩溃恢复保证。原生提交期间禁止通过 radium 重入读写；只延迟 radium 自身的失效处理，不拦截其他模组事件。已提交转移永不重放。

## 转移与有序分配

```python
api.move_energy(source, target, amount, tx)
api.distribute_energy(source, targets, amount, tx)
api.move_fluid(source, target, fluid_id, amount, tx)
api.distribute_fluid(source, targets, fluid_id, amount, tx)
```

这些方法都返回实际移动量，在传入事务内开启可回滚子层。先在放弃的子层模拟源端提取，再按给定顺序暂存接收，最后只提取实际接收量；最终根事务提交前不产生外部副作用。源端每轮分配的限额对整轮有效。拒收部分留在源端。对于多个目标，请将要优先填充的端口放在 `targets` 列表前面，并先过滤掉查询返回的 `None`。

通过 `storage_ids`（共享 Cell 身份集合）识别别名端口。任何与源或本轮已经考虑的目标相交的端点会被保守跳过；组合能源同样跳过与前一端点重叠的整个后续端点。因此重叠的多 Cell 组合可能少传，但不会重复扣取；应提供不重叠视图或在拓扑层消重。同一槽不能经两个面重复参与。同一个罐内不同槽互转须分别使用只含各自槽的 fluid_view。

不要通过重复创建 Cell 包装同一实际存储来伪装独立端点。控制器和多个 IO 方块必须共享同一 Cell 集合。调用方负责本轮优先级、总预算和下次调用时机，不应拿 insert/extract 的最大限额当作全局公平约束。

## 能力 provider

```python
api.register_provider(api.ENERGY, "example:machine", provider)
handler = api.query(api.ENERGY, dimension, (x, y, z), face)
api.unregister_provider(api.ENERGY, "example:machine", provider)
```

`query(capability, dimension, pos, face=None)` 接受整数维度和三个整数方块坐标。`register_provider` 和 `unregister_provider` 均应在事务外调用。支持 `get_provider_revision(capability)` 的版本可用该值检测相应能力的注册表变化，以补查已经铺设的线缆。重复登记同一回调不改变版本。注册成功返回 `None`；同一能力和方块 ID 重复注册同一回调有效，换用其他回调会抛出 `ValueError`。注销时传入原回调，匹配并移除后返回 `True`，未匹配返回 `False`。

`provider(dimension, pos_tuple, face)` 只查宿主的已加载机器表，返回属于当前组件的 handler 或 `None`。区块加载、机器构造、宿主存档读写和资源修改均应在 provider 外完成。内置 vanilla provider 可读取已加载原版容器的类型、配对和内容来建立适配视图，但不会生成战利品、创建机器或写入资源。

face 是被查询方块的原生绝对面：0 下、1 上、2 北、3 南、4 西、5 东。None 是由 provider 自行决定的无面访问，不自动获得绕过过滤的权限；相邻查询必须由调用方换算成目标面。

query 先 CheckChunkState，再 GetBlockNew 取 name，再选择 provider。无匹配、区块未加载或 provider 返回 None 时返回 None。查询注册表不保存宿主机器缓存；vanilla 适配层会复用同一物理库存的 owner 和槽位身份。返回的保护代理在操作及提交时重新核验原生方块、区块和失效代数；过期抛 TransactionError，下一调度轮重新 query。

放置/移除/邻居变化和区块加载/卸载会保守地使所有旧保护代理失效。自定义控制器重绑、侧面模式/过滤器变化、机器卸载等仍需调用 `api.invalidate()`；provider/Cell 的 valid 也应检查机器在所属对象池内是否仍是当前实例。不要长期缓存查询代理。库为注册方块启用 BlockRemove 原生监听。

## 原版容器适配（自 1.3.0 起）

服务端组件启动时自动注册 vanilla provider。运输模组通过 `query(api.ITEM, dimension, pos, face)` 查询物品容器，通过 `query(api.FLUID, dimension, pos, face)` 查询炼药锅，不需要导入 `radium_scripts` 或再次注册。内置注册仍遵守 `(capability, block_id)` 唯一性：第三方用不同回调注册同一键会抛 `ValueError`，不会覆盖内置 provider；同一方块的其他能力不受影响。独立内存 `TransferService` 测试实例不自动连接游戏或注册原版容器。

### 支持范围与面规则

面编号仍是目标方块的绝对面；`face=None` 是合法面的权限并集，不能绕过物品过滤。库存读取可以查看可见槽位，输入和输出权限按下表限制。

| 原版容器 | 能力 / 槽位 | 输入 | 输出 |
| --- | --- | --- | --- |
| 普通箱、陷阱箱、铜箱 | ITEM；单箱 0～26，双箱 0～53 | 所有面全部槽 | 所有面全部槽 |
| 木桶 | ITEM；0～26 | 所有面全部槽 | 所有面全部槽 |
| 潜影盒 | ITEM；0～26 | 所有面全部槽，拒绝任何原版潜影盒 | 所有面全部槽 |
| 漏斗 | ITEM；0～4 | 所有面全部槽 | 所有面全部槽 |
| 发射器、投掷器 | ITEM；0～8 | 所有面全部槽 | 所有面全部槽 |
| 熔炉、烟熏炉、高炉 | ITEM；原料0、燃料1、产物2 | 顶面槽0；四侧槽1，仅合法燃料，不接受空桶 | 底面槽2，以及槽1的空桶 |
| 酿造台 | ITEM；原料0、瓶类1/2/3、燃料4 | 顶面合法原料进槽0；四侧瓶类进1/2/3、烈焰粉进4 | 底面仅1/2/3，不等待酿造完成；不抽取槽0残留瓶 |
| 炼药锅 | FLUID；槽0，1000mB | 所有面，普通水或熔岩 | 所有面，普通水或熔岩 |

铜箱包含原始、斑驳、锈蚀、氧化及对应涂蜡版本，共八种；潜影盒包含未染色、全部颜色及旧 aux 编码；三类炉包含燃烧变体。面规则以当前网易游戏中的原版漏斗实测为准：炉顶可接收泥土等非配方物品，侧面接受橡木木板和煤块、拒绝绯红木板及空桶；酿造台侧面接受空玻璃瓶，底部不会抽走原料槽0的空玻璃瓶，不套用其他版本的例外规则。

炉燃料优先依据原生 `fuelDuration`，并补充该字段无法识别的明确原版方块燃料，不按第三方物品名称后缀猜测。酿造原料采用原版配方名单，药水槽各最多一件。

适配仅开放库存，不替代原版熔炼、酿造、漏斗节拍、红石动作、铜傀儡行为或玩家交互。容量和物品上限由原生数据核验；读取失败不视为空槽。

### 双箱与生命周期

两半以维度和排序后的半箱坐标组成同一物理库存身份，复用相同 owner 和槽位 Cell。所有面和任一半的查询都以字典序较小半箱为原生访问基准，公开槽号 `0..53` 固定对应这一基准；不要按访问半箱自行把槽号再加 27。转移函数会识别两半是同一库存，避免重复计算容量或把同一槽当成两个来源。

配对关系、两半的区块状态、方块类型及容量在操作与提交时核验。合箱、拆箱、半箱替换/卸载，或铜箱氧化/涂蜡等导致身份变化后，旧端口不可继续使用，应重新查询。库不会为访问另一半强加载区块。

### 炼药锅的数量与内容

水位 0～6 固定对应 `0、167、333、500、667、833、1000 mB`。每次存取选择不超过请求量的最大完整水位变化，并返回实际差值。例如空锅请求插入 200mB，接受 167mB；已有 333mB 时请求抽取 200mB，抽出 166mB，剩余 167mB。

熔岩只能进行空锅与满锅之间的 1000mB 存取；请求 999mB 返回 0，请求 1001mB 最多移动 1000mB。来源、目标剩余容量和宿主本次预算都必须足够。库不跨调用累计小额预算；例如管道每次最多传 500mB，就不能直接搬运整桶熔岩。水和熔岩只能在空锅时切换，带属性流体不会当作普通水或熔岩。

锅通过量化候选协议参与 `move_fluid` 和 `distribute_fluid`。无法找到源端和目标共同支持的完整水位差时返回 0，不留下部分注入，也不会把正常容量不足当成事务错误。宿主应按返回的实际数量扣预算，不假定每档都是 167mB。

### 拒绝的容器与物品数据

末影箱需要玩家上下文，不属于按方块坐标发现的共享库存。未展开战利品的箱子不会由适配读取主动生成战利品，待原版初始化后再查询。药水、染色水、细雪、异常部分熔岩、未知锅内容以及无法确认的原生数据格式不开放端口。

vanilla 在原生边界按**实际物品 NBT**规范化身份：附魔、耐久、`extraId` 和自定义提示等便利字段映射到对应 NBT，保留 `userData`、方块放置/破坏限制等可往返数据；`itemId`、`isDiggerItem`、`modId`、`modItemId`、`showInHand` 等 API 派生字段不参与原生物品身份。重复表示冲突、未知字段或无法安全无损表示的数据会被拒绝，不静默截断。

这只发生于 vanilla 端口。核心 `item_resource` / `item_resource_from_stack` 仍保留全部附加属性和原有精确相等语义；普通模组库存不会被全局改写。读取原版槽位后搬运时，优先使用该端口 `get_resource(slot, tx)` 返回的身份；它已经是原生规范化结果。vanilla 端口也提供可选 `normalize_resource(resource)`，供优先合堆辅助函数在比较已有堆叠前取得同一种表示。原生写入的事务与补偿边界见上文“原生提交失败与隔离”。

## 原生快照与恢复

`save_energy(handler)` 和 `save_fluid(handler)` 创建完全脱离运行缓存的原生字典。常规机器应把同一 owner 的 FE 与流体快照写进一个字典，再整体赋值：

```python
bdata["example:resources"] = {
    "energy": api.save_energy(energy),
    "fluid": api.save_fluid(tank),
}
```

FE schema 1：`{"schema": 1, "limbs": [低位, ..., 高位]}`，基数为 10^9，每段均为 int32。零编码为 [0]；不写 Python long，不用整个状态 JSON，也不因大整数转 float 损失精度。

流体写入 schema 2：`{"schema": 2, "slots": {"0": {"resource": 身份记录或None, "amount": "0x1.0p+0", "infinite": bool}}}`。`amount` 是 Python `float.hex()` 的规范字符串，逐值保留 binary64，不经过原生 float32 标签；无限流体写零的 hex 字符串，由 infinite 标志恢复。槽位键统一字符串；恢复时必须与配置精确匹配，拒绝超容量、错误资源、未知槽位与不合法无限状态。

无属性身份仍写字符串，有属性身份写 `{"id": 基础ID, "properties": 属性记录}`。属性记录递归使用 `{"type": 类型名, "value": 数据}`；整数用十进制字符串，float 用 hex 字符串，bool 用 `"0"/"1"`，None 用空字符串；dict 的值是属性记录，list 的元素统一是属性记录 dict。快照只有原生 dict/list/字符串/int/bool/None，不含 Python long、非有限 float 或异构 list。

仍可读取 schema 1 的字符串身份和浮点数量。若旧数量超过配置容量，仅当它恰好等于该容量转换为 float32 后的值时，按容量恢复；其他超量仍拒绝。旧数据下一次保存写为 schema 2，1.0 版本无法读取 schema 2，因此升级后不要直接降级库版本。槽位变化、真正的容量缩小仍由宿主迁移，不静默丢弃资源。

使用 `create_*_storage(..., saved=data)` 在初始化阶段恢复，不产生修改通知。仅写了缓存再即时读取不能证明 NBT 落盘；必须保存、退世界、重进并检验原生数据。可传入自己的 persist 回调适配旧存档，但本库不替任何宿主迁移历史数据。

## 物品能力（自 1.2.0 起）

物品与流体使用相同的服务发现、provider、Cell 和事务机制。先检查 `API_VERSION >= (1, 2, 0)`。`register_provider(api.ITEM, block_id, provider)` 和 `query(api.ITEM, dimension, pos, face)` 采用前述绝对面、已加载机器及失效契约。

### 身份与原生物品字典

| 方法 | 用途 |
| --- | --- |
| `item_resource(item_id, aux=0, properties=None)` | 创建不含数量的不可变、可哈希身份 |
| `get_item_id(resource)` / `get_item_aux(resource)` | 读取基础 ID / aux |
| `get_item_properties(resource)` | 返回附加数据的脱离副本 |
| `item_resource_from_stack(stack)` | 从原生物品字典复制身份，忽略数量；空栈返回 None |
| `item_stack(resource, count=1)` | 返回新的原生物品字典；count 为 0 时返回 None |

所有物品操作接受身份对象，或表示 aux=0、无附加数据物品的 `namespace:name` 字符串。`None` 只表示空槽，不是可插入/提取的物品身份；`minecraft:air` 被拒绝。数量、aux、槽位和容量必须是非负整数，拒绝 bool、浮点数（包括 `1.0`）和无穷；运行时允许 long。

身份包括 ID、aux 和全部附加字段，数量独立。同 ID 不同 aux、耐久、附魔或 userData 的物品不会混堆。属性支持原生 dict/list/tuple、字符串、整数、有限 float、bool 和 None；键为字符串。结构及标量类型都参与相等比较，list 与 tuple 有区别。创建时深度冻结，传入或返回的可变数据不能改动身份。属性中的 `count`、`newItemName`、`itemName`、`newAuxValue`、`auxValue` 为保留键，不能重复定义身份。

`item_resource_from_stack` 接受 `newItemName/newAuxValue`，兼容旧 `itemName/auxValue`；新旧字段同时出现时必须一致。非空字典必须有 count；None、空字典或 count=0 表示空栈。其余字段全部保留，包括 `userData`、`enchantData`、`modEnchantData`、`durability`、`extraId`。附魔列表中的 tuple 保持原类型。输出使用新字段名。空值和缺少字段不会自动合并，宿主需要规范化时，应在创建身份前统一处理。

```python
gear = api.item_resource_from_stack({
    "newItemName": "example:gear", "newAuxValue": 0, "count": 8,
    "userData": {"grade": 2},
})
stack = api.item_stack(gear, 3)  # 新字典，原始数量 8 不属于 gear 身份
```

### 槽位、堆叠与视图

| 方法 | 用途 |
| --- | --- |
| `create_item_storage(capacities, stack_limit, saved=None, persist=None, changed=None, owner=None, input_slots=None, output_slots=None, accepts=None, valid=None)` | 创建稀疏槽位库存；capacities 为非空的槽号 → 容量字典 |
| `create_item_handler(cells, capacity, stack_limit, input_slots=None, output_slots=None, accepts=None, valid=None)` | 以现有 Cell 构造端点；capacity(slot) 返回槽位容量 |
| `item_view(handler, slots=None, input_slots=None, output_slots=None, valid=None, accepts=None)` | 委托端点并收紧可见槽、输入输出及物品过滤 |
| `save_item(handler)` | 创建脱离缓存的 NBT 安全库存快照 |

`stack_limit` 必传，为非负整数或 `stack_limit(resource)` 回调。每个物品的实际槽容量是 `min(槽位容量, stack_limit(resource))`。宿主依据自己掌握的物品定义提供上限，例如普通物品 64、投掷物 16、工具 1；核心不调用 Minecraft，不猜测物品默认上限。该上限不属于身份，保存恢复时由宿主重新提供。

Cell 状态为 `(resource, count)`，空槽严格为 `(None, 0)`。多个面和控制器别名必须共享同一真实槽位的 Cell。`input_slots/output_slots` 的 None 表示全部，空元组禁用该方向；`accepts(slot, resource)` 为输入过滤。提取不受输入过滤影响，已存物品即使不再允许输入也可按输出规则取出。动态缩容不会删除库存，只会阻止继续插入；恢复超容量快照会报错，需由宿主显式迁移。

| 端点方法 | 契约 |
| --- | --- |
| `get_slots()` | 返回可见槽位序号，不能假设连续 |
| `get_resource(slot, tx=None)` | 当前物品身份；空槽返回 None |
| `get_amount(slot, tx=None)` | 当前整数数量；传 tx 可读到暂存状态 |
| `get_capacity(slot, resource=None)` | 槽位总容量；指定身份时计入堆叠上限，输入被禁用/过滤则返回 0 |
| `is_valid(slot, resource)` | 是否允许该物品输入；不代表有剩余空间 |
| `insert(resource, amount, tx, slot=None)` | 返回实际插入数量；省略 slot 按配置输入槽顺序处理 |
| `extract(resource, amount, tx, slot=None)` | 返回实际提取数量；只匹配完整身份 |

内置 handler 另有 `storage_capacity(slot, resource=None)`，表示不含自动化方向/过滤的物理容量，供恢复校验使用；自定义端点无需提供它。

视图按公开协议委托，不要求暴露 cells。不加槽位/输入过滤时保留自定义端点的整体处理方式；限制槽位或插入过滤后会调用单槽方法。只支持整体处理的自定义端点必须明确拒绝不支持的单槽操作。外层视图不能恢复内层已禁止的权限。生命周期、实际插入容量、堆叠上限和参与存取的权限在提交时重验。

### 转移与优先合堆

```python
api.move_item(source, target, resource, amount, tx)
api.distribute_item(source, targets, resource, amount, tx)
api.insert_item_stacking(target, resource, amount, tx)
```

均返回实际整数数量。move/distribute 在可放弃子事务中模拟源端，目标按给定顺序接收，源端最终只扣实际接收量；源端无法提供相同数量时整次调用回滚。重叠的 storage_ids 被保守消重。用 `item_view(inventory, slots=(0,))` 和另一槽位视图可在同一库存内互转；不提供按槽身份的自定义端点保留完整身份集合，不虚构槽位独立性。

普通 bulk 插入遵循端点自身顺序。`insert_item_stacking` 是显式的单槽辅助：先补齐同身份的已有堆叠，再使用空槽；需要端点支持单槽操作。它是插入操作，不替调用者扣除来源库存。与 move/distribute 一样，它会随父事务放弃而撤销，不自行提交根事务。

物品端点可以选择实现 `normalize_resource(resource)`（自 1.3.0 起）。该方法只做与端点实际存储一致的无损身份规范化，返回符合物品身份协议的值；不接受 `tx` 参数，不修改资源、不通知，也不写世界。返回值应可与该端点 `get_resource` 返回的身份直接比较，并与其 `insert/extract` 解释保持一致。不提供该方法的普通端点继续使用核心身份，不会丢弃第三方附加字段。

`insert_item_stacking` 在比较非空槽之前，先在会放弃的探测子事务中调用该方法一次，然后用规范化身份进行已有堆叠匹配和后续插入。这样原生 API 返回的默认值或派生字段不会让同一实物被误判成不同堆叠。该字段存在但不可调用时抛 `TransactionError`；非法返回身份会被拒绝。

查询返回的物品代理和 `item_view` 校验生命周期后转发 `normalize_resource`；底层未实现时返回核心规范化后的原身份。转发不增加可见槽位或输入权限，各槽仍须通过现有视图过滤和底层规则。`move_item` / `distribute_item` 不会替所有端点统一改写身份，vanilla 的边界转换也不改变核心 `ItemResource` 的相等与快照契约。

```python
# 示例中只接受铁锭，上限明确为 64，不代表所有物品都能堆叠 64。
inventory = api.create_item_storage(
    {0: 64, 4: 64}, stack_limit=64,
    accepts=lambda slot, resource: api.get_item_id(resource) == "minecraft:iron_ingot")
water = api.create_fluid_storage({0: 1000})
with api.open_transaction() as tx:
    if (inventory.extract("minecraft:iron_ingot", 2, tx, slot=0) == 2 and
            water.extract("minecraft:water", 100, tx) == 100):
        tx.commit()
```

库存初始化、真实机器生命周期和按面 provider 示例见 [third_party_items.py](../examples/third_party_items.py)。宿主拓扑、tick 调度和持久化策略仍由宿主负责。用 `create_cell(read=..., apply=..., persist=..., changed=...)` 绑定旧缓存时，apply 必须只更新可回滚内存，persist/changed 在根提交后执行；不得在暂存阶段调用旧的立即写入接口。

### 物品快照

schema 1 格式为 `{"schema": 1, "slots": {"0": {"resource": 身份记录或None, "amount": "3"}}}`。身份记录为 `{"id": ID, "aux": "0", "properties": 属性记录}`。数量和 aux 使用规范十进制字符串；属性沿用带类型记录的树编码，增加 tuple 标签，其元素也编码成同质 dict 列表。磁盘快照没有 tuple、long、inf 或异构 list，不丢失大整数、附魔及小数属性。

`create_item_storage(capacities, stack_limit, saved=data)` 严格检查 schema、键、槽位集合、计数、身份和物理容量；不因当前输入过滤或只出方向拒绝已有库存。损坏或超量数据报错，不静默删物品。save 不受当前输入方向/缩容影响，返回完全脱离状态的原生字典。持久化时赋值 `bdata["example:items"] = api.save_item(inventory)`，不要只就地修改嵌套字典。真实落盘与重进仍需宿主验证。

## 游戏内验证

在游戏服务端、没有活动事务时调用 `api.run_self_tests()`。该方法使用独立内存存储，返回含 `ok`、`passed`、`failed` 和 `total` 的字典。验证自己的模组接入时，还需检查无前置启动、按面互通、区块卸载后重新查询、保存退出再进入后的储量。操作步骤见[游戏验收文档](VALIDATION.md)。
