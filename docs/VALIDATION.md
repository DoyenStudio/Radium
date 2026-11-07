# 验证与验收

日期：2026-11-06。版本：1.3.0。测试解释器：当前游戏服务端 Python 2.7.13。

## 已完成

| 验证组 | 结果 | 覆盖范围 |
| --- | --- | --- |
| 隔离回归 | 166/166 | 原有70项；原生参与者25项、量化16项、锅11项、物品转换14项、面规则8项、假引擎后端22项 |
| 真实普通容器 | 32/32 | 普通/陷阱箱、八种铜箱、木桶、全部潜影盒颜色及通用ID、漏斗、发射器、投掷器；全部槽位、覆盖/清空、1/16/64堆叠上限 |
| 真实双箱 | 80/80 | 普通/陷阱/八种铜箱，四方向、两种放置顺序；全部54槽，两半相同槽序与身份 |
| 真实加工容器、锅、物品数据 | 64/64 | 炉三类及燃烧变体6项、酿造台1项、水位组合49项、熔岩1项、物品数据7项 |
| 真实失败与生命周期 | 8/8 | 写入实际发生后返回失败，普通箱、桶、铜双箱、炉、酿造台和锅恢复；外部原生改槽冲突；合箱/拆箱拒绝旧事务 |
| 保存重进 | 12个方块快照一致 | 普通箱、打蜡铜双箱两半、水667mB、熔岩1000mB及支撑/雨棚；完整引擎重载前后NBT、库存快照、配对和状态一致 |

真实容器检查合计 176 项，另有 8 项失败与生命周期检查。测试使用维度 0 的独立空区 `x=-24..-17, y=99..102, z=10..16`。每次先确认测试位置已加载且为空气，结束后清除测试物品和方块，并检查场地已恢复。

保存重进样本包含名称、附魔、剩余耐久和extraId的钻石剑；内含27槽、每槽64个石头的潜影盒物品；铜双箱54槽不同数量的物品；普通水与熔岩。物品数据组另验证userData和收纳袋自定义标记。**收纳袋标记往返不等于实际填充收纳袋的内容验收。**

## 引擎实测与修正

- 普通容器和八种铜箱的GetContainerSize、GetContainerItem(getUserData=True)、SpawnItemToContainer可用，当前使用此后端。炉和酿造台的通用容量不可用，使用完整NBT快照，仅修改Items。
- GetChestPairedPosition属于BlockInfo。方块朝向用GetBlockAuxValueFromStates获取，面编号不能直接作为aux。双箱以字典序最小坐标访问全54槽。
- 双箱重进后按半箱调用SetBlockEntityData不能可靠定位库存。因此普通容器补偿也通过同一槽位API，逆序恢复并核验完整前像，无失败后切换NBT重试。该问题在保存验收清理阶段发现，随后已通过槽位API清理并复核设施。
- 原生槽位写入会添加forceunpair记账字段；快照仅忽略该字段，实际配对单独复核。Block palette和附加字段不能无损转换时拒绝端口/操作。
- 原生NBT写入可同步改变炉燃烧标志；同类型lit/unlit共享物理身份，熔炉、烟熏炉和高炉之间仍区分。
- 原版漏斗跨真实tick对照：炉顶接受原料槽物品；侧面接受木板、煤块，拒绝绯红木板和空桶；底面可抽燃料槽空桶。酿造台侧面输入空瓶和烈焰粉、顶面输入原料；底面抽槽1～3药水，**不抽槽0的龙息残留玻璃瓶**。

## 事务验证

166项隔离回归保留原70项，覆盖模拟/嵌套放弃零写入、prepare顺序、原生写入回读、失败者参与逆序补偿、补偿失败隔离全部相关Cell/owner、日志回调失败不掩盖结果、提交重入拒绝、自身失效延迟、外部改库存、双箱共享/卸载/配对变化、量化多目标守恒与权限、普通端点错误语义及第三方物品身份保留。

真实故障注入只包装独立测试服务的引擎代理，先调用实际setter，再令该次返回False。六类容器均抛普通TransactionError，完整前像恢复且无隔离记录。数量一致但NBT不同、第三状态冲突和补偿再次失败的隔离分支由假引擎/core测试覆盖，没有在玩家设施上制造不可恢复损坏。

原生跨容器写入是同步补偿，不承诺引擎层绝对原子性。RecoveryError后禁止自动重放或解封，需依据诊断核对修复后重载。

## 复现与检查

生产组件完整重载后，在游戏服务端执行：

```python
import mod.server.extraServerApi as serverApi
api = serverApi.GetComponent(serverApi.GetLevelId(), "radium", "transfer")
assert api.API_VERSION == (1, 3, 0)
result = api.run_self_tests()
assert result["ok"] and result["total"] == 166
```

开发脚本位于 `devtools/`。`isolated_tests.py` 隔离载入工作区源码。`native_validation.py`、`native_failure_validation.py` 和 `hopper_validation.py` 验证原生容器、失败恢复和漏斗行为。`persistence_validation.py` 在保存前执行 `seed`，重进后执行 `verify_and_cleanup`。异步报告标记 `done=True` 后才可重载或复用测试区。

Git 忽略的 `.cache/` 目录保存了本次验收使用的报告，包括 `native_ordinary_full.json`、`native_double_validation.json`、`native_processing_validation.json`、`native_failure_validation.json` 和 `persistence_fixture.json`。早期失败报告保留供诊断。

静态审查radium包37个文件：37可解析，0 fail、0 risk；3条warning为参数数量和重复测试收集器，6条hint包含参数数量及故障恢复异常收集。git diff --check通过。manifest、入口与API统一1.3.0，4个UUID唯一。完整重载后的实际生产组件自测166/166，faults=0。打包成功，共123个归档条目，含8个vanilla模块文件；字节码缓存、开发脚本、报告、Git/Studio数据均未进入包，addon.zip保持Git忽略。

## 尚未实测

- 实际装有物品的原版收纳袋：当前背包没有可复制的真实样本，未猜造未知内容格式；普通userData和满潜影盒物品已验证。
- 铜傀儡实际取放、玩家GUI同时点击、真实区块卸载的竞争：原生外部改槽、配对变化及假引擎卸载已测，不等同于上述实际行为。
- 单独仅装radium、完全移除radium后的消费方启动、旧版FE/流体宿主存档迁移：原70项隔离回归通过，本次未更换当前游戏模组集合或使用其他宿主存档。

上述项目不标记为通过。无法无损转换的新增模组物品会被拒绝，具体兼容性应使用真实样本追加验证。

## ToolDelta 服务端裁剪（2026-11-07）

本次使用包含 radium 1.3.0 开发改动的工作区验收。在游戏服务端 Python 2.7.13 重载行为包后，通过 `GetComponent(levelId, "radium", "transfer")` 取得生产组件，166 项自测全部通过。再次重载后，六个引擎事件仍各有一个监听器，模拟 tick 正常推进。客户端未注册 `radium.TDClient`，也未载入 ToolDelta 客户端模块。

在空测试区放置并移除木桶，收到一次 `BlockRemoveServerEvent`，注册表代数增加 1，随后确认测试区已恢复。游戏内另用独立系统实例连续调用两次 `Destroy`，确认只执行一次收尾 tick 和失效处理，并清空 provider、释放组件引用。裁剪后的归档共 50 个文件，其中 ToolDelta 占 9 个，含来源与许可说明。
