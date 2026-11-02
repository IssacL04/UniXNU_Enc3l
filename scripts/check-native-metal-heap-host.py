#!/usr/bin/env python3
"""Check Metal heap reuse and scanout against a host Vulkan loader; no phone GPU claim."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--loader', type=Path, required=True)
args = parser.parse_args()
if sys.platform != 'darwin' or not args.loader.is_file():
    parser.error('Requires macOS and a host Vulkan loader')
subprocess.run([sys.executable, root / 'scripts/build-adreno-metal-bridge.py', '--target', 'host'], check=True)
kit = root / 'drivers/AdrenoMetal'
out = root / 'build/metal-heap-host'
out.mkdir(parents=True, exist_ok=True)
cache = out / 'cache'
cache.mkdir(exist_ok=True)
original = (kit / 'NativeBridgeMetalFrontend.mm').read_text()
negative = original
for kind in ('buffer', 'texture'):
    call = f'nmb_{kind}_make_aliasable(_handle)'
    assert negative.count(call) == 1
    negative = negative.replace(call, 'true /* missing alias transition */')
for label, source in [('fixed', original), ('old', negative)]:
    path = out / (label + '.mm')
    path.write_text(source)
    exe = out / label
    subprocess.run(['xcrun', 'clang++', '-std=c++17', '-O1', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-Wno-deprecated-declarations', '-DNATIVE_ADRENO_SP_CORES=6', '-I', kit,
                    path, kit / 'bridge/heap_aliasing_host.mm',
                    root / 'build/adreno-metal-bridge/host/libadreno_metal_bridge.a',
                    '-framework', 'Foundation', '-framework', 'Metal', '-framework', 'IOSurface',
                    '-framework', 'CoreFoundation', '-o', exe], check=True)
    env = dict(os.environ); env.pop('SHENG_DIAG', None)
    result = subprocess.run([exe, args.loader.resolve(), cache], env=env, text=True, capture_output=True, timeout=120)
    (out / (label + '.log')).write_text(result.stdout + result.stderr)
    if label == 'fixed':
        if result.returncode or 'PASS:' not in result.stdout:
            raise SystemExit('Heap reuse failed: ' + (result.stdout + result.stderr)[-6000:])
        print(result.stdout, end='')
        enabled = subprocess.run([exe, args.loader.resolve(), cache], env=dict(env, SHENG_DIAG='1'),
                                 text=True, capture_output=True, timeout=120)
        (out / 'diagnostics.log').write_text(enabled.stdout + enabled.stderr)
        if enabled.returncode or 'PASS: completion handler QoS' not in enabled.stdout:
            raise SystemExit('Enabled diagnostics failed: ' + (enabled.stdout + enabled.stderr)[-3000:])
        print('PASS: runtime diagnostics enabled in a separate process')
    elif result.returncode != 1 or 'first.isAliasable && heap.usedSize==8192' not in result.stderr:
        raise SystemExit('Old-code control failed unexpectedly: ' + (result.stdout + result.stderr)[-3000:])
    else:
        print('PASS: missing alias transition fails retained-resource reuse')

scanout = out / 'scanout'
subprocess.run(['xcrun', 'clang++', '-std=c++17', '-O1', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-parameter', '-Wno-deprecated-declarations', '-DNATIVE_ADRENO_SP_CORES=6', '-I', kit,
                '-I', root / 'drivers/NativeMobileDisplay', '-I', root / 'drivers/GopFramebuffer',
                kit / 'NativeBridgeMetalFrontend.mm', kit / 'bridge/scanout_host.mm',
                root / 'build/adreno-metal-bridge/host/libadreno_metal_bridge.a',
                '-framework', 'Foundation', '-framework', 'Metal', '-framework', 'IOSurface',
                '-framework', 'CoreFoundation', '-o', scanout], check=True)
result = subprocess.run([scanout, args.loader.resolve(), cache], text=True, capture_output=True, timeout=120)
(out / 'scanout.log').write_text(result.stdout + result.stderr)
if result.returncode or 'PASS:' not in result.stdout:
    raise SystemExit('Scanout failed: ' + (result.stdout + result.stderr)[-6000:])
print(result.stdout, end='')

translator = root / '.cache/gpu-reference/metal2vulkan/Cargo.toml'
for test in ('indexed_constant_tables_use_shared_storage_above_four_kib',
             'specialized_names_resolve_exact_definitions_and_keys'):
    result = subprocess.run(['cargo', '+1.98.0', 'test', '--manifest-path', translator, '-p', 'metal2vulkan',
                             '--lib', test], text=True, capture_output=True, timeout=600)
    (out / (test + '.log')).write_text(result.stdout + result.stderr)
    if result.returncode or '1 passed' not in result.stdout:
        raise SystemExit('Compiler regression failed: ' + (result.stdout + result.stderr)[-6000:])
    print('PASS: compiler ' + test)

interfaces = out / 'interfaces'
subprocess.run(['xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-parameter', '-Wno-deprecated-declarations', '-DNATIVE_ADRENO_SP_CORES=6', '-I', kit,
                kit / 'NativeBridgeMetalFrontend.mm', kit / 'bridge/interface_regressions_host.mm',
                root / 'build/adreno-metal-bridge/host/libadreno_metal_bridge.a',
                '-framework', 'Foundation', '-framework', 'Metal', '-framework', 'IOSurface',
                '-framework', 'CoreFoundation', '-o', interfaces], check=True)
for mode in ('normal', 'single'):
    with tempfile.TemporaryDirectory(prefix='interfaces-' + mode + '-', dir=out) as directory:
        command = [interfaces, args.loader.resolve(), directory, mode]
        env = dict(os.environ, NATIVE_METAL_ABORT_PROBE='1', NMB_LOG_STDERR='1')
        result = subprocess.run(command, env=env,
                                text=True, capture_output=True, timeout=180)
        (out / ('interfaces-' + mode + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode or 'PASS:' not in result.stdout:
            print('Metal interfaces %s exited %d' % (mode, result.returncode), flush=True)
            if result.returncode < 0:
                debug = subprocess.run(['xcrun', 'lldb', '--batch', '--no-lldbinit', '-o', 'run',
                                        '-k', 'thread backtrace all', '--', *command], env=env,
                                       text=True, capture_output=True, timeout=120)
                (out / ('interfaces-' + mode + '-crash.log')).write_text(debug.stdout + debug.stderr)
                print((debug.stdout + debug.stderr)[-12000:], flush=True)
            raise SystemExit('Metal interfaces failed: ' + (result.stdout + result.stderr)[-6000:])
        print(result.stdout, end='')
