#!/usr/bin/env python3
"""Apply opt-in v2.6X NAS cache-maintenance experiment.
Usage: python apply-v26x.py czkawka
Only changes czkawka_core/src/common/cache.rs. Aborts on unfamiliar source.
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('Usage: python apply-v26x.py czkawka')
p = Path(sys.argv[1]) / 'czkawka_core/src/common/cache.rs'
original = p.read_text(encoding='utf-8')
marker = 'NAS_DIAG_V26X cache_cleanup_remote'
if marker in original:
    print('v26X already installed; no files changed')
    raise SystemExit(0)

anchor1 = '        let effective_delete_outdated = delete_outdated_cache && should_clean;\n'
addition1 = '''        // v2.6X: opt-in remote-cache maintenance experiment (default: unchanged).
        // This bypasses *only* existence probes during scheduled duplicate-hash cache
        // cleanup for paths below the explicitly selected root. Actual cache use still
        // requires a matching scanned path, size and modification time.
        // Missing remote cache records may remain stored until a normal cleanup.
        let v26x_remote_root = if cache_file_name.starts_with("cache_duplicates_Blake3_") {
            std::env::var_os("KROKIET_V26X_SKIP_CACHE_EXISTS_ROOT")
                .filter(|value| !value.is_empty())
                .map(std::path::PathBuf::from)
        } else {
            None
        };
        let v26x_skipped = std::sync::atomic::AtomicUsize::new(0);
'''
anchor2 = '''                if effective_delete_outdated && !file_entry.get_path().exists() {
                    return false;
                }
'''
addition2 = '''                if effective_delete_outdated {
                    let skip_remote_probe = v26x_remote_root.as_ref().is_some_and(|root| file_entry.get_path().starts_with(root));
                    if skip_remote_probe {
                        v26x_skipped.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                    } else if !file_entry.get_path().exists() {
                        return false;
                    }
                }
'''
anchor3 = '''        if effective_delete_outdated {
            update_cleaning_timestamp(cache_file_name);
        }
'''
addition3 = '''        if effective_delete_outdated && v26x_remote_root.is_some() {
            debug!(
                "NAS_DIAG_V26X cache_cleanup_remote cache={} skipped_exists={} root={} entries_before={} entries_after={}",
                cache_file_name,
                v26x_skipped.load(std::sync::atomic::Ordering::Relaxed),
                v26x_remote_root.as_ref().expect("checked").display(),
                initial_number_of_entries,
                vec_loaded_entries.len(),
            );
        }
'''
for anchor in [anchor1,anchor2,anchor3]:
    n = original.count(anchor)
    if n != 1:
        raise SystemExit(f'Expected one anchor, found {n}; NO FILES CHANGED: {anchor[:75]!r}')
patched = original.replace(anchor1, anchor1+addition1, 1).replace(anchor2, addition2, 1).replace(anchor3,addition3+anchor3,1)
p.write_text(patched, encoding='utf-8')
print('Applied v26X to', p)
