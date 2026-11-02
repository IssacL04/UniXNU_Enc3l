# AdrenoMetal

Start with the [adaptation procedure](/porting/gpu) for board inputs, source changes, build integration and verification order.

AdrenoMetal provides the Metal frontend through metal2vulkan and Turnip. It
publishes a device through `MTLAddDevice`, translates AIR, and submits work to
the kernel GPU interface.

| Field | Value |
| --- | --- |
| Repository | [UniXNU/AdrenoMetal](https://github.com/UniXNU/AdrenoMetal) |
| Implementation | A740/SM8550 graphics stack and the selected OS ABI |
| Dependencies | Adreno740, Turnip, metal2vulkan, IOGPUFamily and IOSurface interfaces |
| Board inputs | Firmware, power policy, memory layout, display integration |
| Verified device | sheng |
| Runtime plugin | `NativeAdrenoMetal` |

sheng runs the GPU-composited desktop. Exported pipeline caches are reused across
boots. The render server primes every Metal library of the OS image while the
desktop is idle: the payload carries the list (`NativeAdrenoMetal.primelist`) and
a copy of the cryptex QuartzCore library, which the render server's sandbox
cannot reach. The idle desktop submits about 6 command buffers per 250 ms at
120 Hz, so priming waits only above 8. The PR log row shows its progress; all
162 libraries are primed on sheng. With the list present the render server does
not scan directories, and each library is read only while the display is quiet.
The lists, the pipeline pack and the resume rules are in [Warm the shader caches](/porting/gpu#shader-warmup).

A render pass that cannot be encoded still returns an encoder, and its command
buffer is refused: RenderBox caches encoder methods and cannot take nil. The first problem of each process is written to the driver's
per-process text line from the thread that hit it.

```sh
python3 scripts/build-turnip-darwin.py --target ios
python3 scripts/build-adreno-metal-plugin.py
```

See [Adreno740](/drivers/adreno740) for the runtime path, staging commands, and checks.

For the OnePlus 13T A830 candidate, pass `--chip a830` to the plugin builder. This excludes the A740-only recorded command replay even if its generated header remains in the build tree. Turnip still generates commands from the actual device information. The device's `build-metal-userspace.py` prepares the pinned sources, builds the iOS library and plugin, and stages a separate Data seed with its owner trust bundle. Production iOS compilation and signing checks have passed for Turnip, the Metal bridge, the plugin and its probe daemon. OnePlus 13T images have shown GPU submissions and presentation on device; Run 88 boots with improved interaction, and its SYSMEM control restores normal colors. Run 91 confirms correct colors and readable diagnostics at about 40 GPU presentations/s; sustained 120 FPS remains unverified.

When the scanout worker exits, its handoff connection closes. Board presenters can implement the optional close hook to release an outstanding frame and notify display fallback.

Optional heap aliasing now forwards buffer/texture/view ownership and offsets to the pinned runtime, allowing automatic heaps to reuse storage while old objects remain retained. The real frontend/Rust host regression and old-code control cover reuse and destruction; this is separate from phone GPU performance.

The Run 88 OnePlus 13T candidate adopts GPU-parity system BOs, per-process page tables and Metal buffering while preserving A830 SQE/AQE and Gen8 counter differences. Metal reports six configured SPs and the board requests its original 389 MHz OPP. Active cores, achieved frequency and stable 60 FPS remain unverified.

The plugin builder checks the plugin, frontend and probe syntax before Rust bridge compilation. The iPadOS 27 framebuffer branch experiment and its helper are compiled only for arm64e.

The OnePlus 13T scanout follow-up applies the negotiated diagnostic band to opaque BGRA compute copies and half-float conversion. Pixel checks cover empty, middle and full bands and padded rows; the actual macOS/MoltenVK regression passed in Run 90; Run 90 and Run 91 device feedback confirms readable diagnostics.

The OnePlus 13T Run 88 SYSMEM control restored correct colors on device. Its candidate profile now uses `sheng-tu-debug=sysmem,nocb` pending A830 GMEM validation. Interaction is reported around 30-60 FPS with control-center and cold-launch stalls; sustained frame rate has not been measured.

The A830 performance candidate uses opt-in profiling, iOS worker QoS and non-lazy SYSMEM attachments. The upstream runtime patch series is checked against the pinned translator. Its 120 Hz software pacing does not qualify panel refresh or sustained FPS; Run 90 confirms correct colors and readable diagnostic rows on device.

The main-3 baseline integrated AdrenoMetal 831a9dc and the upstream 24-patch runtime series. Scanout markers and periodic PF text are opt-in after the first frame. Optional 40-byte completion records carry dependency-wait, encode/import, submit, completion-wait and runtime GPU timestamp durations; a size/unsupported refusal falls back once to the legacy 16-byte record. Kernel offer-to-delivery time and observed software VSYNC rate are reported separately. A missing GPU timestamp remains unknown; a host Vulkan driver may report a host-derived interval. Run 91 showed about 40 GPU presentations/s on OnePlus 13T, so 120 FPS and physical panel timing remain unqualified.

The A830/iPadOS 17 candidate now shares version-keyed shader caches between writable processes of the same UID, with container-local fallback when the shared directory is unavailable. Unique temporary import files prevent concurrent cache import collisions. The 26-patch runtime series adds specialized function names, shared storage for large indexed constants and allocation-size queries; the frontend adds swizzled texture views, function-constant reflection, asynchronous descriptor selectors, mip/slice range copies, viewport/scissor arrays and command-queue limits. Requested multisampling remains the default.

Optional frame diagnostics link Metal command IDs, runtime/Vulkan commands, kernel fences and the board's scanout request. Completed IOSurface samples retain raw texels and color metadata; the OnePlus presenter adds bounded samples of its completed GPU scanout mapping. Enable `sheng-gpu-trace=1 sheng-gpu-pixels=1` only when collecting a trace. These additions are host-tested; their device behavior and performance still require measurement.
