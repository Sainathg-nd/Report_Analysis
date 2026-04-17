"""
Compares two DAST reports and identifies new, common, and resolved failures.

Also classifies failures by failure reason and service name.
"""
from __future__ import annotations

from collections import defaultdict


def compare_reports(previous_report: dict, current_report: dict) -> dict:
    """
    Compare two parsed DAST reports and return analysis results.

    Args:
        previous_report: Parsed report dict from the older version
        current_report: Parsed report dict from the newer version

    Returns dict with:
    - common_failures: tests that failed in both reports
    - new_failures: tests that failed only in current (new regressions)
    - resolved_failures: tests that failed in previous but passed in current
    - classified_by_reason: failures grouped by failure reason
    - classified_by_service: failures grouped by service name
    - summary: overall comparison summary stats
    """
    # Build lookup maps by TestId (use file_name as fallback key)
    prev_failed = {}
    for tc in previous_report["failed_tests"]:
        key = tc.get("TestId", tc.get("file_name", ""))
        prev_failed[key] = tc

    curr_failed = {}
    for tc in current_report["failed_tests"]:
        key = tc.get("TestId", tc.get("file_name", ""))
        curr_failed[key] = tc

    # Build full test lookup for current report (to check resolved)
    curr_all = {}
    for tc in current_report["test_cases"]:
        key = tc.get("TestId", tc.get("file_name", ""))
        curr_all[key] = tc

    prev_all = {}
    for tc in previous_report["test_cases"]:
        key = tc.get("TestId", tc.get("file_name", ""))
        prev_all[key] = tc

    prev_fail_ids = set(prev_failed.keys())
    curr_fail_ids = set(curr_failed.keys())

    common_ids = prev_fail_ids & curr_fail_ids
    new_ids = curr_fail_ids - prev_fail_ids
    resolved_ids = prev_fail_ids - curr_fail_ids

    # Build result lists with enriched data
    common_failures = []
    for tid in sorted(common_ids):
        common_failures.append({
            "test_id": tid,
            "file_name": curr_failed[tid].get("file_name", ""),
            "description": curr_failed[tid].get("description", ""),
            "service": curr_failed[tid].get("service", ""),
            "failure_reason": _get_failure_reason(curr_failed[tid]),
            "prev_failure_reason": _get_failure_reason(prev_failed[tid]),
            "device_id_current": curr_failed[tid].get("device_id", ""),
            "device_id_previous": prev_failed[tid].get("device_id", ""),
            "linked_issues": curr_failed[tid].get("linked_issues_status", []),
        })

    new_failures = []
    for tid in sorted(new_ids):
        tc = curr_failed[tid]
        prev_status = prev_all.get(tid, {}).get("test_status", "NOT_RUN")
        linked = tc.get("linked_issues_status", [])
        new_failures.append({
            "test_id": tid,
            "file_name": tc.get("file_name", ""),
            "description": tc.get("description", ""),
            "service": tc.get("service", ""),
            "failure_reason": _get_failure_reason(tc),
            "failure_type": _classify_failure_type(tc),
            "is_known_failure": _is_known_failure(linked),
            "previous_status": prev_status,
            "device_id": tc.get("device_id", ""),
            "linked_issues": linked,
        })

    resolved_failures = []
    for tid in sorted(resolved_ids):
        tc = prev_failed[tid]
        curr_status = curr_all.get(tid, {}).get("test_status", "NOT_RUN")
        resolved_failures.append({
            "test_id": tid,
            "file_name": tc.get("file_name", ""),
            "description": tc.get("description", ""),
            "service": tc.get("service", ""),
            "previous_failure_reason": _get_failure_reason(tc),
            "current_status": curr_status,
        })

    # Classify all current failures by reason
    classified_by_reason = _classify_by_reason(
        common_failures, new_failures
    )

    # Classify all current failures by service
    classified_by_service = _classify_by_service(
        common_failures, new_failures
    )

    # Split NEW failures into unknown (not linked) and known (linked to Jira)
    new_unknown_failures = [f for f in new_failures if not f["is_known_failure"]]
    new_known_failures = [f for f in new_failures if f["is_known_failure"]]

    # Group NEW failures by reason and service (all, unknown-only, known-only)
    new_failures_by_reason = _group_by_reason(new_failures)
    new_failures_by_service = _group_by_service(new_failures)
    new_unknown_by_reason = _group_by_reason(new_unknown_failures)
    new_unknown_by_service = _group_by_service(new_unknown_failures)
    new_known_by_reason = _group_by_reason(new_known_failures)
    new_known_by_service = _group_by_service(new_known_failures)

    # Group COMMON failures by reason and service
    common_failures_by_reason = _group_by_reason(common_failures)
    common_failures_by_service = _group_by_service(common_failures)

    return {
        "common_failures": common_failures,
        "new_failures": new_failures,
        "new_unknown_failures": new_unknown_failures,
        "new_known_failures": new_known_failures,
        "resolved_failures": resolved_failures,
        "classified_by_reason": classified_by_reason,
        "classified_by_service": classified_by_service,
        "new_failures_by_reason": new_failures_by_reason,
        "new_failures_by_service": new_failures_by_service,
        "new_unknown_by_reason": new_unknown_by_reason,
        "new_unknown_by_service": new_unknown_by_service,
        "new_known_by_reason": new_known_by_reason,
        "new_known_by_service": new_known_by_service,
        "common_failures_by_reason": common_failures_by_reason,
        "common_failures_by_service": common_failures_by_service,
        "summary": {
            "previous_total_failures": len(prev_failed),
            "current_total_failures": len(curr_failed),
            "common_failure_count": len(common_failures),
            "new_failure_count": len(new_failures),
            "new_unknown_failure_count": len(new_unknown_failures),
            "new_known_failure_count": len(new_known_failures),
            "new_actual_failure_count": sum(
                1 for f in new_failures if f["failure_type"] == "Actual Failure"
            ),
            "new_setup_failure_count": sum(
                1 for f in new_failures if f["failure_type"] == "Setup Failure"
            ),
            "resolved_failure_count": len(resolved_failures),
        },
    }


def _get_failure_reason(test_case: dict) -> str:
    """Extract the primary failure reason from a test case's steps."""
    failure_steps = test_case.get("failure_steps", [])
    if failure_steps:
        # Return the first meaningful failure step
        for step in failure_steps:
            if step and not step.startswith("----"):
                return step
    return "Unknown failure reason"


def _classify_failure_type(test_case: dict) -> str:
    """
    Classify a failed test as 'Setup Failure' or 'Actual Failure'.

    If the very first test step failed, it is a setup failure (the test
    could not get past its precondition / environment setup).
    If the first step passed but a later step failed, it is an actual
    test failure (the test logic itself detected a defect).
    """
    steps = test_case.get("Test_Steps", [])
    if not steps:
        return "Actual Failure"  # no step data → default to actual
    # steps is a list of (description, result) tuples
    first_desc, first_result = steps[0]
    if "fail" in first_result.lower():
        return "Setup Failure"
    return "Actual Failure"


def _is_known_failure(linked_issues: list[dict]) -> bool:
    """
    Return True if the test has at least one real linked Jira issue.

    Issues with id='NA' are ignored — those indicate no linked issue.
    """
    return any(
        iss.get("id", "NA") != "NA"
        for iss in linked_issues
    )


def _classify_by_reason(
    common_failures: list[dict],
    new_failures: list[dict],
) -> dict[str, list[dict]]:
    """
    Group all current failures by their failure reason.

    Returns dict mapping reason -> list of {test_id, type, service, ...}
    """
    reason_map = defaultdict(list)

    for f in common_failures:
        reason = _normalize_reason(f["failure_reason"])
        reason_map[reason].append({
            "test_id": f["test_id"],
            "file_name": f["file_name"],
            "service": f["service"],
            "type": "common",
            "description": f["description"],
        })

    for f in new_failures:
        reason = _normalize_reason(f["failure_reason"])
        reason_map[reason].append({
            "test_id": f["test_id"],
            "file_name": f["file_name"],
            "service": f["service"],
            "type": "new",
            "description": f["description"],
        })

    return dict(reason_map)


def _group_by_reason(failures: list[dict], reason_key: str = "failure_reason") -> list[dict]:
    """
    Group failures by normalized failure reason, sorted by count descending.

    Returns a list of dicts:
      [{"reason": str, "count": int, "tests": [{"test_id", "service", "file_name", "description", "failure_reason"}]}]
    """
    reason_map = defaultdict(list)
    for f in failures:
        reason = _normalize_reason(f.get(reason_key, "Unknown failure reason"))
        entry = {
            "test_id": f["test_id"],
            "file_name": f["file_name"],
            "service": f["service"],
            "description": f["description"],
            "failure_reason": f.get(reason_key, "Unknown failure reason"),
        }
        if "failure_type" in f:
            entry["failure_type"] = f["failure_type"]
        if "is_known_failure" in f:
            entry["is_known_failure"] = f["is_known_failure"]
        if "linked_issues" in f:
            entry["linked_issues"] = f["linked_issues"]
        reason_map[reason].append(entry)
    return sorted(
        [{"reason": r, "count": len(t), "tests": t} for r, t in reason_map.items()],
        key=lambda x: -x["count"],
    )


def _group_by_service(failures: list[dict], reason_key: str = "failure_reason") -> list[dict]:
    """
    Group failures by service name, sorted by count descending.

    Returns a list of dicts:
      [{"service": str, "count": int, "tests": [{"test_id", "file_name", "description", "failure_reason"}]}]
    """
    service_map = defaultdict(list)
    for f in failures:
        entry = {
            "test_id": f["test_id"],
            "file_name": f["file_name"],
            "description": f["description"],
            "failure_reason": f.get(reason_key, "Unknown"),
        }
        if "failure_type" in f:
            entry["failure_type"] = f["failure_type"]
        if "is_known_failure" in f:
            entry["is_known_failure"] = f["is_known_failure"]
        if "linked_issues" in f:
            entry["linked_issues"] = f["linked_issues"]
        service_map[f["service"]].append(entry)
    return sorted(
        [{"service": s, "count": len(t), "tests": t} for s, t in service_map.items()],
        key=lambda x: -x["count"],
    )


def _classify_by_service(
    common_failures: list[dict],
    new_failures: list[dict],
) -> dict[str, dict]:
    """
    Group all current failures by service name.

    Returns dict mapping service -> {common: [...], new: [...]}
    """
    service_map = defaultdict(lambda: {"common": [], "new": []})

    for f in common_failures:
        service_map[f["service"]]["common"].append({
            "test_id": f["test_id"],
            "file_name": f["file_name"],
            "failure_reason": f["failure_reason"],
            "description": f["description"],
        })

    for f in new_failures:
        service_map[f["service"]]["new"].append({
            "test_id": f["test_id"],
            "file_name": f["file_name"],
            "failure_reason": f["failure_reason"],
            "description": f["description"],
        })

    return dict(service_map)


def _normalize_reason(reason: str) -> str:
    """
    Normalize a failure reason string for grouping.

    Strips variable parts like timestamps, file paths, session IDs so
    that similar root causes get grouped together.
    """
    if not reason or reason == "Unknown failure reason":
        return "Unknown failure reason"

    # Strip common variable patterns
    # Remove specific file paths
    normalized = re.sub(r"/home/[^\s'\"]+", "<path>", reason)
    # Remove specific device/session IDs
    normalized = re.sub(r"\b\d{9,}\b", "<device_id>", normalized)
    # Remove timestamps
    normalized = re.sub(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", "<timestamp>", normalized)
    # Remove UUIDs
    normalized = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "<uuid>",
        normalized,
    )

    return normalized.strip()


def compute_service_pass_rates(report: dict) -> dict:
    """
    Compute per-service pass rates from a parsed report.

    Returns a dict mapping service name -> {
        "total": int, "pass": int, "fail": int, "ne": int, "na": int,
        "pass_rate": float,  # 0-100
        "status": str,  # "pass" | "warn" | "fail" | "na"
    }

    Status thresholds:
        pass_rate >= 90  -> "pass"  (checkmark)
        pass_rate >= 85  -> "warn"  (exclamation)
        pass_rate <  85  -> "fail"  (X)
        na (no applicable tests) -> "na"
    """
    from collections import defaultdict

    service_stats = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0, "ne": 0, "na": 0})

    for tc in report["test_cases"]:
        svc = tc.get("service", "UNKNOWN")
        status = tc.get("test_status", "")
        service_stats[svc]["total"] += 1
        if status == "Pass":
            service_stats[svc]["pass"] += 1
        elif status == "Fail":
            service_stats[svc]["fail"] += 1
        elif status == "NE":
            service_stats[svc]["ne"] += 1
        elif status == "NA":
            service_stats[svc]["na"] += 1

    result = {}
    for svc, stats in sorted(service_stats.items()):
        applicable = stats["total"] - stats["na"]
        if applicable <= 0:
            pass_rate = 0.0
            status_label = "na"
        else:
            pass_rate = (stats["pass"] / applicable) * 100
            if pass_rate >= 90:
                status_label = "pass"
            elif pass_rate >= 85:
                status_label = "warn"
            else:
                status_label = "fail"
        result[svc] = {
            **stats,
            "pass_rate": round(pass_rate, 1),
            "status": status_label,
        }

    return result


import re
