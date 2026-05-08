from __future__ import annotations

from pathlib import Path


def plot_placeholder_note(output_dir: Path) -> None:
    """Заготовка: графики день×станция, heatmap покрытия — см. matplotlib/plotly."""
    output_dir.mkdir(parents=True, exist_ok=True)
