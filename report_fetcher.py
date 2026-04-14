"""
Fetches DAST report data from Jenkins report URLs.

Parses the static/scr.js JavaScript file from the published HTML report
to extract test case data, device info, and output metadata.
"""

import re
import json
import requests
from urllib.parse import urljoin


def fetch_report_js(report_url: str, timeout: int = 60) -> str:
    """Fetch the raw scr.js content from a DAST report URL."""
    # Normalize URL
    if not report_url.endswith("/"):
        report_url += "/"
    js_url = urljoin(report_url, "static/scr.js")
    resp = requests.get(js_url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def _js_to_json_array(js_text: str, var_name: str) -> list:
    """
    Extract a JS array variable from scr.js and convert it to Python objects.

    Uses regex to find the variable boundaries, then converts JS object
    notation to valid JSON (adds quotes around keys, handles single quotes, etc.)
    """
    # Find the start of the variable
    pattern = rf'^(const|var|let)\s+{var_name}\s*=\s*\['
    match = re.search(pattern, js_text, re.MULTILINE)
    if not match:
        raise ValueError(f"Variable '{var_name}' not found in JS content")

    start = match.start()
    # Find the matching bracket
    bracket_start = js_text.index("[", start)
    depth = 0
    pos = bracket_start
    while pos < len(js_text):
        ch = js_text[pos]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                break
        elif ch in ("'", '"'):
            # Skip strings
            quote = ch
            pos += 1
            while pos < len(js_text) and js_text[pos] != quote:
                if js_text[pos] == "\\":
                    pos += 1
                pos += 1
        pos += 1

    raw_array = js_text[bracket_start : pos + 1]
    return raw_array


def _parse_test_data(js_text: str) -> list[dict]:
    """
    Parse the 'data' array from scr.js into a list of test case dicts.

    Each test case dict contains:
    - TestId, file_name, description, test_status, device_id
    - Test_Steps (list of dicts mapping step description -> result)
    - linked_issues_status, start_time, end_time, time_taken
    """
    # We'll use a line-by-line approach to parse the JS objects
    # since the data array is too large and has non-JSON syntax
    tests = []
    current_test = {}
    in_data = False

    lines = js_text.split("\n")
    i = 0

    # Find the 'const data = [' line
    while i < len(lines):
        if re.match(r'^const\s+data\s*=\s*\[', lines[i]):
            in_data = True
            i += 1
            break
        i += 1

    if not in_data:
        return tests

    while i < len(lines):
        line = lines[i].strip()

        # End of data array
        if line == "]" or line.startswith("const ") or line.startswith("var "):
            # Save last test if exists
            if current_test and "TestId" in current_test:
                tests.append(current_test)
            break

        # Start of new test object
        if line == "{":
            if current_test and "TestId" in current_test:
                tests.append(current_test)
            current_test = {}
            i += 1
            continue

        # End of test object
        if line in ("},", "}"):
            i += 1
            continue

        # Parse key-value pairs (skip Test_Steps for now - too complex)
        for field in ["TestId", "file_name", "description", "test_status",
                       "device_id", "time_taken", "start_time", "end_time",
                       "is_child", "isExecuted", "IsForceto", "retry"]:
            match = re.match(rf'^{field}:\s*"([^"]*)"', line)
            if match:
                current_test[field] = match.group(1)
                break

        # Parse Test_Steps - extract failure steps
        if line.startswith("Test_Steps:"):
            steps = _extract_test_steps(line)
            current_test["Test_Steps"] = steps
            current_test["failure_steps"] = [
                step_desc for step_desc, result in steps
                if "fail" in result.lower()
            ]

        # Parse linked_issues_status
        if line.startswith("linked_issues_status:"):
            issues = _extract_linked_issues(line)
            current_test["linked_issues_status"] = issues

        i += 1

    return tests


def _extract_test_steps(line: str) -> list[tuple[str, str]]:
    """Extract (description, result) pairs from the Test_Steps line."""
    steps = []
    # Match patterns like {'step_desc': 'Pass'} or {'step_desc': 'Fail'}
    pattern = r"\{['\"]([^'\"]*?)['\"]\s*:\s*['\"]([^'\"]*?)['\"]"
    # Also handle the dict-style with multiple keys
    for match in re.finditer(pattern, line):
        desc = match.group(1)
        result = match.group(2)
        if desc and not desc.startswith("----"):
            steps.append((desc, result))
    return steps


def _extract_linked_issues(line: str) -> list[dict]:
    """Extract linked issues from the linked_issues_status line."""
    issues = []
    # Match patterns like ['TC-642', 'In Progress', 'https://...']
    pattern = r"\['([^']+)',\s*'([^']+)',\s*'([^']+)'\]"
    for match in re.finditer(pattern, line):
        issues.append({
            "id": match.group(1),
            "status": match.group(2),
            "url": match.group(3),
        })
    return issues


# Known DAST service names (ordered longest-first for greedy matching)
_KNOWN_SERVICES = sorted([
    "CONNECTIONMANAGER", "BAGHEERA-OFFDUTY-PRIVACY", "BAGHEERA-ENHANCED-PRIVACY",
    "BAGHEERA-REGULAR-PRIVACY", "BAGHEERA-DISABLED-PRIVACY",
    "AWSIOT-SDK", "AWSIOT",
    "EVENT-ACCESS-PREVIEW-CONFIG", "EVENT-ACCESS-PREVIEW-PRIVACY",
    "EVENT-ACCESS-PREVIEW-SESSION", "EVENT-ACCESS-PREVIEW-NEGATIVE",
    "SVC", "APM", "SCHEDULER", "HEALTHSTATSMANAGER", "GPS",
    "KEEP-ALIVE-MANAGER", "FANCONTROL",
    "POWER-MON-LPM", "POWER-MON-CRANKLOW", "POWER-MON",
    "TIMESYNC", "BAGHEERA", "CIRCBUFF", "NDSAM", "OTACHECK", "WAF",
    "SERVICEMONITOR", "WIFI", "AUDIOPLAYBACK", "SPEED",
    "NDSUSPENDRESUME", "UNIFIEDUPLOADER", "DIAGNOSTIC",
    "DMS", "SANITY3", "BTFV",
], key=len, reverse=True)


def _extract_service_name(file_name: str) -> str:
    """
    Extract the service name from a test case file name.

    e.g., TC_645_CONNECTIONMANAGER_SERVICE_LOG_FOLDERS.py -> CONNECTIONMANAGER
          TC_1587_BAGHEERA-OFFDUTY-PRIVACY_MASTER.py -> BAGHEERA-OFFDUTY-PRIVACY
    """
    # Remove .py extension and TC_{number}_ prefix
    name = re.sub(r"\.py$", "", file_name)
    match = re.match(r"TC_\d+_(.*)", name)
    if not match:
        return "UNKNOWN"

    rest = match.group(1)

    # Try matching against known service names (longest first)
    for svc in _KNOWN_SERVICES:
        # Service name in file uses underscores for hyphens sometimes
        svc_pattern = svc.replace("-", "[-_]")
        if re.match(rf"^{svc_pattern}(?:_|$)", rest):
            return svc

    # Fallback: take the first uppercase segment before underscored description
    parts = rest.split("_")
    return parts[0] if parts else "UNKNOWN"


def parse_report(report_url: str) -> dict:
    """
    Fetch and parse a DAST report from the given Jenkins URL.

    Returns a dict with:
    - url: the report URL
    - test_cases: list of parsed test case dicts
    - summary: dict with total, pass, fail, ne, na counts
    - failed_tests: list of failed test case dicts
    - service_failures: dict mapping service name -> list of failed tests
    """
    js_text = fetch_report_js(report_url)
    test_cases = _parse_test_data(js_text)

    # Enrich with service name
    for tc in test_cases:
        tc["service"] = _extract_service_name(tc.get("file_name", ""))

    # Build summary
    total = len(test_cases)
    pass_count = sum(1 for tc in test_cases if tc.get("test_status") == "Pass")
    fail_count = sum(1 for tc in test_cases if tc.get("test_status") == "Fail")
    ne_count = sum(1 for tc in test_cases if tc.get("test_status") == "NE")
    na_count = sum(1 for tc in test_cases if tc.get("test_status") == "NA")

    failed_tests = [tc for tc in test_cases if tc.get("test_status") == "Fail"]

    # Group failures by service
    service_failures = {}
    for tc in failed_tests:
        svc = tc["service"]
        service_failures.setdefault(svc, []).append(tc)

    return {
        "url": report_url,
        "test_cases": test_cases,
        "summary": {
            "total": total,
            "pass": pass_count,
            "fail": fail_count,
            "not_executed": ne_count,
            "not_applicable": na_count,
            "pass_rate": f"{(pass_count / total * 100):.1f}%" if total > 0 else "N/A",
        },
        "failed_tests": failed_tests,
        "service_failures": service_failures,
    }
