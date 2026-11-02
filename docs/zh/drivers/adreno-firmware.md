# AdrenoFirmware

先按[适配流程](/zh/porting/gpu)准备板级输入、修改源码、接入构建并逐步验证。

Adreno GMU 固件和 HFI kit。加载 GMU 固件并使用 HFI 协议。

| 仓库 | 维护者 | 范围 |
| --- | --- | --- |
| [AdrenoFirmware](https://github.com/UniXNU/AdrenoFirmware) | [UniXNU](https://github.com/UniXNU) | Adreno GMU 固件和 HFI kit。加载 GMU 固件并使用 HFI 协议。 |

## 状态

Adreno740 使用它。

## 构建

板级 GPU 归档配方编译固件/HFI kit 并嵌入固定的本地固件镜像。提取路径、板级投票和启动检查点见 [GPU 适配](/zh/porting/gpu)。

开发中的启动接口可显式选择 A8xx 可变长度 TABLE 消息，并接收逐档依赖电源投票。软件模型检查覆盖线格式、A7xx 兼容性与失败处理。调用平台仍须提供经过核对的电源数据、已上电映射和一致性内存；这些检查不代表 A830 真机验证。

`AdrenoHfiGen8Votes` 按实际选中的主电源档位生成 MX/BX 依赖投票，检查索引宽度，并在出错时保留原输出。A7xx 投票接口保持原有语义。command-db 解析和 PKX110 六组 speed-bin 策略分别由 SM8750 与一加 13T 仓库提供。
