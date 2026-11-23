#!/usr/bin/env python3
"""Krokiet v2.6R: sampled Win32/Rust directory listing latency histograms.
Apply AFTER v26O, v26Q Stage 1 and v26Q Stage 2. Only one Rust source file changes.
Does not affect traversal decisions, directory entries, hardlinks, or NAS files.
"""
from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit('Usage: python apply-v26r.py czkawka')
p = Path(sys.argv[1]) / 'czkawka_core/src/common/dir_traversal.rs'
if not p.is_file():
    raise SystemExit(f'V26R_ABORT source missing: {p}')
s = p.read_text(encoding='utf-8')
if 'V26R_DIRECTORY_SAMPLE' in s:
    raise SystemExit('V26R_ABORT already applied (no changes made)')
for required in ('V26OTraversalStats', 'V26Q2_NATIVE_FAST', 'v26q_read_dir_probe(', 'v26q_native_parity::list_for_scan('):
    if required not in s:
        raise SystemExit(f'V26R_ABORT prerequisite missing: {required}')

def replace_unique(needle, replacement, reason):
    global s
    n = s.count(needle)
    if n != 1:
        raise SystemExit(f'V26R_ABORT {reason}: expected one anchor, found {n}; no changes made')
    s = s.replace(needle, replacement, 1)

# Preserve the existing v26O imports; use distinct aliases for all new imports.
imports = '''// V26R_DIRECTORY_SAMPLE: light sampled enumeration profiler, opt-in only.
use std::sync::atomic::{AtomicU64 as V26RAtomicU64, Ordering as V26ROrdering};
use std::time::Instant as V26RInstant;
'''
s = imports + s

# Layout of the histogram: [<1ms, <5ms, <20ms, <100ms, <500ms, <2000ms, >=2000ms].
# Log at most one line for each mode per completed scan; no per-path information.
source = r'''// V26R_DIRECTORY_SAMPLE: sampled directory enumeration latency only.
// No per-file or per-directory logging; no file names in diagnostic output.
#[derive(Default)]
struct V26RModeStats {
    calls: V26RAtomicU64,
    samples: V26RAtomicU64,
    sampled_us: V26RAtomicU64,
    buckets: [V26RAtomicU64; 7],
}

#[derive(Default)]
struct V26RStats {
    standard: V26RModeStats,
    native: V26RModeStats,
}

fn v26r_profiled<T, F: FnOnce() -> T>(stats: Option<&std::sync::Arc<V26RStats>>, native: bool, work: F) -> T {
    let Some(stats) = stats else { return work(); };
    let mode = if native { &stats.native } else { &stats.standard };
    let call = mode.calls.fetch_add(1, V26ROrdering::Relaxed);
    // Sample every 16th directory to avoid the profiler's previous overhead.
    if call % 16 != 0 { return work(); }
    let started = V26RInstant::now();
    let result = work();
    let us = u64::try_from(started.elapsed().as_micros()).unwrap_or(u64::MAX);
    let bucket = if us < 1_000 { 0 }
        else if us < 5_000 { 1 }
        else if us < 20_000 { 2 }
        else if us < 100_000 { 3 }
        else if us < 500_000 { 4 }
        else if us < 2_000_000 { 5 }
        else { 6 };
    mode.samples.fetch_add(1, V26ROrdering::Relaxed);
    mode.sampled_us.fetch_add(us, V26ROrdering::Relaxed);
    mode.buckets[bucket].fetch_add(1, V26ROrdering::Relaxed);
    result
}

fn v26r_report(stats: &V26RStats) {
    for (method, mode) in [("standard", &stats.standard), ("native", &stats.native)] {
        let read = |v: &V26RAtomicU64| v.load(V26ROrdering::Relaxed);
        let counts: Vec<u64> = mode.buckets.iter().map(read).collect();
        let samples = read(&mode.samples);
        log::info!(
            "NAS_DIAG_V26R method={} calls={} samples={} sampled_sum_ms={:.3} avg_sample_ms={:.3} bins_lt1_lt5_lt20_lt100_lt500_lt2000_ge2000_ms={:?} (sample_1_in_16; parallel_sampled_times_cumulative; no_paths)",
            method, read(&mode.calls), samples, read(&mode.sampled_us) as f64 / 1000.0,
            if samples == 0 { 0.0 } else { read(&mode.sampled_us) as f64 / (samples as f64 * 1000.0) },
            counts,
        );
    }
}

'''
replace_unique('#[derive(Default)]\nstruct V26OTraversalStats {', source + '#[derive(Default)]\nstruct V26OTraversalStats {', 'stats insertion')
# Do not modify existing v26O variables or stats.
activation = '''        let v26r_stats = std::env::var("KROKIET_V26R_DIRECTORY_SAMPLE")
            .ok().filter(|value| value == "1")
            .map(|_| std::sync::Arc::new(V26RStats::default()));
'''
needle = '        let v26o_total_start = v26o_enabled.then(V26OInstant::now);'
replace_unique(needle, needle + '\n' + activation.rstrip('\n'), 'scan-scoped activation')

# Both anchors are in the post-v26Q Stage 2 traversal source; instrument returned
# listing results only, without modifying downstream logic or error handling.
standard_re = r'\bv26q_read_dir_probe\s*\(\s*&current_folder\s*,\s*&mut\s+warnings\s*\)'
ms = list(re.finditer(standard_re, s))
if len(ms) != 1:
    raise SystemExit(f'V26R_ABORT Rust listing call count={len(ms)} (expected 1)')
m = ms[0]
s = s[:m.start()] + 'v26r_profiled(v26r_stats.as_ref(), false, || v26q_read_dir_probe(&current_folder, &mut warnings))' + s[m.end():]
native_re = r'\bv26q_native_parity::list_for_scan\s*\(\s*&current_folder\s*\)'
ms = list(re.finditer(native_re, s))
if len(ms) != 1:
    raise SystemExit(f'V26R_ABORT native listing call count={len(ms)} (expected 1)')
m = ms[0]
s = s[:m.start()] + 'v26r_profiled(v26r_stats.as_ref(), true, || v26q_native_parity::list_for_scan(&current_folder))' + s[m.end():]

# The existing aggregate v26O logging is invoked only after traversal workers
# finish; record our aggregate here as well. No per-directory telemetry.
needle = '        if let (Some(stats), Some(started)) = (v26o_stats.as_ref(), v26o_total_start) {'
replace_unique(needle,
    '        if let Some(stats) = v26r_stats.as_deref() { v26r_report(stats); }\n' + needle,
    'scan-complete reporting')

# Source is written only after all strict matches have succeeded.
p.write_text(s, encoding='utf-8')
print('V26R_OK: sampled listing profiler added (opt-in KROKIET_V26R_DIRECTORY_SAMPLE=1); no scan behaviour changes.')
