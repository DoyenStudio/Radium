# radium

radium 1.3.0 是网易我的世界服务端（Python 2.7.13）的可选前置库，为模组提供物品、流体和 FE 的事务接口。

能量统一使用 FE，储量、容量、传输量、每次调用限额和回调数量均以 FE 计。

各模组通过同一套公开接口接入。机器可以注册资源端口，管道可以查询端口并发起搬运。两种用法见[接口文档](docs/API.md)。

## 安装与可选获取

将本项目的行为包与资源包导入开发环境。radium 启动时注册并在 levelId 上创建唯一服务端组件：

```python
import mod.server.extraServerApi as serverApi

api = serverApi.GetComponent(serverApi.GetLevelId(), "radium", "transfer")
if api is None:
    # 前置未安装或尚未初始化：使用方继续自己的原有流程。
    pass
elif api.API_VERSION[0] == 1:
    # 使用 radium v1。
    pass
```

使用方不需要导入 `radium_scripts`，不调用 `CreateComponent`，不声明强制 manifest 依赖。请在所有附加包脚本加载结束后获取，或首次业务调用时惰性获取；不要把早期的 `None` 永久缓存。客户端没有资源写入组件。

## 已提供

- 物品 ID、aux 与完整附加数据组成的不可变身份，数量独立；支持原生物品字典往返及附魔 tuple。
- 物品稀疏槽位、宿主提供的堆叠上限、方向/物品过滤、共享视图、按序转移与优先合堆，以及 NBT 安全快照。
- 非负整数 FE 存储、组合存储、只入/只出视图、虚空接收端和每次调用限额。
- 流体 ID + 可选不可变属性身份、浮点 mB 存储、稀疏槽位、输入/输出槽过滤、资源过滤、共享存储视图和显式无限源。
- 有限流体按实际可表示的储量差返回数量，精度不足时少接收或返回 0；源端和目标总量严格核对。
- 委托视图可包装查询代理、组合能源、自定义端点和其他视图，保留原端点限制与特殊存取规则。
- 物品、FE 与流体共用一个事务：嵌套提交只合并到父事务，最外层提交才统一更新内存、持久化并通知。
- `move_item`、`move_energy`、`move_fluid` 及按调用方给定顺序分配的 `distribute_*`；识别共享 Cell，避免同一控制器的别名端口重复参与。
- 按能力、方块 ID、维度、坐标和目标绝对面查询；只查询已加载区块，不创建机器。
- 默认注册原版容器 provider：普通箱、陷阱箱、铜箱八种变体、木桶、潜影盒、漏斗、发射器、投掷器，以及按面存取的三类炉和酿造台；双箱两半共享库存身份。
- 炼药锅提供容量 1000mB 的流体端口，水按原版六级水位量化，熔岩只接受整桶存取；量化转移会协商双方能共同接受的数量。
- 原生容器采用提交前复核、同步写入回读与失败补偿；不能确认恢复时以 `RecoveryError` 隔离相关库存，禁止自动重放。
- 原生 NBT 安全快照：FE 大整数分解为 int32 数组，流体 schema 2 用 hex 字符串保留完整浮点数量和属性，兼容读取 schema 1，永不写入 `long` 或 `inf`。
- 仅游戏解释器运行的独立内存自测，不访问或改变真实机器。

本库不维护电线/管道拓扑，不自行搬运资源，不规定 tick 频率、全网预算或公平策略。调用方决定优先级、速率和网络行为。原版包装不接管原版加工、漏斗节拍或红石行为；不含玩家充电、桶交互或热量能力。物品接入见 [API 文档](docs/API.md#物品能力自-120-起)及[物品宿主示例](examples/third_party_items.py)。

## 原版容器（vanilla）

安装后即可用 `query(api.ITEM, dimension, pos, face)` 查询受支持的原版库存，用 `query(api.FLUID, dimension, pos, face)` 查询炼药锅；无需使用方额外注册或导入脚本。内置 provider 遵循现有注册冲突规则，不允许另一回调静默覆盖。

水位 0～6 对应 `0/167/333/500/667/833/1000 mB`，每次返回完整水位差。熔岩一次至少需要 1000mB 的来源、目标空间和传输预算；不足一档或一桶返回 0，不跨调用积累预算。末影箱、未展开战利品的容器，以及装有药水、染色水、细雪等不支持内容的锅不开放端口。

原生读写不是引擎级跨容器原子事务。失败且完整补偿后可重新查询；发生 `RecoveryError` 时应停止使用相关库存，依据诊断人工核对修复后再重载，不自动重试。各类面规则、物品 NBT 规范化和数量协商契约见 [原版容器接口](docs/API.md#原版容器适配自-130-起)。

## 最小事务

```python
energy = api.create_energy_storage(10000, amount=1000)
tank = api.create_fluid_storage({0: 4000, 3: 4000})

with api.open_transaction() as tx:
    if (energy.extract(80, tx) == 80 and
            tank.insert("minecraft:water", 250.0, tx, slot=0) == 250.0):
        tx.commit()
# 任一步不足，离开 with 时放弃本次扣费和注水。
```

精确配方必须检查每一步返回的实际数量，只有全部满足才 commit。转移方法返回实际移动量，不返回 overflow。详见 [API 与契约](docs/API.md)、[独立机器示例](examples/third_party_machine.py) 和 [游戏验收](docs/VALIDATION.md)。

## 构建

在项目目录运行 `powershell -ExecutionPolicy Bypass -File .\pack.ps1` 生成 `addon.zip`。打包仅压缩文件，不执行或编译项目 Python。输出已被 .gitignore 排除。

## 验证状态

隔离自测、原生容器读写和保存重进检查均在游戏 Python 2.7.13 环境中执行。结果及待验收项目见[游戏验收记录](docs/VALIDATION.md)。

radium 内置一份直接从 ToolDeltaMod `lite` 分支裁剪的服务端副本，只保留服务端常量和事件监听所需代码。上游版本和本地修改见 [THIRD_PARTY.md](THIRD_PARTY.md)。
