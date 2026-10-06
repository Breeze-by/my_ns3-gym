"""File outputs and dependency-free SVG charts from the shared metrics source."""

import csv
import html
import json
import math
from pathlib import Path


def flatten(row):
    result = {key: value for key, value in row.items() if key not in
              ("counts", "delays", "aoi", "queues", "first_events", "configuration")}
    result.update({"count_" + key: value for key, value in row["counts"].items()})
    result.update({"aoi_" + key: value for key, value in row["aoi"].items()})
    for name, stats in row["delays"].items():
        result.update({name + "_" + key: value for key, value in stats.items()})
    result["fault_configuration"] = json.dumps(row["configuration"], sort_keys=True)
    result["queues"] = json.dumps(row["queues"], sort_keys=True)
    return result


def write_csv(path, rows):
    flat = [flatten(row) for row in rows]
    fields = sorted({key for row in flat for key in row})
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flat)


def windows(metrics, start, end, per_stream=True):
    scopes = [("uplink",), ("downlink",)]
    if per_stream:
        scopes += sorted({key[:2] for key in metrics.routes})
        scopes += sorted(metrics.routes)
    result = []
    for index in range(math.ceil(max(0, end - start))):
        left, right = start + index, min(start + index + 1, end)
        for scope in scopes:
            row = metrics.report(left, right, *scope)
            row["provisional"] = False
            result.append(row)
    return result


def render_svg(path, rows, timeline=(), reference=()):
    """Four aligned charts; absent values stay gaps, not invented zeroes."""
    width, height, left, right = 1100, 810, 82, 1055
    plots = [
        ("Application offered / accepted goodput (B/s)", lambda r: r.get("offered_bytes_per_sec"), lambda r: r.get("goodput_bytes_per_sec")),
        ("Resolved attempt PDR / loss (ratio)", lambda r: r.get("attempt_pdr"), lambda r: r.get("attempt_loss_rate")),
        ("Source delivery p95 / observed AoI p95 (s)", lambda r: r["delays"]["source_to_delivery"]["p95"], lambda r: r["aoi"]["p95"]),
        ("Exact in-flight queue / retry ratio (queue unavailable in legacy traces)",
         lambda r: sum(v["in_flight"] for v in r["queues"].values()) if r["queues"] else None,
         lambda r: r.get("retry_rate")),
    ]
    all_rows = list(rows) + list(reference)
    points = [float(r["elapsed_sim_time"]) for r in all_rows]
    limit = max(points, default=1) or 1
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="#f8fafc"/>',
           '<style>text{font-family:DejaVu Sans,sans-serif;font-size:12px;fill:#172033}</style>',
           '<text x="82" y="26" font-size="18">Gateway simulation-time communication metrics (application model)</text>',
           '<text x="82" y="47">Blue uplink; orange downlink. Solid first measure, dashed second. Thin gray reference. Null values are gaps.</text>']
    for index, (title, first, second) in enumerate(plots):
        top, bottom = 87 + index * 174, 217 + index * 174
        values = [value for row in all_rows for value in (first(row), second(row)) if value is not None and math.isfinite(value)]
        maximum = max(values, default=1) or 1
        maximum = max(maximum, 1) if index in (1, 3) else maximum
        svg.append(f'<text x="{left}" y="{top-12}">{html.escape(title)}</text>')
        for tick in range(5):
            y = bottom - tick * (bottom-top)/4
            svg.extend([f'<line x1="{left}" y1="{y}" x2="{right}" y2="{y}" stroke="#dce3ed"/>',
                        f'<text x="8" y="{y+4}">{maximum*tick/4:.2g}</text>'])
        for kind, collection in (("reference", reference), ("current", rows)):
            for direction, color in (("uplink", "#1864ab"), ("downlink", "#d66a13")):
                for number, getter in enumerate((first, second)):
                    segments, segment = [], []
                    for row in collection:
                        if row.get("direction") != direction or row.get("message_type") != "all":
                            continue
                        value = getter(row)
                        if value is None:
                            if segment:
                                segments.append(segment)
                                segment = []
                            continue
                        segment.append(f'{left+(right-left)*row["elapsed_sim_time"]/limit:.2f},{bottom-(bottom-top)*value/maximum:.2f}')
                    if segment:
                        segments.append(segment)
                    for segment in segments:
                        stroke = "#94a3b8" if kind == "reference" else color
                        dash = 'stroke-dasharray="5 4"' if number else ""
                        svg.append(f'<polyline points="{" ".join(segment)}" fill="none" stroke="{stroke}" stroke-width="{1 if kind == "reference" else 1.6}" {dash}/>')
        for event in timeline:
            if event.get("event") not in ("configuration_applied", "task_phase", "navigation_deadline", "robot_failure"):
                continue
            when = float(event.get("elapsed_sim_time", -1))
            if not 0 <= when <= limit:
                continue
            x = left + (right-left)*when/limit
            svg.append(f'<line x1="{x}" y1="{top}" x2="{x}" y2="{bottom}" stroke="#8490a5" stroke-dasharray="2 4"/>')
            if index == 0:
                label = str(event.get("phase", event.get("event")))
                svg.append(f'<text x="{x+2}" y="{top+12}" transform="rotate(45 {x+2} {top+12})">{html.escape(label)}</text>')
        for tick in range(7):
            x = left + (right-left)*tick/6
            svg.append(f'<text x="{x-10}" y="{bottom+20}">{limit*tick/6:.0f}</text>')
    svg.append('<text x="430" y="792">Simulation seconds since episode start</text></svg>')
    Path(path).write_text("\n".join(svg), encoding="utf-8")


def save_final(metrics, directory, start=None, end=None, result=None, sampled_rows=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    start = float(start if start is not None else metrics.context.get("episode_start_sim_time", 0.0))
    end = float(end if end is not None else metrics.last_time + 1e-6)
    metrics.context["episode_start_sim_time"] = start
    rows = windows(metrics, start, end) if sampled_rows is None else sampled_rows
    write_csv(directory / "windows.csv", rows)
    with (directory / "windows.jsonl").open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    summary = {"schema_version": 1, "context": metrics.context, "start_sim_time": start, "end_sim_time": end,
               "conservation": metrics.audit(), "streams": [metrics.report(start, end, *key) for key in sorted(metrics.routes)],
               "directions": [metrics.report(start, end, direction) for direction in ("uplink", "downlink")],
               "first_events": metrics.first_events, "task_result": result, "source_record_count": len(metrics.events)}
    summary["window_semantics"] = "final full-ledger reconstruction" if sampled_rows is None else "live prefix samples; cumulative totals reconcile complete saved ledger"
    for event in metrics.timeline:
        event["elapsed_sim_time"] = event_stamp_safe(event) - start
    with (directory / "events.jsonl").open("w", encoding="utf-8") as stream:
        for event in metrics.timeline:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
    render_svg(directory / "curves.svg", rows, metrics.timeline)
    (directory / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return summary


def event_stamp_safe(event):
    return float(event.get("time", event.get("event_time", event.get("observer_time", 0.0))))
