#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import html
from pathlib import Path


def read_rows(path):
    with Path(path).open(newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def save_line_svg(path, title, ylabel, points):
    width = 900
    height = 420
    left = 75
    right = 30
    top = 50
    bottom = 55
    plot_w = width - left - right
    plot_h = height - top - bottom

    if not points:
        return

    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)

    if min_x == max_x:
        max_x = min_x + 1
    if min_y == max_y:
        max_y = min_y + 1

    pad_y = (max_y - min_y) * 0.08
    min_y -= pad_y
    max_y += pad_y

    def sx(x):
        return left + (x - min_x) / (max_x - min_x) * plot_w

    def sy(y):
        return top + (max_y - y) / (max_y - min_y) * plot_h

    polyline = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in points)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="Arial" font-size="18" font-weight="bold">{html.escape(title)}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#111827"/>',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#111827"/>',
        f'<text x="{width / 2}" y="{height - 14}" text-anchor="middle" font-family="Arial" font-size="12">episode</text>',
        f'<text x="18" y="{height / 2}" transform="rotate(-90 18 {height / 2})" text-anchor="middle" font-family="Arial" font-size="12">{html.escape(ylabel)}</text>',
    ]

    for i in range(6):
        value = min_y + (max_y - min_y) * i / 5
        y = sy(value)
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{value:.2f}</text>')

    parts.append(f'<polyline fill="none" stroke="#2563eb" stroke-width="2.2" points="{polyline}"/>')
    parts.append("</svg>")
    Path(path).write_text("\n".join(parts))


def main():
    parser = argparse.ArgumentParser(description="Plot DQN training CSV as SVG curves")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--tag", default=None)
    parser.add_argument("--outputDir", default="runtime/plots")
    args = parser.parse_args()

    rows = read_rows(args.csv)
    tag = args.tag or Path(args.csv).stem
    output_dir = Path(args.outputDir)
    output_dir.mkdir(parents=True, exist_ok=True)

    specs = [
        ("total_reward", "Total Reward", "reward"),
        ("epsilon", "Epsilon", "epsilon"),
        ("average_throughput", "Average Throughput", "throughput"),
        ("average_queue", "Average Reward Queue", "queue"),
        ("average_total_delay", "Average Total Delay", "delay"),
        ("average_deadline_misses", "Average Deadline Misses", "misses"),
        ("final_total_delay", "Final Total Delay", "delay"),
        ("final_deadline_misses", "Final Deadline Misses", "misses"),
        ("average_loss", "Average Loss", "loss"),
    ]

    for key, title, ylabel in specs:
        if not rows or key not in rows[0]:
            print(f"Skip missing training column: {key}")
            continue
        points = [(int(row["episode"]), float(row[key])) for row in rows]
        save_line_svg(output_dir / f"{tag}_{key}.svg", title, ylabel, points)

    print("Saved DQN training plots:", output_dir)


if __name__ == "__main__":
    main()
