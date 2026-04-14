"""
Formats the comparison results into readable output (console + HTML report).
"""

import os
import json
from datetime import datetime


# ─── Console Output ──────────────────────────────────────────────────────────

def print_summary(comparison: dict, prev_report: dict, curr_report: dict,
                  prev_version: str, curr_version: str):
    """Print the full comparison summary to the console."""
    s = comparison["summary"]
    print("=" * 80)
    print("DAST REPORT COMPARISON ANALYSIS")
    print("=" * 80)
    print(f"  Previous : {prev_version}")
    print(f"  Current  : {curr_version}")
    print("-" * 80)

    # Overall stats
    ps = prev_report["summary"]
    cs = curr_report["summary"]
    print(f"\n{'Metric':<30} {'Previous':>12} {'Current':>12} {'Delta':>12}")
    print("-" * 66)
    print(f"{'Total Test Cases':<30} {ps['total']:>12} {cs['total']:>12} {cs['total']-ps['total']:>+12}")
    print(f"{'Pass':<30} {ps['pass']:>12} {cs['pass']:>12} {cs['pass']-ps['pass']:>+12}")
    print(f"{'Fail':<30} {ps['fail']:>12} {cs['fail']:>12} {cs['fail']-ps['fail']:>+12}")
    print(f"{'Not Executed':<30} {ps['not_executed']:>12} {cs['not_executed']:>12} {cs['not_executed']-ps['not_executed']:>+12}")
    print(f"{'Pass Rate':<30} {ps['pass_rate']:>12} {cs['pass_rate']:>12}")

    # Failure comparison summary
    print(f"\n{'─' * 80}")
    print(f"FAILURE COMPARISON")
    print(f"{'─' * 80}")
    print(f"  Common failures (in both reports) : {s['common_failure_count']}")
    print(f"  New failures (only in current)    : {s['new_failure_count']}")
    print(f"      Unknown (no linked issue)     : {s.get('new_unknown_failure_count', '-')}")
    print(f"      Known  (linked Jira issue)    : {s.get('new_known_failure_count', '-')}")
    print(f"  Resolved (fixed in current)       : {s['resolved_failure_count']}")

    # New failures detail
    if comparison["new_failures"]:
        print(f"\n{'─' * 80}")
        print(f"NEW FAILURES ({len(comparison['new_failures'])})")
        print(f"{'─' * 80}")
        for i, f in enumerate(comparison["new_failures"], 1):
            known_tag = "Known" if f.get("is_known_failure") else "Unknown"
            print(f"\n  {i}. {f['test_id']} [{f['service']}] ({f.get('failure_type', '')}) [{known_tag}]")
            print(f"     File: {f['file_name']}")
            print(f"     Desc: {f['description']}")
            print(f"     Reason: {f['failure_reason']}")
            print(f"     Previous Status: {f['previous_status']}")
            if f.get("linked_issues"):
                issues_str = ", ".join(
                    f"{iss['id']}({iss['status']})" for iss in f["linked_issues"]
                )
                print(f"     Linked Issues: {issues_str}")

    # Top new failures by reason
    if comparison.get("new_failures_by_reason"):
        print(f"\n{'─' * 80}")
        print(f"TOP NEW FAILURE REASONS (ranked by count)")
        print(f"{'─' * 80}")
        print(f"\n  {'#':<4} {'Count':>5}  {'Reason':<60} Services Affected")
        print(f"  {'─'*4} {'─'*5}  {'─'*60} {'─'*30}")
        for i, entry in enumerate(comparison["new_failures_by_reason"], 1):
            services = sorted(set(t["service"] for t in entry["tests"]))
            svc_str = ", ".join(services)
            print(f"  {i:<4} {entry['count']:>5}  {entry['reason'][:60]:<60} {svc_str}")
        # Detail for top reasons (count >= 2)
        print(f"\n  --- Detail for top reasons (count >= 2) ---")
        for entry in comparison["new_failures_by_reason"]:
            if entry["count"] < 2:
                break
            print(f"\n  [{entry['count']}] {entry['reason']}")
            for tc in entry["tests"]:
                print(f"       {tc['test_id']} [{tc['service']}] - {tc['description']}")

    # Common failures detail
    if comparison["common_failures"]:
        print(f"\n{'─' * 80}")
        print(f"COMMON FAILURES ({len(comparison['common_failures'])})")
        print(f"{'─' * 80}")
        for i, f in enumerate(comparison["common_failures"], 1):
            print(f"\n  {i}. {f['test_id']} [{f['service']}]")
            print(f"     File: {f['file_name']}")
            print(f"     Desc: {f['description']}")
            print(f"     Reason: {f['failure_reason']}")
            if f.get("linked_issues"):
                issues_str = ", ".join(
                    f"{iss['id']}({iss['status']})" for iss in f["linked_issues"]
                )
                print(f"     Linked Issues: {issues_str}")

    # Resolved failures
    if comparison["resolved_failures"]:
        print(f"\n{'─' * 80}")
        print(f"RESOLVED FAILURES ({len(comparison['resolved_failures'])})")
        print(f"{'─' * 80}")
        for i, f in enumerate(comparison["resolved_failures"], 1):
            print(f"  {i}. {f['test_id']} [{f['service']}] -> {f['current_status']}")

    # Classification by service
    if comparison["classified_by_service"]:
        print(f"\n{'─' * 80}")
        print(f"FAILURES CLASSIFIED BY SERVICE")
        print(f"{'─' * 80}")
        for svc, data in sorted(comparison["classified_by_service"].items()):
            total = len(data["common"]) + len(data["new"])
            print(f"\n  {svc} (Total: {total} | Common: {len(data['common'])} | New: {len(data['new'])})")
            for tc in data["common"]:
                print(f"    [COMMON] {tc['test_id']}: {tc['failure_reason']}")
            for tc in data["new"]:
                print(f"    [NEW]    {tc['test_id']}: {tc['failure_reason']}")

    # Classification by reason
    if comparison["classified_by_reason"]:
        print(f"\n{'─' * 80}")
        print(f"FAILURES CLASSIFIED BY REASON")
        print(f"{'─' * 80}")
        for reason, tests in sorted(
            comparison["classified_by_reason"].items(),
            key=lambda x: -len(x[1]),
        ):
            print(f"\n  Reason: {reason}")
            print(f"  Count: {len(tests)}")
            for tc in tests:
                tag = "[COMMON]" if tc["type"] == "common" else "[NEW]   "
                print(f"    {tag} {tc['test_id']} [{tc['service']}]")

    print(f"\n{'=' * 80}")


# ─── HTML Report ─────────────────────────────────────────────────────────────

def _build_grouped_by_reason_html(data: list[dict], badge_class: str, color: str) -> tuple[str, str]:
    """Build summary rows and detail cards for grouped-by-reason sections."""
    summary_rows = ""
    detail_cards = ""
    for i, entry in enumerate(data, 1):
        services = sorted(set(t["service"] for t in entry["tests"]))
        svc_badges = " ".join(
            f'<span class="badge badge-svc">{_html_escape(s)}</span>' for s in services
        )
        summary_rows += f"""
        <tr>
            <td style="text-align:center;font-weight:bold">{i}</td>
            <td style="text-align:center"><span class="count-badge {badge_class}">{entry['count']}</span></td>
            <td>{_html_escape(entry['reason'])}</td>
            <td>{svc_badges}</td>
        </tr>"""
        detail_rows = "".join(
            f"""<tr><td>{t['test_id']}</td><td>{_html_escape(t['service'])}</td>
            <td>{_html_escape(t['file_name'])}</td><td>{_html_escape(t['description'])}</td>
            <td>{_failure_type_badge(t.get('failure_type', ''))}</td>
            <td>{_known_failure_badge(t)}</td></tr>"""
            for t in entry["tests"]
        )
        detail_cards += f"""
        <details class="detail-card">
            <summary style="color:{color};cursor:pointer;font-weight:bold;font-size:13px;">#{i} [{entry['count']} tests] {_html_escape(entry['reason'])}</summary>
            <table style="margin-top:8px;"><thead><tr><th>Test ID</th><th>Service</th><th>File Name</th><th>Description</th><th>Type</th><th>Status</th></tr></thead>
            <tbody>{detail_rows}</tbody></table>
        </details>"""
    return summary_rows, detail_cards


def _build_grouped_by_service_html(data: list[dict], badge_class: str, color: str) -> tuple[str, str]:
    """Build summary rows and detail cards for grouped-by-service sections."""
    summary_rows = ""
    detail_cards = ""
    for i, entry in enumerate(data, 1):
        reasons = {}
        for t in entry["tests"]:
            r = t["failure_reason"][:80]
            reasons[r] = reasons.get(r, 0) + 1
        reason_parts = sorted(reasons.items(), key=lambda x: -x[1])
        reason_summary = ", ".join(f"{_html_escape(r)} ({c})" for r, c in reason_parts)
        summary_rows += f"""
        <tr>
            <td style="text-align:center;font-weight:bold">{i}</td>
            <td style="text-align:center"><span class="count-badge {badge_class}">{entry['count']}</span></td>
            <td><strong>{_html_escape(entry['service'])}</strong></td>
            <td style="font-size:12px">{reason_summary}</td>
        </tr>"""
        detail_rows = "".join(
            f"""<tr><td>{t['test_id']}</td><td>{_html_escape(t['file_name'])}</td>
            <td>{_html_escape(t['failure_reason'])}</td><td>{_html_escape(t['description'])}</td>
            <td>{_failure_type_badge(t.get('failure_type', ''))}</td>
            <td>{_known_failure_badge(t)}</td></tr>"""
            for t in entry["tests"]
        )
        detail_cards += f"""
        <details class="detail-card">
            <summary style="color:{color};cursor:pointer;font-weight:bold;font-size:13px;">#{i} {_html_escape(entry['service'])} [{entry['count']} tests]</summary>
            <table style="margin-top:8px;"><thead><tr><th>Test ID</th><th>File Name</th><th>Failure Reason</th><th>Description</th><th>Type</th><th>Status</th></tr></thead>
            <tbody>{detail_rows}</tbody></table>
        </details>"""
    return summary_rows, detail_cards


def generate_html_report(
    comparison: dict,
    prev_report: dict,
    curr_report: dict,
    prev_version: str,
    curr_version: str,
    output_path: str = "comparison_report.html",
):
    """Generate an HTML comparison report."""
    s = comparison["summary"]
    ps = prev_report["summary"] if prev_report.get("summary") else comparison.get("prev_report_summary", {})
    cs = curr_report["summary"] if curr_report.get("summary") else comparison.get("curr_report_summary", {})

    # --- Build grouped data rows ---

    # New failures by reason (all)
    new_by_reason = comparison.get("new_failures_by_reason", [])
    new_reason_rows, new_reason_details = _build_grouped_by_reason_html(
        new_by_reason, "count-new", "#c62828"
    )

    # New failures by service (all)
    new_by_service = comparison.get("new_failures_by_service", [])
    new_service_rows, new_service_details = _build_grouped_by_service_html(
        new_by_service, "count-new", "#c62828"
    )

    # New UNKNOWN failures by reason and service
    new_unk_by_reason = comparison.get("new_unknown_by_reason", [])
    new_unk_reason_rows, new_unk_reason_details = _build_grouped_by_reason_html(
        new_unk_by_reason, "count-new", "#c62828"
    )
    new_unk_by_service = comparison.get("new_unknown_by_service", [])
    new_unk_service_rows, new_unk_service_details = _build_grouped_by_service_html(
        new_unk_by_service, "count-new", "#c62828"
    )

    # New KNOWN failures by reason and service
    new_known_by_reason = comparison.get("new_known_by_reason", [])
    new_known_reason_rows, new_known_reason_details = _build_grouped_by_reason_html(
        new_known_by_reason, "count-known", "#6a1b9a"
    )
    new_known_by_service = comparison.get("new_known_by_service", [])
    new_known_service_rows, new_known_service_details = _build_grouped_by_service_html(
        new_known_by_service, "count-known", "#6a1b9a"
    )

    # Common failures by reason
    common_by_reason = comparison.get("common_failures_by_reason", [])
    common_reason_rows, common_reason_details = _build_grouped_by_reason_html(
        common_by_reason, "count-common", "#e65100"
    )

    # Common failures by service
    common_by_service = comparison.get("common_failures_by_service", [])
    common_service_rows, common_service_details = _build_grouped_by_service_html(
        common_by_service, "count-common", "#e65100"
    )

    # Resolved rows
    resolved_rows = ""
    for f in comparison["resolved_failures"]:
        resolved_rows += f"""
        <tr>
            <td>{f['test_id']}</td>
            <td>{_html_escape(f['file_name'])}</td>
            <td>{_html_escape(f['service'])}</td>
            <td>{f['current_status']}</td>
        </tr>"""

    # Compute pass rate delta
    prev_rate = float(ps.get('pass_rate', 'N/A').rstrip('%')) if ps.get('pass_rate', 'N/A') != 'N/A' else None
    curr_rate = float(cs.get('pass_rate', 'N/A').rstrip('%')) if cs.get('pass_rate', 'N/A') != 'N/A' else None
    has_full_summary = ps.get('total', 0) > 0 or cs.get('total', 0) > 0

    # Build comparison table rows — always show all rows
    def _val(v):
        return v if v is not None and v != 0 else "N/A"

    def _data_row(label, pv, cv, higher_is_good=True):
        if pv in (None, "N/A", 0) and cv in (None, "N/A", 0):
            # Both unavailable — show N/A
            return f'<tr><td>{label}</td><td>N/A</td><td>N/A</td><td class="delta-zero">—</td></tr>'
        delta = cv - pv
        if higher_is_good:
            cls = 'delta-good' if delta > 0 else ('delta-bad' if delta < 0 else 'delta-zero')
        else:
            cls = 'delta-bad' if delta > 0 else ('delta-good' if delta < 0 else 'delta-zero')
        return f'<tr><td>{label}</td><td>{pv}</td><td>{cv}</td><td class="{cls}">{delta:+d}</td></tr>'

    compare_rows = ""
    if has_full_summary:
        compare_rows += _data_row("Total Test Cases", ps.get('total', 0), cs.get('total', 0))
        compare_rows += _data_row("Pass", ps.get('pass', 0), cs.get('pass', 0))
        compare_rows += _data_row("Fail", ps.get('fail', 0), cs.get('fail', 0), higher_is_good=False)
        compare_rows += _data_row("Not Executed", ps.get('not_executed', 0), cs.get('not_executed', 0), higher_is_good=False)
        if prev_rate is not None and curr_rate is not None:
            rate_delta = curr_rate - prev_rate
            rate_cls = 'delta-good' if rate_delta > 0 else ('delta-bad' if rate_delta < 0 else 'delta-zero')
            compare_rows += (f'<tr><td>Pass Rate</td><td>{ps["pass_rate"]}</td>'
                             f'<td>{cs["pass_rate"]}</td><td class="{rate_cls}">{rate_delta:+.1f}%</td></tr>')
        else:
            compare_rows += '<tr><td>Pass Rate</td><td>N/A</td><td>N/A</td><td class="delta-zero">—</td></tr>'
    else:
        # Only failure counts from comparison summary
        prev_fail = s['previous_total_failures']
        curr_fail = s['current_total_failures']
        compare_rows += '<tr><td>Total Test Cases</td><td>N/A</td><td>N/A</td><td class="delta-zero">—</td></tr>'
        compare_rows += '<tr><td>Pass</td><td>N/A</td><td>N/A</td><td class="delta-zero">—</td></tr>'
        compare_rows += _data_row("Fail", prev_fail, curr_fail, higher_is_good=False)
        compare_rows += '<tr><td>Not Executed</td><td>N/A</td><td>N/A</td><td class="delta-zero">—</td></tr>'
        compare_rows += '<tr><td>Pass Rate</td><td>N/A</td><td>N/A</td><td class="delta-zero">—</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DAST Report Comparison - {prev_version} vs {curr_version}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; color: #333; }}
        .header {{
            background: linear-gradient(135deg, #1a237e, #283593);
            color: white; padding: 25px 40px;
        }}
        .header h1 {{ font-size: 24px; margin-bottom: 5px; }}
        .header p {{ opacity: 0.85; font-size: 14px; }}
        .container {{ max-width: 1400px; margin: 20px auto; padding: 0 20px; }}
        .card {{
            background: white; border-radius: 8px; padding: 20px;
            margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .card h2 {{
            font-size: 18px; margin-bottom: 15px; padding-bottom: 8px;
            border-bottom: 2px solid #e0e0e0; color: #1a237e;
        }}
        .card h3 {{
            font-size: 15px; margin: 18px 0 10px 0; color: #333;
        }}
        .stats-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px; margin-bottom: 20px;
        }}
        .stat-box {{
            background: #f5f7fa; border-radius: 6px; padding: 15px;
            text-align: center; border-left: 4px solid #1a237e;
        }}
        .stat-box.total {{ border-left-color: #1a237e; background: #e8eaf6; }}
        .stat-box.new {{ border-left-color: #c62828; }}
        .stat-box.common {{ border-left-color: #f57f17; }}
        .stat-box.resolved {{ border-left-color: #2e7d32; }}
        .stat-box .number {{ font-size: 28px; font-weight: bold; }}
        .stat-box .label {{ font-size: 12px; color: #666; margin-top: 4px; }}

        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th {{ background: #1a237e; color: white; padding: 10px 8px; text-align: left; }}
        td {{ padding: 8px; border-bottom: 1px solid #e0e0e0; }}
        tr:hover {{ background: #f5f7fa; }}
        .badge {{
            display: inline-block; padding: 2px 8px; border-radius: 3px;
            font-size: 11px; font-weight: bold;
        }}
        .badge-new {{ background: #ffebee; color: #c62828; }}
        .badge-common {{ background: #fff8e1; color: #f57f17; }}
        .badge-resolved {{ background: #e8f5e9; color: #2e7d32; }}
        .badge-svc {{ background: #e3f2fd; color: #1565c0; }}
        .count-badge {{
            display: inline-block; font-size: 16px; font-weight: bold;
            min-width: 28px; text-align: center;
        }}
        .count-new {{ color: #c62828; }}
        .count-common {{ color: #e65100; }}
        .count-known {{ color: #6a1b9a; }}
        .detail-card {{
            margin-top: 12px; padding: 10px; background: #fafafa;
            border-radius: 6px; border: 1px solid #e0e0e0;
        }}
        .detail-card h4 {{
            margin-bottom: 8px; font-size: 13px;
        }}
        .section-label {{
            display: inline-block; padding: 3px 10px; border-radius: 4px;
            font-size: 12px; font-weight: bold; margin-bottom: 10px;
        }}
        .section-label.new {{ background: #ffebee; color: #c62828; }}
        .section-label.common {{ background: #fff8e1; color: #e65100; }}
        .section-label.known {{ background: #f3e5f5; color: #6a1b9a; }}
        .nav {{
            position: sticky; top: 0; background: white; z-index: 100;
            padding: 10px 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex; gap: 8px; flex-wrap: wrap; align-items: center;
        }}
        .nav a {{
            color: #1a237e; text-decoration: none; padding: 5px 12px;
            border-radius: 4px; font-size: 13px; font-weight: 500;
        }}
        .nav a:hover {{ background: #e8eaf6; }}
        .nav .sep {{ color: #ccc; font-size: 16px; }}
        .delta-good {{ color: #2e7d32; font-weight: bold; }}
        .delta-bad {{ color: #c62828; font-weight: bold; }}
        .delta-zero {{ color: #666; }}
        details.detail-card {{ margin-top: 12px; padding: 10px; background: #fafafa; border-radius: 6px; border: 1px solid #e0e0e0; }}
        details.detail-card summary {{ padding: 4px 0; }}
        details.detail-card summary::-webkit-details-marker {{ margin-right: 6px; }}
        .expand-btn {{
            display: inline-block; padding: 4px 12px; border-radius: 4px;
            font-size: 12px; font-weight: 500; cursor: pointer;
            background: #e8eaf6; color: #1a237e; border: 1px solid #c5cae9;
            margin-bottom: 10px;
        }}
        .expand-btn:hover {{ background: #c5cae9; }}
        .compare-table td:nth-child(n+2) {{ text-align: center; }}
        .compare-table th:nth-child(n+2) {{ text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>DAST Report Comparison Analysis</h1>
        <p>{prev_version} &rarr; {curr_version} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <div class="nav">
        <a href="#overview">Overview</a>
        <span class="sep">|</span>
        <a href="#new-unknown-by-reason" style="color:#c62828">Unknown New: By Reason ({s.get('new_unknown_failure_count', 0)})</a>
        <a href="#new-unknown-by-service" style="color:#c62828">Unknown New: By Service</a>
        <span class="sep">|</span>
        <a href="#new-known-by-reason" style="color:#6a1b9a">Known New: By Reason ({s.get('new_known_failure_count', 0)})</a>
        <a href="#new-known-by-service" style="color:#6a1b9a">Known New: By Service</a>
        <span class="sep">|</span>
        <a href="#new-by-reason" style="color:#c62828">All New: By Reason ({s['new_failure_count']})</a>
        <a href="#new-by-service" style="color:#c62828">All New: By Service</a>
        <span class="sep">|</span>
        <a href="#common-by-reason" style="color:#e65100">Common: By Reason ({s['common_failure_count']})</a>
        <a href="#common-by-service" style="color:#e65100">Common: By Service</a>
        <span class="sep">|</span>
        <a href="#resolved" style="color:#2e7d32">Resolved ({s['resolved_failure_count']})</a>
    </div>

    <div class="container">

        <!-- ============ OVERVIEW ============ -->
        <div class="card" id="overview">
            <h2>Overview</h2>

            <div class="stats-grid">
                <div class="stat-box total">
                    <div class="number">{s['current_total_failures']}</div>
                    <div class="label">Total Current Failures</div>
                </div>
                <div class="stat-box new">
                    <div class="number">{s['new_failure_count']}</div>
                    <div class="label">New Failures (Regressions)</div>
                </div>
                <div class="stat-box common">
                    <div class="number">{s['common_failure_count']}</div>
                    <div class="label">Common Failures (Persistent)</div>
                </div>
                <div class="stat-box resolved">
                    <div class="number">{s['resolved_failure_count']}</div>
                    <div class="label">Resolved (Fixed)</div>
                </div>
            </div>

            <table class="compare-table">
                <thead>
                    <tr><th>Metric</th><th>{prev_version}</th><th>{curr_version}</th><th>Delta</th></tr>
                </thead>
                <tbody>
                    {compare_rows}
                </tbody>
            </table>

            <!-- New Failures Breakdown: Unknown vs Known -->
            <div style="margin-top:20px;">
                <h3 style="font-size:14px;color:#333;margin-bottom:10px;">New Failures Breakdown</h3>
                <div style="display:flex;gap:20px;font-size:13px;">
                    <span>&#9679; <strong style="color:#c62828;">Unknown ({s.get('new_unknown_failure_count',0)})</strong> &mdash; No linked Jira issue, needs investigation</span>
                    <span>&#9679; <strong style="color:#6a1b9a;">Known ({s.get('new_known_failure_count',0)})</strong> &mdash; Linked to Jira, already tracked</span>
                </div>
            </div>
        </div>

        <!-- ============ NEW UNKNOWN FAILURES - BY REASON ============ -->
        <div class="card" id="new-unknown-by-reason">
            <h2><span class="section-label new">NEW &mdash; UNKNOWN</span> Failures Grouped by Reason ({s.get('new_unknown_failure_count', 0)} total &mdash; no linked Jira issue)</h2>
            {"<p>No unknown new failures.</p>" if not new_unk_by_reason else f'''
            <table>
                <thead>
                    <tr><th style="width:40px">#</th><th style="width:60px">Count</th><th>Failure Reason</th><th>Services Affected</th></tr>
                </thead>
                <tbody>{new_unk_reason_rows}</tbody>
            </table>
            <h3>Detailed Breakdown <span class="expand-btn" onclick="toggleAll(this)">Expand All</span></h3>
            {new_unk_reason_details}'''}
        </div>

        <!-- ============ NEW UNKNOWN FAILURES - BY SERVICE ============ -->
        <div class="card" id="new-unknown-by-service">
            <h2><span class="section-label new">NEW &mdash; UNKNOWN</span> Failures Grouped by Service ({s.get('new_unknown_failure_count', 0)} total)</h2>
            {"<p>No unknown new failures.</p>" if not new_unk_by_service else f'''
            <table>
                <thead>
                    <tr><th style="width:40px">#</th><th style="width:60px">Count</th><th>Service</th><th>Failure Reasons (count)</th></tr>
                </thead>
                <tbody>{new_unk_service_rows}</tbody>
            </table>
            <h3>Detailed Breakdown <span class="expand-btn" onclick="toggleAll(this)">Expand All</span></h3>
            {new_unk_service_details}'''}
        </div>

        <!-- ============ NEW KNOWN FAILURES - BY REASON ============ -->
        <div class="card" id="new-known-by-reason">
            <h2><span class="section-label known">NEW &mdash; KNOWN</span> Failures Grouped by Reason ({s.get('new_known_failure_count', 0)} total &mdash; linked to Jira)</h2>
            {"<p>No known new failures.</p>" if not new_known_by_reason else f'''
            <table>
                <thead>
                    <tr><th style="width:40px">#</th><th style="width:60px">Count</th><th>Failure Reason</th><th>Services Affected</th></tr>
                </thead>
                <tbody>{new_known_reason_rows}</tbody>
            </table>
            <h3>Detailed Breakdown <span class="expand-btn" onclick="toggleAll(this)">Expand All</span></h3>
            {new_known_reason_details}'''}
        </div>

        <!-- ============ NEW KNOWN FAILURES - BY SERVICE ============ -->
        <div class="card" id="new-known-by-service">
            <h2><span class="section-label known">NEW &mdash; KNOWN</span> Failures Grouped by Service ({s.get('new_known_failure_count', 0)} total)</h2>
            {"<p>No known new failures.</p>" if not new_known_by_service else f'''
            <table>
                <thead>
                    <tr><th style="width:40px">#</th><th style="width:60px">Count</th><th>Service</th><th>Failure Reasons (count)</th></tr>
                </thead>
                <tbody>{new_known_service_rows}</tbody>
            </table>
            <h3>Detailed Breakdown <span class="expand-btn" onclick="toggleAll(this)">Expand All</span></h3>
            {new_known_service_details}'''}
        </div>

        <!-- ============ NEW FAILURES - BY REASON (ALL) ============ -->
        <div class="card" id="new-by-reason">
            <h2><span class="section-label new">NEW</span> All Failures Grouped by Reason ({s['new_failure_count']} total)</h2>
            {"<p>No new failures.</p>" if not new_by_reason else f'''
            <table>
                <thead>
                    <tr><th style="width:40px">#</th><th style="width:60px">Count</th><th>Failure Reason</th><th>Services Affected</th></tr>
                </thead>
                <tbody>{new_reason_rows}</tbody>
            </table>
            <h3>Detailed Breakdown <span class="expand-btn" onclick="toggleAll(this)">Expand All</span></h3>
            {new_reason_details}'''}
        </div>

        <!-- ============ NEW FAILURES - BY SERVICE ============ -->
        <div class="card" id="new-by-service">
            <h2><span class="section-label new">NEW</span> All Failures Grouped by Service ({s['new_failure_count']} total)</h2>
            {"<p>No new failures.</p>" if not new_by_service else f'''
            <table>
                <thead>
                    <tr><th style="width:40px">#</th><th style="width:60px">Count</th><th>Service</th><th>Failure Reasons (count)</th></tr>
                </thead>
                <tbody>{new_service_rows}</tbody>
            </table>
            <h3>Detailed Breakdown <span class="expand-btn" onclick="toggleAll(this)">Expand All</span></h3>
            {new_service_details}'''}
        </div>

        <!-- ============ COMMON FAILURES - BY REASON ============ -->
        <div class="card" id="common-by-reason">
            <h2><span class="section-label common">COMMON</span> Failures Grouped by Reason ({s['common_failure_count']} total)</h2>
            {"<p>No common failures.</p>" if not common_by_reason else f'''
            <table>
                <thead>
                    <tr><th style="width:40px">#</th><th style="width:60px">Count</th><th>Failure Reason</th><th>Services Affected</th></tr>
                </thead>
                <tbody>{common_reason_rows}</tbody>
            </table>
            <h3>Detailed Breakdown <span class="expand-btn" onclick="toggleAll(this)">Expand All</span></h3>
            {common_reason_details}'''}
        </div>

        <!-- ============ COMMON FAILURES - BY SERVICE ============ -->
        <div class="card" id="common-by-service">
            <h2><span class="section-label common">COMMON</span> Failures Grouped by Service ({s['common_failure_count']} total)</h2>
            {"<p>No common failures.</p>" if not common_by_service else f'''
            <table>
                <thead>
                    <tr><th style="width:40px">#</th><th style="width:60px">Count</th><th>Service</th><th>Failure Reasons (count)</th></tr>
                </thead>
                <tbody>{common_service_rows}</tbody>
            </table>
            <h3>Detailed Breakdown <span class="expand-btn" onclick="toggleAll(this)">Expand All</span></h3>
            {common_service_details}'''}
        </div>

        <!-- ============ RESOLVED ============ -->
        <div class="card" id="resolved">
            <h2><span class="section-label" style="background:#e8f5e9;color:#2e7d32;">RESOLVED</span> Failures ({s['resolved_failure_count']})</h2>
            {"<p>No resolved failures.</p>" if not comparison["resolved_failures"] else f'''
            <table>
                <thead>
                    <tr><th>Test ID</th><th>File Name</th><th>Service</th><th>Current Status</th></tr>
                </thead>
                <tbody>{resolved_rows}</tbody>
            </table>'''}
        </div>

    </div>
    <script>
    function toggleAll(btn) {{
        const card = btn.closest('.card');
        const details = card.querySelectorAll('details');
        const allOpen = Array.from(details).every(d => d.open);
        details.forEach(d => d.open = !allOpen);
        btn.textContent = allOpen ? 'Expand All' : 'Collapse All';
    }}
    </script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nHTML report saved to: {os.path.abspath(output_path)}")


# ─── JSON Export ─────────────────────────────────────────────────────────────

def export_json(comparison: dict, output_path: str = "comparison_report.json",
                prev_report: dict = None, curr_report: dict = None,
                prev_version: str = "", curr_version: str = ""):
    """Export comparison results as JSON, including report summaries for regeneration."""
    data = dict(comparison)
    if prev_report:
        data["prev_report_summary"] = prev_report["summary"]
    if curr_report:
        data["curr_report_summary"] = curr_report["summary"]
    if prev_version:
        data["prev_version"] = prev_version
    if curr_version:
        data["curr_version"] = curr_version
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"JSON report saved to: {os.path.abspath(output_path)}")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _html_escape(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _delta_class(delta: int, invert: bool = False) -> str:
    """Return CSS class based on delta direction."""
    if delta == 0:
        return "delta-zero"
    if invert:
        return "delta-neg" if delta > 0 else "delta-pos"
    return "delta-pos" if delta > 0 else "delta-neg"


def _failure_type_badge(failure_type: str) -> str:
    """Return an HTML badge for the failure type."""
    if failure_type == "Setup Failure":
        return '<span class="badge" style="background:#fff3e0;color:#e65100;">Setup</span>'
    if failure_type == "Actual Failure":
        return '<span class="badge" style="background:#ffebee;color:#c62828;">Actual</span>'
    return ""


def _known_failure_badge(test: dict) -> str:
    """Return an HTML badge indicating Known or Unknown failure."""
    if test.get("is_known_failure"):
        issues = test.get("linked_issues", [])
        real = [i for i in issues if i.get("id", "NA") != "NA"]
        ids = ", ".join(i["id"] for i in real[:3])
        if len(real) > 3:
            ids += f" +{len(real) - 3}"
        return (f'<span class="badge" style="background:#f3e5f5;color:#6a1b9a;" '
                f'title="{_html_escape(ids)}">Known</span>')
    return '<span class="badge" style="background:#e8eaf6;color:#1a237e;">Unknown</span>'
