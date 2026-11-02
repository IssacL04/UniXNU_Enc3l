#!/usr/bin/env python3
"""Regenerate A830 register data from Linux 65ba8f34ec886ec72b2c07ddc8cf3d815c32869d.

Input directory: a6xx.xml, a6xx_gmu.xml, adreno_common.xml, a8xx_catalog.c.
Only numeric register facts are emitted. No Linux runtime code is imported.
"""
import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'drivers/Adreno740/NativeAdrenoA830Regs.h'
SOURCE_SHA256 = {
    'a6xx.xml': '6e20d0347b06f26220f6b87d8600e94790331fec45363a167c5e63ea6ad8f9c2',
    'a6xx_gmu.xml': 'f13f07aa3c975c1d671c1a7f5ba62ddaaf525aedb7a0e481186cbfffe461f88b',
    'adreno_common.xml': 'f898e4eee3de5f92d25597f003e5550a24fe50552d25555d6916dcd1b922d6f6',
    'a8xx_catalog.c': 'a53ef7a20e0c0c9e765a78b9510efa2039671607b5dde7bbfc82f4521aa74afb',
}


def generate(source):
    for name, expected in SOURCE_SHA256.items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Source revision mismatch: {name}')
    xml = [(source / n).read_text() for n in ('a6xx.xml', 'adreno_common.xml', 'a6xx_gmu.xml')]
    catalog = (source / 'a8xx_catalog.c').read_text()
    catalog = re.sub(r'/\*.*?\*/', '', catalog, flags=re.S)
    registers = {}

    def resolve(expression):
        m = re.fullmatch(r'REG_A[678]XX_(\w+)(?:\((\d+)\))?(?:\s*\+\s*(\d+))?', expression.strip())
        if not m:
            raise ValueError(f'Unsupported register expression: {expression}')
        name, index, add = m.groups()
        if name not in registers:
            for document in xml:
                selected, common = set(), set()
                for offset, attributes in re.findall(r'<(?:reg32|reg64|array) offset="(0x[\da-fA-F]+)" name="' + name + '"([^>]*)>', document):
                    variant = re.search(r'variants="([^"]+)"', attributes)
                    matches = False
                    for part in variant[1].split(',') if variant else []:
                        span = re.fullmatch(r'(A[2-9]XX)?-(A[2-9]XX)?', part.strip())
                        if part.strip() == 'A8XX' or (span and int((span[1] or 'A2XX')[1]) <= 8 <= int((span[2] or 'A9XX')[1])):
                            matches = True
                    if matches:
                        selected.add(int(offset, 16))
                    elif not variant:
                        common.add(int(offset, 16))
                candidates = selected or common
                if candidates:
                    if len(candidates) != 1:
                        raise ValueError(f'Ambiguous register: {name}')
                    registers[name] = candidates.pop()
                    break
            else:
                raise ValueError(f'Missing A830 register: {name}')
        return registers[name] + int(index or 0) + int(add or 0)

    pipes = dict(zip(('NONE', 'BR', 'BV', 'LPAC', 'AQE0', 'AQE1', 'DDE_BR', 'DDE_BV'), range(8)))

    def value(text):
        parts = text.strip().split('|')
        result = 0
        for part in parts:
            bit = re.fullmatch(r'\s*BIT\((\d+)\)\s*', part)
            result |= 1 << int(bit[1]) if bit else int(part.strip(), 0)
        return result

    def block(name):
        m = re.search(r'\b' + name + r'\[\]\s*=\s*\{(.*?)\};', catalog, re.S)
        if not m:
            raise ValueError(f'Missing table: {name}')
        return m[1]

    def pipe_table(name):
        rows = []
        for register, val, mask in re.findall(r'\{\s*(REG_\w+(?:\(\d+\))?),\s*([^,]+),\s*([^}]+)\}', block(name)):
            names = re.findall(r'BIT\(PIPE_(\w+)\)', mask)
            if not names or re.sub(r'BIT\(PIPE_\w+\)|[\s|]', '', mask):
                raise ValueError(f'Unsupported pipe mask: {mask}')
            rows.append((resolve(register), value(val), sum(1 << pipes[n] for n in names)))
        if len(rows) != block(name).count('REG_'):
            raise ValueError(f'Unparsed rows: {name}')
        return rows

    noncontext = pipe_table('a830_nonctxt_regs')
    dynamic = pipe_table('a830_dyn_pwrup_reglist_regs')
    lists = {}
    for name in ('pwrup', 'ifpc'):
        lists[name] = [resolve(r) for r in block('a830_' + name + '_reglist_regs').split(',') if r.strip()]
    protected = []
    for kind, start, length in re.findall(r'A6XX_PROTECT_(NORDWR|RDONLY)\((0x[\da-f]+),\s*(0x[\da-f]+)\)', block('a830_protect_regs')):
        protected.append((int(kind == 'NORDWR') << 31) | (int(length, 16) << 18) | int(start, 16))
    assert len(noncontext) == 40 and len(protected) == 48 and len(dynamic) == 28
    names = '''GBIF_HALT RBBM_GBIF_HALT RBBM_SECVID_TSB_CNTL RBBM_SECVID_TSB_TRUSTED_BASE
RBBM_SECVID_TSB_TRUSTED_SIZE RBBM_PERFCTR_GPU_BUSY_MASKED UCHE_CCHE_GC_GMEM_RANGE_MIN
SP_HLSQ_GC_GMEM_RANGE_MIN UCHE_TRAP_BASE UCHE_WRITE_THRU_BASE UCHE_CCHE_TRAP_BASE
UCHE_CCHE_WRITE_THRU_BASE RBBM_PERFCTR_CNTL RBBM_SLICE_PERFCTR_CNTL CP_PERFCTR_CP_SEL
GRAS_NC_MODE_CNTL RB_CCU_NC_MODE_CNTL RB_CMP_NC_MODE_CNTL SP_NC_MODE_CNTL TPL1_NC_MODE_CNTL
TPL1_BICUBIC_WEIGHTS_TABLE UCHE_CLIENT_PF RBBM_INTERFACE_HANG_INT_CNTL
RBBM_SLICE_INTERFACE_HANG_INT_CNTL CP_APERTURE_CNTL_HOST CP_PROTECT_GLOBAL CP_PROTECT_PIPE
CP_PROTECT_CNTL_PIPE RB_CONTEXT_SWITCH_GMEM_SAVE_RESTORE_ENABLE CP_APRIV_CNTL_PIPE
CP_INTERRUPT_STATUS_MASK_PIPE CP_HW_FAULT_STATUS_MASK_PIPE CP_INTERRUPT_STATUS_MASK_GLOBAL
CP_SQE_CNTL RBBM_CGC_0_PC RBBM_CLOCK_CNTL_GLOBAL RBBM_CGC_GLOBAL_LOAD_CMD RBBM_CGC_P2S_TRIG_CMD
RBBM_CGC_P2S_STATUS GPU_GMU_AO_GPU_CX_BUSY_MASK GMU_CX_GMU_POWER_COUNTER_SELECT_XOCLK_0
GMU_CX_GMU_POWER_COUNTER_SELECT_XOCLK_1 GMU_CX_GMU_POWER_COUNTER_ENABLE
GPU_GMU_AO_GMU_CGC_MODE_CNTL GPU_GMU_AO_GMU_CGC_DELAY_CNTL GPU_GMU_AO_GMU_CGC_HYST_CNTL'''
    for name in names.split():
        resolve('REG_A8XX_' + name)
    lines = ['/* SPDX-License-Identifier: MIT */', '#pragma once', '#include <stdint.h>',
             '/* Numeric register facts from Linux 65ba8f34ec886ec72b2c07ddc8cf3d815c32869d.',
             ' * Regenerate with scripts/derive-a830-hwinit.py; all offsets are dwords. */']
    lines += [f'#define A830_{n} 0x{v:05x}' for n, v in sorted(registers.items())]
    for name, rows in (('Noncontext', noncontext), ('Dynamic', dynamic)):
        lines.append(f'static const uint32_t NativeAdrenoA830{name}[][3]={{')
        lines += [f'    {{0x{r:05x},0x{v:08x},0x{p:02x}}},' for r, v, p in rows]
        lines.append('};')
    for name, rows in (('Pwrup', lists['pwrup']), ('Ifpc', lists['ifpc']), ('Protect', protected)):
        lines.append(f'static const uint32_t NativeAdrenoA830{name}[]={{')
        lines += [f'    0x{v:08x},' for v in rows]
        lines.append('};')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    text = generate(args.source)
    if args.write:
        OUT.write_text(text)
    elif OUT.read_text() != text:
        raise SystemExit('A830 register header differs from the source data')
    print('PASS: A830 register offsets, noncontext/protection and power-up data')


if __name__ == '__main__':
    main()
