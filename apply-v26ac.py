#!/usr/bin/env python3
"""Apply v2.6AC local-only checkpoint-producer throttle to Krokiet Rust source.

Place after v2.6Y patches and before cargo build. Fails closed if source differs.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'czkawka')
core = root / 'czkawka_core/src/tools/duplicate/core.rs'
if not core.is_file():
    sys.exit(f'V26AC_ABORT: missing {core}')
src = core.read_text(encoding='utf-8')
marker = 'V26AC_LOCAL_HASH_SEND_DELAY'
if marker in src:
    sys.exit('V26AC_ABORT: already applied; refusing duplicate patch')

anchor = '''                                if let Some(sender) = &checkpoint_sender {
                                    let _ = sender.send(file_entry.clone());
                                }
                                hashmap_with_hash.entry(hash_string).or_default().push(file_entry);'''
if src.count(anchor) != 1:
    sys.exit(f'V26AC_ABORT: expected one full-hash send anchor; found {src.count(anchor)}. Nothing changed.')

replacement = '''                                if let Some(sender) = &checkpoint_sender {
                                    let _ = sender.send(file_entry.clone());
                                    // V26AC_LOCAL_HASH_SEND_DELAY: test-only producer throttle.
                                    // The SQLite writer is asynchronous. This pause gives the
                                    // writer time to commit a subset before intentional process
                                    // termination; it is NOT proof of durability by itself.
                                    // Both variables must be present, and file path must be
                                    // strictly beneath a fixture inside LOCALAPPDATA. NAS paths
                                    // never qualify, even if the user supplies them as the root.
                                    let delay = std::env::var("KROKIET_V26AC_LOCAL_DELAY_MS")
                                        .ok().and_then(|v| v.parse::<u64>().ok())
                                        .filter(|v| (1..=10000).contains(v));
                                    let local_root = std::env::var_os("KROKIET_V26AC_LOCAL_ROOT");
                                    let local_app_data = std::env::var_os("LOCALAPPDATA");
                                    if let (Some(ms), Some(root), Some(local)) = (delay, local_root, local_app_data) {
                                        let root = std::path::PathBuf::from(root);
                                        let local = std::path::PathBuf::from(local);
                                        let canonical_root = root.canonicalize().ok();
                                        let canonical_local = local.canonicalize().ok();
                                        if let (Some(root), Some(local)) = (canonical_root, canonical_local) {
                                            // Requiring a named folder below LOCALAPPDATA also
                                            // rules out LOCALAPPDATA itself as an overly broad root.
                                            let allowed = root.starts_with(&local) && root != local
                                                && file_entry.path.starts_with(&root);
                                            if allowed {
                                                std::thread::sleep(std::time::Duration::from_millis(ms));
                                            }
                                        }
                                    }
                                }
                                hashmap_with_hash.entry(hash_string).or_default().push(file_entry);'''
# Note: canonical file path not needed: only a local fixture under LOCALAPPDATA
# and a path already derived from the traversal can pass. Treat symlink fixture
# paths as unsupported, not as permission to reach other volumes.
core.write_text(src.replace(anchor, replacement, 1), encoding='utf-8')
print('V26AC_OK: local-only throttle inserted after checkpoint sender enqueue')
