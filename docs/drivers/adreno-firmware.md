# AdrenoFirmware

Start with the [adaptation procedure](/porting/gpu) for board inputs, source changes, build integration and verification order.

Adreno GMU firmware and HFI kit. Loads the GMU firmware and speaks the HFI protocol.

| Repository | Maintainer | Scope |
| --- | --- | --- |
| [AdrenoFirmware](https://github.com/UniXNU/AdrenoFirmware) | [UniXNU](https://github.com/UniXNU) | Adreno GMU firmware and HFI kit. Loads the GMU firmware and speaks the HFI protocol. |

## State

Used by Adreno740.

## Build

The board GPU archive recipe compiles the firmware/HFI kit and embeds the pinned local firmware images. Follow [GPU adaptation](/porting/gpu) for extraction paths, board votes and startup checkpoints.

The development startup interface selects the A8xx variable TABLE message explicitly and accepts per-level dependency votes. Software-peer checks cover its wire layout, A7xx compatibility and failure handling. The consuming platform must supply validated rail data, powered mappings and coherent memory; no A830 hardware result is implied.

`AdrenoHfiGen8Votes` derives MX/BX dependency votes from the selected primary corner, validates index widths and preserves output on error. The A7xx vote interface keeps its existing semantics. Command-db parsing and the six PKX110 speed-bin policies belong to the SM8750 and OnePlus 13T repositories.
