#!/usr/bin/env python3
"""Exercise A740/A830 command paths and HFI encoding over software peers; no hardware."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
gpu = ROOT / 'drivers/Adreno740'
firmware = ROOT / 'kits/AdrenoFirmware'
pm4 = ROOT / 'kits/AdrenoPM4'

with tempfile.TemporaryDirectory(prefix='adreno-a830-') as directory:
    work = Path(directory)
    for name in ('IOKit/IOTypes.h', 'IOKit/IOLib.h', 'IOKit/IOBufferMemoryDescriptor.h', 'kern/task.h', 'sys/resource_private.h'):
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#include "XnuMemoryFixture.h"\n')
    flags = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined']
    c = [os.environ.get('CC', 'cc'), '-std=gnu11', *flags]
    cpp = [os.environ.get('CXX', 'c++'), '-std=c++17', *flags,
           '-Wno-misleading-indentation', '-I', str(work), '-I', str(gpu),
           '-I', str(gpu / 'tests'), '-I', str(pm4)]
    publish = (gpu / 'NativeAdrenoPublish.cpp').read_text()
    diagnostics = publish.split('extern "C" bool native_adreno_diagnostics', 1)[1].split(
        'extern "C" IOService *native_adreno_published_service', 1)[0]
    source = work / 'diagnostics.cpp'
    source.write_text(r'''
#include <cassert>
#include <cstring>
#include "NativeAdrenoDiagnostics.h"
static bool held;
static unsigned tries, unlocks;
static bool IOLockTryLock(bool *) {++tries;if(held)return false;held=true;return true;}
static void IOLockUnlock(bool *) {assert(held);held=false;++unlocks;}
struct Stats {uint32_t submissions=9,completed=8,timeouts=1,poisoned_jobs=2;};
struct Submit {Stats stats() {assert(held);return {};}} submit;
static struct {bool published=false;bool *lock=&held;Submit *submit=&::submit;} g;
static struct {uint32_t opens=3,closes=1,busy=2,calls=50,last_status=7;char opener[3][17];} native_adreno_metal_diag;
static uint64_t native_adreno_last_call=(uint64_t(16)<<32)|7;
static uint64_t native_adreno_last_error=(uint64_t(8)<<32)|0xe00002c7;
extern "C" bool native_adreno_diagnostics
''' + diagnostics + r'''
int main() {
    NativeAdrenoDiagnostics out{},before{};
    memset(&out,0xab,sizeof out);memcpy(&before,&out,sizeof out);
    assert(!native_adreno_diagnostics(nullptr) && !native_adreno_diagnostics(&out));
    assert(!tries && !memcmp(&out,&before,sizeof out));
    g.published=true;held=true;
    assert(!native_adreno_diagnostics(&out) && tries==1 && !unlocks);
    assert(!memcmp(&out,&before,sizeof out));held=false;
    memset(native_adreno_metal_diag.opener[0],'x',17);
    assert(native_adreno_diagnostics(&out) && !held && unlocks==1);
    assert(out.opens==3 && out.closes==1 && out.busy==2 && out.calls==50 && out.last_status==7);
    assert(out.submissions==9 && out.completed==8 && out.poll_misses==1 && out.poisoned==2);
    assert(out.last_method==16 && !out.cached);
    assert(out.last_error_method==8 && out.last_error==0xe00002c7);
    assert(strlen(out.opener)==16);
    held=true;
    assert(native_adreno_diagnostics(&out) && held && unlocks==1);
    assert(out.submissions==9 && out.completed==8 && strlen(out.opener)==16);
    assert(out.cached);
    held=false;native_adreno_last_call=(uint64_t(7)<<32)|0xe00002c7;
    assert(native_adreno_diagnostics(&out) && !out.cached && out.last_method==7 && out.last_status==0xe00002c7);
}
''')
    binary = work / 'diagnostics'
    subprocess.run([*cpp, source, '-o', binary], check=True)
    subprocess.run([binary], check=True)
    obj = work / 'pm4.o'
    subprocess.run([*c, '-c', pm4 / 'AdrenoPM4.c', '-o', obj], check=True)
    for test, sources in (
        ('ring', ['NativeAdrenoRing.cpp']),
        ('cpinit', ['NativeAdrenoRing.cpp', 'NativeAdrenoCpInit.cpp']),
        ('irq', ['NativeAdrenoIrq.cpp']),
        ('timer', ['NativeAdrenoTimer.cpp']),
        ('a830_hwinit', ['NativeAdrenoA830HwInit.cpp', 'NativeAdrenoPwrup.cpp',
                         'NativeAdrenoRing.cpp', 'NativeAdrenoCpInit.cpp']),
        ('gpu', ['NativeAdrenoGpu.cpp', 'NativeAdrenoRing.cpp', 'NativeAdrenoCpInit.cpp',
                 'NativeAdrenoIrq.cpp', 'NativeAdrenoTimer.cpp']),
    ):
        if 'NativeAdrenoRing.cpp' in sources:
            sources.append('NativeAdrenoPreempt.cpp')
        binary = work / test
        subprocess.run([*cpp, gpu / ('tests/test_' + test + '.cpp'),
                        *[gpu / source for source in sources], obj, '-o', binary], check=True)
        subprocess.run([binary], check=True)
    binary = work / 'hfi-startup'
    subprocess.run([*c, '-DADRENO_HFI_HOST_TEST', firmware / 'AdrenoHfi.c', firmware / 'AdrenoHfiStartup.c',
                    firmware / 'test_startup.c', '-o', binary], check=True)
    subprocess.run([binary], check=True)
    smmu = ROOT / 'kits/ArmSmmu4K'
    objects = []
    for name in ('ArmSmmu4KContext', 'ArmSmmu4KProgram', 'ArmSmmu4KLive', 'ArmSmmu4KStreams'):
        obj = work / (name + '.o')
        subprocess.run([*c, '-c', smmu / (name + '.c'), '-o', obj], check=True)
        objects.append(obj)
    binary = work / 'system-memory'
    subprocess.run([*cpp, '-DNATIVE_ADRENO_HOST_TEST', gpu / 'tests/test_system_memory.cpp',
                    gpu / 'NativeAdrenoMemory.cpp', '-o', binary], check=True)
    subprocess.run([binary], check=True)
    binary = work / 'gmuctx'
    subprocess.run([*cpp, '-DNATIVE_ADRENO_HOST_TEST', '-I', smmu, gpu / 'tests/test_gmuctx.cpp',
                    *[gpu / (name + '.cpp') for name in ('NativeAdrenoMemory', 'NativeAdrenoSmmuMemory',
                        'NativeAdrenoSmmuContext', 'NativeAdrenoVm', 'NativeAdrenoGmuMemory', 'NativeAdrenoGmuContext')],
                    *objects, '-o', binary], check=True)
    subprocess.run([binary], check=True)
    binary = work / 'gpuctx'
    subprocess.run([*cpp, '-DNATIVE_ADRENO_HOST_TEST', '-I', smmu, gpu / 'tests/test_gpuctx.cpp',
                    *[gpu / (name + '.cpp') for name in ('NativeAdrenoMemory', 'NativeAdrenoSmmuMemory',
                        'NativeAdrenoSmmuContext', 'NativeAdrenoVm', 'NativeAdrenoGpuContext')],
                    *objects, work / 'pm4.o', '-o', binary], check=True)
    subprocess.run([binary], check=True)
    binary = work / 'userclient'
    client_flags = ['-Wno-missing-field-initializers']
    if 'Free Software Foundation' in subprocess.check_output([cpp[0], '--version'], text=True):
        client_flags.append('-Wno-class-memaccess')
    subprocess.run([*cpp, *client_flags, '-DNATIVE_ADRENO_HOST_TEST', '-I', smmu, gpu / 'tests/test_userclient.cpp',
                    *[gpu / (name + '.cpp') for name in ('NativeAdrenoMemory', 'NativeAdrenoSmmuMemory',
                        'NativeAdrenoVm', 'NativeAdrenoRing', 'NativeAdrenoPreempt', 'NativeAdrenoSubmit', 'NativeAdrenoTimer',
                        'NativeAdrenoUserClient')], *objects, work / 'pm4.o', '-o', binary], check=True)
    subprocess.run([binary], check=True)
