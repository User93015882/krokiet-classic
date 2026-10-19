#!/usr/bin/env python3
"""Apply v2.6I to a czkawka checkout AFTER the v2.6G stable API fix.
Strictly asserts known v2.6G anchor points; no partial file writes.
"""
import pathlib, sys
root=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else 'czkawka')
mod=root/'czkawka_core/src/tools/duplicate/mod.rs'
core=root/'czkawka_core/src/tools/duplicate/core.rs'
a=mod.read_text(encoding='utf-8'); b=core.read_text(encoding='utf-8')

def once(hay, old, new, name):
    count=hay.count(old)
    if count!=1: raise SystemExit(f'v2.6I ABORT: expected exactly one {name} anchor; got {count}. No files changed.')
    return hay.replace(old,new,1)

# Implementation uses a distinct identity namespace for each API, avoiding accidental
# equivalence of the low 64 bits of unrelated high-resolution IDs.
needle='''    let mut inodes: IndexSet<u128> = IndexSet::with_capacity(vec_file_entry.len());'''
a=once(a,needle,needle+'''
    let mut fallback_inodes: IndexSet<(String, u32, u64)> = IndexSet::with_capacity(vec_file_entry.len());''','Windows highres identity set')
needle='''    errors_other: u64,'''
a=once(a,needle,needle+'''
    fallback_ok: u64,
    fallback_errors: u64,
    fallback_same_id_skipped: u64,''','identity probe fields')
old='''                    if code == 87 {
                        probe_windows_metadata_identity(&f.path);
                    }'''
new='''                    if code == 87 {
                        // Retain the v2.6G diagnostic sampler for comparison.
                        probe_windows_metadata_identity(&f.path);
                        match v26i_windows_file_identity(&f.path) {
                            Ok(Some(id)) => {
                                probe.fallback_ok += 1;
                                // Partition identities by path root (drive/UNC prefix) so
                                // unrelated SMB servers cannot collide on volume serial/index.
                                let root = f.path.components().next()
                                    .map(|c| c.as_os_str().to_string_lossy().to_ascii_lowercase())
                                    .unwrap_or_default();
                                if root.is_empty() {
                                    probe.fallback_errors += 1;
                                } else if !fallback_inodes.insert((root, id.0, id.1)) {
                                    probe.fallback_same_id_skipped += 1;
                                    probe.same_id_skipped += 1;
                                    continue;
                                }
                            }
                            Ok(None) | Err(_) => {
                                // Unknown identity is NEVER grounds for exclusion.
                                probe.fallback_errors += 1;
                            }
                        }
                    }'''
import re
pattern = r'(?m)^([ \t]*)if code == 87 \{\s*probe_windows_metadata_identity\(&f\.path\);\s*\}'
matches = list(re.finditer(pattern, a))
if len(matches) != 1:
    raise SystemExit(
        f'v2.6I ABORT: expected one error-87 branch; got {len(matches)}. No files changed.'
    )
indent = matches[0].group(1)
replacement = '\n'.join(
    indent + line[20:] if line.startswith(' ' * 20) else line
    for line in new.split('\n')
)
a = a[:matches[0].start()] + replacement + a[matches[0].end():]
# File open + by-handle query are supported on stable Rust. This API may return
# unusable zero IDs on some providers; in that case the entry must be retained.
impl='''
/// v2.6I: Windows fallback for error 87. A zero identity is treated as unknown.
/// The tuple is scoped to the volume; do not log IDs or paths.
#[cfg(target_family = "windows")]
fn v26i_windows_file_identity(path: &Path) -> std::io::Result<Option<(u32, u64)>> {
    use std::os::windows::io::AsRawHandle;
    #[repr(C)]
    #[derive(Default)]
    struct FileTime { low: u32, high: u32 }
    #[repr(C)]
    #[derive(Default)]
    struct Info {
        attrs: u32, created: FileTime, accessed: FileTime, modified: FileTime,
        volume: u32, size_high: u32, size_low: u32, links: u32,
        index_high: u32, index_low: u32,
    }
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetFileInformationByHandle(handle: *mut std::ffi::c_void, info: *mut Info) -> i32;
    }
    let file = std::fs::File::open(path)?;
    let mut info = Info::default();
    // SAFETY: valid owned file handle and ABI-compatible writable info structure.
    if unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut info) } == 0 {
        return Err(std::io::Error::last_os_error());
    }
    let index = (u64::from(info.index_high) << 32) | u64::from(info.index_low);
    Ok((info.volume != 0 && index != 0).then_some((info.volume, index)))
}

'''
a=once(a,'#[cfg(target_family = "windows")]\nfn filter_hard_links_profiled',impl+'#[cfg(target_family = "windows")]\nfn filter_hard_links_profiled','Windows filter function insertion')
# Diagnostics aggregates use existing atomic worker aggregation.
needle='''                let id_same_skipped = AtomicU64::new(0);'''
b=once(b,needle,needle+'''
                let id_fallback_ok = AtomicU64::new(0);
                let id_fallback_errors = AtomicU64::new(0);
                let id_fallback_skipped = AtomicU64::new(0);''','fallback atomics')
needle='''                            id_same_skipped.fetch_add(identity_probe.same_id_skipped, Ordering::Relaxed);'''
b=once(b,needle,needle+'''
                            id_fallback_ok.fetch_add(identity_probe.fallback_ok, Ordering::Relaxed);
                            id_fallback_errors.fetch_add(identity_probe.fallback_errors, Ordering::Relaxed);
                            id_fallback_skipped.fetch_add(identity_probe.fallback_same_id_skipped, Ordering::Relaxed);''','fallback aggregates')
# Existing F logging is a good adjacent anchor, but the warning is significant:
# successful alternate IDs are conditional on another API's failure (87).
needle='''                if check_if_stop_received(stop_flag) {'''
# Unique? likely multiple such statements. Insert directly after V26F log block instead.
start=b.find('NAS_DIAG_V26F hardlink_os_errors')
if start<0: raise SystemExit('v2.6I ABORT: v2.6F diagnostic block absent; no files changed.')
end=b.find(');',start)
if end<0: raise SystemExit('v2.6I ABORT: v2.6F log incomplete; no files changed.')
end+=2
b=b[:end]+'''
                info!("NAS_DIAG_V26I fallback_identity success={} failed_or_unusable={} same_identity_skipped={} (error_87_only; distinct_api_namespace; no paths or ids)",
                    id_fallback_ok.load(Ordering::Relaxed),
                    id_fallback_errors.load(Ordering::Relaxed),
                    id_fallback_skipped.load(Ordering::Relaxed));'''+b[end:]
# On Unix add fields (defaulted) but unused, no different behavior.
mod.write_text(a,encoding='utf-8');core.write_text(b,encoding='utf-8')
print('V26I_PATCH_APPLIED')
