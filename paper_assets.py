"""Generate publication assets from the frozen Stage 5.6 result set.

Data extraction is kept separate from rendering so input integrity and tables
can be tested without importing Matplotlib. Figures are saved as deterministic
SVG and PDF files suitable for journal submission.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence


CONTROLLER_ORDER = (
    "static",
    "throughput",
    "bola-basic",
    "robust-mpc",
    "q-learning",
)
CONTROLLER_LABELS = {
    "static": "Static",
    "throughput": "Throughput",
    "bola-basic": "BOLA-BASIC",
    "robust-mpc": "RobustMPC",
    "q-learning": "Q-Learning",
}
CONTENT_ORDER = (
    "big_buck_bunny",
    "elephants_dream",
    "sita_sings_the_blues",
    "tears_of_steel",
)
CONTENT_LABELS = {
    "big_buck_bunny": "Big Buck Bunny",
    "elephants_dream": "Elephants Dream",
    "sita_sings_the_blues": "Sita Sings the Blues",
    "tears_of_steel": "Tears of Steel",
}
TRACE_ORDER = (
    "stage56_evaluation_low_start",
    "stage56_evaluation_mixed_start",
    "stage56_evaluation_high_start",
)
TRACE_LABELS = {
    "stage56_evaluation_low_start": "Low start",
    "stage56_evaluation_mixed_start": "Mixed start",
    "stage56_evaluation_high_start": "High start",
}
METRIC_LABELS = {
    "mean_objective_reward": "Objective reward",
    "startup_delay_s": "Startup delay (s)",
    "rebuffering_rate_percent": "Rebuffering (%)",
    "average_payload_bitrate_kbps": "Payload bitrate (kbps)",
    "mean_psnr_y_db": "PSNR-Y (dB)",
    "buffer_std_s": "Buffer deviation (s)",
    "switch_count": "Representation switches",
}
PAPER_METRICS = (
    "mean_objective_reward",
    "rebuffering_rate_percent",
    "startup_delay_s",
    "average_payload_bitrate_kbps",
    "mean_psnr_y_db",
    "switch_count",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_paper_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_frozen_inputs(root: Path, config: dict[str, Any]) -> None:
    errors: list[str] = []
    for relative, expected in config["frozen_inputs_sha256"].items():
        path = root / relative
        if not path.is_file():
            errors.append(f"missing input: {relative}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            errors.append(
                f"hash mismatch for {relative}: expected {expected}, got {actual}"
            )
    if errors:
        raise ValueError("frozen paper inputs failed validation:\n" + "\n".join(errors))


def _one(
    rows: Sequence[dict[str, str]], **filters: str
) -> dict[str, str]:
    matches = [
        row
        for row in rows
        if all(row.get(field) == value for field, value in filters.items())
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one row for {filters}, found {len(matches)}")
    return matches[0]


def _fmt(value: float, decimals: int = 3) -> str:
    if math.isclose(value, 0.0, abs_tol=0.5 * 10 ** (-decimals)):
        value = 0.0
    return f"{value:.{decimals}f}"


def _ci(row: dict[str, str], decimals: int = 3) -> str:
    return (
        f"[{_fmt(float(row['ci95_low']), decimals)}, "
        f"{_fmt(float(row['ci95_high']), decimals)}]"
    )


def build_protocol_table(result_manifest: dict[str, Any]) -> list[dict[str, str]]:
    content_count = len(result_manifest["contents"])
    segment_count = result_manifest["contents"][0]["manifest"]["segment_count"]
    representation_count = len(
        result_manifest["contents"][0]["manifest"]["representations"]
    )
    return [
        {"Item": "VVC contents", "Value": str(content_count)},
        {"Item": "Segments per content", "Value": str(segment_count)},
        {
            "Item": "Representations per content",
            "Value": str(representation_count),
        },
        {
            "Item": "Independent VVC bitstreams",
            "Value": str(content_count * segment_count * representation_count),
        },
        {"Item": "Training seeds", "Value": str(len(result_manifest["seeds"]))},
        {
            "Item": "Evaluation traces",
            "Value": str(len(result_manifest["evaluation_traces"])),
        },
        {
            "Item": "ABR controllers",
            "Value": str(len(result_manifest["controllers"])),
        },
        {"Item": "Final evaluations", "Value": "600"},
        {
            "Item": "Statistical unit",
            "Value": result_manifest["statistical_unit"].replace("_", " "),
        },
        {"Item": "Confidence interval", "Value": "Two-sided Student t, 95%"},
    ]


def build_ladder_table(
    manifest_rows: dict[str, list[dict[str, str]]]
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for content in CONTENT_ORDER:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in manifest_rows[content]:
            grouped[row["representation_id"]].append(row)
        for representation in sorted(grouped):
            rows = grouped[representation]
            actual = [
                float(row["size_bytes"]) * 8.0 / 1000.0 / float(row["duration_s"])
                for row in rows
            ]
            psnr = [float(row["psnr_y_db"]) for row in rows]
            output.append(
                {
                    "Content": CONTENT_LABELS[content],
                    "Representation": representation,
                    "Target (kbps)": rows[0]["encoder_target_kbps"],
                    "Measured mean (kbps)": _fmt(statistics.mean(actual), 1),
                    "Measured SD (kbps)": _fmt(statistics.stdev(actual), 1),
                    "Min--max (kbps)": f"{_fmt(min(actual), 1)}--{_fmt(max(actual), 1)}",
                    "Mean PSNR-Y (dB)": _fmt(statistics.mean(psnr), 3),
                }
            )
    return output


def build_controller_table(
    aggregate_rows: Sequence[dict[str, str]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for controller in CONTROLLER_ORDER:
        item = {"Controller": CONTROLLER_LABELS[controller]}
        for metric in PAPER_METRICS:
            row = _one(
                aggregate_rows,
                scope="overall_content_balanced_per_seed",
                controller=controller,
                metric=metric,
            )
            decimals = 1 if metric == "average_payload_bitrate_kbps" else 3
            item[METRIC_LABELS[metric]] = _fmt(float(row["mean"]), decimals)
        output.append(item)
    return output


def build_primary_contrast_table(
    paired_rows: Sequence[dict[str, str]],
) -> list[dict[str, str]]:
    scopes = [("Overall", "overall_content_balanced_per_seed", None)] + [
        (CONTENT_LABELS[content], "per_content_per_seed", content)
        for content in CONTENT_ORDER
    ]
    output: list[dict[str, str]] = []
    for label, scope, content in scopes:
        filters = {
            "scope": scope,
            "baseline": "robust-mpc",
            "metric": "mean_objective_reward",
        }
        if content is not None:
            filters["content"] = content
        row = _one(paired_rows, **filters)
        output.append(
            {
                "Scope": label,
                "QL - RobustMPC": _fmt(float(row["mean"]), 3),
                "95% CI": _ci(row, 3),
                "Favored controller": (
                    "RobustMPC" if float(row["ci95_high"]) < 0 else "Inconclusive"
                ),
            }
        )
    return output


def build_ql_rmpc_table(
    paired_rows: Sequence[dict[str, str]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for metric in PAPER_METRICS:
        row = _one(
            paired_rows,
            scope="overall_content_balanced_per_seed",
            baseline="robust-mpc",
            metric=metric,
        )
        delta = float(row["mean"])
        low = float(row["ci95_low"])
        high = float(row["ci95_high"])
        excludes_zero = high < 0 or low > 0
        better_when = row["better_when"]
        if not excludes_zero:
            favored = "Inconclusive"
        elif (better_when == "higher" and delta > 0) or (
            better_when == "lower" and delta < 0
        ):
            favored = "Q-Learning"
        else:
            favored = "RobustMPC"
        decimals = 1 if metric == "average_payload_bitrate_kbps" else 3
        output.append(
            {
                "Metric": METRIC_LABELS[metric],
                "Better when": better_when,
                "QL - RobustMPC": _fmt(delta, decimals),
                "95% CI": _ci(row, decimals),
                "Favored controller": favored,
            }
        )
    return output


def write_csv_table(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_table(path: Path, rows: Sequence[dict[str, str]]) -> None:
    fields = list(rows[0])
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(row[field]).replace("|", "\\|") for field in fields)
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(character, character) for character in value)


def write_latex_table(path: Path, rows: Sequence[dict[str, str]]) -> None:
    fields = list(rows[0])
    alignment = "l" + "r" * (len(fields) - 1)
    lines = [
        f"\\begin{{tabular}}{{{alignment}}}",
        r"\toprule",
        " & ".join(_latex_escape(field) for field in fields) + " \\\\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(_latex_escape(str(row[field])) for field in fields) + " \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_table_set(
    directory: Path, stem: str, rows: Sequence[dict[str, str]]
) -> list[Path]:
    paths = [
        directory / f"{stem}.csv",
        directory / f"{stem}.md",
        directory / f"{stem}.tex",
    ]
    write_csv_table(paths[0], rows)
    write_markdown_table(paths[1], rows)
    write_latex_table(paths[2], rows)
    return paths


def build_and_write_tables(
    root: Path, config: dict[str, Any], output_dir: Path
) -> list[Path]:
    results_dir = root / config["results_directory"]
    aggregate = read_csv_rows(results_dir / "aggregate.csv")
    paired = read_csv_rows(results_dir / "paired_differences.csv")
    result_manifest = json.loads(
        (results_dir / "manifest.json").read_text(encoding="utf-8")
    )
    manifests = {
        content: read_csv_rows(root / config["segment_manifests"][content])
        for content in CONTENT_ORDER
    }
    table_dir = output_dir / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    generated += write_table_set(
        table_dir, "table_01_experimental_protocol", build_protocol_table(result_manifest)
    )
    generated += write_table_set(
        table_dir, "table_02_measured_vvc_ladders", build_ladder_table(manifests)
    )
    generated += write_table_set(
        table_dir, "table_03_controller_results", build_controller_table(aggregate)
    )
    generated += write_table_set(
        table_dir,
        "table_04_primary_contrast",
        build_primary_contrast_table(paired),
    )
    generated += write_table_set(
        table_dir,
        "table_05_qlearning_vs_robustmpc",
        build_ql_rmpc_table(paired),
    )
    return generated


def _matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.hashsalt": "stage57a-paper-assets-v1",
        }
    )
    import matplotlib.pyplot as plt

    return matplotlib, plt


def _save_figure(fig: Any, stem: Path) -> list[Path]:
    paths = [stem.with_suffix(".svg"), stem.with_suffix(".pdf")]
    formats = (
        (
            paths[0],
            "svg",
            {"Date": None, "Creator": "stage57a paper asset generator"},
        ),
        (
            paths[1],
            "pdf",
            {
                "CreationDate": None,
                "ModDate": None,
                "Creator": "stage57a paper asset generator",
            },
        ),
    )
    for path, output_format, metadata in formats:
        buffer = io.BytesIO()
        fig.savefig(
            buffer,
            format=output_format,
            bbox_inches="tight",
            metadata=metadata,
        )
        payload = buffer.getvalue()
        if output_format == "svg":
            text = payload.decode("utf-8")
            payload = (
                "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
            ).encode("utf-8")
        path.write_bytes(payload)
    return paths


def _controller_colors() -> dict[str, str]:
    return {
        "static": "#7A7A7A",
        "throughput": "#4C78A8",
        "bola-basic": "#F2A541",
        "robust-mpc": "#2A9D8F",
        "q-learning": "#C44E52",
    }


def _figure_pipeline(figure_dir: Path) -> list[Path]:
    _, plt = _matplotlib()
    from matplotlib.patches import FancyBboxPatch

    fig, ax = plt.subplots(figsize=(11.4, 2.45))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    boxes = [
        (0.015, "Source preparation", "4 open 1080p sequences\n60 s per content"),
        (0.215, "VVC encoding", "VVEnc/VVDec\n60 segments x 4 levels"),
        (0.415, "Measured manifests", "Payload size and PSNR-Y\n960 independent bitstreams"),
        (0.615, "ABR evaluation", "5 controllers x 3 traces\n10 training seeds"),
        (0.815, "Statistical analysis", "Content-balanced estimates\nPaired 95% t intervals"),
    ]
    colors = ["#E8F1F8", "#E9F5EF", "#FFF3DD", "#FBE9E7", "#EEEAF7"]
    width = 0.17
    for index, (x, title, subtitle) in enumerate(boxes):
        patch = FancyBboxPatch(
            (x, 0.24),
            width,
            0.52,
            boxstyle="round,pad=0.012,rounding_size=0.018",
            linewidth=1.1,
            edgecolor="#34495E",
            facecolor=colors[index],
        )
        ax.add_patch(patch)
        ax.text(x + width / 2, 0.59, title, ha="center", va="center", weight="bold")
        ax.text(x + width / 2, 0.41, subtitle, ha="center", va="center", fontsize=8)
        if index < len(boxes) - 1:
            ax.annotate(
                "",
                xy=(boxes[index + 1][0] - 0.01, 0.5),
                xytext=(x + width + 0.01, 0.5),
                arrowprops={"arrowstyle": "->", "lw": 1.3, "color": "#34495E"},
            )
    fig.tight_layout()
    paths = _save_figure(fig, figure_dir / "figure_01_experimental_pipeline")
    plt.close(fig)
    return paths


def _figure_segment_variability(
    root: Path, config: dict[str, Any], figure_dir: Path
) -> list[Path]:
    _, plt = _matplotlib()
    fig, axes = plt.subplots(2, 2, figsize=(9.2, 6.5))
    level_colors = ("#4C78A8", "#59A14F", "#F2A541", "#C44E52")
    for ax, content in zip(axes.flat, CONTENT_ORDER):
        rows = read_csv_rows(root / config["segment_manifests"][content])
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            grouped[row["representation_id"]].append(row)
        mean_x: list[float] = []
        mean_y: list[float] = []
        has_lossless = False
        for color, representation in zip(level_colors, sorted(grouped)):
            rep_rows = grouped[representation]
            actual = [
                float(row["size_bytes"]) * 8.0 / 1000.0 / float(row["duration_s"])
                for row in rep_rows
            ]
            psnr = [float(row["psnr_y_db"]) for row in rep_rows]
            regular = [index for index, value in enumerate(psnr) if value < 99.999]
            lossless = [index for index, value in enumerate(psnr) if value >= 99.999]
            ax.scatter(
                [actual[index] for index in regular],
                [psnr[index] for index in regular],
                s=13,
                alpha=0.28,
                color=color,
                edgecolors="none",
                label=representation,
            )
            if lossless:
                has_lossless = True
                ax.scatter(
                    [actual[index] for index in lossless],
                    [73.5] * len(lossless),
                    s=25,
                    marker="^",
                    alpha=0.75,
                    color=color,
                    edgecolors="#303030",
                    linewidths=0.4,
                )
            mean_x.append(statistics.mean(actual))
            mean_y.append(statistics.mean(psnr))
        ax.plot(mean_x, mean_y, color="#202020", marker="o", linewidth=1.4, markersize=4)
        ax.set_xscale("log")
        ax.grid(True, which="both", alpha=0.22, linewidth=0.6)
        ax.set_title(CONTENT_LABELS[content])
        ax.set_xlabel("Actual segment bitrate (kbps, log scale)")
        ax.set_ylabel("PSNR-Y (dB)")
        if has_lossless:
            ax.set_ylim(top=75)
            ax.text(
                0.98,
                0.96,
                "▲ lossless (100 dB cap)",
                transform=ax.transAxes,
                ha="right",
                va="top",
                fontsize=7,
                color="#303030",
            )
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, title="Representation", ncol=4, loc="upper center")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    paths = _save_figure(fig, figure_dir / "figure_02_vvc_segment_variability")
    plt.close(fig)
    return paths


def _figure_controller_metrics(
    aggregate: Sequence[dict[str, str]], figure_dir: Path
) -> list[Path]:
    _, plt = _matplotlib()
    fig, axes = plt.subplots(2, 3, figsize=(11.5, 6.2))
    colors = _controller_colors()
    titles = {
        "mean_objective_reward": "Objective reward (higher is better)",
        "rebuffering_rate_percent": "Rebuffering (lower is better)",
        "startup_delay_s": "Startup delay (lower is better)",
        "average_payload_bitrate_kbps": "Payload bitrate (higher is better)",
        "mean_psnr_y_db": "PSNR-Y (higher is better)",
        "switch_count": "Representation switches (lower is better)",
    }
    for ax, metric in zip(axes.flat, PAPER_METRICS):
        selected = [
            _one(
                aggregate,
                scope="overall_content_balanced_per_seed",
                controller=controller,
                metric=metric,
            )
            for controller in CONTROLLER_ORDER
        ]
        values = [float(row["mean"]) for row in selected]
        errors = [float(row["ci95_half_width"]) for row in selected]
        ax.bar(
            range(len(CONTROLLER_ORDER)),
            values,
            yerr=errors,
            capsize=3,
            color=[colors[controller] for controller in CONTROLLER_ORDER],
            linewidth=0,
        )
        ax.axhline(0, color="#444444", linewidth=0.7)
        ax.set_xticks(range(len(CONTROLLER_ORDER)))
        ax.set_xticklabels(
            [CONTROLLER_LABELS[item] for item in CONTROLLER_ORDER],
            rotation=23,
            ha="right",
        )
        ax.set_title(titles[metric])
        ax.set_ylabel(METRIC_LABELS[metric])
        ax.grid(axis="y", alpha=0.22, linewidth=0.6)
    fig.text(
        0.5,
        0.01,
        "95% intervals are computed across training seeds; deterministic baselines repeat identically.",
        ha="center",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    paths = _save_figure(fig, figure_dir / "figure_03_controller_metrics")
    plt.close(fig)
    return paths


def _primary_rows(paired: Sequence[dict[str, str]]) -> list[tuple[str, dict[str, str]]]:
    output = [
        (
            "Overall",
            _one(
                paired,
                scope="overall_content_balanced_per_seed",
                baseline="robust-mpc",
                metric="mean_objective_reward",
            ),
        )
    ]
    output.extend(
        (
            CONTENT_LABELS[content],
            _one(
                paired,
                scope="per_content_per_seed",
                content=content,
                baseline="robust-mpc",
                metric="mean_objective_reward",
            ),
        )
        for content in CONTENT_ORDER
    )
    return output


def _figure_primary_forest(
    paired: Sequence[dict[str, str]], figure_dir: Path
) -> list[Path]:
    _, plt = _matplotlib()
    rows = _primary_rows(paired)
    positions = list(reversed(range(len(rows))))
    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    lows = [float(row["ci95_low"]) for _, row in rows]
    for position, (label, row) in zip(positions, rows):
        value = float(row["mean"])
        low = float(row["ci95_low"])
        high = float(row["ci95_high"])
        color = "#1F6F78" if label == "Overall" else "#4C78A8"
        ax.errorbar(
            value,
            position,
            xerr=[[value - low], [high - value]],
            fmt="o",
            color=color,
            ecolor=color,
            capsize=4,
            markersize=7 if label == "Overall" else 5,
            linewidth=1.5,
        )
    ax.axvline(0, color="#303030", linestyle="--", linewidth=1)
    ax.axvspan(min(lows) - 0.15, 0, color="#E6F2F2", alpha=0.55, zorder=-2)
    ax.set_yticks(positions)
    ax.set_yticklabels([label for label, _ in rows])
    ax.set_xlabel("Difference in objective reward (Q-Learning − RobustMPC)")
    ax.set_title("Primary contrast overall and by VVC content")
    ax.text(0.02, 0.95, "Favors RobustMPC", transform=ax.transAxes, color="#1F6F78")
    ax.grid(axis="x", alpha=0.22, linewidth=0.6)
    fig.tight_layout()
    paths = _save_figure(fig, figure_dir / "figure_04_primary_contrast_forest")
    plt.close(fig)
    return paths


def _figure_qoe_tradeoff(
    aggregate: Sequence[dict[str, str]], figure_dir: Path
) -> list[Path]:
    _, plt = _matplotlib()
    colors = _controller_colors()
    offsets = {
        "static": (5, 5),
        "throughput": (5, -13),
        "bola-basic": (5, 5),
        "robust-mpc": (-70, 5),
        "q-learning": (5, 5),
    }
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for controller in CONTROLLER_ORDER:
        startup = float(
            _one(
                aggregate,
                scope="overall_content_balanced_per_seed",
                controller=controller,
                metric="startup_delay_s",
            )["mean"]
        )
        rebuffer = float(
            _one(
                aggregate,
                scope="overall_content_balanced_per_seed",
                controller=controller,
                metric="rebuffering_rate_percent",
            )["mean"]
        )
        ax.scatter(
            startup,
            rebuffer,
            s=85,
            color=colors[controller],
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
        )
        ax.annotate(
            CONTROLLER_LABELS[controller],
            (startup, rebuffer),
            xytext=offsets[controller],
            textcoords="offset points",
            fontsize=8.5,
        )
    ax.set_xlabel("Startup delay (s)")
    ax.set_ylabel("Rebuffering rate (%)")
    ax.set_title("Startup–rebuffering trade-off")
    ax.text(0.02, 0.08, "Preferred region", transform=ax.transAxes, color="#2A7F62")
    ax.annotate(
        "",
        xy=(0.03, 0.03),
        xytext=(0.18, 0.11),
        xycoords="axes fraction",
        arrowprops={"arrowstyle": "->", "color": "#2A7F62"},
    )
    ax.grid(alpha=0.22, linewidth=0.6)
    fig.tight_layout()
    paths = _save_figure(fig, figure_dir / "figure_05_startup_rebuffer_tradeoff")
    plt.close(fig)
    return paths


def _figure_content_trace_heatmap(
    paired: Sequence[dict[str, str]], figure_dir: Path
) -> list[Path]:
    matplotlib, plt = _matplotlib()
    import numpy as np

    matrix = np.array(
        [
            [
                float(
                    _one(
                        paired,
                        scope="per_content_trace",
                        content=content,
                        trace=trace,
                        baseline="robust-mpc",
                        metric="mean_objective_reward",
                    )["mean"]
                )
                for trace in TRACE_ORDER
            ]
            for content in CONTENT_ORDER
        ]
    )
    limit = max(abs(float(matrix.min())), abs(float(matrix.max())))
    norm = matplotlib.colors.TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    image = ax.imshow(matrix, cmap="RdBu_r", norm=norm, aspect="auto")
    ax.set_xticks(range(len(TRACE_ORDER)))
    ax.set_xticklabels([TRACE_LABELS[item] for item in TRACE_ORDER])
    ax.set_yticks(range(len(CONTENT_ORDER)))
    ax.set_yticklabels([CONTENT_LABELS[item] for item in CONTENT_ORDER])
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = matrix[row, column]
            text_color = "white" if abs(value) > limit * 0.48 else "#202020"
            ax.text(column, row, f"{value:.3f}", ha="center", va="center", color=text_color)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    colorbar.set_label("Objective reward difference (Q-Learning − RobustMPC)")
    ax.set_title("Primary contrast by content and evaluation trace")
    ax.set_xlabel("Evaluation trace")
    fig.tight_layout()
    paths = _save_figure(fig, figure_dir / "figure_06_content_trace_heatmap")
    plt.close(fig)
    return paths


def _figure_state_coverage(
    training: Sequence[dict[str, str]], figure_dir: Path
) -> list[Path]:
    _, plt = _matplotlib()
    values = [
        [
            100.0 * float(row["visited_states"]) / float(row["total_states"])
            for row in training
            if row["content"] == content
        ]
        for content in CONTENT_ORDER
    ]
    fig, ax = plt.subplots(figsize=(7.7, 4.2))
    box = ax.boxplot(values, patch_artist=True, widths=0.55, showfliers=False)
    for patch, color in zip(
        box["boxes"], ("#4C78A8", "#59A14F", "#F2A541", "#C44E52")
    ):
        patch.set_facecolor(color)
        patch.set_alpha(0.65)
    for index, content_values in enumerate(values, start=1):
        offsets = [index + (position - 4.5) * 0.025 for position in range(len(content_values))]
        ax.scatter(offsets, content_values, s=18, color="#303030", alpha=0.65, zorder=3)
    ax.set_xticks(range(1, len(CONTENT_ORDER) + 1))
    ax.set_xticklabels(
        [CONTENT_LABELS[item] for item in CONTENT_ORDER], rotation=15, ha="right"
    )
    ax.set_ylabel("Visited tabular states (%)")
    ax.set_title("Q-Learning state-space coverage across training seeds")
    ax.grid(axis="y", alpha=0.22, linewidth=0.6)
    fig.tight_layout()
    paths = _save_figure(fig, figure_dir / "figure_s1_qlearning_state_coverage")
    plt.close(fig)
    return paths


def build_and_write_figures(
    root: Path, config: dict[str, Any], output_dir: Path
) -> list[Path]:
    results_dir = root / config["results_directory"]
    aggregate = read_csv_rows(results_dir / "aggregate.csv")
    paired = read_csv_rows(results_dir / "paired_differences.csv")
    training = read_csv_rows(results_dir / "training_summary.csv")
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    generated += _figure_pipeline(figure_dir)
    generated += _figure_segment_variability(root, config, figure_dir)
    generated += _figure_controller_metrics(aggregate, figure_dir)
    generated += _figure_primary_forest(paired, figure_dir)
    generated += _figure_qoe_tradeoff(aggregate, figure_dir)
    generated += _figure_content_trace_heatmap(paired, figure_dir)
    generated += _figure_state_coverage(training, figure_dir)
    return generated


def write_asset_manifest(
    config: dict[str, Any], output_dir: Path, generated: Iterable[Path]
) -> Path:
    manifest_path = output_dir / "asset_manifest.json"
    payload = {
        "asset_manifest_version": 1,
        "paper_title": config["paper_title"],
        "frozen_results_commit": config["frozen_results_commit"],
        "generation_policy": "derived_only_from_sha256_pinned_stage56_inputs",
        "frozen_inputs_sha256": config["frozen_inputs_sha256"],
        "generated_assets": {
            str(path.relative_to(output_dir)).replace("\\", "/"): sha256_file(path)
            for path in sorted(generated)
        },
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def generate_all(
    root: Path, config_path: Path, output_dir: Path | None = None
) -> dict[str, Any]:
    config = load_paper_config(config_path)
    validate_frozen_inputs(root, config)
    destination = output_dir or root / config["output_directory"]
    destination.mkdir(parents=True, exist_ok=True)
    generated = build_and_write_tables(root, config, destination)
    generated += build_and_write_figures(root, config, destination)
    manifest_path = write_asset_manifest(config, destination, generated)
    return json.loads(manifest_path.read_text(encoding="utf-8"))
