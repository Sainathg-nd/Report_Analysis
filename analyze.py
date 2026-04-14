#!/usr/bin/env python3
"""
ND BOT Report Analyzer - DAST Report Comparison Tool

Compares two DAST test reports from Jenkins and identifies:
  - New failures (regressions introduced in the current version)
  - Common failures (persistent failures across both versions)
  - Resolved failures (fixed in the current version)
  - Classification of failures by service name and failure reason

Usage:
    python analyze.py --previous <URL> --current <URL> \
                      --prev-version <VERSION> --curr-version <VERSION> \
                      [--output-html report.html] [--output-json report.json]

Example:
    python analyze.py \
        --previous "http://10.200.8.71:8080/job/Krait1_Mainline_QA_Phase_Validation_Setup_9157/172/Test_5freport/" \
        --current  "http://10.200.8.71:8080/job/D210_Global_Regression/52/Test_5freport/" \
        --prev-version "D210 (2.6.13.rc.4)" \
        --curr-version "D210 (2.6.14.rc.3)"
"""

import argparse
import sys

from report_fetcher import parse_report
from report_comparator import compare_reports
from report_formatter import print_summary, generate_html_report, export_json


def main():
    parser = argparse.ArgumentParser(
        description="Compare two DAST reports and analyze failure differences.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--previous", "-p", required=True,
        help="URL to the previous (baseline) DAST report",
    )
    parser.add_argument(
        "--current", "-c", required=True,
        help="URL to the current DAST report",
    )
    parser.add_argument(
        "--prev-version", default="Previous",
        help="Label for the previous version (e.g., 'D210 (2.6.13.rc.4)')",
    )
    parser.add_argument(
        "--curr-version", default="Current",
        help="Label for the current version (e.g., 'D210 (2.6.14.rc.3)')",
    )
    parser.add_argument(
        "--output-html", default="comparison_report.html",
        help="Path for the HTML comparison report (default: comparison_report.html)",
    )
    parser.add_argument(
        "--output-json",
        help="Path for JSON export (optional)",
    )
    args = parser.parse_args()

    # Step 1: Fetch and parse both reports
    print(f"Fetching previous report: {args.previous}")
    try:
        prev_report = parse_report(args.previous)
    except Exception as e:
        print(f"Error fetching previous report: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"  -> Parsed {prev_report['summary']['total']} test cases "
          f"({prev_report['summary']['fail']} failures)")

    print(f"Fetching current report: {args.current}")
    try:
        curr_report = parse_report(args.current)
    except Exception as e:
        print(f"Error fetching current report: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"  -> Parsed {curr_report['summary']['total']} test cases "
          f"({curr_report['summary']['fail']} failures)")

    # Step 2: Compare reports
    print("\nComparing reports...")
    comparison = compare_reports(prev_report, curr_report)

    # Step 3: Output results
    print_summary(comparison, prev_report, curr_report,
                  args.prev_version, args.curr_version)

    # Step 4: Generate HTML report
    generate_html_report(
        comparison, prev_report, curr_report,
        args.prev_version, args.curr_version,
        args.output_html,
    )

    # Step 5: Optional JSON export
    if args.output_json:
        export_json(comparison, args.output_json,
                    prev_report, curr_report,
                    args.prev_version, args.curr_version)


if __name__ == "__main__":
    main()
