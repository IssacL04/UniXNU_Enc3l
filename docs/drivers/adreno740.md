# Adreno740

Start with the [adaptation procedure](/porting/gpu) for board inputs, source changes, build integration and verification order.

Adreno740 implements the A740 kernel GPU interface used by SM8550. It manages command submission, memory, fences, and GPU initialization. The SoC profile supplies shared GPU, GMU, and SMMU operations. Each board supplies signed firmware, power policy, reserved-memory adjustments, and display integration.

The recorded hardware target is sheng. Its stack uses 4 KiB SMMU translation, GMU firmware, a CP ring, fences, and GPU compositing into scanout.

## Runtime path

```mermaid
flowchart LR
  A[iPadOS app] --> B[QuartzCore and RenderBox]
  B --> C[AdrenoMetal plugin]
  C --> D[metal2vulkan]
  D --> E[Turnip]
  E --> F[NIR and IR3]
  F --> G[Darwin KMD]
  G --> H[Adreno740]
  H --> I[GMU, CP, SMMU and ring]
  I --> J[Adreno 740]
  J --> K[GPU composite to scanout]
  K --> L[GopFramebuffer]
```

1. AdrenoMetal publishes a Metal device through the system `MTLAddDevice` path. The published mode returns the device to backboardd, and listed processes receive their own device. It owns the Metal objects, encoders, IOSurfaces, events, fences and pipeline archives.
2. metal2vulkan translates AIR to SPIR-V and supplies pipeline descriptors, binding plans and function constants.
3. Turnip compiles SPIR-V through NIR to A740 IR3. Its Darwin KMD talks to the Adreno740 user client.
4. Adreno740 owns BOs, GPU addresses, the submission ring, fences and SMMU contexts. The GMU brings the GPU out of reset and applies power votes. The CP executes the IBs.
5. The plugin composites the finished frame into scanout pages. GopFramebuffer offers and retires the swap.

The runtime compiler chain is Metal, AIR, SPIR-V, NIR, IR3. AirNir is an offline direct AIR to NIR to IR3 compiler.

## Publish to the render server

`scripts/add-gpu-plugin-data.py` stages the plugin into a copy of the packed Data seed.

| Option | Effect |
| --- | --- |
| `--publish` | Writes `NativeAdrenoMetal.publish`. backboardd returns the native device to the original discovery, and CARenderServer composites the system UI through it. |
| `--clients NAME,...` | Writes `NativeAdrenoMetal.clients`. Each listed process gets its own device and driver connection. Up to two also get a 256 MiB GPU window and their own shader cache. `*` lists every process. |

The published device turns off backboardd's deep and compressed framebuffers. Patch `zzw-native-adreno-sandbox-grant` lets the accelerator service name the render server in `NativeSandboxGrantProcess`, so its user-client open passes the sandbox check.

Adreno740 serves one user-client core per connection. The render server gets a 1 GiB window at `0x20000000`, and up to two listed clients get 256 MiB each with their own queue range and teardown.

## Components

| Component | Role |
| --- | --- |
| `drivers/AdrenoMetal` | Metal frontend, metal2vulkan, command encoding, IOSurface and scanout client |
| `drivers/Adreno740` | GPU service, GMU/CP startup, user client, BO, VM, ring, submit and fence |
| `drivers/GopFramebuffer` | Swap offer, validation, retirement and scanout hand-off |
| `kits/AdrenoFirmware` | GMU HFI, startup, power votes and SQE firmware data |
| `kits/AdrenoPM4` | A740 PM4 state, constants, VPC and rasterizer packets |
| `kits/ArmSmmu4K` | Native 4 KiB tables, context, streams, live mappings and TLB maintenance |
| `kits/AirNir` | Offline AIR to NIR to IR3 compiler |

## State

| Step | Result |
| --- | --- |
| GMU cold start and HFI | works |
| GPU context and CP commands | works |
| Native 4 KiB SMMU context | active |
| Metal device discovery | works |
| GPU frame copy into scanout | works, pixel-identical |
| Render server compositing | works |
| Per-process Metal devices | works |
| GPU-composited desktop | works |

The GPU path covers discovery, command encoding, pipeline archives, IOSurface imports, fences, compositing and scanout. The render server and listed clients use the native device.

## Memory and TLB

| Item | Behavior |
| --- | --- |
| Objects per client | Limited by memory, found through a handle index |
| Owned BOs | System memory, as Metal resources: pageable memory with no kernel mapping, wired by `prepare()`. The VM zero-fills the pages and sets the write-combined attribute in one batch, and restores it on free. Client views map the BO's own descriptor. No fixed pool. Mapped without the alias check against existing ranges |
| Imported memory | Mapped without that check when every mapped import shares its cache class and none of its pages is in a BO of this driver (a page bitmap over DRAM); otherwise fully checked |
| Unmap | Up to 512 pages invalidated one by one, larger unmaps by ASID |
| Submission | No TLB invalidation; a stalled fence still invalidates |
| Boot log rows | `[vm map]`, `[vm unmap]`, `[vm kinds]`, `[bo memory]` |

## Shader compilation

The driver compiles the original UI shaders on the device:

1. `default.metallib` carries AIR plus Apple GPU machine code. The AIR feeds the translation path.
2. metal2vulkan translates AIR to SPIR-V, then Turnip compiles IR3 at pipeline creation.
3. A cold boot compiles every UI variant it reaches. int-148: 77 pipelines, about 43 s, cache hit 0. int-150: 103 Metal pipelines, 40.1 s total, 1.40 s max; 94 Vulkan pipelines, 23.3 s.
4. Patch `0004` specializes the QuartzCore uber shaders and folds constant loads before inlining. Patch `0005` keeps recent module decodes and device-profile fingerprints. The pipeline journal records each render pipeline creation.

Implemented mitigations:

| Mitigation | Effect |
| --- | --- |
| NDEBUG release build | Removes per-pass Mesa assertions and NIR validation. |
| metal2vulkan patch `0004` | Specializes and prunes QuartzCore uber shaders before Vulkan compilation. |
| metal2vulkan patch `0005` | Keeps recent module decodes and device-profile fingerprints. |
| Priming cache | Caches runtime startup entry-point work. |
| `m2vpack` export and import | Reuses earlier compiled pipeline caches; the export is incremental. |
| Turnip builtin pack | Embeds clear, blit and empty shader variants. |
| Pipeline journal | Records per-pipeline CPU and system time, page faults and context switches. |

The cache chain covers runtime startup and the UI variants an earlier boot exported. A new UI variant compiles once, then enters the exported cache.

## Build

```sh
python3 scripts/build-turnip-darwin.py --target ios
python3 scripts/build-adreno-metal-plugin.py
python3 scripts/add-gpu-plugin-data.py --publish --clients <name,...> <seed>.dbr <output>.dbr
```

The staging script output is the Data seed for `unixnu build payload --data-ramdisk`.

Host checks:

```sh
python3 scripts/check-native-metal-frontend-host.py
python3 scripts/check-turnip-darwin-host.py
python3 scripts/check-smmu4k-live.py
python3 scripts/check-turnip-pipeline-cache-host.py
python3 scripts/check-priming-cache-host.py --output build/priming-cache/run
python3 scripts/probe-turnip-internal-compiler-host.py --qualification <old> --output <new>
```

The device repository adds the original-input checks:

```sh
python3 scripts/build-adreno-compiler-host.py --probe
python3 scripts/build-turnip-ios-compiler-peer.py
python3 scripts/check-turnip-ios-compiler-cache.py
python3 scripts/check-quartzcore-turnip-cache-host.py
```

## Related

- [Xiaomi Pad 6S Pro (sheng)](/devices/sheng)
- [XNU drivers](/drivers/xnu-drivers)
- [Four-kilobyte pages](/xnu/four-k-page-tables)

The development helpers accept A830 chip ID `0x44050001` for ring/CP, IRQ, timestamp and six-buffer GPU contexts. The larger SQE buffer and separate AQE buffer have executable mappings. `NativeAdrenoA830HwInit` programs Gen8 protection, UBWC and restore state, then requires ZAP authentication and a secure-exit fence before readiness. The OnePlus 13T board package connects power, GMU, SMMU and service publication. Both generations pass software-peer regressions through `scripts/check-adreno-a830.py`. Earlier OnePlus 13T candidates built and prelinked successfully, reached GPU readiness and completed GPU presentation with user-confirmed UI startup. The new parity candidate still requires production and device qualification.

The development source exposes `native_adreno_diagnostics` through `NativeAdrenoDiagnostics.h`. The nonblocking snapshot reports plugin connections, the latest opener, core calls/status and submit/fence counters. A busy GPU lock returns the last successful sample with `cached=1`; before the first sample, during snapshot contention or without a published service, the output stays untouched and the function returns false. Core method/status are paired; fence poll misses include zero-timeout incomplete waits and do not count only stalled jobs. Boards can display these counters without waiting on GPU execution; they do not measure display FPS or prove pixel correctness.

Ordinary user BOs use wired system-backed pages without a reserved BO pool, a task mapping or a permanent kernel mapping. Allocation and release happen outside the shared device lock. Explicit contiguous allocations retain their requirement. The user-client software-peer regression covers fragmented pages through map, submit and retirement; it does not measure hardware performance.

Diagnostics also retain the latest nonzero core method/status pair across later successful calls. It is historical evidence and may record an ordinary timed wait; the method identifies which operation returned it.

The Run 88 OnePlus 13T candidate adopts GPU-parity system BOs, per-process page tables and Metal buffering while preserving A830 SQE/AQE and Gen8 counter differences. Metal reports six configured SPs and the board requests its original 389 MHz OPP. Active cores, achieved frequency and stable 60 FPS remain unverified.

The main update to a9a2cbb retains the upstream A740 two-ring preemption implementation. A830 explicitly rejects that preemption setup and keeps its six-buffer Gen8 context, SQE/AQE mappings, reset/table packets and counter address. On iPadOS 17 headers without GPU-role APIs, submit priority uses the existing foreground fallback; newer headers retain the upstream role policy.

An opt-in GPU trace ABI now retains bounded command/fence/import records, build identity and completion-tagged pixel samples. User records are stamped with the caller PID; stage-3 scanout samples are kernel-only. The shared ABI is checked against AdrenoMetal and the OnePlus NativeMobileDisplay presenter. The A830 single-ring policy and Gen8 setup are unchanged; no A740 preemption policy is enabled by diagnostics. The OnePlus board owns export into volatile RAM Data, while its UFS driver remains read-only.
