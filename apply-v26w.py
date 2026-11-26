#!/usr/bin/env python3
"""v2.6W opt-in direct-file identity for single-candidate directories.
Apply after all v2.6V patches. Fail closed on unknown source layouts.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'czkawka')
mod = root / 'czkawka_core/src/tools/duplicate/mod.rs'
core = root / 'czkawka_core/src/tools/duplicate/core.rs'
source = {p: p.read_text(encoding='utf-8') for p in (mod,core)}
changes = {p: [] for p in source}

def replace(path, name, old, new):
    count = source[path].count(old)
    if count != 1:
        raise RuntimeError(f'V26W_ABORT: {name} expected once, found {count}; no files changed')
    source[path] = source[path].replace(old, new, 1)

try:
    replace(mod,'cache definition', '''    >>,\n}\n\n#[cfg(target_family = "windows")]\nmod v26l_directory_ids {''', '''    >>,\n    // v2.6W: paths whose directory has exactly one same-size candidate.\n    // Computed entirely from the collected in-memory scan results.\n    v26w_single_candidate_dirs: std::collections::HashSet<std::path::PathBuf>,\n}\n\n#[cfg(target_family = "windows")]\nimpl V26MDirectoryCache {\n    pub(crate) fn v26w_from_groups(groups: &[(u64, Vec<FileEntry>)]) -> Self {\n        let mut cache = Self::default();\n        if std::env::var_os("KROKIET_V26W_SINGLE_CANDIDATE_DIRECT")\n            .as_deref() != Some(std::ffi::OsStr::new("1")) {\n            return cache;\n        }\n        let mut counts = std::collections::HashMap::<std::path::PathBuf, usize>::new();\n        for (_size, files) in groups {\n            if files.len() < 2 { continue; }\n            for file in files {\n                if let Some(parent) = file.path.parent() {\n                    *counts.entry(parent.to_path_buf()).or_default() += 1;\n                }\n            }\n        }\n        cache.v26w_single_candidate_dirs = counts.into_iter()\n            .filter_map(|(parent, count)| (count == 1).then_some(parent))\n            .collect();\n        log::info!("NAS_DIAG_V26W configured single_candidate_directories={} (opt_in; no_paths)",\n            cache.v26w_single_candidate_dirs.len());\n        cache\n    }\n}\n\n#[cfg(target_family = "windows")]\nmod v26l_directory_ids {''')
    replace(mod,'probe field', '''    v26l_file_fallbacks: u64,\n    /// Numeric OS errors only''', '''    v26l_file_fallbacks: u64,\n    v26w_direct_files: u64,\n    /// Numeric OS errors only''')
    replace(mod,'directory identity decision', '''            let from_directory = if v26l_root.as_ref().is_some_and(|root| f.path.starts_with(root)) {\n                f.path.parent().and_then(|parent| {''', '''            let v26w_direct = v26l_root.as_ref().is_some_and(|root| f.path.starts_with(root))\n                && f.path.parent().is_some_and(|parent|\n                    shared_directory_cache.v26w_single_candidate_dirs.contains(parent));\n            if v26w_direct { probe.v26w_direct_files += 1; }\n            let from_directory = if !v26w_direct && v26l_root.as_ref().is_some_and(|root| f.path.starts_with(root)) {\n                f.path.parent().and_then(|parent| {''')
    replace(core,'cache initialization', '''                let v26m_directory_cache = V26MDirectoryCache::default();''', '''                let v26m_directory_cache = V26MDirectoryCache::v26w_from_groups(&grouped_file_entries);''')
    replace(core,'v26w atomic', '''                let id_v26l_fallbacks = AtomicU64::new(0);''', '''                let id_v26l_fallbacks = AtomicU64::new(0);\n                let id_v26w_direct_files = AtomicU64::new(0);''')
    replace(core,'v26w aggregate', '''                            id_v26l_fallbacks.fetch_add(identity_probe.v26l_file_fallbacks, Ordering::Relaxed);''', '''                            id_v26l_fallbacks.fetch_add(identity_probe.v26l_file_fallbacks, Ordering::Relaxed);\n                            id_v26w_direct_files.fetch_add(identity_probe.v26w_direct_files, Ordering::Relaxed);''')
    replace(core,'v26w log', '''                info!("NAS_DIAG_V26K direct_fallback attempts={} usable={} unusable={} bypassed_original={} (opt_in_only; no paths or ids)",''', '''                if std::env::var_os("KROKIET_V26W_SINGLE_CANDIDATE_DIRECT")\n                    .as_deref() == Some(std::ffi::OsStr::new("1")) {\n                    info!("NAS_DIAG_V26W direct_single_candidate_files={} (one_direct_lookup_replaces_one_directory_lookup; no_paths)",\n                        id_v26w_direct_files.load(Ordering::Relaxed));\n                }\n                info!("NAS_DIAG_V26K direct_fallback attempts={} usable={} unusable={} bypassed_original={} (opt_in_only; no paths or ids)",''')
except Exception as err:
    print(err, file=sys.stderr)
    sys.exit(1)

# All anchors have matched. Only now write files.
for path, data in source.items():
    path.write_text(data, encoding='utf-8')
print('V26W_OK: opt-in single-candidate direct identity applied to mod.rs and core.rs')
