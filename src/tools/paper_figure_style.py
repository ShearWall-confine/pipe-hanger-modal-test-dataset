from __future__ import annotations

from dataclasses import dataclass

from matplotlib.lines import Line2D
from matplotlib.backends.backend_agg import FigureCanvasAgg


PT_PER_INCH = 72.27
CAS_TEXT_WIDTH_IN = 6.45
WORD_A4_TEXT_WIDTH_IN = 21.0 / 2.54 - 2.0

SUPPORT_ORDER = ("CA", "TB", "CSBD", "CSB")
SUPPORT_COLORS = {
    "CA": "#d62828",
    "TB": "#0077b6",
    "CSBD": "#6a994e",
    "CSB": "#8d6a9f",
}
SUPPORT_MARKERS = {
    "CA": "o",
    "TB": "s",
    "CSBD": "^",
    "CSB": "D",
}


@dataclass(frozen=True)
class InsertFontProfile:
    title_size: float = 14.0
    label_size: float = 13.0
    tick_size: float = 11.5
    legend_size: float = 11.5
    text_size: float = 10.2


@dataclass(frozen=True)
class TargetPdfFontProfile:
    """Desired apparent font sizes after LaTeX scales the figure."""

    title_size: float = 8.6
    label_size: float = 8.2
    tick_size: float = 7.2
    legend_size: float = 7.0
    text_size: float = 6.8


DEFAULT_TARGET_PDF_FONTS = TargetPdfFontProfile()


def font_profile_for_latex_insert(
    figure_width_in: float,
    *,
    latex_width_fraction: float = 1.0,
    latex_text_width_in: float = CAS_TEXT_WIDTH_IN,
    target: TargetPdfFontProfile = DEFAULT_TARGET_PDF_FONTS,
    min_source_size: float = 6.0,
    max_source_size: float = 11.5,
) -> InsertFontProfile:
    """Return source font sizes that will read as ``target`` after LaTeX scaling.

    Matplotlib font sizes are embedded in the source figure. LaTeX then scales
    the whole figure to the requested includegraphics width, so the apparent
    PDF font size is ``source_size * inserted_width / source_width``. This
    helper inverts that relationship and clamps only to avoid unusable extremes.
    """

    if figure_width_in <= 0:
        raise ValueError("figure_width_in must be positive")
    inserted_width_in = latex_text_width_in * latex_width_fraction
    if inserted_width_in <= 0:
        raise ValueError("inserted_width_in must be positive")
    scale = inserted_width_in / figure_width_in

    def source_size(apparent_size: float) -> float:
        return min(max(apparent_size / scale, min_source_size), max_source_size)

    return InsertFontProfile(
        title_size=source_size(target.title_size),
        label_size=source_size(target.label_size),
        tick_size=source_size(target.tick_size),
        legend_size=source_size(target.legend_size),
        text_size=source_size(target.text_size),
    )


def effective_figure_width_in(
    fig,
    *,
    use_tight_bbox: bool = True,
    pad_inches: float = 0.0,
) -> float:
    """Return the width that LaTeX will effectively scale when the figure is saved.

    When figures are exported with ``bbox_inches="tight"``, Matplotlib crops the
    canvas to the tight bounding box rather than preserving ``figsize``. The
    apparent font size in the manuscript depends on that cropped PDF width, so
    any size inversion must use the effective tight-bbox width instead of the
    nominal figure width.
    """

    canvas = getattr(fig, "canvas", None)
    if canvas is None or not hasattr(canvas, "get_renderer"):
        canvas = FigureCanvasAgg(fig)
    canvas.draw()
    if not use_tight_bbox:
        return float(fig.get_size_inches()[0])

    renderer = canvas.get_renderer()
    tight_bbox = fig.get_tightbbox(renderer)
    width_in = float(tight_bbox.width) + 2.0 * float(pad_inches)
    if width_in <= 0:
        return float(fig.get_size_inches()[0])
    return width_in


PAPER_INSERT_FONTS = font_profile_for_latex_insert(
    WORD_A4_TEXT_WIDTH_IN,
    latex_width_fraction=1.0,
)
MANUSCRIPT_MATCH_FONTS = font_profile_for_latex_insert(
    9.0,
    latex_width_fraction=1.0,
)


def support_marker_handles(
    supports=SUPPORT_ORDER,
    *,
    markersize: float = 6.8,
    edgecolor: str = "white",
) -> list[Line2D]:
    return [
        Line2D(
            [0],
            [0],
            marker=SUPPORT_MARKERS.get(sup, "o"),
            linestyle="None",
            markersize=markersize,
            markerfacecolor=SUPPORT_COLORS.get(sup, "#6c757d"),
            markeredgecolor=edgecolor,
            color="none",
            label=sup,
        )
        for sup in supports
    ]


def apply_insert_text_style(
    fig,
    profile: InsertFontProfile = PAPER_INSERT_FONTS,
    *,
    remove_suptitle: bool = True,
) -> None:
    if remove_suptitle and getattr(fig, "_suptitle", None) is not None:
        fig._suptitle.remove()
        fig._suptitle = None

    for ax in fig.axes:
        if ax.get_gid() == "keep-local-fontsizes":
            continue
        if ax.get_title():
            ax.set_title(ax.get_title(), fontsize=profile.title_size, pad=8)
        if ax.get_xlabel():
            ax.set_xlabel(ax.get_xlabel(), fontsize=profile.label_size, labelpad=7)
        if ax.get_ylabel():
            ax.set_ylabel(ax.get_ylabel(), fontsize=profile.label_size, labelpad=7)
        ax.tick_params(labelsize=profile.tick_size)
        leg = ax.get_legend()
        if leg is not None:
            _style_legend(leg, profile.legend_size)
        for txt in ax.texts:
            if txt.get_gid() == "keep-fontsize":
                continue
            txt.set_fontsize(profile.text_size)

    for leg in getattr(fig, "legends", []):
        _style_legend(leg, profile.legend_size)

    supxlabel = getattr(fig, "_supxlabel", None)
    if supxlabel is not None and supxlabel.get_gid() != "keep-fontsize":
        supxlabel.set_fontsize(profile.label_size)

    supylabel = getattr(fig, "_supylabel", None)
    if supylabel is not None and supylabel.get_gid() != "keep-fontsize":
        supylabel.set_fontsize(profile.label_size)

    for txt in getattr(fig, "texts", []):
        if txt is getattr(fig, "_suptitle", None):
            continue
        if txt is supxlabel or txt is supylabel:
            continue
        if txt.get_gid() == "keep-fontsize":
            continue
        txt.set_fontsize(profile.label_size)


def apply_insert_text_style_for_figure(
    fig,
    *,
    latex_width_fraction: float = 1.0,
    latex_text_width_in: float = CAS_TEXT_WIDTH_IN,
    target: TargetPdfFontProfile = DEFAULT_TARGET_PDF_FONTS,
    min_source_size: float = 6.0,
    max_source_size: float = 11.5,
    use_tight_bbox: bool = True,
    pad_inches: float = 0.0,
    iterations: int = 3,
    remove_suptitle: bool = True,
) -> InsertFontProfile:
    """Apply insert text sizes using the figure's effective saved width.

    The tight bounding box depends slightly on text extents, so a short fixed-
    point iteration is used to stabilize the profile before saving.
    """

    profile = font_profile_for_latex_insert(
        effective_figure_width_in(
            fig,
            use_tight_bbox=use_tight_bbox,
            pad_inches=pad_inches,
        ),
        latex_width_fraction=latex_width_fraction,
        latex_text_width_in=latex_text_width_in,
        target=target,
        min_source_size=min_source_size,
        max_source_size=max_source_size,
    )
    for _ in range(max(1, int(iterations))):
        apply_insert_text_style(fig, profile, remove_suptitle=remove_suptitle)
        profile = font_profile_for_latex_insert(
            effective_figure_width_in(
                fig,
                use_tight_bbox=use_tight_bbox,
                pad_inches=pad_inches,
            ),
            latex_width_fraction=latex_width_fraction,
            latex_text_width_in=latex_text_width_in,
            target=target,
            min_source_size=min_source_size,
            max_source_size=max_source_size,
        )
    apply_insert_text_style(fig, profile, remove_suptitle=remove_suptitle)
    return profile


def _style_legend(legend, size: float) -> None:
    for txt in legend.get_texts():
        txt.set_fontsize(size)
    if legend.get_title() is not None:
        legend.get_title().set_fontsize(size)
