#!/usr/bin/env python3
"""Check shared-cache fallback, same-UID selection and concurrent pack import."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

kit = Path(__file__).resolve().parents[1] / 'drivers/AdrenoMetal'
compiler = os.environ.get('CXX', 'c++')
with tempfile.TemporaryDirectory(prefix='metal-shared-cache-') as directory:
    work = Path(directory)
    source = work / 'directory.cpp'
    source.write_text('#include "SharedShaderCache.h"\n#include <cstdio>\n'
                      'int main(){auto path=sharedShaderCacheDirectory();'
                      'configureShaderDiskCache(path);puts(path.c_str());}\n')
    exe = work / 'directory'
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', kit,
                    source, '-o', exe], check=True)
    cache = work / 'shared'
    def resolve(value):
        return subprocess.check_output([exe], env=dict(os.environ, NATIVE_METAL_SHARED_CACHE_DIR=str(value)),
                                       text=True).strip()
    assert resolve(cache) == str(cache) and resolve(cache) == str(cache)
    assert (cache / 'ir3').is_dir() and not list(cache.glob('.write-*'))
    assert resolve('') == ''
    cache.chmod(0o777)
    assert resolve(cache) == ''
    cache.chmod(0o700)
    (work / 'link').symlink_to(cache)
    assert resolve(work / 'link') == ''
    assert resolve(work / 'missing/child') == ''
    packed = work / 'cache-export'
    host_stat = ['-Dst_mtimespec=st_mtim'] if sys.platform == 'linux' else []
    if sys.platform == 'linux':
        shim = work / 'darwin-zlib.h'
        shim.write_text('#include <dlfcn.h>\n#include <cstring>\n'
                        'static void *host_dlopen(const char *p,int mode){return dlopen('
                        '!strcmp(p,"/usr/lib/libz.1.dylib")?"libz.so.1":p,mode);}\n'
                        '#define dlopen host_dlopen\n')
        host_stat += ['-include', str(shim)]
    subprocess.run([compiler, '-std=c++17', '-O1', '-g', '-fsanitize=address,undefined',
                    *host_stat, kit / 'bridge/cache_export_host.cpp', '-lz', '-o', packed], check=True)
    src = work / 'source'
    (src / 'nested').mkdir(parents=True)
    for name, data in [('shader', b'shader' * 1000), ('pipeline', bytes(range(256))), ('nested/key', b'key')]:
        (src / name).write_bytes(data)
    subprocess.run([packed, src, work / 'imported', work / 'pack'], check=True)
print('PASS: shared directory selection, private fallback and concurrent cache import')
