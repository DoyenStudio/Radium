# 来源

## ToolDelta

`behavior_pack/radium_scripts/tooldelta` 直接取自 ToolDeltaMod 的 `lite` 分支，基准提交为 [a0320212beefa4c3ba0a861d9a22eb22d45d7811](https://github.com/SuperScript-PRC/ToolDeltaMod/tree/a0320212beefa4c3ba0a861d9a22eb22d45d7811)。

随包保留 `srv.py` 的 `CF` 和 `LEVEL_ID`、六个服务端事件的包装与监听，以及自定义方块移除事件的登记。radium 自行管理服务端系统和组件的生命周期。

上游 `BlockRemoveServerEvent.AddExtraBlocks` 将方块 ID 加入物品使用白名单。本地改为调用 `ListenOnBlockRemoveEvent`，让引擎为已登记方块发送移除事件。

该上游提交未附独立的许可证文件。工作区提供的版权与许可声明见 [LICENSE.workspace-source](LICENSE.workspace-source)。

## 设计参考

参考 D:/addon/jemods 中 NeoForge 26.3.x 的能力 provider、资源 handler 和事务思想（浅克隆 commit 3bb720446f9290c23eaf493a467a3eaaa93efe1b）。本库为网易 Python 2.7 环境重新实现，没有复制 NeoForge Java 源码，也不提供 Java 二进制或 API 兼容性。

1.2.0 物品能力进一步参考用户指定的 D:/gitclone/jemods/neoforge（同一 commit）的 `transfer/item/ItemResource.java`、`ItemStacksResourceHandler.java`、`transfer/ResourceHandler.java`、`StacksResourceHandler.java` 与 `ResourceHandlerUtil.java`：物品身份与数量分离、按身份计算容量、事务内槽位存取，以及显式优先合堆。上游版权为 NeoForged and contributors，SPDX `LGPL-2.1-only`。本次仍为独立 Python 实现，未复制或翻译 Java 源码。原生物品字典字段和附魔 tuple 格式曾参照当时随包附带的 [ToolDelta 物品定义](https://github.com/SuperScript-PRC/ToolDeltaMod/blob/ee005eb319b74fb9a6b649a9af38ad830cbb7c73/define/item.py)。
