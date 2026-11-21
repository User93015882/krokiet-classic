#!/usr/bin/env python3
"""v2.6N: opt-in forced class-10 failure for the isolated NAS test fixture.
Apply AFTER v2.6M. Does not change the fallback or scanning algorithms.
"""
from pathlib import Path
import sys
root = Path(sys.argv[1] if len(sys.argv) > 1 else 'czkawka')
source = root / 'czkawka_core/src/tools/duplicate/mod.rs'
original = source.read_text(encoding='utf-8')
anchor = '''    pub(super) fn enumerate(folder: &Path) -> Result<(u32, HashMap<OsString,u64>), ()> {
        const BUFFER_BYTES: usize = 65536;'''
replacement = '''    pub(super) fn enumerate(folder: &Path) -> Result<(u32, HashMap<OsString,u64>), ()> {
        // v2.6N: deterministic failure injection for the ISOLATED test fixture only.
        // Does not affect any other directory even if the environment flag is set.
        // Remove this patch step after validating automatic v2.6K fallback.
        if std::env::var_os("KROKIET_V26N_TEST_FORCE_DIR_ERROR").as_deref()
            == Some(std::ffi::OsStr::new("1"))
            && folder.to_string_lossy().to_ascii_lowercase()
                .contains("_krokiet_v26l_test_4211126c")
        {
            return Err(());
        }
        const BUFFER_BYTES: usize = 65536;'''
count = original.count(anchor)
if count != 1:
    raise SystemExit(f'V26N_ABORT directory enumerate anchor: expected 1, found {count}. No files changed.')
source.write_text(original.replace(anchor, replacement, 1), encoding='utf-8')
print('V26N_PATCH_APPLIED fixture_only=1 opt_in=1 deliberate_class10_error=1')
