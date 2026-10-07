#!/usr/bin/env python3
"""Plot the frozen application audit; no estimated PHY/MAC measurements."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ORDER = ["lab2", "lab3", "rooms2", "rooms3", "corridors2", "corridors3",
         "holdout2", "holdout3", "forced2", "delay_lab2", "delay_rooms3",
         "loss_corridors2", "direct_lab2", "direct_rooms3"]
LABELS = ["lab / 2", "lab / 3", "rooms / 2", "rooms / 3", "corridors / 2",
          "corridors / 3", "809 / 2", "809 / 3", "forced / 2", "delay lab / 2",
          "delay rooms / 3", "loss corridors / 2", "direct lab / 2", "direct rooms / 3"]
ROLES = ["data", "candidate", "request", "grant", "heartbeat", "critical-event", "feedback"]
COLORS = ["#4477aa", "#ee6677", "#ccbb44", "#228833", "#66ccee", "#aa3377", "#bbbbbb"]


def tidy(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e5e7eb", linewidth=.7)
    ax.set_axisbelow(True)


def save(fig, output, name):
    fig.savefig(output/(name+".png"), dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def selected_stratum(episode, kind="pose_state", phase="EXPLORE"):
    rows = [r for r in episode["audit"]["strata"] if r["phase"] == phase
            and r["message_type"] == kind and r["direction"] == "uplink" and r["robot"] == "tb1"]
    assert len(rows) <= 1
    return rows[0] if rows else None


def plot_traffic(episodes, output):
    fig, axes = plt.subplots(2, 1, figsize=(14, 8.5), sharex=True, layout="constrained")
    x, bottom = np.arange(len(ORDER)), np.zeros(len(ORDER))
    for role, color in zip(ROLES, COLORS):
        values = np.array([episodes[c]["audit"]["tx_cdr_bytes_by_role"].get(role, 0)*8/
                           episodes[c]["audit"]["duration_sec"]/1000 for c in ORDER])
        axes[0].bar(x, values, bottom=bottom, label=role, color=color, width=.75)
        bottom += values
    for i, c in enumerate(ORDER):
        axes[0].text(i, bottom[i]+max(bottom)*.025,
                     f'{episodes[c]["audit"]["control_cdr_fraction"]:.0%}', ha="center", fontsize=8)
    axes[0].set_ylim(0, max(bottom)*1.23)
    axes[0].set_ylabel("Mean envelope traffic (kbit/s)")
    axes[0].set_title("All 14 original cells: actual application CDR bytes, including every control attempt", loc="left")
    axes[0].legend(ncols=4, frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(0, 1.29))
    axes[0].text(.99, .98, "Labels: all non-data byte fraction", transform=axes[0].transAxes,
                 ha="right", va="top", fontsize=9)
    for off, key, color in ((-.19, "p95", "#4477aa"), (.19, "max", "#ee6677")):
        axes[1].bar(x+off, [episodes[c]["audit"]["one_second_cdr_bps"][key]/1000 for c in ORDER],
                    width=.36, color=color, label="1 s "+key)
    axes[1].set_ylabel("One-second envelope traffic (kbit/s)")
    axes[1].set_title("Bursts use all native-interval windows, including empty windows; final window uses its actual duration", loc="left", fontsize=10)
    axes[1].legend(frameon=False)
    axes[1].set_xticks(x, LABELS, rotation=48, ha="right", fontsize=9)
    for ax in axes:
        tidy(ax)
    fig.supxlabel("CDR excludes IP / DDS transport / MAC / PHY; this is neither Wi-Fi throughput nor measured airtime", fontsize=10)
    save(fig, output, "20261007_p3c5_traffic")


def plot_feedback(episodes, output):
    cases = ["direct_lab2", "lab2", "delay_lab2", "direct_rooms3", "rooms3",
             "delay_rooms3", "corridors2", "loss_corridors2"]
    labels = ["direct\nlab2", "admit\nlab2", "0.5 s\nlab2", "direct\nrooms3",
              "admit\nrooms3", "0.5 s\nrooms3", "admit\ncorridors2", "10% loss\ncorridors2"]
    x = np.arange(len(cases))
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), layout="constrained")
    for ax, metric, title in ((axes[0, 0], "local_wait_sec", "Grant waiting p95 during EXPLORE"),
                              (axes[0, 1], "source_to_delivery_sec", "Original source to delivery p95 during EXPLORE")):
        values, ns = [], []
        for c in cases:
            row = selected_stratum(episodes[c])
            d = row["distributions"].get(metric, {}) if row else {}
            values.append(d.get("p95"))
            ns.append(d.get("n", 0))
        for i, (value, n) in enumerate(zip(values, ns)):
            if value is None:
                ax.text(i, .02, "n/a", ha="center", fontsize=8)
            else:
                ax.bar(i, value, color="#4477aa", width=.65)
                ax.text(i, value+.04, f"n={n}", ha="center", fontsize=7)
        if metric == "source_to_delivery_sec":
            ttls = [selected_stratum(episodes[c])["distributions"]["ttl_sec"]["min"] for c in cases
                    if selected_stratum(episodes[c]) is not None]
            assert len(set(ttls)) == 1
            ax.axhline(ttls[0], color="#aa3377", linestyle="--", linewidth=1, label=f"Original TTL {ttls[0]:g} s")
            ax.legend(frameon=False, fontsize=9)
        ax.set_title(title, loc="left", fontsize=11)
        ax.set_ylabel("Seconds")
        ax.set_ylim(bottom=0, top=max([v for v in values if v is not None]+[2])*.1+max([v for v in values if v is not None]+[2]))
    aoi = []
    for c in cases:
        rows = [r for r in episodes[c]["audit"]["aoi_streams"] if r["direction"] == "uplink"
                and r["message_type"] == "pose_state" and r["sender"] == "tb1"]
        assert len(rows) == 1
        aoi.append(rows[0]["aoi"])
    for i, row in enumerate(aoi):
        if row["p95"] is None:
            axes[1, 0].text(i, .02, "unknown", ha="center", fontsize=8)
        else:
            axes[1, 0].bar(i, row["p95"], color="#228833", width=.65)
    axes[1, 0].set_title("AoI p95 over the complete native interval", loc="left", fontsize=11)
    axes[1, 0].set_ylabel("Seconds")
    bottom = np.zeros(len(cases))
    for key, label, color in (("fresh_sec", "fresh", "#228833"), ("stale_sec", "source-stale", "#ee6677"),
                              ("no_data_sec", "unknown", "#bbbbbb")):
        values = np.array([r[key]/r["monitored_sec"] for r in aoi])
        axes[1, 1].bar(x, values, bottom=bottom, color=color, label=label, width=.65)
        bottom += values
    assert np.allclose(bottom, 1)
    axes[1, 1].set_ylim(0, 1.08)
    axes[1, 1].set_title("Time with fresh / stale / unknown received pose", loc="left", fontsize=11)
    axes[1, 1].set_ylabel("Native-interval time fraction")
    axes[1, 1].legend(frameon=False, ncols=3, fontsize=8, loc="upper left", bbox_to_anchor=(0, 1.20))
    for ax in axes.flat:
        ax.set_xticks(x, labels, fontsize=8)
        tidy(ax)
    fig.supxlabel("pose_state / tb1 uplink. Each condition is one asynchronous original episode; descriptive comparison, no causal benefit claim.", fontsize=10)
    save(fig, output, "20261007_p3c5_feedback")


def plot_compression(episodes, output):
    cases = ORDER[:8]
    fig, axes = plt.subplots(2, 1, figsize=(12, 7.8), sharex=True, layout="constrained")
    payload, raw, ratios = [], [], []
    for c in cases:
        rows = [r for r in episodes[c]["audit"]["strata"]
                if r["message_type"] in ("map_snapshot", "fused_map_snapshot")]
        n = sum(r["counts"].get("generated_messages", 0) for r in rows)
        after = sum(r["counts"].get("generated_payload_bytes", 0) for r in rows)
        before = sum(r["counts"].get("uncompressed_payload_bytes", 0) for r in rows)
        assert n > 0 and before >= after > 0
        payload.append(after/n/1024)
        raw.append(before/n/1024)
        ratios.append(after/before)
    x = np.arange(len(cases))
    axes[0].bar(x-.18, raw, width=.35, label="Before zlib (raw CDR payload)", color="#bbbbbb")
    axes[0].bar(x+.18, payload, width=.35, label="Actual compressed payload", color="#4477aa")
    axes[0].set_yscale("log")
    axes[0].set_ylabel("Mean generated map payload (KiB, log scale)")
    axes[0].set_title("Measured map compression: every generated uplink and fused downlink map, all native phases", loc="left", fontsize=11)
    axes[0].legend(frameon=False)
    axes[1].bar(x, np.array(ratios)*100, color="#228833", width=.65)
    for i, v in enumerate(ratios):
        axes[1].text(i, v*100+.05, f"{v:.2%}", ha="center", fontsize=9)
    axes[1].set_ylim(0, max(ratios)*125)
    axes[1].set_ylabel("Sum compressed / sum raw payload (%)")
    axes[1].set_xticks(x, LABELS[:8], fontsize=9)
    for ax in axes:
        tidy(ax)
    fig.supxlabel("Only existing gateway map messages are measured. No raw RGB/depth/image/video stream or artificial load is added.", fontsize=10)
    save(fig, output, "20261007_p3c5_compression")


def plot_native(episodes, output):
    fig, ax = plt.subplots(figsize=(14, 5.5), layout="constrained")
    x = np.arange(len(ORDER))
    for i, c in enumerate(ORDER):
        r = episodes[c]["result"]
        failed = r["termination_reason"] == "mission_failed"
        value = min(r["elapsed_sim_time_sec"], 300)
        color = "#228833" if r["success"] else "#ee9944" if failed else "#ee6677"
        ax.bar(i, value, color=color, width=.7, hatch=None if r["success"] else "///")
        label = f"{value:.1f}" if r["success"] else f"FAILED\n{value:.1f}" if failed else "timeout"
        ax.text(i, value+7, label, ha="center", fontsize=8)
        for name, marker, color in (("time_to_detect_sec", "o", "#222222"),
                                    ("time_to_rally_sec", "x", "#4477aa")):
            if r[name] is not None:
                ax.scatter(i, r[name], color=color, marker=marker, s=24, zorder=3)
    ax.axhline(300, color="#aa3377", linestyle="--", linewidth=1)
    ax.set_ylim(0, 335)
    ax.set_ylabel("Seconds from native episode start")
    ax.set_xticks(x, LABELS, rotation=48, ha="right", fontsize=9)
    ax.set_title("Every original native result: strict COMPLETE proof, FAILED, or retained 300 s timeout", loc="left")
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    ax.legend(handles=[Patch(color="#228833", label="Native COMPLETE"), Patch(facecolor="#ee9944", hatch="///", label="Native FAILED"),
                       Patch(facecolor="#ee6677", hatch="///", label="Timeout"),
                       Line2D([], [], color="#222222", marker="o", linestyle="", label="Detection"),
                       Line2D([], [], color="#4477aa", marker="x", linestyle="", label="RALLY begins")], frameon=False, ncols=5,
              loc="upper left", bbox_to_anchor=(0, 1.16))
    tidy(ax)
    fig.supxlabel("Original 300 s / 0.35 m / 0.05 m/s / 0.10 rad/s / continuous 5 s gates unchanged. No task retry or success-only selection.", fontsize=10)
    save(fig, output, "20261007_p3c5_native")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_dir():
        parser.error("output directory must exist")
    source = json.loads(args.gate.read_text())
    assert source["status"] == "PASS" and source["original_count"] == 14
    episodes = {row["case"]: row for row in source["episodes"]}
    assert set(episodes) == set(ORDER)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    for plot in (plot_traffic, plot_feedback, plot_compression, plot_native):
        plot(episodes, args.output)
    print(json.dumps({"status": "PASS", "figures": 4, "gate": str(args.gate)}))


if __name__ == "__main__":
    main()
