#!/usr/bin/env python3
"""v2.6U opt-in exact-path LARGE_FETCH experiment.
Apply AFTER v26Q Stage 2 and v26R Stage 2. Source change only affects opt-in selection.
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('Usage: python apply-v26u.py czkawka')
p = Path(sys.argv[1]) / 'czkawka_core/src/common/dir_traversal.rs'
if not p.is_file():
    raise SystemExit(f'V26U_ABORT: source missing: {p}')
s = p.read_text(encoding='utf-8')
if 'V26U_SELECTIVE_LARGE_DIR' in s:
    raise SystemExit('V26U_ABORT: already applied')
if 'V26Q2_NATIVE_FAST' not in s or 'V26R_STAGE2_TLS_SAMPLE' not in s:
    raise SystemExit('V26U_ABORT: requires v26Q Stage 2 and v26R Stage 2 applied')
old = 'fn v26q2_enabled_here(folder: &Path) -> bool {\n    let Ok(root) = std::env::var("KROKIET_V26Q_FAST_ROOT") else { return false; };\n    if root.trim().is_empty() { return false; }\n    let folder = folder.to_string_lossy().replace(\'/\', "\\\\").trim_end_matches(\'\\\\\').to_lowercase();\n    let root = root.replace(\'/\', "\\\\").trim_end_matches(\'\\\\\').to_lowercase();\n    folder == root || folder.starts_with(&(root + "\\\\"))\n}'
new = 'fn v26q2_enabled_here(folder: &Path) -> bool {\n    // V26U_SELECTIVE_LARGE_DIR: fail-closed exact path selection, never subtree matching.\n    // Explicitly reject the older blanket native mode while this experiment is active.\n    if std::env::var_os("KROKIET_V26Q_FAST_ROOT").is_some() {\n        return false;\n    }\n    static ALLOWED: std::sync::OnceLock<std::collections::HashSet<String>> = std::sync::OnceLock::new();\n    let allowed = ALLOWED.get_or_init(|| {\n        let mut paths = std::collections::HashSet::new();\n        let Some(filename) = std::env::var_os("KROKIET_V26U_LARGE_DIR_LIST") else {\n            return paths;\n        };\n        let Ok(contents) = std::fs::read_to_string(&filename) else {\n            log::warn!("V26U_SELECTIVE_LARGE_DIR allowlist_read_failed; standard Rust fallback");\n            return paths;\n        };\n        for raw in contents.trim_start_matches(\'\\u{feff}\').lines() {\n            let raw = raw.trim();\n            if raw.is_empty() || raw.starts_with(\'#\') { continue; }\n            let normalized = raw.replace(\'/\', "\\\\").trim_end_matches(\'\\\\\').to_lowercase();\n            // Each entry must be an absolute path under W:\\Incoming.\n            if !normalized.starts_with("w:\\\\incoming\\\\") || normalized.contains("\\\\..\\\\")\n                || normalized.ends_with("\\\\..") || normalized.contains("\\\\.\\\\")\n                || normalized.ends_with("\\\\.") {\n                log::warn!("V26U_SELECTIVE_LARGE_DIR invalid_allowlist; standard Rust fallback");\n                return std::collections::HashSet::new();\n            }\n            paths.insert(normalized);\n        }\n        if paths.len() != 64 {\n            log::warn!("V26U_SELECTIVE_LARGE_DIR wrong_allowlist_count={} expected=64; standard Rust fallback", paths.len());\n            return std::collections::HashSet::new();\n        }\n        log::info!("V26U_SELECTIVE_LARGE_DIR enabled exact_directories={} (no_paths)", paths.len());\n        paths\n    });\n    let folder = folder.to_string_lossy().replace(\'/\', "\\\\").trim_end_matches(\'\\\\\').to_lowercase();\n    allowed.contains(&folder)\n}'
if s.count(old) != 1:
    raise SystemExit(f'V26U_ABORT: expected exactly one original v26q2_enabled_here function; found {s.count(old)}; source unchanged')
# Only replace the opt-in selector. Native enumeration/fallback code is unchanged.
p.write_text(s.replace(old, new, 1), encoding='utf-8')
print('V26U_OK: native LARGE_FETCH enabled ONLY for 64 explicit allowlisted folders; otherwise standard Rust.')
