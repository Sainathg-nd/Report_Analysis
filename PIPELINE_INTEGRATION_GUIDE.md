# Report Analysis — Pipeline Integration Guide

This document describes how to add **report comparison analysis** to any existing Device Automation Jenkins pipeline using the shared `report_analysis_stages.groovy` file.

The groovy file handles everything internally (report comparison, git diff, packaging, archiving, HTML publishing), so you only need **3 small changes** to any pipeline.

> **Prerequisite**: The `Report_Analysis` directory (`analyze.py`, `report_fetcher.py`, `report_comparator.py`, `report_formatter.py`, `requirements.txt`, `report_analysis_stages.groovy`) must be present on the Jenkins agent at the path specified by `report_analysis_path` (default: `/home/deviceqa/Report_Analysis`).

---

## Change 1 — Add 3 Parameters

Add the following inside the `parameters { }` block, **after** all existing parameters (batch/testsuite/port/branch):

```groovy
            booleanParam(name: 'enable_report_analysis', defaultValue: true, description: 'Enable comparison analysis against previous build')
            string(name: 'report_analysis_path', defaultValue: '/home/deviceqa/Report_Analysis', description: 'Static path to Report_Analysis scripts on the agent')
            string(name: 'prev_build_number', defaultValue: '', description: 'Previous build number to compare against (leave empty for auto-detect)')
```

| Parameter                | Type    | Purpose |
|--------------------------|---------|---------|
| `enable_report_analysis` | Boolean | Master toggle — when `false`, report analysis is skipped entirely. |
| `report_analysis_path`   | String  | Path on the Jenkins agent where the Report_Analysis scripts live. |
| `prev_build_number`      | String  | Manually pick which build to compare against. Leave empty to auto-detect the last successful build. |

---

## Change 2 — Add 1 Stage

Add this **single stage** after `Publish_Test_Report` (or after the last stage that produces the test report):

```groovy
        stage('Report_Analysis') {
            when {
                expression { return params.enable_report_analysis }
            }
            steps {
                script {
                    def reportAnalysis = load "${params.report_analysis_path}/report_analysis_stages.groovy"
                    reportAnalysis.run(
                        port: params.port,
                        branch: params.branch,
                        reportAnalysisPath: params.report_analysis_path,
                        prevBuildNumber: params.prev_build_number
                    )
                }
            }
        }
```

This single stage call internally runs:
- **Run_Report_Analysis** — resolves previous build, calls `analyze.py` to produce `comparison_report.html` + `.json`
- **Generate_Git_Diff** — produces `git_diff_report.txt` with diff summary, commits, and full diff
- **Package_and_Publish_Analysis** — tars the outputs, calls `archiveArtifacts`, and calls `publishHTML` to create the "Report_Comparison" sidebar link in Jenkins

No changes to the existing `archiveArtifacts` or `publishHTML` in `post` are needed — the groovy file handles both.

---

## Change 3 — Add 1 Line in the Email

In the `post > success` email body, find the test report link:

```html
<p>Test report details available at <a href='${reportUrl}Test_5freport/'>Test_Automation_Report</a></p>
```

Add this line **immediately after** it:

```html
<p>Report comparison available at <a href='${reportUrl}Report_5fComparison/'>Report_Comparison</a></p>
```

> `Report_5fComparison` is Jenkins URL-encoding for `Report_Comparison` (space → `_5f`).

---

## Quick Checklist

- [ ] Added 3 parameters (`enable_report_analysis`, `report_analysis_path`, `prev_build_number`)
- [ ] Added `Report_Analysis` stage after `Publish_Test_Report`
- [ ] Added report comparison link in email body
- [ ] Verified `report_analysis_path` default is correct for the target agent

---

## Things to Adapt Per Pipeline

| Item | What to check |
|------|---------------|
| **`report_analysis_path` default** | Confirm the Report_Analysis scripts exist at this path on the target agent. |
| **`Test_5freport/` URL suffix** | Must match the `reportName` from the pipeline's existing `publishHTML`. Jenkins encodes spaces as `_5f`. |
| **Email subject line** | The subject includes the pipeline/setup name — already pipeline-specific, no change needed. |
| **Python venv path** | The groovy file uses `/home/deviceqa/DTA_venv/nd_test_bot_env/bin/activate`. Change inside the groovy file if the agent uses a different virtualenv. |
| **`nd_test_bot` clone directory** | Git diff runs in `${WORKSPACE}/nd_test_bot`. Adjust inside the groovy file if the repo is cloned elsewhere. |

---

## What the Groovy File Does (Internal Details)

For reference, `report_analysis_stages.groovy` performs these steps when `run()` is called:

1. **Resolves previous build** — uses `prev_build_number` parameter if provided, otherwise finds the last successful build automatically.
2. **Constructs report URLs** — builds Jenkins URLs for both the previous and current build's published test reports.
3. **Runs `analyze.py`** — compares the two reports, producing `comparison_report.html` and `comparison_report.json`.
4. **Generates git diff** — fetches the previous build's branch and produces a diff report with summary stats, commit log, and full diff.
5. **Packages outputs** — creates `report_analysis_output.tar.gz` containing all 3 output files.
6. **Archives the tarball** — calls `archiveArtifacts` so the tarball appears in Jenkins build artifacts.
7. **Publishes HTML report** — calls `publishHTML` so "Report_Comparison" appears in the Jenkins sidebar.
