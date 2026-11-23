#!/usr/bin/env python3
"""V26O: optional aggregate directory traversal timing diagnostics; no scan-behaviour change.
Apply AFTER v26M; omit the v26N test-only patch for normal builds.
"""
from pathlib import Path
import sys
import re

if len(sys.argv)!=2:
    raise SystemExit('Usage: python apply-v26o.py czkawka')
p=Path(sys.argv[1])/'czkawka_core/src/common/dir_traversal.rs'
if not p.is_file():
    raise SystemExit(f'V26O_ABORT missing source: {p}')
s=p.read_text(encoding='utf-8')

def replace_once(old, new, name):
    """Accept whitespace changes in the pinned tag without weakening uniqueness checks."""
    global s
    count = s.count(old)
    if count == 1:
        s = s.replace(old, new, 1)
        return
    if count > 1:
        raise SystemExit(f'V26O_ABORT {name}: ambiguous exact anchor count={count}; source unchanged')
    # GitHub's pinned 12.0.2 tree differs in whitespace/formatting from
    # the later source snapshot. Check token text but tolerate whitespace.
    pattern = r'\s*'.join(re.escape(x) for x in re.findall(r'\S+', old))
    matches = list(re.finditer(pattern, s, flags=re.MULTILINE))
    if len(matches) != 1:
        raise SystemExit(f'V26O_ABORT {name}: expected unique semantic anchor, found {len(matches)}; source unchanged')
    s = s[:matches[0].start()] + new + s[matches[0].end():]

def replace_directory_read():
    """Time the unique common_read_dir invocation, preserving ALL existing control flow.

    Supports both the original `let Some(read_dir) = ... else {...};` and the
    pinned checkout's `let read_dir_result = common_read_dir(...);` form.
    """
    global s
    pattern = (r'(?P<indent>^[ \t]*)let\s+(?:(?P<some>Some\s*\(\s*\w+\s*\))|(?P<plain>\w+))'
               r'\s*=\s*common_read_dir\s*\(\s*&current_folder\s*,\s*&mut\s+warnings\s*\)')
    matches = list(re.finditer(pattern, s, flags=re.MULTILINE))
    if len(matches) != 1:
        nearby = [x.strip()[:160] for x in s.splitlines() if 'common_read_dir(' in x and 'fn common_read_dir' not in x]
        raise SystemExit(f'V26O_ABORT directory reading: expected one binding for common_read_dir, found {len(matches)}. Nearby calls: {nearby[:3]!r}. Source unchanged')
    m = matches[0]
    indent = m.group('indent')
    original_expression = s[m.start()+len(indent):m.end()]
    # Do not rewrite the existing bind/control flow. Instead, wrap the call in
    # a small expression block. This works whether its result is bound using
    # let-else or a regular let assignment; preserves the later error path.
    original_binding = original_expression.split('common_read_dir', 1)[0]
    replacement = (f'{indent}{original_binding}({{\n'
                   f'{indent}    let v26o_read_started = v26o_stats.as_ref().map(|_| V26OInstant::now());\n'
                   f'{indent}    let v26o_read_result = common_read_dir(&current_folder, &mut warnings);\n'
                   f'{indent}    if let (Some(stats), Some(started)) = (v26o_stats.as_ref(), v26o_read_started) {{\n'
                   f'{indent}        stats.read_dir_calls.fetch_add(1, V26OOrdering::Relaxed);\n'
                   f'{indent}        stats.read_dir_ns.fetch_add(v26o_time_ns(started), V26OOrdering::Relaxed);\n'
                   f'{indent}        if v26o_read_result.is_none() {{\n'
                   f'{indent}            stats.read_dir_failures.fetch_add(1, V26OOrdering::Relaxed);\n'
                   f'{indent}        }}\n'
                   f'{indent}    }}\n'
                   f'{indent}    v26o_read_result\n'
                   f'{indent}}})')
    s = s[:m.start()] + replacement + s[m.end():]

# The pinned upstream tag may import AtomicBool via a grouped `use` or a
# different order. Insert collision-proof imports without touching existing ones.
# Rust permits imports before other module items, regardless of import ordering.
if 'V26OAtomicU64' in s or 'V26OInstant' in s or 'V26OOrdering' in s:
    raise SystemExit('V26O_ABORT profiler names already present; source unchanged')
s = ("use std::sync::atomic::{AtomicU64 as V26OAtomicU64, Ordering as V26OOrdering};\n"
     "use std::time::Instant as V26OInstant;\n" + s)

replace_once('pub enum DirTraversalResult<T: Ord + PartialOrd> {', '''// V26O: exclusively opt-in, scan-scoped aggregate timing. No file names or IDs logged.
#[derive(Default)]
struct V26OTraversalStats {
    read_dir_calls: V26OAtomicU64,
    read_dir_failures: V26OAtomicU64,
    read_dir_ns: V26OAtomicU64,
    entries_examined: V26OAtomicU64,
    file_type_calls: V26OAtomicU64,
    file_type_failures: V26OAtomicU64,
    file_type_ns: V26OAtomicU64,
    file_process_calls: V26OAtomicU64,
    file_process_ns: V26OAtomicU64,
    metadata_calls: V26OAtomicU64,
    metadata_failures: V26OAtomicU64,
    metadata_ns: V26OAtomicU64,
    group_ns: V26OAtomicU64,
}

fn v26o_time_ns(start: V26OInstant) -> u64 {
    u64::try_from(start.elapsed().as_nanos()).unwrap_or(u64::MAX)
}

pub enum DirTraversalResult<T: Ord + PartialOrd> {''','stats struct')
replace_once('        assert_ne!(self.tool_type, ToolType::None, "Tool type cannot be None");', '''        assert_ne!(self.tool_type, ToolType::None, "Tool type cannot be None");
        let v26o_enabled = std::env::var("KROKIET_V26O_TRAVERSAL_DIAG").is_ok_and(|s| s == "1");
        let v26o_stats = v26o_enabled.then(|| Arc::new(V26OTraversalStats::default()));
        let v26o_total_start = v26o_enabled.then(V26OInstant::now);''', 'activation')
replace_directory_read()
replace_once('''                        let Some(entry_data) = common_get_entry_data(&entry, &mut warnings, &current_folder) else {
                            continue;
                        };
                        let Ok(file_type) = entry_data.file_type() else { continue };''','''                        if let Some(stats) = v26o_stats.as_ref() {
                            stats.entries_examined.fetch_add(1, V26OOrdering::Relaxed);
                        }
                        let Some(entry_data) = common_get_entry_data(&entry, &mut warnings, &current_folder) else {
                            continue;
                        };
                        let v26o_type_started = v26o_stats.as_ref().map(|_| V26OInstant::now());
                        let file_type_result = entry_data.file_type();
                        if let (Some(stats), Some(started)) = (v26o_stats.as_ref(), v26o_type_started) {
                            stats.file_type_calls.fetch_add(1, V26OOrdering::Relaxed);
                            stats.file_type_ns.fetch_add(v26o_time_ns(started), V26OOrdering::Relaxed);
                            if file_type_result.is_err() {
                                stats.file_type_failures.fetch_add(1, V26OOrdering::Relaxed);
                            }
                        }
                        let Ok(file_type) = file_type_result else { continue };''','entry file type')
replace_once('''                                process_file_in_file_mode(
                                    entry_data,
                                    &mut warnings,
                                    &mut fe_result,
                                    &extensions,
                                    &directories,
                                    &excluded_items,
                                    minimal_file_size,
                                    maximal_file_size,
                                );''','''                                let v26o_file_started = v26o_stats.as_ref().map(|_| V26OInstant::now());
                                process_file_in_file_mode(
                                    entry_data,
                                    &mut warnings,
                                    &mut fe_result,
                                    &extensions,
                                    &directories,
                                    &excluded_items,
                                    minimal_file_size,
                                    maximal_file_size,
                                    v26o_stats.as_deref(),
                                );
                                if let (Some(stats), Some(started)) = (v26o_stats.as_ref(), v26o_file_started) {
                                    stats.file_process_calls.fetch_add(1, V26OOrdering::Relaxed);
                                    stats.file_process_ns.fetch_add(v26o_time_ns(started), V26OOrdering::Relaxed);
                                }''','file process call')
replace_once('''            // Process collected data
            for (segment, warnings, mut fe_result) in segments {''','''            // Process collected data
            let v26o_group_started = v26o_stats.as_ref().map(|_| V26OInstant::now());
            for (segment, warnings, mut fe_result) in segments {''','group start')
replace_once('''                    grouped_file_entries.entry(key).or_default().push(fe);
                }
            }
        }

        progress_handler.join_thread();''','''                    grouped_file_entries.entry(key).or_default().push(fe);
                }
            }
            if let (Some(stats), Some(started)) = (v26o_stats.as_ref(), v26o_group_started) {
                stats.group_ns.fetch_add(v26o_time_ns(started), V26OOrdering::Relaxed);
            }
        }

        progress_handler.join_thread();''','group end')
replace_once('''        debug!("Collected {} files", grouped_file_entries.values().map(Vec::len).sum::<usize>());''','''        debug!("Collected {} files", grouped_file_entries.values().map(Vec::len).sum::<usize>());
        if let (Some(stats), Some(started)) = (v26o_stats.as_ref(), v26o_total_start) {
            let get = |x: &V26OAtomicU64| x.load(V26OOrdering::Relaxed);
            log::info!(
                "NAS_DIAG_V26O traversal total_ms={:.3} read_dir_calls={} read_dir_failures={} read_dir_sum_ms={:.3} entries={} file_type_calls={} file_type_failures={} file_type_sum_ms={:.3} file_process_calls={} file_process_sum_ms={:.3} metadata_calls={} metadata_failures={} metadata_sum_ms={:.3} grouping_sum_ms={:.3} (parallel_times_are_cumulative; diagnostics_opt_in; no_paths)",
                started.elapsed().as_secs_f64() * 1000.0,
                get(&stats.read_dir_calls), get(&stats.read_dir_failures), get(&stats.read_dir_ns) as f64 / 1e6,
                get(&stats.entries_examined), get(&stats.file_type_calls), get(&stats.file_type_failures),
                get(&stats.file_type_ns) as f64 / 1e6,
                get(&stats.file_process_calls), get(&stats.file_process_ns) as f64 / 1e6,
                get(&stats.metadata_calls), get(&stats.metadata_failures), get(&stats.metadata_ns) as f64 / 1e6,
                get(&stats.group_ns) as f64 / 1e6,
            );
        }''','aggregate log')
replace_once('''    minimal_file_size: u64,
    maximal_file_size: u64,
) {
    if !extensions.check_if_entry_have_valid_extension(&entry_data.file_name()) {''','''    minimal_file_size: u64,
    maximal_file_size: u64,
    v26o_stats: Option<&V26OTraversalStats>,
) {
    if !extensions.check_if_entry_have_valid_extension(&entry_data.file_name()) {''','metadata function argument')
replace_once('''    let Some(metadata) = common_get_metadata_dir(entry_data, warnings, &current_file_name) else {
        return;
    };

    if (minimal_file_size..=maximal_file_size).contains(&metadata.len()) {''','''    let v26o_metadata_started = v26o_stats.map(|_| V26OInstant::now());
    let metadata_result = common_get_metadata_dir(entry_data, warnings, &current_file_name);
    if let (Some(stats), Some(started)) = (v26o_stats, v26o_metadata_started) {
        stats.metadata_calls.fetch_add(1, V26OOrdering::Relaxed);
        stats.metadata_ns.fetch_add(v26o_time_ns(started), V26OOrdering::Relaxed);
        if metadata_result.is_none() {
            stats.metadata_failures.fetch_add(1, V26OOrdering::Relaxed);
        }
    }
    let Some(metadata) = metadata_result else {
        return;
    };

    if (minimal_file_size..=maximal_file_size).contains(&metadata.len()) {''','metadata measurement')

# Source-file atomic update only once all anchors match.
p.write_text(s,encoding='utf-8')
print('V26O_OK traversal instrumentation inserted; opt-in only, one file changed.')
