#!/usr/bin/env python3
"""v2.6R Stage 2: replace per-directory shared atomic sampling with thread-local sampling.
Apply AFTER apply-v26r.py. This changes only diagnostics, not traversal results.
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('Usage: python apply-v26r-stage2.py czkawka')
p = Path(sys.argv[1]) / 'czkawka_core/src/common/dir_traversal.rs'
if not p.is_file():
    raise SystemExit(f'V26R2_ABORT source missing: {p}')
s = p.read_text(encoding='utf-8')
if 'V26R_STAGE2_TLS_SAMPLE' in s:
    raise SystemExit('V26R2_ABORT already applied; no changes made')
if 'V26R_DIRECTORY_SAMPLE' not in s or 'V26Q2_NATIVE_FAST' not in s:
    raise SystemExit('V26R2_ABORT prerequisite v26R and v26Q Stage 2 missing; no changes made')

start_anchor = 'fn v26r_profiled<T, F: FnOnce() -> T>'
end_anchor = '\nfn v26r_report(stats: &V26RStats) {'
if s.count(start_anchor) != 1 or s.count(end_anchor) != 1:
    raise SystemExit('V26R2_ABORT missing or ambiguous profiler anchors; no changes made')
start = s.index(start_anchor)
end = s.index(end_anchor, start)
replacement = '''// V26R_STAGE2_TLS_SAMPLE: one sampler counter per thread, no shared per-call increment.
// This is diagnostic-only; downstream file and directory handling is unchanged.
thread_local! {
    static V26R2_STANDARD_COUNT: std::cell::Cell<u64> = const { std::cell::Cell::new(0) };
    static V26R2_NATIVE_COUNT: std::cell::Cell<u64> = const { std::cell::Cell::new(0) };
}

fn v26r_profiled<T, F: FnOnce() -> T>(stats: Option<&std::sync::Arc<V26RStats>>, native: bool, work: F) -> T {
    let Some(stats) = stats else { return work(); };
    // Each worker samples 1/16 calls. No shared atomic operation on the other 15 calls.
    let sample = if native { &V26R2_NATIVE_COUNT } else { &V26R2_STANDARD_COUNT };
    let should_time = sample.with(|counter| {
        let next = counter.get().wrapping_add(1);
        counter.set(next);
        next % 16 == 0
    });
    if !should_time { return work(); }
    let mode = if native { &stats.native } else { &stats.standard };
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
'''
s = s[:start] + replacement + s[end:]
# The old global call count becomes meaningless; explicitly report estimated count.
old = '"NAS_DIAG_V26R method={} calls={} samples={} sampled_sum_ms={:.3} avg_sample_ms={:.3} bins_lt1_lt5_lt20_lt100_lt500_lt2000_ge2000_ms={:?} (sample_1_in_16; parallel_sampled_times_cumulative; no_paths)",\n            method, read(&mode.calls), samples, read(&mode.sampled_us) as f64 / 1000.0,'
new = '"NAS_DIAG_V26R2 method={} estimated_calls={} samples={} sampled_sum_ms={:.3} avg_sample_ms={:.3} bins_lt1_lt5_lt20_lt100_lt500_lt2000_ge2000_ms={:?} (worker_local_sample_1_in_16; estimated_calls_approximate; parallel_sampled_times_cumulative; no_paths)",\n            method, samples.saturating_mul(16), samples, read(&mode.sampled_us) as f64 / 1000.0,'
if s.count(old) != 1:
    raise SystemExit('V26R2_ABORT v26R report anchor changed; no changes made')
s = s.replace(old, new, 1)
# Remove unused call-count atomic from mode stats to avoid accidentally restoring contention.
old_field = '    calls: V26RAtomicU64,\n'
if s.count(old_field) != 1:
    raise SystemExit('V26R2_ABORT original call-counter field missing; no changes made')
s = s.replace(old_field, '', 1)
p.write_text(s, encoding='utf-8')
print('V26R2_OK: thread-local 1-in-16 selection; only timed samples update shared statistics; no traversal changes.')
