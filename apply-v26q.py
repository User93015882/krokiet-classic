#!/usr/bin/env python3
"""V26Q stage 1: Windows native large-fetch directory enumeration parity validation.
Read-only and opt-in; standard Rust DirEntry remains authoritative.
Run after v26O. Only modifies czkawka_core/src/common/dir_traversal.rs.
"""
from pathlib import Path
import re, sys

if len(sys.argv) != 2:
    raise SystemExit('Usage: python apply-v26q.py czkawka')
p = Path(sys.argv[1]) / 'czkawka_core/src/common/dir_traversal.rs'
if not p.exists():
    raise SystemExit(f'V26Q_ABORT missing source: {p}')
s = p.read_text(encoding='utf-8')
if 'v26q_read_dir_probe' in s or 'V26Q_NATIVE_PARITY' in s:
    raise SystemExit('V26Q_ABORT already applied; source unchanged')
pat = r'\bcommon_read_dir\s*\(\s*&current_folder\s*,\s*&mut\s+warnings\s*\)'
matches = list(re.finditer(pat, s))
if len(matches) != 1:
    raise SystemExit(f'V26Q_ABORT expected one directory-read invocation, found {len(matches)}; source unchanged')
mod_anchor = 'pub(crate) fn common_read_dir('
if s.count(mod_anchor) != 1:
    raise SystemExit(f'V26Q_ABORT expected one common_read_dir definition, found {s.count(mod_anchor)}; source unchanged')

# Explicit Win32 FFI; no Cargo dependency changes. Matches WIN32_FIND_DATAW layout.
code = r'''// V26Q stage 1: Windows LARGE_FETCH enumeration parity check; NO scan behavior changes.
// The standard Rust fs::read_dir result remains authoritative. Read-only, opt-in.
#[cfg(windows)]
mod v26q_native_parity {
    use std::collections::BTreeMap;
    use std::ffi::{OsStr, OsString, c_void};
    use std::io;
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    use std::path::Path;

    const FILE_ATTRIBUTE_DIRECTORY: u32 = 0x10;
    const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
    const ERROR_FILE_NOT_FOUND: i32 = 2;
    const ERROR_NO_MORE_FILES: i32 = 18;
    const FIND_FIRST_EX_LARGE_FETCH: u32 = 2;

    #[repr(C)]
    #[derive(Clone, Copy)]
    struct FileTime { low: u32, high: u32 }

    #[repr(C)]
    struct FindDataW {
        attributes: u32,
        created: FileTime,
        accessed: FileTime,
        written: FileTime,
        size_high: u32,
        size_low: u32,
        reserved0: u32,
        reserved1: u32,
        filename: [u16; 260],
        alternate_filename: [u16; 14],
    }

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn FindFirstFileExW(
            filename: *const u16,
            info_level: i32,
            find_data: *mut FindDataW,
            search_op: i32,
            search_filter: *const c_void,
            flags: u32,
        ) -> *mut c_void;
        fn FindNextFileW(handle: *mut c_void, find_data: *mut FindDataW) -> i32;
        fn FindClose(handle: *mut c_void) -> i32;
    }

    struct FindHandle(*mut c_void);
    impl Drop for FindHandle {
        fn drop(&mut self) {
            unsafe { FindClose(self.0); }
        }
    }

    fn insert_entry(result: &mut BTreeMap<OsString, (bool, bool)>, info: &FindDataW) {
        let length = info.filename.iter().position(|&ch| ch == 0).unwrap_or(info.filename.len());
        let name = OsString::from_wide(&info.filename[..length]);
        if name == OsStr::new(".") || name == OsStr::new("..") {
            return;
        }
        result.insert(name, (
            info.attributes & FILE_ATTRIBUTE_DIRECTORY != 0,
            info.attributes & FILE_ATTRIBUTE_REPARSE_POINT != 0,
        ));
    }

    fn list_native(path: &Path) -> io::Result<BTreeMap<OsString, (bool, bool)>> {
        let pattern = path.join("*");
        let wide: Vec<u16> = pattern.as_os_str().encode_wide().chain(std::iter::once(0)).collect();
        let mut result = BTreeMap::new();
        let mut data = std::mem::MaybeUninit::<FindDataW>::zeroed();
        // SAFETY: null-terminated path; properly sized writable output struct;
        // the handle is closed on all subsequent return paths.
        let raw = unsafe { FindFirstFileExW(wide.as_ptr(), 1, data.as_mut_ptr(), 0, std::ptr::null(), FIND_FIRST_EX_LARGE_FETCH) };
        if raw == (-1isize as *mut c_void) {
            let error = io::Error::last_os_error();
            if error.raw_os_error() == Some(ERROR_FILE_NOT_FOUND) {
                return Ok(result); // Empty directory.
            }
            return Err(error);
        }
        let _handle = FindHandle(raw);
        loop {
            // SAFETY: the successful FindFirstFileExW / FindNextFileW call initialized data.
            insert_entry(&mut result, unsafe { data.assume_init_ref() });
            let ok = unsafe { FindNextFileW(raw, data.as_mut_ptr()) };
            if ok == 0 {
                let error = io::Error::last_os_error();
                if error.raw_os_error() == Some(ERROR_NO_MORE_FILES) {
                    break;
                }
                return Err(error);
            }
        }
        Ok(result)
    }

    pub(super) fn check(path: &Path, rust: &[Result<std::fs::DirEntry, io::Error>]) {
        let start = std::time::Instant::now();
        match list_native(path) {
            Ok(native) => {
                let mut rust_names = BTreeMap::<OsString, (bool, bool)>::new();
                let mut rust_errors = 0usize;
                let mut types_unavailable = 0usize;
                for entry in rust {
                    match entry {
                        Ok(entry) => {
                            let typ = entry.file_type();
                            let flags = match typ {
                                Ok(typ) => (typ.is_dir(), typ.is_symlink()),
                                Err(_) => { types_unavailable += 1; (false, false) }
                            };
                            rust_names.insert(entry.file_name(), flags);
                        }
                        Err(_) => rust_errors += 1,
                    }
                }
                let only_native = native.keys().filter(|name| !rust_names.contains_key(*name)).count();
                let only_rust = rust_names.keys().filter(|name| !native.contains_key(*name)).count();
                // Compare directory flags only for non-reparse entries with available file types.
                // Windows reparse points and Rust symlinks have different type semantics.
                let type_mismatches = native.iter().filter(|entry| {
                    let (name, flags) = *entry;
                    let (is_dir, is_reparse) = *flags;
                    !is_reparse && rust_names.get(name).is_some_and(|&(rust_dir, rust_link)| !rust_link && rust_dir != is_dir)
                }).count();
                log::info!(
                    "V26Q_NATIVE_PARITY native_entries={} rust_entries={} only_native={} only_rust={} type_mismatches={} rust_errors={} type_unavailable={} elapsed_ms={:.3} (opt_in; no_paths; standard_results_used)",
                    native.len(), rust_names.len(), only_native, only_rust, type_mismatches,
                    rust_errors, types_unavailable, start.elapsed().as_secs_f64() * 1000.0
                );
            }
            Err(error) => log::warn!(
                "V26Q_NATIVE_PARITY native_error={} (standard_results_used; no_paths)",
                error.raw_os_error().unwrap_or(-1),
            ),
        }
    }
}

fn v26q_read_dir_probe(current_folder: &Path, warnings: &mut Vec<String>) -> Option<Vec<Result<DirEntry, std::io::Error>>> {
    let standard = common_read_dir(current_folder, warnings);
    #[cfg(windows)]
    if let Some(ref entries) = standard {
        if let Ok(root) = std::env::var("KROKIET_V26Q_VALIDATE_ROOT") {
            if !root.is_empty() {
                // Case-insensitive path-component comparison, scoped to the requested test root.
                let normalized_path = current_folder.to_string_lossy().replace('/', "\\").to_lowercase();
                let normalized_root = root.replace('/', "\\").trim_end_matches('\\').to_lowercase();
                let in_scope = normalized_path == normalized_root ||
                    normalized_path.starts_with(&(normalized_root + "\\"));
                if in_scope {
                    v26q_native_parity::check(current_folder, entries);
                }
            }
        }
    }
    standard
}

'''
# Replace precisely one use, retaining the existing `let`/else control flow.
m = matches[0]
s2 = s[:m.start()] + 'v26q_read_dir_probe(&current_folder, &mut warnings)' + s[m.end():]
s2 = s2.replace(mod_anchor, code + mod_anchor, 1)
p.write_text(s2, encoding='utf-8')
print('V26Q_OK installed opt-in Win32 large-fetch parity validation; original enumeration remains authoritative')
