#!/usr/bin/env python3
"""
ND BOT Report Analyzer - Multi-Product Line Comparison Tool

Compares DAST reports across multiple product lines and generates:
  - Individual comparison reports per product line
  - A combined summary report with service validation status across all product lines

Usage:
    python multi_analyze.py --config config.json [--output-dir output/]

Config JSON format:
    {
        "release_label": "6.14",
        "product_lines": [
            {
                "name": "D450 US",
                "version": "5.6.14.rc.3",
                "prev_version": "5.6.13.rc.2",
                "current_url": "http://...",
                "previous_url": "http://..."
            },
            ...
        ]
    }

Example:
    python multi_analyze.py --config release_config.json --output-dir reports/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

from report_fetcher import parse_report, merge_reports
from report_comparator import compare_reports, compute_service_pass_rates
from report_formatter import print_summary, generate_html_report, export_json


def _fetch_report(urls) -> dict:
    """Fetch a report from one or more URLs, merging if multiple."""
    if isinstance(urls, list):
        return merge_reports(urls)
    return parse_report(urls)


def _run_single_comparison(product: dict, output_dir: str) -> dict:
    """
    Run a single product line comparison and return results.

    Returns a dict with the comparison data, reports, and service pass rates.
    """
    name = product["name"]
    safe_name = name.replace(" ", "_")

    print(f"\n{'=' * 80}")
    print(f"  Processing: {name}")
    print(f"{'=' * 80}")

    # Fetch reports (support single URL string or list of URLs)
    prev_urls = product.get("previous_urls", product.get("previous_url"))
    curr_urls = product.get("current_urls", product.get("current_url"))

    if isinstance(prev_urls, list):
        print(f"  Fetching previous report from {len(prev_urls)} URLs...")
    else:
        print(f"  Fetching previous report: {prev_urls}")
    prev_report = _fetch_report(prev_urls)
    print(f"    -> Parsed {prev_report['summary']['total']} test cases "
          f"({prev_report['summary']['fail']} failures)")

    if isinstance(curr_urls, list):
        print(f"  Fetching current report from {len(curr_urls)} URLs...")
    else:
        print(f"  Fetching current report: {curr_urls}")
    curr_report = _fetch_report(curr_urls)
    print(f"    -> Parsed {curr_report['summary']['total']} test cases "
          f"({curr_report['summary']['fail']} failures)")

    # Compare
    print("  Comparing reports...")
    comparison = compare_reports(prev_report, curr_report)

    # Service pass rates (from current report)
    service_rates = compute_service_pass_rates(curr_report)

    # Generate individual HTML report
    html_path = os.path.join(output_dir, f"comparison_report_{safe_name}.html")
    generate_html_report(
        comparison, prev_report, curr_report,
        f"{name} {product['prev_version']}", f"{name} {product['version']}",
        html_path,
    )

    # Generate individual JSON export
    json_path = os.path.join(output_dir, f"comparison_report_{safe_name}.json")
    export_json(
        comparison, json_path,
        prev_report, curr_report,
        f"{name} {product['prev_version']}", f"{name} {product['version']}",
    )

    # Console summary
    print_summary(
        comparison, prev_report, curr_report,
        f"{name} {product['prev_version']}", f"{name} {product['version']}",
    )

    return {
        "name": name,
        "version": product["version"],
        "prev_version": product["prev_version"],
        "comparison": comparison,
        "prev_summary": prev_report["summary"],
        "curr_summary": curr_report["summary"],
        "service_pass_rates": service_rates,
        "html_file": os.path.basename(html_path),
        "json_file": os.path.basename(json_path),
    }


def _generate_combined_html(results: list[dict], release_label: str,
                            output_path: str):
    """Generate a combined HTML report with cross-product service validation."""
    # Collect all service names across all product lines
    all_services = set()
    for r in results:
        all_services.update(r["service_pass_rates"].keys())
    all_services = sorted(all_services)

    product_names = [r["name"] for r in results]
    product_versions = [r["version"] for r in results]

    # Status symbols and styling
    status_map = {
        "pass": ("✔", "#2e7d32", "#e8f5e9"),
        "warn": ("!", "#e65100", "#fff3e0"),
        "fail": ("✖", "#c62828", "#ffebee"),
        "na": ("NA", "#757575", "#f5f5f5"),
    }

    # Build service validation table rows
    svc_rows = ""
    for svc in all_services:
        svc_rows += f"<tr><td class='svc-name'>{svc}</td>"
        for r in results:
            stats = r["service_pass_rates"].get(svc)
            if stats is None:
                symbol, color, bg = status_map["na"]
                tooltip = "No tests for this service"
            else:
                symbol, color, bg = status_map[stats["status"]]
                tooltip = (f"Pass: {stats['pass']}/{stats['total']} "
                           f"({stats['pass_rate']:.1f}%)")
            svc_rows += (f'<td class="status-cell" style="background:{bg};color:{color};" '
                         f'title="{tooltip}">'
                         f'<span class="status-icon">{symbol}</span>'
                         f'<span class="rate-hint">{stats["pass_rate"]:.0f}%</span>'
                         f'</td>' if stats else
                         f'<td class="status-cell" style="background:{bg};color:{color};" '
                         f'title="{tooltip}">'
                         f'<span class="status-icon">{symbol}</span></td>')
        svc_rows += "</tr>"

    # Build per-product summary cards
    product_cards = ""
    for r in results:
        s = r["comparison"]["summary"]
        cs = r["curr_summary"]
        product_cards += f"""
        <div class="product-card">
            <h3>{r['name']} <span class="version-badge">{r['version']}</span></h3>
            <div class="product-stats">
                <div class="mini-stat">
                    <span class="mini-number">{cs['total']}</span>
                    <span class="mini-label">Total</span>
                </div>
                <div class="mini-stat">
                    <span class="mini-number" style="color:#2e7d32">{cs['pass']}</span>
                    <span class="mini-label">Pass</span>
                </div>
                <div class="mini-stat">
                    <span class="mini-number" style="color:#c62828">{cs['fail']}</span>
                    <span class="mini-label">Fail</span>
                </div>
                <div class="mini-stat">
                    <span class="mini-number" style="color:#1a237e">{cs['pass_rate']}</span>
                    <span class="mini-label">Pass Rate</span>
                </div>
            </div>
            <div class="product-comparison">
                <span style="color:#c62828">New: {s['new_failure_count']}</span> |
                <span style="color:#e65100">Common: {s['common_failure_count']}</span> |
                <span style="color:#2e7d32">Resolved: {s['resolved_failure_count']}</span>
            </div>
            <a href="{r['html_file']}" class="detail-link">View Detailed Report &rarr;</a>
        </div>"""

    # Product version headers
    version_headers = ""
    for i, r in enumerate(results):
        version_headers += f'<th class="version-header">{r["version"]}</th>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Multi-Product Comparison — {release_label}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #333; }}
        .header {{
            background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
            color: white; padding: 25px 30px;
        }}
        .header h1 {{ font-size: 22px; margin-bottom: 5px; }}
        .header p {{ font-size: 13px; opacity: 0.85; }}
        .container {{ max-width: 1400px; margin: 20px auto; padding: 0 20px; }}
        .card {{
            background: white; border-radius: 8px; padding: 20px 25px;
            margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .card h2 {{
            font-size: 18px; margin-bottom: 15px; padding-bottom: 10px;
            border-bottom: 2px solid #e0e0e0; color: #1a237e;
        }}

        /* Product summary cards */
        .products-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 15px; margin-bottom: 20px;
        }}
        .product-card {{
            background: #f5f7fa; border-radius: 8px; padding: 18px;
            border-left: 4px solid #1a237e;
        }}
        .product-card h3 {{ font-size: 15px; margin-bottom: 12px; color: #1a237e; }}
        .version-badge {{
            display: inline-block; padding: 2px 8px; border-radius: 3px;
            font-size: 11px; background: #e8eaf6; color: #1a237e; font-weight: 600;
        }}
        .product-stats {{
            display: flex; gap: 12px; margin-bottom: 10px;
        }}
        .mini-stat {{ text-align: center; }}
        .mini-number {{ display: block; font-size: 20px; font-weight: bold; }}
        .mini-label {{ display: block; font-size: 10px; color: #666; }}
        .product-comparison {{ font-size: 12px; margin-bottom: 10px; color: #555; }}
        .detail-link {{
            display: inline-block; font-size: 12px; color: #1a237e;
            text-decoration: none; font-weight: 500;
        }}
        .detail-link:hover {{ text-decoration: underline; }}

        /* Service validation table */
        .svc-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        .svc-table th {{
            background: #1a237e; color: white; padding: 10px 8px; text-align: center;
        }}
        .svc-table th:first-child {{ text-align: left; min-width: 200px; }}
        .svc-table td {{ padding: 8px; border-bottom: 1px solid #e0e0e0; text-align: center; }}
        .svc-table tr:hover {{ background: #f5f7fa; }}
        .svc-name {{ text-align: left !important; font-weight: 600; font-size: 12px; }}
        .status-cell {{
            font-weight: bold; font-size: 16px; position: relative;
        }}
        .status-icon {{ display: block; }}
        .rate-hint {{
            display: block; font-size: 10px; font-weight: normal; opacity: 0.7;
        }}
        .version-header {{ font-size: 12px; min-width: 100px; }}

        /* Legend */
        .legend {{
            display: flex; gap: 25px; margin-top: 15px; font-size: 12px;
            padding: 10px 15px; background: #f5f7fa; border-radius: 6px;
        }}
        .legend-item {{ display: flex; align-items: center; gap: 6px; }}
        .legend-icon {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 24px; height: 24px; border-radius: 4px; font-weight: bold; font-size: 14px;
        }}

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
    </style>
</head>
<body>
    <div class="header">
        <h1>Multi-Product Line Comparison — Release {release_label}</h1>
        <p>{len(results)} product lines | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <div class="nav">
        <a href="#overview">Product Overview</a>
        <span class="sep">|</span>
        <a href="#service-validation">Service Validation Status</a>
        <span class="sep">|</span>
        {"".join(f'<a href="{r["html_file"]}">{r["name"]}</a>' for r in results)}
    </div>

    <div class="container">

        <!-- Product Overview Cards -->
        <div class="card" id="overview">
            <h2>Product Line Overview</h2>
            <div class="products-grid">
                {product_cards}
            </div>
        </div>

        <!-- Service Validation Status -->
        <div class="card" id="service-validation">
            <h2>Services Validation Status</h2>
            <table class="svc-table">
                <thead>
                    <tr>
                        <th>Services</th>
                        {version_headers}
                    </tr>
                </thead>
                <tbody>
                    {svc_rows}
                </tbody>
            </table>

            <div class="legend">
                <div class="legend-item">
                    <span class="legend-icon" style="background:#e8f5e9;color:#2e7d32;">✔</span>
                    Pass% &ge; 90%
                </div>
                <div class="legend-item">
                    <span class="legend-icon" style="background:#ffebee;color:#c62828;">✖</span>
                    Pass% &lt; 85%
                </div>
                <div class="legend-item">
                    <span class="legend-icon" style="background:#fff3e0;color:#e65100;">!</span>
                    Pass% &ge; 85% and &lt; 90%
                </div>
                <div class="legend-item">
                    <span class="legend-icon" style="background:#f5f5f5;color:#757575;">NA</span>
                    Not applicable
                </div>
            </div>
        </div>

    </div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nCombined report saved to: {os.path.abspath(output_path)}")


def main():
    parser = argparse.ArgumentParser(
        description="Multi-product line DAST report comparison.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config", required=True,
        help="Path to JSON config file defining product lines and URLs",
    )
    parser.add_argument(
        "--output-dir", default=".",
        help="Output directory for reports (default: current directory)",
    )
    args = parser.parse_args()

    # Load config
    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    release_label = config.get("release_label", "Release")
    product_lines = config["product_lines"]

    if not product_lines:
        print("Error: No product lines defined in config.", file=sys.stderr)
        sys.exit(1)

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Multi-Product Comparison — Release {release_label}")
    print(f"Processing {len(product_lines)} product lines...\n")

    # Run comparisons for each product line
    results = []
    for product in product_lines:
        try:
            result = _run_single_comparison(product, args.output_dir)
            results.append(result)
        except Exception as e:
            print(f"\nERROR processing {product['name']}: {e}", file=sys.stderr)
            print("Skipping this product line.\n", file=sys.stderr)

    if not results:
        print("Error: No product lines could be processed.", file=sys.stderr)
        sys.exit(1)

    # Generate combined report
    combined_path = os.path.join(args.output_dir, "multi_product_summary.html")
    _generate_combined_html(results, release_label, combined_path)

    # Export combined JSON
    combined_json_path = os.path.join(args.output_dir, "multi_product_summary.json")
    combined_data = {
        "release_label": release_label,
        "generated": datetime.now().isoformat(),
        "product_lines": [],
    }
    for r in results:
        combined_data["product_lines"].append({
            "name": r["name"],
            "version": r["version"],
            "prev_version": r["prev_version"],
            "curr_summary": r["curr_summary"],
            "prev_summary": r["prev_summary"],
            "comparison_summary": r["comparison"]["summary"],
            "service_pass_rates": r["service_pass_rates"],
            "html_file": r["html_file"],
            "json_file": r["json_file"],
        })
    with open(combined_json_path, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, indent=2, default=str)
    print(f"Combined JSON saved to: {os.path.abspath(combined_json_path)}")

    print(f"\nDone! Generated {len(results)} individual reports + 1 combined summary.")


if __name__ == "__main__":
    main()
