#!/usr/bin/env python3
"""v2.6Y: opt-in single-run exercise of v2.6X cache-maintenance path.

Usage: python apply-v26y.py czkawka
Requires v2.6X already applied. Modifies only common/cache.rs; fails closed.
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('Usage: python apply-v26y.py czkawka')
p = Path(sys.argv[1]) / 'czkawka_core/src/common/cache.rs'
source = p.read_text(encoding='utf-8')
marker = 'NAS_DIAG_V26Y forced_cleanup'
if marker in source:
    print('v26Y already installed; no files changed')
    raise SystemExit(0)
if 'NAS_DIAG_V26X cache_cleanup_remote' not in source:
    raise SystemExit('v26X is not installed; NO FILES CHANGED')
anchor = '        let v26x_skipped = std::sync::atomic::AtomicUsize::new(0);\n'
if source.count(anchor) != 1:
    raise SystemExit(f'Expected exactly one v26X anchor; found {source.count(anchor)}; NO FILES CHANGED')
addition = '''        // v2.6Y: diagnostics only. Set to 1 to exercise the *existing* cache
        // cleanup path now, rather than waiting for the seven-day interval.
        // Restricted to Blake3 duplicate caches with v26X remote root enabled.
        // Only local cache metadata may change; no NAS modifications.
        let v26y_force_cleanup = v26x_remote_root.is_some()
            && std::env::var("KROKIET_V26Y_FORCE_CACHE_CLEANUP")
                .is_ok_and(|value| value == "1");
        let effective_delete_outdated = effective_delete_outdated
            || (delete_outdated_cache && v26y_force_cleanup);
        if v26y_force_cleanup && delete_outdated_cache {
            debug!(
                "NAS_DIAG_V26Y forced_cleanup cache={} normally_due={} active={} root={}",
                cache_file_name,
                should_clean,
                effective_delete_outdated,
                v26x_remote_root.as_ref().expect("checked").display(),
            );
        }
'''
p.write_text(source.replace(anchor, anchor + addition, 1), encoding='utf-8')
print('Applied v26Y to', p)
