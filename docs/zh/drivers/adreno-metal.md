# AdrenoMetal

先按[适配流程](/zh/porting/gpu)准备板级输入、修改源码、接入构建并逐步验证。

AdrenoMetal 通过 metal2vulkan 和 Turnip 提供 Metal 前端。它通过 `MTLAddDevice`
发布设备，翻译 AIR，并向内核 GPU 接口提交任务。

| 字段 | 值 |
| --- | --- |
| 仓库 | [UniXNU/AdrenoMetal](https://github.com/UniXNU/AdrenoMetal) |
| 实现 | A740/SM8550 图形栈和所选 OS ABI |
| 依赖 | Adreno740、Turnip、metal2vulkan、IOGPUFamily 和 IOSurface 接口 |
| 板级输入 | 固件、电源策略、内存布局、显示集成 |
| 已验证设备 | sheng |
| 运行时插件 | `NativeAdrenoMetal` |

sheng 已运行 GPU 合成桌面。导出的 pipeline cache 可在后续启动复用。桌面空闲时，
render server 会预编译系统镜像中的全部 Metal 库：payload 带有库列表
（`NativeAdrenoMetal.primelist`），以及一份 cryptex 中 QuartzCore 库的副本，因为
render server 的沙盒访问不到 cryptex 路径。120 Hz 下空闲桌面每 250 ms 提交约
6 个命令缓冲区，所以只有超过 8 个时预编译才会等待。日志 PR 行显示进度；sheng 上
162 个库已全部预编译。有列表时 render server 不扫描目录，并且只在显示空闲时读取
每个库。
列表、pipeline 包和续编译规则见[预热着色器缓存](/zh/porting/gpu#shader-warmup)。

无法编码的 render pass 仍返回 encoder，并拒绝其命令缓冲区：RenderBox 会缓存
encoder 的方法，不能接受 nil。每个进程的第一个问题由出错
的线程写入驱动的进程文本行。

```sh
python3 scripts/build-turnip-darwin.py --target ios
python3 scripts/build-adreno-metal-plugin.py
```

运行时流程、发布命令和检查见 [Adreno740](/zh/drivers/adreno740)。

构建一加 13T 的 A830 候选插件时，给插件构建脚本传入 `--chip a830`。即使构建目录残留生成的回放头文件，该选项也会排除 A740 专用命令回放；Turnip 继续根据实际设备信息生成命令。设备仓库的 `build-metal-userspace.py` 准备固定版本的源码、构建 iOS 库和插件，再生成独立 Data seed 与 owner trust bundle。Turnip、Metal 桥接库、插件和探测程序已通过正式 iOS 编译及相应签名检查。一加 13T 镜像已在真机观察到 GPU 提交和呈现；Run 88 已启动并改善交互，SYSMEM 对照恢复正常颜色。诊断区域修复和持续动画性能仍待设备验证。

scanout 线程退出时会关闭 handoff 连接。板级 presenter 可实现可选的关闭接口，释放待处理帧并通知显示回退。

堆资源的 alias 操作、所属 heap 和 offset 现转发到锁定运行库，允许自动 heap 在旧对象仍保留时复用存储。真实前端/Rust 主机回归及旧代码对照覆盖复用和销毁；手机 GPU 性能仍需单独测试。

OnePlus 13T 的 Run 88 候选接入 GPU parity 分支的系统 BO、每进程页表和 Metal 缓冲区复用，保留 A830 的 SQE/AQE 与 Gen8 计数器差异。Metal 报告六个已配置 SP，板级通过原机 OPP 请求 389 MHz；实际活动核心数、频率和稳定 60 FPS 尚未验证。

插件构建器在 Rust bridge 编译前检查插件、frontend 和 probe 的语法。iPadOS 27 的 framebuffer 分支实验及其辅助函数只在 arm64e 构建中启用。

一加 13T 的后续修正将协商的日志保留区域用于 BGRA 计算拷贝和半浮点转换。Run 90 的实际 macOS/MoltenVK 逐像素检查已通过，覆盖无保留区、中间保留区、整帧保留区及行尾留白；设备日志可读性待验证。

一加 13T 的 Run 88 SYSMEM 对照已在设备上恢复正常颜色。候选配置使用 `sheng-tu-debug=sysmem,nocb`，等待 A830 GMEM 正确性验证。用户反馈流畅时约 30-60 FPS，控制中心和冷启动仍卡顿，持续帧率尚未测量。

A830 性能候选关闭默认追踪，给 iOS 工作线程应用 QoS，并在 SYSMEM 使用非 lazy 附件内存。上游完整运行时补丁序列已按固定 translator 校验。120 Hz 软件呈现请求仍需实测帧率和面板刷新；Run 90 已由用户确认颜色正常、日志完整。

main-3 基线集成 AdrenoMetal 831a9dc 及上游 24 个运行时补丁。首帧之后的呈现标记和周期 PF 文本需显式开启诊断。可选 40 字节完成消息附带依赖等待、编码/导入、提交、完成等待和运行时 GPU 时间戳差；旧内核拒绝扩展后退回原 16 字节消息。内核另统计 offer 到交付的时间及实际软件 VSYNC 通知频率。缺少 GPU 时间戳时显示未知；主机 Vulkan 驱动可能提供主机时钟区间。Run 91 在一加 13T 上约 40 次 GPU 呈现/秒，120 FPS 与物理面板时序仍未验证。

A830／iPadOS 17 候选现可让同 UID、具备写入权限的进程共享按版本区分的着色器缓存；共享目录不可用时继续使用容器缓存。导入临时文件使用进程和序列标识，避免并发覆盖。26 个运行时补丁加入函数专用链接名称、大型索引常量的共享存储和实际分配大小查询；前端补齐纹理通道重排视图、函数常量查询、描述符异步回调、mip／slice 范围复制、多 viewport／scissor 及命令队列容量。默认保留调用方请求的多重采样。

可选帧诊断通过明确 ID 关联 Metal 命令、运行时／Vulkan 命令、内核 fence 和扫描输出请求。IOSurface 仅在命令成功完成后采样，并保留原始像素及色彩元数据；一加 presenter 另外采样已完成 GPU 拷贝的扫描输出映射。采集时开启 `sheng-gpu-trace=1 sheng-gpu-pixels=1`。上述新增路径已接入主机检查，实机效果和性能仍待验证。

[OnePlus Metal run 8](https://github.com/IssacL04/UniXNU-Pagani_SM8750/actions/runs/41502995541) 已通过缓存／追踪／presenter 检查、两项编译器回归、heap 与 scanout 像素检查，以及 normal／single 两种接口测试。产物使用 run 5 重新完整编译的内核和 run 6 构建签名的 A830／iPadOS 17 用户态。主机接口测试关闭 MoltenVK placement heap，避免 AppleParavirt 在共享纹理 CPU 上传时崩溃；生产分配策略不变。
