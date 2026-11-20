#!/usr/bin/env python3
"""v2.6M: per-scan, concurrent, once-per-directory cache for v2.6L class-10 identity.
Apply AFTER v2.6L. Checks all source anchors before writing either source file.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else 'czkawka')
mod=root/'czkawka_core/src/tools/duplicate/mod.rs'
core=root/'czkawka_core/src/tools/duplicate/core.rs'
a=mod.read_text(encoding='utf-8'); b=core.read_text(encoding='utf-8')
def once(s, old, new, label):
    n=s.count(old)
    if n!=1: raise SystemExit(f'V26M_ABORT {label}: expected exactly one anchor; found {n}. Neither file changed.')
    return s.replace(old,new,1)

# Each scan holds exactly one cache. Concurrent groups share a per-folder OnceLock.
# Never hold the map lock during an SMB call, and do not persist IDs across scans.
cache=r'''#[cfg(target_family = "windows")]
#[derive(Default)]
pub(crate) struct V26MDirectoryCache {
    entries: std::sync::Mutex<std::collections::HashMap<
        std::path::PathBuf,
        std::sync::Arc<std::sync::OnceLock<Result<
            (u32, std::collections::HashMap<std::ffi::OsString, u64>), ()
        >>>,
    >>,
}

'''
a=once(a,'#[cfg(target_family = "windows")]\nmod v26l_directory_ids {',cache+'#[cfg(target_family = "windows")]\nmod v26l_directory_ids {','cache type')
# The v26L windows filtering function is the only one that gets the cache argument.
a=once(a,'#[cfg(target_family = "windows")]\nfn filter_hard_links_profiled(vec_file_entry: Vec<FileEntry>) -> (Vec<FileEntry>, HardlinkIdentityProbe) {',
'''#[cfg(target_family = "windows")]
fn filter_hard_links_profiled(vec_file_entry: Vec<FileEntry>, shared_directory_cache: &V26MDirectoryCache) -> (Vec<FileEntry>, HardlinkIdentityProbe) {''','Windows function signature')
old='''    let mut v26l_cache: std::collections::HashMap<
        std::path::PathBuf,
        Result<(u32, std::collections::HashMap<std::ffi::OsString, u64>), ()>
    > = std::collections::HashMap::new();
    for f in vec_file_entry {'''
a=once(a,old,'''    for f in vec_file_entry {''','remove per-group cache')
old='''                    if !v26l_cache.contains_key(parent) {
                        probe.v26l_directory_queries += 1;
                        let result = v26l_directory_ids::enumerate(parent);
                        if result.is_err() { probe.v26l_directory_errors += 1; }
                        v26l_cache.insert(parent.to_path_buf(), result);
                    }
                    v26l_cache.get(parent).and_then(|entry| entry.as_ref().ok())
                        .and_then(|(volume, ids)| f.path.file_name()
                            .and_then(|name| ids.get(name))
                            .copied().map(|id| (*volume, id)))'''
new='''                    let slot = shared_directory_cache.entries.lock().ok().map(|mut map| {
                        map.entry(parent.to_path_buf())
                            .or_insert_with(|| std::sync::Arc::new(std::sync::OnceLock::new()))
                            .clone()
                    });
                    slot.and_then(|slot| {
                        let data = slot.get_or_init(|| {
                            probe.v26l_directory_queries += 1;
                            let result = v26l_directory_ids::enumerate(parent);
                            if result.is_err() { probe.v26l_directory_errors += 1; }
                            result
                        });
                        data.as_ref().ok().and_then(|(volume, ids)| f.path.file_name()
                            .and_then(|name| ids.get(name))
                            .copied().map(|id| (*volume, id)))
                    })'''
a=once(a,old,new,'per-directory OnceLock lookup')
a=once(a,'''#[cfg_attr(not(test), allow(dead_code))]
fn filter_hard_links(vec_file_entry: Vec<FileEntry>) -> Vec<FileEntry> {
    filter_hard_links_profiled(vec_file_entry).0
}''','''#[cfg_attr(not(test), allow(dead_code))]
fn filter_hard_links(vec_file_entry: Vec<FileEntry>) -> Vec<FileEntry> {
    #[cfg(target_family = "windows")]
    { filter_hard_links_profiled(vec_file_entry, &V26MDirectoryCache::default()).0 }
    #[cfg(not(target_family = "windows"))]
    { filter_hard_links_profiled(vec_file_entry).0 }
}''','compatibility function')
# Create the cache inside the scan method, outside of rayon's per-size-group closure.
b=once(b,'use crate::tools::duplicate::{', '#[cfg(target_family = "windows")]\nuse crate::tools::duplicate::V26MDirectoryCache;\nuse crate::tools::duplicate::{', 'core import')
# NOTE: cfg attributes inside grouped use imports are supported by Rust.
needle='''                let initial_size = grouped_file_entries'''
replacement='''                #[cfg(target_family = "windows")]
                let v26m_directory_cache = V26MDirectoryCache::default();
                let initial_size = grouped_file_entries'''
b=once(b,needle,replacement,'scan-scoped cache before initial_size')
needle='''                            let (result, identity_probe) = filter_hard_links_profiled(vec);'''
replacement='''                            #[cfg(target_family = "windows")]
                            let (result, identity_probe) = filter_hard_links_profiled(vec, &v26m_directory_cache);
                            #[cfg(not(target_family = "windows"))]
                            let (result, identity_probe) = filter_hard_links_profiled(vec);'''
b=once(b,needle,replacement,'pass shared cache into filter')
b=once(b,'(per_size_group; opt_in_only; no paths or ids)', '(scan_wide_once_per_directory; opt_in_only; no paths or ids)', 'diagnostic label')
# No partial writes on an anchor mismatch; both updated strings are ready.
mod.write_text(a,encoding='utf-8'); core.write_text(b,encoding='utf-8')
print('V26M_PATCH_APPLIED scan_scoped_cache=1 once_per_parent_directory=1 v26k_fallback=1')
