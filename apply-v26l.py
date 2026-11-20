#!/usr/bin/env python3
"""Krokiet v2.6L opt-in SMB FileIdBothDirectoryInfo(10) fast path.
Apply after v2.6K. All edits preflight in memory; no NAS files touched.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else 'czkawka')
mod=root/'czkawka_core/src/tools/duplicate/mod.rs'
core=root/'czkawka_core/src/tools/duplicate/core.rs'
a=mod.read_text(encoding='utf-8'); b=core.read_text(encoding='utf-8')
def one(s, old, new, label):
    n=s.count(old)
    if n!=1: raise SystemExit(f'V26L_ABORT {label}: expected exactly one anchor, found {n}. No files changed.')
    return s.replace(old,new,1)

# Class 10 layout matches the successful read-only Windows PowerShell probe.
# Directory handle provides volume serial; directory entry provides 64-bit file ID.
# Only use identities when every record is unambiguous and safely parsed.
helper=r'''
#[cfg(target_family = "windows")]
mod v26l_directory_ids {
    use std::collections::HashMap;
    use std::ffi::{OsStr, OsString, c_void};
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    use std::path::Path;

    #[repr(C)]
    #[derive(Default)]
    struct FileTime { low: u32, high: u32 }
    #[repr(C)]
    #[derive(Default)]
    struct HandleInfo {
        attrs: u32, created: FileTime, accessed: FileTime, modified: FileTime,
        volume: u32, size_high: u32, size_low: u32, links: u32,
        index_high: u32, index_low: u32,
    }
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn CreateFileW(name: *const u16, access: u32, share: u32, security: *mut c_void,
            disposition: u32, flags: u32, template: *mut c_void) -> *mut c_void;
        fn GetFileInformationByHandle(handle: *mut c_void, info: *mut HandleInfo) -> i32;
        fn GetFileInformationByHandleEx(handle: *mut c_void, kind: i32, data: *mut c_void, size: u32) -> i32;
        fn CloseHandle(handle: *mut c_void) -> i32;
        fn GetLastError() -> u32;
    }
    struct Handle(*mut c_void);
    impl Drop for Handle {
        fn drop(&mut self) { unsafe { CloseHandle(self.0); } }
    }
    fn u32_at(buf: &[u8], i: usize) -> Option<u32> {
        Some(u32::from_le_bytes(buf.get(i..i.checked_add(4)?)?.try_into().ok()?))
    }
    fn u64_at(buf: &[u8], i: usize) -> Option<u64> {
        Some(u64::from_le_bytes(buf.get(i..i.checked_add(8)?)?.try_into().ok()?))
    }

    pub(super) fn enumerate(folder: &Path) -> Result<(u32, HashMap<OsString,u64>), ()> {
        const BUFFER_BYTES: usize = 65536;
        // Read-only access; the folder is never modified.
        let mut wide: Vec<u16> = folder.as_os_str().encode_wide().collect();
        wide.push(0);
        let raw = unsafe { CreateFileW(wide.as_ptr(), 0x0001 | 0x0080, 7,
            std::ptr::null_mut(), 3, 0x02000000, std::ptr::null_mut()) };
        if raw.is_null() || raw as isize == -1 { return Err(()); }
        let handle = Handle(raw);
        let mut info = HandleInfo::default();
        if unsafe { GetFileInformationByHandle(handle.0, &mut info) } == 0 || info.volume == 0 {
            return Err(());
        }
        // u64 storage guarantees suitable alignment for the Windows API buffer.
        let mut storage = vec![0_u64; BUFFER_BYTES / 8];
        let mut entries = HashMap::new();
        let mut seen_any = false;
        for _ in 0..100000 {
            let success = unsafe { GetFileInformationByHandleEx(handle.0, 10,
                storage.as_mut_ptr().cast::<c_void>(), BUFFER_BYTES as u32) };
            if success == 0 {
                let error = unsafe { GetLastError() };
                // ERROR_NO_MORE_FILES / ERROR_HANDLE_EOF after successful enumeration.
                return if seen_any && (error == 18 || error == 38) {
                    Ok((info.volume, entries))
                } else { Err(()) };
            }
            seen_any = true;
            let bytes = unsafe { std::slice::from_raw_parts(storage.as_ptr().cast::<u8>(), BUFFER_BYTES) };
            let mut offset: usize = 0;
            loop {
                // FILE_ID_BOTH_DIR_INFO: NextEntryOffset +0, FileNameLength +60,
                // FileId +96, FileName +104. Bounds-check all untrusted results.
                let next = u32_at(bytes, offset).ok_or(())? as usize;
                let name_bytes = u32_at(bytes, offset.checked_add(60).ok_or(())?).ok_or(())? as usize;
                let id = u64_at(bytes, offset.checked_add(96).ok_or(())?).ok_or(())?;
                if name_bytes % 2 != 0 { return Err(()); }
                let start = offset.checked_add(104).ok_or(())?;
                let end = start.checked_add(name_bytes).ok_or(())?;
                let name_bytes_slice = bytes.get(start..end).ok_or(())?;
                let mut units = Vec::with_capacity(name_bytes/2);
                for chunk in name_bytes_slice.chunks_exact(2) {
                    units.push(u16::from_le_bytes([chunk[0],chunk[1]]));
                }
                let name = OsString::from_wide(&units);
                if name.as_os_str() != OsStr::new(".") && name.as_os_str() != OsStr::new("..") {
                    if id == 0 || entries.insert(name, id).is_some() { return Err(()); }
                }
                if next == 0 { break; }
                if next < 104 || next % 8 != 0 || offset.checked_add(next).is_none_or(|p| p >= BUFFER_BYTES) {
                    return Err(());
                }
                offset += next;
            }
        }
        Err(()) // Defensive limit rather than accepting incomplete data.
    }
}

'''
a=one(a,'#[cfg(target_family = "windows")]\nfn v26i_windows_file_identity',helper+'#[cfg(target_family = "windows")]\nfn v26i_windows_file_identity','insert Windows class10 implementation')
a=one(a,'    direct_unusable: u64,','''    direct_unusable: u64,
    v26l_directory_queries: u64,
    v26l_directory_errors: u64,
    v26l_directory_hits: u64,
    v26l_file_fallbacks: u64,''','probe counters')
needle='''    for f in vec_file_entry {
        if direct_root.as_ref().is_some_and(|root| f.path.starts_with(root)) {'''
replacement='''    // v2.6L is enabled only within the v2.6K direct fallback scope.
    // It never changes behaviour for paths outside that scope.
    let v26l_root = std::env::var_os("KROKIET_V26L_DIRECTORY_ID_ROOT")
        .filter(|value| !value.is_empty())
        .map(std::path::PathBuf::from)
        .filter(|path| path.is_absolute() && direct_root.as_ref().is_some_and(|d| path.starts_with(d)));
    let mut v26l_cache: std::collections::HashMap<
        std::path::PathBuf,
        Result<(u32, std::collections::HashMap<std::ffi::OsString, u64>), ()>
    > = std::collections::HashMap::new();
    for f in vec_file_entry {
        if direct_root.as_ref().is_some_and(|root| f.path.starts_with(root)) {'''
a=one(a,needle,replacement,'opt-in directory cache')
needle='''            let fallback_result = v26i_windows_file_identity(&f.path);
            probe.fallback_elapsed_ns = probe.fallback_elapsed_ns.saturating_add(
                fallback_started.elapsed().as_nanos().min(u128::from(u64::MAX)) as u64
            );'''
replacement='''            let from_directory = if v26l_root.as_ref().is_some_and(|root| f.path.starts_with(root)) {
                f.path.parent().and_then(|parent| {
                    if !v26l_cache.contains_key(parent) {
                        probe.v26l_directory_queries += 1;
                        let result = v26l_directory_ids::enumerate(parent);
                        if result.is_err() { probe.v26l_directory_errors += 1; }
                        v26l_cache.insert(parent.to_path_buf(), result);
                    }
                    v26l_cache.get(parent).and_then(|entry| entry.as_ref().ok())
                        .and_then(|(volume, ids)| f.path.file_name()
                            .and_then(|name| ids.get(name))
                            .copied().map(|id| (*volume, id)))
                })
            } else { None };
            let fallback_result = if let Some(id) = from_directory {
                probe.v26l_directory_hits += 1;
                Ok(Some(id))
            } else {
                if v26l_root.as_ref().is_some_and(|root| f.path.starts_with(root)) {
                    probe.v26l_file_fallbacks += 1;
                }
                let result = v26i_windows_file_identity(&f.path);
                probe.fallback_elapsed_ns = probe.fallback_elapsed_ns.saturating_add(
                    fallback_started.elapsed().as_nanos().min(u128::from(u64::MAX)) as u64
                );
                result
            };'''
a=one(a,needle,replacement,'directory hit or v26k fallback')
b=one(b,'                let id_direct_unusable = AtomicU64::new(0);','''                let id_direct_unusable = AtomicU64::new(0);
                let id_v26l_queries = AtomicU64::new(0);
                let id_v26l_errors = AtomicU64::new(0);
                let id_v26l_hits = AtomicU64::new(0);
                let id_v26l_fallbacks = AtomicU64::new(0);''','core counters')
b=one(b,'                            id_direct_unusable.fetch_add(identity_probe.direct_unusable, Ordering::Relaxed);','''                            id_direct_unusable.fetch_add(identity_probe.direct_unusable, Ordering::Relaxed);
                            id_v26l_queries.fetch_add(identity_probe.v26l_directory_queries, Ordering::Relaxed);
                            id_v26l_errors.fetch_add(identity_probe.v26l_directory_errors, Ordering::Relaxed);
                            id_v26l_hits.fetch_add(identity_probe.v26l_directory_hits, Ordering::Relaxed);
                            id_v26l_fallbacks.fetch_add(identity_probe.v26l_file_fallbacks, Ordering::Relaxed);''','aggregate counters')
needle='''                info!("NAS_DIAG_V26K direct_fallback attempts={} usable={} unusable={} bypassed_original={} (opt_in_only; no paths or ids)",'''
b=one(b,needle,'''                info!("NAS_DIAG_V26L directory_identity queries={} errors={} file_hits={} per_file_fallbacks={} (per_size_group; opt_in_only; no paths or ids)",
                    id_v26l_queries.load(Ordering::Relaxed),
                    id_v26l_errors.load(Ordering::Relaxed),
                    id_v26l_hits.load(Ordering::Relaxed),
                    id_v26l_fallbacks.load(Ordering::Relaxed));
'''+needle,'new log')
# All validations happened before any write.
mod.write_text(a,encoding='utf-8'); core.write_text(b,encoding='utf-8')
print('V26L_PATCH_APPLIED opt_in_only=1; class10=1; v26k_fallback=1')
