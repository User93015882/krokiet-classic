# Krokiet Classic v2.5E — Completed Scan Report

This incremental source patch applies **after v2.5D** in the existing `backend-development` GitHub Actions Windows build. It modifies only `krokiet/ui/main_window.slint` and does not change the scanner, hashes, SQLite checkpoint database, deletion logic, or saved text-report format.

## Improvements

- A completed-report header and summary replace the frozen live progress bars.
- Displays the existing scan result summary, start and end timestamps and total elapsed time.
- Shows the cached BLAKE3/SQLite metrics and final-stage elapsed time.
- Hides live worker-activity and hypothetical per-file throughput lines after the scan ends.
- Retains the existing activity log and Results/Report toggle.

## GitHub steps

1. Switch to branch `backend-development` in GitHub.
2. Upload `backend-v25e-completed-report.patch` to the repository root.
3. In `.github/workflows/build-krokiet-classic.yml`, insert this step **immediately after v2.5D** (same indentation as the other patch steps):

```yaml
      - name: Apply v2.5E completed scan report
        shell: pwsh
        run: |
          git -C czkawka apply --check ../backend-v25e-completed-report.patch
          if ($LASTEXITCODE -ne 0) { exit 1 }
          git -C czkawka apply ../backend-v25e-completed-report.patch
          if ($LASTEXITCODE -ne 0) { exit 1 }
```

4. Commit and start your normal Windows build on `backend-development`.
5. Run a test scan, open **Show Scan Report**, and test **Show Results**.

## Verification and boundaries

Patch application and whitespace checks passed against the full reconstructed source/patch chain through v2.5D. **A Rust/Slint compiler and Windows runtime were not available in this environment**, so your GitHub build remains the integration test.

The existing GUI result-summary duration and report elapsed timer still originate from different timing boundaries. This release labels the report's elapsed timer consistently, but does not claim to eliminate the several-second discrepancy. That will need a follow-up timing-source alignment. The report displays `SCAN ENDED`, not necessarily `COMPLETED`, because stopped/error scenarios require a separate backend outcome event.
