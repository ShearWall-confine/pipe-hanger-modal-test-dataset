from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib.pyplot as plt

try:
    from IPython.display import Image, display
except Exception:  # pragma: no cover - optional notebook dependency
    Image = None
    display = None


CM_PER_INCH = 2.54
A4_WIDTH_IN = 21.0 / CM_PER_INCH
A4_HEIGHT_IN = 29.7 / CM_PER_INCH
DEFAULT_WORD_MARGIN_IN = 2.54 / CM_PER_INCH
WORD_A4_TEXT_WIDTH_IN = A4_WIDTH_IN - 2.0 * DEFAULT_WORD_MARGIN_IN
WORD_A4_TEXT_HEIGHT_IN = A4_HEIGHT_IN - 2.0 * DEFAULT_WORD_MARGIN_IN


@dataclass(frozen=True)
class FigureSpec:
    width: float
    height: float
    name: str


@dataclass(frozen=True)
class PublicationTheme:
    dpi: int = 400
    font_family: str = "serif"
    font_serif: tuple[str, ...] = ("Times New Roman", "Times", "DejaVu Serif")
    font_size: float = 8.5
    title_size: float = 9.5
    label_size: float = 8.8
    tick_size: float = 8.0
    legend_size: float = 7.8
    annotation_size: float = 7.6
    axes_linewidth: float = 0.9
    tick_major_width: float = 0.9
    tick_minor_width: float = 0.7
    tick_major_size: float = 4.5
    tick_minor_size: float = 2.8
    legend_frameon: bool = False
    fontweight_axes: str = "normal"
    fontweight_title: str = "normal"
    fontweight_annotation: str = "normal"

    def rcparams(self) -> dict[str, object]:
        return {
            "font.family": self.font_family,
            "font.serif": list(self.font_serif),
            "mathtext.fontset": "stix",
            "mathtext.default": "it",
            "font.size": self.font_size,
            "axes.titlesize": self.title_size,
            "axes.labelsize": self.label_size,
            "xtick.labelsize": self.tick_size,
            "ytick.labelsize": self.tick_size,
            "legend.fontsize": self.legend_size,
            "figure.dpi": self.dpi,
            "savefig.dpi": self.dpi,
            "axes.linewidth": self.axes_linewidth,
            "xtick.major.width": self.tick_major_width,
            "ytick.major.width": self.tick_major_width,
            "xtick.minor.width": self.tick_minor_width,
            "ytick.minor.width": self.tick_minor_width,
            "xtick.major.size": self.tick_major_size,
            "ytick.major.size": self.tick_major_size,
            "xtick.minor.size": self.tick_minor_size,
            "ytick.minor.size": self.tick_minor_size,
            "legend.frameon": self.legend_frameon,
        }


DEFAULT_THEME = PublicationTheme()
WORD_THEME = replace(
    DEFAULT_THEME,
    font_size=9.0,
    title_size=10.5,
    label_size=9.3,
    tick_size=8.4,
    legend_size=8.0,
    annotation_size=7.8,
)

FIGURE_SPECS: dict[str, FigureSpec] = {
    "a4_half": FigureSpec(WORD_A4_TEXT_WIDTH_IN, 3.6, "a4_half"),
    "a4_standard": FigureSpec(WORD_A4_TEXT_WIDTH_IN, 4.6, "a4_standard"),
    "a4_tall": FigureSpec(WORD_A4_TEXT_WIDTH_IN, 6.2, "a4_tall"),
    "a4_fullpage": FigureSpec(WORD_A4_TEXT_WIDTH_IN, 8.4, "a4_fullpage"),
    "a4_landscape": FigureSpec(WORD_A4_TEXT_HEIGHT_IN, 6.2, "a4_landscape"),
}


def get_figure_spec(name: str = "a4_standard") -> FigureSpec:
    if name not in FIGURE_SPECS:
        raise KeyError(f"Unknown figure spec: {name}")
    return FIGURE_SPECS[name]


def apply_publication_theme(theme: PublicationTheme = WORD_THEME) -> PublicationTheme:
    plt.rcParams.update(theme.rcparams())
    return theme


def create_figure(
    *,
    spec: str = "a4_standard",
    theme: PublicationTheme = WORD_THEME,
    nrows: int = 1,
    ncols: int = 1,
    sharex: bool = False,
    sharey: bool = False,
    constrained_layout: bool = False,
    squeeze: bool = True,
    **kwargs,
):
    apply_publication_theme(theme)
    fig_spec = get_figure_spec(spec)
    return plt.subplots(
        nrows,
        ncols,
        figsize=(fig_spec.width, fig_spec.height),
        sharex=sharex,
        sharey=sharey,
        constrained_layout=constrained_layout,
        squeeze=squeeze,
        **kwargs,
    )


def style_axis(ax, *, theme: PublicationTheme = WORD_THEME, grid: bool = False) -> None:
    for side in ("left", "right", "top", "bottom"):
        ax.spines[side].set_linewidth(theme.axes_linewidth)
    ax.tick_params(
        direction="in",
        length=theme.tick_major_size,
        width=theme.tick_major_width,
        labelsize=theme.tick_size,
    )
    if grid:
        ax.grid(True, alpha=0.18)
    else:
        ax.grid(False)

    if ax.get_title():
        current = ax.title.get_fontsize()
        ax.set_title(
            ax.get_title(),
            fontsize=min(float(current), theme.title_size),
            fontweight=theme.fontweight_title,
            pad=6,
        )
    if ax.get_xlabel():
        ax.set_xlabel(
            ax.get_xlabel(),
            fontsize=theme.label_size,
            fontweight=theme.fontweight_axes,
            labelpad=6,
        )
    if ax.get_ylabel():
        ax.set_ylabel(
            ax.get_ylabel(),
            fontsize=theme.label_size,
            fontweight=theme.fontweight_axes,
            labelpad=6,
        )

    legend = ax.get_legend()
    if legend is not None:
        for text in legend.get_texts():
            text.set_fontsize(min(float(text.get_fontsize()), theme.legend_size))
        if legend.get_title() is not None:
            legend.get_title().set_fontsize(min(float(legend.get_title().get_fontsize()), theme.legend_size))

    for text in ax.texts:
        try:
            text.set_fontsize(min(float(text.get_fontsize()), theme.annotation_size))
            text.set_fontweight(theme.fontweight_annotation)
        except Exception:
            continue


def style_figure(fig, *, theme: PublicationTheme = WORD_THEME, grid: bool = False) -> None:
    if getattr(fig, "_suptitle", None) is not None:
        fig._suptitle.set_fontsize(min(float(fig._suptitle.get_fontsize()), theme.title_size))
        fig._suptitle.set_fontweight(theme.fontweight_title)
    for ax in fig.axes:
        style_axis(ax, theme=theme, grid=grid)


def save_figure_bundle(
    fig,
    out_base: Path | str,
    *,
    formats: Sequence[str] = ("png", "tiff"),
    dpi: int | None = None,
    bbox_inches: str = "tight",
    facecolor: str | None = None,
    split_format_dirs: bool = False,
    close: bool = False,
) -> list[Path]:
    out_base = Path(out_base)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    for fmt in formats:
        if split_format_dirs:
            out_path = out_base.parent / fmt.lower() / f"{out_base.stem}.{fmt}"
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_path = out_base.with_suffix(f".{fmt}")
        effective_dpi = max(int(dpi or fig.dpi), 600)
        save_kwargs = {
            "dpi": effective_dpi,
            "bbox_inches": bbox_inches,
            "facecolor": facecolor or fig.get_facecolor(),
        }
        if fmt.lower() in {"tif", "tiff"}:
            save_kwargs["pil_kwargs"] = {"compression": "tiff_lzw"}
        fig.savefig(out_path, **save_kwargs)
        saved_paths.append(out_path)
    if close:
        plt.close(fig)
    return saved_paths


def show_saved_figure(path: Path | str) -> None:
    if display is None or Image is None:
        return
    display(Image(filename=str(path)))


def save_and_maybe_display(
    fig,
    out_base: Path | str,
    *,
    formats: Sequence[str] = ("png", "tiff"),
    display_format: str = "png",
    split_format_dirs: bool = False,
    close: bool = False,
) -> list[Path]:
    saved_paths = save_figure_bundle(
        fig,
        out_base,
        formats=formats,
        split_format_dirs=split_format_dirs,
        close=close,
    )
    for path in saved_paths:
        if path.suffix.lower() == f".{display_format.lower()}":
            show_saved_figure(path)
            break
    return saved_paths


def explain_word_a4_specs() -> dict[str, float]:
    return {
        "a4_width_in": A4_WIDTH_IN,
        "a4_height_in": A4_HEIGHT_IN,
        "word_text_width_in": WORD_A4_TEXT_WIDTH_IN,
        "word_text_height_in": WORD_A4_TEXT_HEIGHT_IN,
    }


__all__ = [
    "A4_HEIGHT_IN",
    "A4_WIDTH_IN",
    "DEFAULT_THEME",
    "FIGURE_SPECS",
    "FigureSpec",
    "PublicationTheme",
    "WORD_A4_TEXT_HEIGHT_IN",
    "WORD_A4_TEXT_WIDTH_IN",
    "WORD_THEME",
    "apply_publication_theme",
    "create_figure",
    "explain_word_a4_specs",
    "get_figure_spec",
    "save_and_maybe_display",
    "save_figure_bundle",
    "show_saved_figure",
    "style_axis",
    "style_figure",
]
