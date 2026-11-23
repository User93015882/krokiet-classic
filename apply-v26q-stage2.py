#!/usr/bin/env python3
"""v2.6Q Stage 2 opt-in Win32 large-fetch directory traversal.
Apply AFTER v2.6Q Stage 1 (fix r2). Changes only dir_traversal.rs.
"""
from pathlib import Path
import re,sys
if len(sys.argv)!=2: raise SystemExit('Usage: python apply-v26q-stage2.py czkawka')
p=Path(sys.argv[1])/'czkawka_core/src/common/dir_traversal.rs'
if not p.is_file(): raise SystemExit(f'V26Q2_ABORT missing: {p}')
s=p.read_text(encoding='utf-8')
if 'V26Q2_NATIVE_FAST' in s: raise SystemExit('V26Q2_ABORT already applied')
if 'mod v26q_native_parity {' not in s or 'v26q_read_dir_probe(' not in s: raise SystemExit('V26Q2_ABORT requires Stage 1 fix r2')
# Insert directly before the existing parity module's check() function.
anchor='    pub(super) fn check(path: &Path, rust: &[Result<std::fs::DirEntry, io::Error>]) {'
if s.count(anchor)!=1: raise SystemExit(f'V26Q2_ABORT parity module anchor count={s.count(anchor)}')
native_code=r'''    // V26Q2_NATIVE_FAST: file information from the Win32 enumeration packet.
    // If any entry needs nuanced type resolution, caller uses the unmodified Rust traversal.
    pub(super) struct NativeEntry {
        pub(super) name: OsString,
        pub(super) is_dir: bool,
        pub(super) length: u64,
        pub(super) modified_epoch: u64,
    }

    pub(super) fn list_for_scan(path: &Path) -> io::Result<Option<Vec<NativeEntry>>> {
        const WINDOWS_TO_UNIX_TICKS: u64 = 116_444_736_000_000_000;
        let wide: Vec<u16> = path.join("*").as_os_str().encode_wide().chain(std::iter::once(0)).collect();
        let mut entries = Vec::new();
        let mut data = std::mem::MaybeUninit::<FindDataW>::zeroed();
        // SAFETY: wide is null-terminated; data has the Win32 ABI layout.
        let raw = unsafe { FindFirstFileExW(wide.as_ptr(), 1, data.as_mut_ptr(), 0, std::ptr::null(), FIND_FIRST_EX_LARGE_FETCH) };
        if raw == (-1isize as *mut c_void) {
            // Distinguish an empty existing directory from a missing directory.
            // For error 2, returning None lets the standard implementation decide.
            return Err(io::Error::last_os_error());
        }
        let _handle = FindHandle(raw);
        loop {
            // SAFETY: FindFirstFileExW or FindNextFileW initialized data.
            let info = unsafe { data.assume_init_ref() };
            let end = info.filename.iter().position(|&c| c == 0).unwrap_or(info.filename.len());
            let name = OsString::from_wide(&info.filename[..end]);
            if name != OsStr::new(".") && name != OsStr::new("..") {
                // Do not attempt to reimplement symlink/junction semantics.
                if name.is_empty() || info.attributes & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
                    return Ok(None);
                }
                let ticks = ((info.written.high as u64) << 32) | info.written.low as u64;
                // Preserve existing metadata/error paths if timestamps are unusual.
                if ticks < WINDOWS_TO_UNIX_TICKS {
                    return Ok(None);
                }
                entries.push(NativeEntry {
                    name,
                    is_dir: info.attributes & FILE_ATTRIBUTE_DIRECTORY != 0,
                    length: ((info.size_high as u64) << 32) | info.size_low as u64,
                    modified_epoch: (ticks - WINDOWS_TO_UNIX_TICKS) / 10_000_000,
                });
            }
            // SAFETY: raw is a valid enumeration handle until _handle is dropped.
            if unsafe { FindNextFileW(raw, data.as_mut_ptr()) } == 0 {
                let error = io::Error::last_os_error();
                if error.raw_os_error() == Some(ERROR_NO_MORE_FILES) { break; }
                return Err(error);
            }
        }
        Ok(Some(entries))
    }

'''
s=s.replace(anchor,native_code+anchor,1)
# top-level opt-in root check; no path logging and no global mutable state.
mod_anchor='fn v26q_read_dir_probe(current_folder: &Path, warnings: &mut Vec<String>)'
if s.count(mod_anchor)!=1: raise SystemExit('V26Q2_ABORT missing probe')
helper=r'''// V26Q2_NATIVE_FAST: only enabled for the requested Windows directory subtree.
#[cfg(windows)]
fn v26q2_enabled_here(folder: &Path) -> bool {
    let Ok(root) = std::env::var("KROKIET_V26Q_FAST_ROOT") else { return false; };
    if root.trim().is_empty() { return false; }
    let folder = folder.to_string_lossy().replace('/', "\\").trim_end_matches('\\').to_lowercase();
    let root = root.replace('/', "\\").trim_end_matches('\\').to_lowercase();
    folder == root || folder.starts_with(&(root + "\\"))
}

'''
s=s.replace(mod_anchor,helper+mod_anchor,1)
# insert early return in closure, BEFORE existing read_dir invocation.
pattern=r'(?m)^(?P<indent>[ \t]*)let\s+(?:Some\s*\(\s*\w+\s*\)|\w+)\s*=\s*v26q_read_dir_probe\s*\(\s*&current_folder\s*,\s*&mut\s+warnings\s*\)'
ms=list(re.finditer(pattern,s))
if len(ms)!=1: raise SystemExit(f'V26Q2_ABORT expected one v26q_read_dir_probe binding; found {len(ms)}')
m=ms[0]; indent=m.group('indent')
branch=r'''// V26Q2_NATIVE_FAST: opt-in only; the original Rust scan below remains intact.
#[cfg(windows)]
if collect == Collect::Files && v26q2_enabled_here(&current_folder) {
    match v26q_native_parity::list_for_scan(&current_folder) {
        Ok(Some(entries)) => {
            let mut native_counter = 0;
            let total_entries = entries.len();
            for native in entries {
                if check_if_stop_received(&stop_flag) { return None; }
                let path = current_folder.join(&native.name);
                if native.is_dir {
                    if recursive_search && !directories.is_excluded_dir(&path) && !excluded_items.is_excluded(&path) {
                        dir_result.push(path);
                    }
                } else {
                    native_counter += 1;
                    if !extensions.check_if_entry_have_valid_extension(&native.name)
                        || excluded_items.is_excluded(&path)
                        || directories.is_excluded_file(&path)
                    { continue; }
                    if (minimal_file_size..=maximal_file_size).contains(&native.length) {
                        fe_result.push(FileEntry {
                            size: native.length,
                            modified_date: native.modified_epoch,
                            path,
                        });
                    }
                }
            }
            if native_counter > 0 { progress_handler.increase_items(native_counter); }
            log::debug!("V26Q2_NATIVE_FAST used entries={} (no_paths)", total_entries);
            return Some((dir_result, warnings, fe_result));
        }
        Ok(None) => {
            log::debug!("V26Q2_NATIVE_FAST fallback=unsupported_entry (no_paths)");
        }
        Err(err) => {
            log::debug!("V26Q2_NATIVE_FAST fallback=enumeration_error code={} (no_paths)", err.raw_os_error().unwrap_or(-1));
        }
    }
}
'''
branch='\n'.join(indent + line if line else '' for line in branch.splitlines())+'\n'
s=s[:m.start()]+branch+s[m.start():]
p.write_text(s,encoding='utf-8')
print('V26Q2_OK native LARGE_FETCH scan path installed; opt in with KROKIET_V26Q_FAST_ROOT; standard fallback remains')
