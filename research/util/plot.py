from collections.abc import Iterable, Mapping, Sequence

import matplotlib.pyplot as plt
import pandas as pd


def plot_lines_with_average(
    data: Mapping[str, tuple[Sequence[float], Sequence[float]]],
    title: str,
    xlabel: str,
    ylabel: str,
    lines: Iterable[str] | None = None,
    *,
    average_label: str = "Average",
    figsize: tuple[float, float] = (12, 6.5),
    show_markers: bool = True,
    show_zero_line: bool = True,
) -> tuple[plt.Figure, plt.Axes, pd.DataFrame]:
    """
    Plot selected lines from a dictionary and their pointwise average.

    Expected data format:
        {
            "CFX": ([1, 2, 3], [10.0, 12.0, 14.0]),
            "EUL": ([1, 2, 3], [3.0, 4.0, 5.0]),
        }

    Parameters
    ----------
    data:
        Mapping from line name to an (x_values, y_values) tuple.

    lines:
        Names of the lines to plot. When None, all lines are plotted.

    Returns
    -------
    fig, ax, dataframe:
        The Matplotlib objects and the aligned data used for plotting.
        The dataframe contains an additional average column.
    """
    if not data:
        raise ValueError("data cannot be empty.")

    selected_lines = list(data) if lines is None else list(lines)

    if not selected_lines:
        raise ValueError("At least one line must be selected.")

    missing_lines = [name for name in selected_lines if name not in data]
    if missing_lines:
        raise KeyError(f"Lines not found in data: {missing_lines}")

    series = {}

    for name in selected_lines:
        x_values, y_values = data[name]

        if len(x_values) != len(y_values):
            raise ValueError(
                f"{name!r} has {len(x_values)} x-values but "
                f"{len(y_values)} y-values."
            )

        if len(x_values) == 0:
            raise ValueError(f"{name!r} contains no observations.")

        if len(set(x_values)) != len(x_values):
            raise ValueError(f"{name!r} contains duplicate x-values.")

        series[name] = pd.Series(
            data=y_values,
            index=x_values,
            name=name,
            dtype=float,
        )

    # Align all lines using the union of their x-values.
    plot_data = pd.concat(series.values(), axis=1).sort_index()

    # Missing values are ignored, so SPX can be absent at x=9.
    plot_data[average_label] = plot_data[selected_lines].mean(
        axis=1,
        skipna=True,
    )

    fig, ax = plt.subplots(figsize=figsize)

    marker = "o" if show_markers else None

    for name in selected_lines:
        ax.plot(
            plot_data.index,
            plot_data[name],
            linewidth=1.2,
            marker=marker,
            markersize=4,
            alpha=0.7,
            label=name,
        )

    ax.plot(
        plot_data.index,
        plot_data[average_label],
        linewidth=3,
        marker=marker,
        markersize=7,
        label=average_label,
        zorder=10,
    )

    if show_zero_line:
        ax.axhline(
            y=0,
            linewidth=1,
            linestyle="--",
            alpha=0.6,
        )

    ax.set_title(
        title,
        fontsize=16,
        fontweight="bold",
        pad=15,
    )
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)

    ax.grid(
        True,
        linestyle="--",
        linewidth=0.7,
        alpha=0.35,
    )

    ax.legend(
        frameon=False,
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
    )

    fig.tight_layout()
    return fig, ax, plot_data