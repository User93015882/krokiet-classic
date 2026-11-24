#!/usr/bin/env python3
"""Krokiet v2.6V opt-in, low-volume timing of existing v2.6L directory identity calls.
Apply after v26L and other v26 patches, incl v26U. No changes to enumeration,
identity selection, cache logic or NAS content. Preflight all changes before writes.
"""
from pathlib import Path
import sys
if len(sys.argv) != 2:
    raise SystemExit('Usage: python apply-v26v.py czkawka')
root=Path(sys.argv[1]); a_file=root/'czkawka_core/src/tools/duplicate/mod.rs'; b_file=root/'czkawka_core/src/tools/duplicate/core.rs'
if not a_file.is_file() or not b_file.is_file():
    raise SystemExit('V26V_ABORT: missing source file(s); no files changed')
a=a_file.read_text(encoding='utf-8'); b=b_file.read_text(encoding='utf-8')
if 'NAS_DIAG_V26V' in b or 'v26v_query_elapsed_ns' in a:
    raise SystemExit('V26V_ABORT: already applied; no files changed')
if 'NAS_DIAG_V26L' not in b or 'v26l_directory_queries' not in a:
    raise SystemExit('V26V_ABORT: v26L expected; no files changed')
def one(s, old, new, name):
    n=s.count(old)
    if n!=1: raise SystemExit(f'V26V_ABORT: {name} expected once, found {n}; no files changed')
    return s.replace(old,new,1)
a=one(a,'    v26l_directory_queries: u64,','''    v26l_directory_queries: u64,
    v26v_query_elapsed_ns: u64,
    v26v_query_max_ns: u64,
    v26v_query_timed: u64,''','probe fields')
a=one(a,'''                        probe.v26l_directory_queries += 1;
                        let result = v26l_directory_ids::enumerate(parent);
                        if result.is_err() { probe.v26l_directory_errors += 1; }''','''                        probe.v26l_directory_queries += 1;
                        // v26V measures only the already-required directory identity call.
                        // One timestamp pair per directory, gated by an opt-in env flag.
                        let v26v_enabled = std::env::var_os("KROKIET_V26V_ID_TIMING")
                            .as_deref() == Some(std::ffi::OsStr::new("1"));
                        let v26v_start = if v26v_enabled {
                            Some(std::time::Instant::now())
                        } else { None };
                        let result = v26l_directory_ids::enumerate(parent);
                        if let Some(start) = v26v_start {
                            let ns = start.elapsed().as_nanos().min(u128::from(u64::MAX)) as u64;
                            probe.v26v_query_elapsed_ns = probe.v26v_query_elapsed_ns.saturating_add(ns);
                            probe.v26v_query_max_ns = probe.v26v_query_max_ns.max(ns);
                            probe.v26v_query_timed = probe.v26v_query_timed.saturating_add(1);
                        }
                        if result.is_err() { probe.v26l_directory_errors += 1; }''','query timing anchor')
b=one(b,'                let id_v26l_queries = AtomicU64::new(0);','''                let id_v26l_queries = AtomicU64::new(0);
                let id_v26v_query_elapsed_ns = AtomicU64::new(0);
                let id_v26v_query_max_ns = AtomicU64::new(0);
                let id_v26v_query_timed = AtomicU64::new(0);''','atomic counters')
b=one(b,'''                            id_v26l_queries.fetch_add(identity_probe.v26l_directory_queries, Ordering::Relaxed);''','''                            id_v26l_queries.fetch_add(identity_probe.v26l_directory_queries, Ordering::Relaxed);
                            id_v26v_query_elapsed_ns.fetch_add(identity_probe.v26v_query_elapsed_ns, Ordering::Relaxed);
                            id_v26v_query_max_ns.fetch_max(identity_probe.v26v_query_max_ns, Ordering::Relaxed);
                            id_v26v_query_timed.fetch_add(identity_probe.v26v_query_timed, Ordering::Relaxed);''','aggregate timing')
b=one(b,'''                info!("NAS_DIAG_V26L directory_identity queries={} errors={} file_hits={} per_file_fallbacks={} (per_size_group; opt_in_only; no paths or ids)",''','''                if std::env::var_os("KROKIET_V26V_ID_TIMING")
                    .as_deref() == Some(std::ffi::OsStr::new("1")) {
                    let timed = id_v26v_query_timed.load(Ordering::Relaxed);
                    let total_ns = id_v26v_query_elapsed_ns.load(Ordering::Relaxed);
                    let max_ns = id_v26v_query_max_ns.load(Ordering::Relaxed);
                    info!("NAS_DIAG_V26V identity_call_timing timed_queries={} query_total_ms={:.3} query_mean_ms={:.3} query_max_ms={:.3} (sum_of_calls; no_paths; opt_in_only)",
                        timed, total_ns as f64 / 1_000_000.0,
                        if timed == 0 { 0.0 } else { (total_ns as f64 / timed as f64) / 1_000_000.0 },
                        max_ns as f64 / 1_000_000.0);
                }
                info!("NAS_DIAG_V26L directory_identity queries={} errors={} file_hits={} per_file_fallbacks={} (per_size_group; opt_in_only; no paths or ids)",''','log summary')
# Write after both source files have passed all assertions.
a_file.write_text(a,encoding='utf-8'); b_file.write_text(b,encoding='utf-8')
print('V26V_OK: opt-in identity-call latency aggregation added; classification untouched')
