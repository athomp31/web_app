"""Tkinter desktop version of the Beam Designer web application."""

from __future__ import annotations

import csv
import math
import tkinter as tk
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Sequence
from xml.sax.saxutils import escape


STEEL_SHAPES: dict[str, tuple[float, float, float, float, float]] = {
    "W12x26": (26, 12.22, 6.49, 204, 33.4),
    "W12x30": (30, 12.34, 6.56, 238, 38.6),
    "W12x35": (35, 12.50, 6.56, 285, 45.6),
    "W12x40": (40, 12.71, 6.56, 350, 55.1),
}
ELASTIC_MODULUS_KSI = 29000.0
SAMPLE_DIVISIONS = 480


@dataclass(frozen=True)
class PointLoad:
    force_kip: float
    x_in: float


@dataclass(frozen=True)
class UniformLoad:
    intensity_kip_per_in: float
    start_in: float
    end_in: float


@dataclass(frozen=True)
class BeamModel:
    span_ft: float
    length_in: float
    support: str
    points: tuple[PointLoad, ...]
    uniforms: tuple[UniformLoad, ...]
    self_weight: bool


@dataclass(frozen=True)
class SectionProperties:
    name: str
    weight_lb_per_ft: float
    depth_in: float
    flange_in: float
    inertia_in4: float
    section_modulus_in3: float
    modulus_ksi: float
    allowable_bending_ksi: float
    grade: str
    yield_ksi: float


@dataclass(frozen=True)
class Sample:
    x_in: float
    shear_kip: float
    moment_kip_in: float
    deflection_in: float


@dataclass(frozen=True)
class AnalysisResult:
    reaction_a_kip: float
    reaction_b_kip: float
    reaction_moment_kip_in: float
    samples: tuple[Sample, ...]
    shear_max: Sample
    moment_max: Sample
    deflection_max: Sample
    properties: SectionProperties
    effective_uniforms: tuple[UniformLoad, ...]


def section_properties(section: str, grade: str) -> SectionProperties:
    """Return rounded sample-catalog values used by the web app."""
    try:
        weight, depth, flange, inertia, section_modulus = STEEL_SHAPES[section]
    except KeyError as exc:
        raise ValueError(f"Unknown W-shape: {section}") from exc
    if grade not in {"A992", "A36"}:
        raise ValueError(f"Unknown steel grade: {grade}")
    yield_stress = 50.0 if grade == "A992" else 36.0
    return SectionProperties(
        name=section,
        weight_lb_per_ft=weight,
        depth_in=depth,
        flange_in=flange,
        inertia_in4=inertia,
        section_modulus_in3=section_modulus,
        modulus_ksi=ELASTIC_MODULUS_KSI,
        allowable_bending_ksi=0.66 * yield_stress,
        grade=grade,
        yield_ksi=yield_stress,
    )


def _finite_number(value: str | float, description: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{description}: enter a number.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{description}: enter a finite number.")
    return result


def build_model(
    span: str | float,
    support: str,
    points: Sequence[dict[str, str]],
    uniforms: Sequence[dict[str, str]],
    self_weight: bool,
) -> BeamModel:
    span_ft = _finite_number(span, "Span")
    if span_ft <= 0:
        raise ValueError("Enter a span greater than zero.")
    if support not in {"simple", "cantilever"}:
        raise ValueError("Select a supported support condition.")
    length_in = span_ft * 12.0

    point_loads: list[PointLoad] = []
    for index, load in enumerate(points, start=1):
        magnitude = _finite_number(load.get("magnitude", ""), f"Point load {index} magnitude")
        position_ft = _finite_number(load.get("position", ""), f"Point load {index} position")
        direction = load.get("direction", "down")
        if magnitude < 0:
            raise ValueError(f"Point load {index}: magnitude cannot be negative.")
        if not 0 <= position_ft <= span_ft:
            raise ValueError(f"Point load {index}: position must be within the beam span.")
        if direction not in {"up", "down"}:
            raise ValueError(f"Point load {index}: select up or down.")
        force = magnitude if direction == "up" else -magnitude
        point_loads.append(PointLoad(force_kip=force, x_in=position_ft * 12.0))

    uniform_loads: list[UniformLoad] = []
    for index, load in enumerate(uniforms, start=1):
        intensity = _finite_number(load.get("intensity", ""), f"Uniform load {index} intensity")
        start_ft = _finite_number(load.get("start", ""), f"Uniform load {index} start")
        end_ft = _finite_number(load.get("end", ""), f"Uniform load {index} end")
        direction = load.get("direction", "down")
        if intensity < 0:
            raise ValueError(f"Uniform load {index}: intensity cannot be negative.")
        if not 0 <= start_ft < end_ft <= span_ft:
            raise ValueError(
                f"Uniform load {index}: use positions within the span, with start before end."
            )
        if direction not in {"up", "down"}:
            raise ValueError(f"Uniform load {index}: select up or down.")
        signed_intensity = intensity / 12.0 * (1 if direction == "up" else -1)
        uniform_loads.append(
            UniformLoad(signed_intensity, start_ft * 12.0, end_ft * 12.0)
        )

    return BeamModel(
        span_ft=span_ft,
        length_in=length_in,
        support=support,
        points=tuple(point_loads),
        uniforms=tuple(uniform_loads),
        self_weight=self_weight,
    )


def solve_beam(model: BeamModel, properties: SectionProperties) -> AnalysisResult:
    effective_uniforms = list(model.uniforms)
    if model.self_weight:
        self_weight_kip_per_in = -properties.weight_lb_per_ft / 1000.0 / 12.0
        effective_uniforms.append(
            UniformLoad(self_weight_kip_per_in, 0.0, model.length_in)
        )

    total_force = sum(load.force_kip for load in model.points)
    total_moment = sum(load.force_kip * load.x_in for load in model.points)
    for load in effective_uniforms:
        total_force += load.intensity_kip_per_in * (load.end_in - load.start_in)
        total_moment += (
            load.intensity_kip_per_in
            * (load.end_in**2 - load.start_in**2)
            / 2.0
        )

    if model.support == "simple":
        reaction_b = -total_moment / model.length_in
        reaction_a = -total_force - reaction_b
        reaction_moment = 0.0
    else:
        reaction_a = -total_force
        reaction_b = 0.0
        reaction_moment = -total_moment

    def shear_at(x_in: float) -> float:
        shear = reaction_a
        for load in model.points:
            if x_in >= load.x_in:
                shear += load.force_kip
        for load in effective_uniforms:
            loaded_length = max(0.0, min(x_in, load.end_in) - load.start_in)
            shear += load.intensity_kip_per_in * loaded_length
        if model.support == "simple" and x_in >= model.length_in:
            shear += reaction_b
        return shear

    def moment_at(x_in: float) -> float:
        moment = -reaction_moment + reaction_a * x_in
        for load in model.points:
            if x_in > load.x_in:
                moment += load.force_kip * (x_in - load.x_in)
        for load in effective_uniforms:
            left = max(0.0, x_in - load.start_in)
            right = max(0.0, x_in - load.end_in)
            moment += load.intensity_kip_per_in * (left**2 - right**2) / 2.0
        return moment

    positions = {model.length_in * index / SAMPLE_DIVISIONS for index in range(SAMPLE_DIVISIONS + 1)}
    positions.update(load.x_in for load in model.points)
    for load in effective_uniforms:
        positions.add(load.start_in)
        positions.add(load.end_in)
    xs = sorted(positions)

    moments = [moment_at(x_in) for x_in in xs]
    slopes = [0.0] * len(xs)
    deflections = [0.0] * len(xs)
    flexural_rigidity = properties.modulus_ksi * properties.inertia_in4
    for index in range(1, len(xs)):
        dx = xs[index] - xs[index - 1]
        slopes[index] = slopes[index - 1] + (
            (moments[index - 1] + moments[index]) / (2.0 * flexural_rigidity) * dx
        )
        deflections[index] = deflections[index - 1] + (
            (slopes[index - 1] + slopes[index]) / 2.0 * dx
        )
    if model.support == "simple":
        slope_correction = -deflections[-1] / model.length_in
        for index, x_in in enumerate(xs):
            deflections[index] += slope_correction * x_in

    samples = tuple(
        Sample(x_in, shear_at(x_in), moments[index], deflections[index])
        for index, x_in in enumerate(xs)
    )
    return AnalysisResult(
        reaction_a_kip=reaction_a,
        reaction_b_kip=reaction_b,
        reaction_moment_kip_in=reaction_moment,
        samples=samples,
        shear_max=max(samples, key=lambda sample: abs(sample.shear_kip)),
        moment_max=max(samples, key=lambda sample: abs(sample.moment_kip_in)),
        deflection_max=max(samples, key=lambda sample: abs(sample.deflection_in)),
        properties=properties,
        effective_uniforms=tuple(effective_uniforms),
    )


def _interpolate(samples: Sequence[Sample], x_in: float, field: str) -> float:
    if x_in <= samples[0].x_in:
        return getattr(samples[0], field)
    if x_in >= samples[-1].x_in:
        return getattr(samples[-1], field)
    low, high = 0, len(samples) - 1
    while high - low > 1:
        middle = (low + high) // 2
        if samples[middle].x_in <= x_in:
            low = middle
        else:
            high = middle
    left = samples[low]
    right = samples[high]
    ratio = (x_in - left.x_in) / (right.x_in - left.x_in)
    return getattr(left, field) + (
        getattr(right, field) - getattr(left, field)
    ) * ratio


def export_rows(
    model: BeamModel, result: AnalysisResult
) -> list[list[str | float]]:
    rows: list[list[str | float]] = [
        ["Type", "Name", "Value", "Unit", "Position (ft)", "V (kip)", "M (kip-ft)", "Deflection (in)"],
        ["Input", "Section", result.properties.name, "", "", "", "", ""],
        ["Input", "Steel grade", result.properties.grade, "", "", "", "", ""],
        ["Input", "Support", model.support, "", "", "", "", ""],
        ["Input", "Span", model.span_ft, "ft", "", "", "", ""],
        ["Input", "Self-weight included", "Yes" if model.self_weight else "No", "", "", "", "", ""],
    ]
    for index, load in enumerate(model.points, start=1):
        rows.extend(
            [
                ["Input", f"Point load {index} magnitude", abs(load.force_kip), "kip", "", "", "", ""],
                ["Input", f"Point load {index} direction", "up" if load.force_kip >= 0 else "down", "", "", "", "", ""],
                ["Input", f"Point load {index} position", load.x_in / 12.0, "ft", "", "", "", ""],
            ]
        )
    for index, load in enumerate(model.uniforms, start=1):
        rows.extend(
            [
                ["Input", f"Uniform load {index} intensity", abs(load.intensity_kip_per_in) * 12.0, "kip/ft", "", "", "", ""],
                ["Input", f"Uniform load {index} direction", "up" if load.intensity_kip_per_in >= 0 else "down", "", "", "", "", ""],
                ["Input", f"Uniform load {index} start", load.start_in / 12.0, "ft", "", "", "", ""],
                ["Input", f"Uniform load {index} end", load.end_in / 12.0, "ft", "", "", "", ""],
            ]
        )
    rows.extend(
        [
            ["Result", "Left reaction", result.reaction_a_kip, "kip", "", "", "", ""],
            ["Result", "Right reaction", result.reaction_b_kip, "kip", "", "", "", ""],
            ["Result", "Fixed-end reaction moment", result.reaction_moment_kip_in / 12.0, "kip-ft", "", "", "", ""],
            ["Result", "Maximum absolute shear", abs(result.shear_max.shear_kip), "kip", result.shear_max.x_in / 12.0, "", "", ""],
            ["Result", "Maximum absolute moment", abs(result.moment_max.moment_kip_in) / 12.0, "kip-ft", result.moment_max.x_in / 12.0, "", "", ""],
            ["Result", "Maximum absolute deflection", abs(result.deflection_max.deflection_in), "in", result.deflection_max.x_in / 12.0, "", "", ""],
        ]
    )
    bending_actual = abs(result.moment_max.moment_kip_in) / result.properties.section_modulus_in3
    bending_pass = bending_actual <= result.properties.allowable_bending_ksi
    deflection_limit = model.length_in / 360.0
    deflection_actual = abs(result.deflection_max.deflection_in)
    rows.extend(
        [
            ["Check", "Bending actual", bending_actual, "ksi", "", "", "", ""],
            ["Check", "Bending allowable", result.properties.allowable_bending_ksi, "ksi", "", "", "", ""],
            ["Check", "Bending status", "PASS" if bending_pass else "FAIL", "", "", "", "", ""],
            ["Check", "Deflection actual", deflection_actual, "in", "", "", "", ""],
            ["Check", "Deflection allowable (L/360)", deflection_limit, "in", "", "", "", ""],
            ["Check", "Deflection status", "PASS" if deflection_actual <= deflection_limit else "FAIL", "", "", "", "", ""],
        ]
    )
    for sample in result.samples:
        rows.append(
            [
                "Diagram sample",
                "Beam position",
                "",
                "",
                sample.x_in / 12.0,
                sample.shear_kip,
                sample.moment_kip_in / 12.0,
                sample.deflection_in,
            ]
        )
    return rows


def _xlsx_cell(reference: str, value: str | float) -> str:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return f'<c r="{reference}"><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{reference}" t="inlineStr"><is><t>{text}</t></is></c>'


def write_xlsx(path: Path, rows: Sequence[Sequence[str | float]]) -> None:
    """Write a minimal standards-compliant single-sheet XLSX using stdlib."""
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = "".join(
            _xlsx_cell(f"{_excel_column(column_index)}{row_index}", value)
            for column_index, value in enumerate(row, start=1)
        )
        sheet_rows.append(f'<row r="{row_index}">{cells}</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Beam Results" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    root_relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as workbook_file:
        workbook_file.writestr("[Content_Types].xml", content_types)
        workbook_file.writestr("_rels/.rels", root_relationships)
        workbook_file.writestr("xl/workbook.xml", workbook)
        workbook_file.writestr("xl/_rels/workbook.xml.rels", relationships)
        workbook_file.writestr("xl/worksheets/sheet1.xml", worksheet)


def _excel_column(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


class BeamDesignerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Beam Designer")
        self.root.geometry("1440x940")
        self.root.minsize(1080, 720)
        self.root.configure(bg="#f7f8f4")
        self._set_styles()

        self.section_var = tk.StringVar(value="W12x26")
        self.grade_var = tk.StringVar(value="A992")
        self.support_var = tk.StringVar(value="simple")
        self.span_var = tk.StringVar(value="20")
        self.self_weight_var = tk.BooleanVar(value=False)
        self.export_format_var = tk.StringVar(value="CSV")
        self.selected_point_var = tk.StringVar(value="")
        self.slider_var = tk.DoubleVar(value=0.0)
        self.points: list[dict[str, tk.Variable]] = []
        self.uniforms: list[dict[str, tk.Variable]] = []
        self.latest_model: BeamModel | None = None
        self.latest_result: AnalysisResult | None = None
        self._slider_syncing = False
        self._bulk_update = False
        self._traces: list[tuple[tk.Variable, str]] = []
        self._crosshair_x: float | None = None
        self._control_canvas: tk.Canvas | None = None
        self._control_inner: ttk.Frame | None = None
        self._plot: tk.Canvas | None = None
        self._status_var = tk.StringVar(value="")
        self._reaction_var = tk.StringVar(value="Reactions: —")
        self._shear_var = tk.StringVar(value="Maximum shear: —")
        self._moment_var = tk.StringVar(value="Maximum moment: —")
        self._deflection_var = tk.StringVar(value="Maximum deflection: —")
        self._bending_check_var = tk.StringVar(value="Bending check: —")
        self._deflection_check_var = tk.StringVar(value="Deflection check: —")
        self._readout_var = tk.StringVar(value="Move over a diagram to inspect values.")
        self._bending_ratio_canvas: tk.Canvas | None = None
        self._deflection_ratio_canvas: tk.Canvas | None = None
        self._bending_ratio = 0.0
        self._deflection_ratio = 0.0

        self._make_default_loads()
        self._build_window()
        self._bind_variable_updates()
        self._build_controls()
        self.refresh()

    def _set_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        available = set(self.root.tk.call("font", "families"))
        family = "Papyrus" if "Papyrus" in available else (
            "Georgia" if "Georgia" in available else "TkDefaultFont"
        )
        self.font_family = family
        style.configure(".", font=(family, 10), background="#f7f8f4", foreground="#253b32")
        style.configure("TFrame", background="#f7f8f4")
        style.configure("Panel.TFrame", background="#fffefa")
        style.configure("TLabel", background="#f7f8f4", foreground="#253b32")
        style.configure("Panel.TLabel", background="#fffefa")
        style.configure("Title.TLabel", font=(family, 20, "bold"), foreground="#253b32")
        style.configure("Section.TLabel", font=(family, 12, "bold"), foreground="#334a40")
        style.configure("Helper.TLabel", foreground="#728078")
        style.configure("Status.TLabel", foreground="#a23340")
        style.configure("TButton", padding=(8, 5))
        style.configure("Accent.TButton", foreground="#fffefa", background="#277653")

    def _make_default_loads(self) -> None:
        self.uniforms = [
            {
                "intensity": tk.StringVar(value="1"),
                "direction": tk.StringVar(value="down"),
                "start": tk.StringVar(value="0"),
                "end": tk.StringVar(value="20"),
            }
        ]
        for variable in self.uniforms[0].values():
            self._trace_variable(variable)

    def _new_point(
        self, magnitude: str = "5", position: str = "10", direction: str = "down"
    ) -> dict[str, tk.Variable]:
        load: dict[str, tk.Variable] = {
            "magnitude": tk.StringVar(value=magnitude),
            "position": tk.StringVar(value=position),
            "direction": tk.StringVar(value=direction),
        }
        for variable in load.values():
            self._trace_variable(variable)
        return load

    def _new_uniform(
        self,
        intensity: str = "0.5",
        start: str = "0",
        end: str | None = None,
        direction: str = "down",
    ) -> dict[str, tk.Variable]:
        load: dict[str, tk.Variable] = {
            "intensity": tk.StringVar(value=intensity),
            "direction": tk.StringVar(value=direction),
            "start": tk.StringVar(value=start),
            "end": tk.StringVar(value=end or self.span_var.get()),
        }
        for variable in load.values():
            self._trace_variable(variable)
        return load

    def _trace_variable(self, variable: tk.Variable) -> None:
        trace_id = variable.trace_add("write", self._on_input_changed)
        self._traces.append((variable, trace_id))

    def _bind_variable_updates(self) -> None:
        for variable in (
            self.section_var,
            self.grade_var,
            self.support_var,
            self.span_var,
            self.self_weight_var,
        ):
            self._trace_variable(variable)
        self._trace_variable(self.selected_point_var)

    def _build_window(self) -> None:
        header = ttk.Frame(self.root, padding=(18, 12, 18, 8))
        header.pack(fill="x")
        ttk.Label(header, text="Beam Designer", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="Steel W-shape analysis · preliminary/educational use",
            style="Helper.TLabel",
        ).pack(side="left", padx=(14, 0), pady=(8, 0))

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        input_panel = ttk.Frame(body, style="Panel.TFrame", padding=4, width=350)
        input_panel.pack_propagate(False)
        body.add(input_panel, weight=0)

        self._control_canvas = tk.Canvas(
            input_panel, background="#fffefa", highlightthickness=0, width=340
        )
        scrollbar = ttk.Scrollbar(
            input_panel, orient="vertical", command=self._control_canvas.yview
        )
        self._control_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._control_canvas.pack(side="left", fill="both", expand=True)
        self._control_inner = ttk.Frame(self._control_canvas, style="Panel.TFrame", padding=12)
        self._control_window = self._control_canvas.create_window(
            (0, 0), window=self._control_inner, anchor="nw"
        )
        self._control_inner.bind("<Configure>", self._update_control_scrollregion)
        self._control_canvas.bind("<Configure>", self._resize_control_inner)

        results = ttk.Frame(body, padding=(10, 4))
        body.add(results, weight=1)
        ttk.Label(results, textvariable=self._status_var, style="Status.TLabel").pack(
            anchor="w", pady=(0, 4)
        )
        metrics = ttk.Frame(results)
        metrics.pack(fill="x", pady=(0, 6))
        for variable in (
            self._reaction_var,
            self._shear_var,
            self._moment_var,
            self._deflection_var,
        ):
            ttk.Label(metrics, textvariable=variable, style="Panel.TLabel", padding=7).pack(
                side="left", fill="x", expand=True, padx=(0, 5)
            )
        self._plot = tk.Canvas(
            results, background="#fffefa", highlightthickness=1,
            highlightbackground="#dce3db", height=650, takefocus=True,
        )
        self._plot.pack(fill="both", expand=True)
        self._plot.bind("<Configure>", self._on_plot_resize)
        self._plot.bind("<Motion>", self._on_plot_motion)
        self._plot.bind("<Leave>", self._on_plot_leave)
        self._plot.bind("<Button-1>", self._on_plot_click)
        self._plot.bind("<Left>", self._on_plot_key)
        self._plot.bind("<Right>", self._on_plot_key)

        checks = ttk.Frame(results)
        checks.pack(fill="x", pady=(8, 0))
        bending_card = ttk.Frame(checks, style="Panel.TFrame", padding=8)
        bending_card.pack(side="left", fill="x", expand=True, padx=(0, 5))
        deflection_card = ttk.Frame(checks, style="Panel.TFrame", padding=8)
        deflection_card.pack(side="left", fill="x", expand=True)
        ttk.Label(
            bending_card, textvariable=self._bending_check_var, style="Panel.TLabel"
        ).pack(anchor="w")
        ttk.Label(
            deflection_card, textvariable=self._deflection_check_var, style="Panel.TLabel"
        ).pack(anchor="w")
        self._bending_ratio_canvas = tk.Canvas(
            bending_card, height=12, background="#e5eae3", highlightthickness=0
        )
        self._bending_ratio_canvas.pack(fill="x", pady=(6, 0))
        self._bending_ratio_canvas.bind(
            "<Configure>",
            lambda event: self._draw_ratio(
                self._bending_ratio_canvas, self._bending_ratio, event.width
            ),
        )
        self._deflection_ratio_canvas = tk.Canvas(
            deflection_card, height=12, background="#e5eae3", highlightthickness=0
        )
        self._deflection_ratio_canvas.pack(fill="x", pady=(6, 0))
        self._deflection_ratio_canvas.bind(
            "<Configure>",
            lambda event: self._draw_ratio(
                self._deflection_ratio_canvas, self._deflection_ratio, event.width
            ),
        )
        ttk.Label(results, textvariable=self._readout_var, style="Helper.TLabel").pack(
            anchor="w", pady=(5, 0)
        )

    def _update_control_scrollregion(self, event: tk.Event[tk.Misc]) -> None:
        if self._control_canvas is not None and event.widget is self._control_inner:
            self._control_canvas.configure(scrollregion=self._control_canvas.bbox("all"))

    def _resize_control_inner(self, event: tk.Event[tk.Misc]) -> None:
        if self._control_canvas is not None:
            self._control_canvas.itemconfigure(self._control_window, width=event.width)

    def _build_controls(self) -> None:
        if self._control_inner is None:
            return
        for child in self._control_inner.winfo_children():
            child.destroy()

        self._section_heading(self._control_inner, "Member and supports")
        self._field_combo(
            self._control_inner, "Steel grade", self.grade_var,
            (("A992", "A992 · Fy 50 ksi"), ("A36", "A36 · Fy 36 ksi")),
        )
        self._field_combo(
            self._control_inner, "Beam section", self.section_var,
            tuple((name, f"{name} · {values[0]:g} lb/ft") for name, values in STEEL_SHAPES.items()),
        )
        self._field_entry(self._control_inner, "Span (ft)", self.span_var)
        self._field_combo(
            self._control_inner, "Supports", self.support_var,
            (("simple", "Simply supported"), ("cantilever", "Cantilever")),
        )
        ttk.Checkbutton(
            self._control_inner,
            text="Include member self-weight",
            variable=self.self_weight_var,
        ).pack(anchor="w", pady=(5, 12))
        ttk.Button(
            self._control_inner, text="Reset example", command=self._reset_example
        ).pack(anchor="w", pady=(0, 10))

        self._section_heading(self._control_inner, f"Point loads ({len(self.points)})")
        if not self.points:
            ttk.Label(
                self._control_inner, text="No point loads.", style="Helper.TLabel"
            ).pack(anchor="w", pady=(0, 6))
        for index, load in enumerate(self.points):
            card = ttk.LabelFrame(self._control_inner, text=f"Point load {index + 1}", padding=8)
            card.pack(fill="x", pady=(0, 7))
            self._field_entry(card, "Magnitude (kip)", load["magnitude"])
            self._field_entry(card, "Position (ft)", load["position"])
            self._field_combo(
                card, "Direction", load["direction"],
                (("down", "Down"), ("up", "Up")),
            )
            ttk.Button(
                card, text="Remove point load",
                command=lambda selected=index: self._remove_point(selected),
            ).pack(anchor="e", pady=(5, 0))
        ttk.Button(
            self._control_inner, text="+ Add point load", command=self._add_point
        ).pack(anchor="w", pady=(0, 8))

        slider_frame = ttk.LabelFrame(
            self._control_inner, text="Move selected point load", padding=8
        )
        slider_frame.pack(fill="x", pady=(0, 12))
        selector_values = tuple(f"Point load {index + 1}" for index in range(len(self.points)))
        self._field_combo(
            slider_frame, "Selected load", self.selected_point_var,
            tuple((value, value) for value in selector_values),
        )
        self._point_slider = ttk.Scale(
            slider_frame, from_=0.0, to=max(0.01, self._span_for_slider()),
            variable=self.slider_var, command=self._on_slider_moved,
        )
        self._point_slider.pack(fill="x", padx=3, pady=(5, 2))
        ttk.Label(
            slider_frame,
            text="Drag to move the selected load and update the plots.",
            style="Helper.TLabel",
        ).pack(anchor="w")
        self._sync_slider_to_selection()

        self._section_heading(self._control_inner, f"Uniform loads ({len(self.uniforms)})")
        if not self.uniforms:
            ttk.Label(
                self._control_inner, text="No uniform loads.", style="Helper.TLabel"
            ).pack(anchor="w", pady=(0, 6))
        for index, load in enumerate(self.uniforms):
            card = ttk.LabelFrame(self._control_inner, text=f"Uniform load {index + 1}", padding=8)
            card.pack(fill="x", pady=(0, 7))
            self._field_entry(card, "Intensity (kip/ft)", load["intensity"])
            self._field_combo(
                card, "Direction", load["direction"],
                (("down", "Down"), ("up", "Up")),
            )
            self._field_entry(card, "Start (ft)", load["start"])
            self._field_entry(card, "End (ft)", load["end"])
            ttk.Button(
                card, text="Remove uniform load",
                command=lambda selected=index: self._remove_uniform(selected),
            ).pack(anchor="e", pady=(5, 0))
        ttk.Button(
            self._control_inner, text="+ Add uniform load", command=self._add_uniform
        ).pack(anchor="w", pady=(0, 12))

        self._section_heading(self._control_inner, "Export results")
        export_row = ttk.Frame(self._control_inner, style="Panel.TFrame")
        export_row.pack(fill="x", pady=(0, 8))
        ttk.Combobox(
            export_row, textvariable=self.export_format_var,
            values=("CSV", "Excel (.xlsx)"), state="readonly", width=16,
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(
            export_row, text="Export", style="Accent.TButton", command=self._export
        ).pack(side="left")

        ttk.Label(
            self._control_inner,
            text=(
                "Embedded sample W-shape catalog with rounded properties. "
                "E = 29,000 ksi; Fb = 0.66Fy. Confirm properties and design "
                "provisions against an authoritative source before real design use."
            ),
            style="Helper.TLabel", wraplength=295, justify="left",
        ).pack(anchor="w", pady=(5, 3))

    def _discard_load_traces(self, load: dict[str, tk.Variable]) -> None:
        retained: list[tuple[tk.Variable, str]] = []
        for variable, trace_id in self._traces:
            if any(variable is load_variable for load_variable in load.values()):
                variable.trace_remove("write", trace_id)
            else:
                retained.append((variable, trace_id))
        self._traces = retained

    def _section_heading(self, parent: ttk.Frame, text: str) -> None:
        ttk.Label(parent, text=text, style="Section.TLabel").pack(
            anchor="w", pady=(5, 7)
        )

    def _field_entry(
        self, parent: ttk.Frame, label: str, variable: tk.Variable
    ) -> None:
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, style="Panel.TLabel").pack(side="left")
        ttk.Entry(row, textvariable=variable, width=12).pack(side="right")

    def _field_combo(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        options: Sequence[tuple[str, str]],
    ) -> None:
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, style="Panel.TLabel").pack(side="left")
        display_to_value = {display: value for value, display in options}
        value_to_display = {value: display for value, display in options}
        display_var = tk.StringVar(
            value=value_to_display.get(variable.get(), variable.get())
        )
        combo = ttk.Combobox(
            row, textvariable=display_var,
            values=tuple(option[1] for option in options),
            state="readonly", width=22,
        )
        combo.pack(side="right")
        combo.bind(
            "<<ComboboxSelected>>",
            lambda event, var=variable,
            mapping=display_to_value, field=label: self._combo_selected(
                var, event.widget.get(), mapping, field
            ),
            add="+",
        )

    def _combo_selected(
        self,
        variable: tk.StringVar,
        selected: str,
        display_to_value: dict[str, str],
        field: str,
    ) -> None:
        if selected in display_to_value:
            variable.set(display_to_value[selected])
        if field == "Selected load":
            self._sync_slider_to_selection()
        self.refresh()

    def _on_input_changed(self, *trace_info: str) -> None:
        if len(trace_info) != 3 or trace_info[2] != "write":
            return
        if not self._slider_syncing and not self._bulk_update:
            self._sync_slider_to_selection()
            self.refresh()

    def _span_for_slider(self) -> float:
        try:
            span = float(self.span_var.get())
        except ValueError:
            return 1.0
        return span if math.isfinite(span) and span > 0 else 1.0

    def _selected_point_index(self) -> int | None:
        label = self.selected_point_var.get()
        if not label.startswith("Point load "):
            return None
        try:
            index = int(label.rsplit(" ", 1)[1]) - 1
        except ValueError:
            return None
        return index if 0 <= index < len(self.points) else None

    def _sync_slider_to_selection(self) -> None:
        if not hasattr(self, "_point_slider"):
            return
        self._slider_syncing = True
        try:
            self._point_slider.configure(to=max(0.01, self._span_for_slider()))
            index = self._selected_point_index()
            if index is None:
                self._point_slider.state(["disabled"])
                self.slider_var.set(0.0)
            else:
                self._point_slider.state(["!disabled"])
                try:
                    position = float(self.points[index]["position"].get())
                except (ValueError, tk.TclError):
                    position = 0.0
                self.slider_var.set(min(max(position, 0.0), self._span_for_slider()))
        finally:
            self._slider_syncing = False

    def _on_slider_moved(self, value: str) -> None:
        if self._slider_syncing:
            return
        index = self._selected_point_index()
        if index is None:
            return
        try:
            position = min(max(float(value), 0.0), self._span_for_slider())
        except ValueError:
            return
        self._slider_syncing = True
        try:
            self.points[index]["position"].set(f"{position:.3f}")
        finally:
            self._slider_syncing = False
        self.refresh()

    def _add_point(self) -> None:
        position = str(self._span_for_slider() / 2.0)
        self.points.append(self._new_point(position=position))
        self.selected_point_var.set(f"Point load {len(self.points)}")
        self._build_controls()
        self.refresh()

    def _remove_point(self, index: int) -> None:
        if 0 <= index < len(self.points):
            self._discard_load_traces(self.points[index])
            self.points.pop(index)
        self.selected_point_var.set(
            f"Point load {min(index, len(self.points) - 1) + 1}" if self.points else ""
        )
        self._build_controls()
        self.refresh()

    def _add_uniform(self) -> None:
        self.uniforms.append(self._new_uniform())
        self._build_controls()
        self.refresh()

    def _remove_uniform(self, index: int) -> None:
        if 0 <= index < len(self.uniforms):
            self._discard_load_traces(self.uniforms[index])
            self.uniforms.pop(index)
        self._build_controls()
        self.refresh()

    def _reset_example(self) -> None:
        self._bulk_update = True
        try:
            for load in (*self.points, *self.uniforms):
                self._discard_load_traces(load)
            self.points.clear()
            self.uniforms.clear()
            self.section_var.set("W12x26")
            self.grade_var.set("A992")
            self.support_var.set("simple")
            self.span_var.set("20")
            self.self_weight_var.set(False)
            self.selected_point_var.set("")
            self._make_default_loads()
        finally:
            self._bulk_update = False
        self._build_controls()
        self.refresh()

    def _current_raw_loads(self) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        points = [
            {key: str(variable.get()) for key, variable in load.items()}
            for load in self.points
        ]
        uniforms = [
            {key: str(variable.get()) for key, variable in load.items()}
            for load in self.uniforms
        ]
        return points, uniforms

    def refresh(self) -> None:
        try:
            points, uniforms = self._current_raw_loads()
            model = build_model(
                self.span_var.get(),
                self.support_var.get(),
                points,
                uniforms,
                self.self_weight_var.get(),
            )
            properties = section_properties(self.section_var.get(), self.grade_var.get())
            result = solve_beam(model, properties)
        except ValueError as exc:
            self.latest_model = None
            self.latest_result = None
            self._status_var.set(str(exc))
            self._reaction_var.set("Reactions: —")
            self._shear_var.set("Maximum shear: —")
            self._moment_var.set("Maximum moment: —")
            self._deflection_var.set("Maximum deflection: —")
            self._bending_check_var.set("Bending check: pending")
            self._deflection_check_var.set("Deflection check: pending")
            self._readout_var.set("Correct the inputs to inspect results.")
            if self._plot is not None:
                self._plot.delete("all")
                self._plot.create_text(
                    max(200, self._plot.winfo_width() / 2),
                    max(100, self._plot.winfo_height() / 2),
                    text="Valid inputs are needed to draw the beam.",
                    fill="#a23340", font=(self.font_family, 14),
                )
            return

        self.latest_model = model
        self.latest_result = result
        self._status_var.set(
            f"{properties.name} · {properties.grade} · "
            f"{'Simply supported' if model.support == 'simple' else 'Cantilever'} · "
            f"{model.span_ft:g} ft span"
        )
        if model.support == "simple":
            self._reaction_var.set(
                f"Reactions: Rₐ {result.reaction_a_kip:+.2f} kip · "
                f"Rᵦ {result.reaction_b_kip:+.2f} kip"
            )
        else:
            self._reaction_var.set(
                f"Reactions: Rₐ {result.reaction_a_kip:+.2f} kip · "
                f"Mₐ {result.reaction_moment_kip_in / 12:+.2f} kip-ft"
            )
        self._shear_var.set(
            f"Max |V|: {abs(result.shear_max.shear_kip):.2f} kip"
        )
        self._moment_var.set(
            f"Max |M|: {abs(result.moment_max.moment_kip_in) / 12:.2f} kip-ft"
        )
        self._deflection_var.set(
            f"Max |v|: {abs(result.deflection_max.deflection_in):.3f} in"
        )
        bending_actual = abs(result.moment_max.moment_kip_in) / properties.section_modulus_in3
        bending_passes = bending_actual <= properties.allowable_bending_ksi
        bending_percent = bending_actual / properties.allowable_bending_ksi * 100
        deflection_actual = abs(result.deflection_max.deflection_in)
        deflection_limit = model.length_in / 360.0
        deflection_passes = deflection_actual <= deflection_limit
        deflection_percent = deflection_actual / deflection_limit * 100
        self._bending_check_var.set(
            f"Bending: {'PASS' if bending_passes else 'FAIL'} · "
            f"{bending_actual:.2f} / {properties.allowable_bending_ksi:.2f} ksi "
            f"({bending_percent:.1f}%)"
        )
        self._deflection_check_var.set(
            f"Deflection: {'PASS' if deflection_passes else 'FAIL'} · "
            f"{deflection_actual:.3f} / {deflection_limit:.3f} in "
            f"({deflection_percent:.1f}%)"
        )
        self._bending_ratio = bending_actual / properties.allowable_bending_ksi
        self._deflection_ratio = deflection_actual / deflection_limit
        self._draw_ratio(self._bending_ratio_canvas, self._bending_ratio)
        self._draw_ratio(self._deflection_ratio_canvas, self._deflection_ratio)
        self._readout_var.set("Move over a diagram to inspect V, M, and deflection.")
        self._crosshair_x = None
        self._sync_slider_to_selection()
        self._draw_plot()

    def _draw_ratio(
        self, canvas: tk.Canvas | None, ratio: float, configured_width: int | None = None
    ) -> None:
        if canvas is None or not canvas.winfo_exists():
            return
        canvas.delete("all")
        width = max(1, configured_width or canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        percent = ratio * 100.0
        color = "#277653" if percent < 70 else "#d99b24" if percent <= 100 else "#c6404e"
        canvas.create_rectangle(
            0, 0, width * min(max(percent, 0.0), 100.0) / 100.0, height,
            fill=color, outline="",
        )

    def _on_plot_resize(self, event: tk.Event[tk.Misc]) -> None:
        self._draw_plot(event.width)

    def _on_plot_motion(self, event: tk.Event[tk.Misc]) -> None:
        if self.latest_model is None or self.latest_result is None or self._plot is None:
            return
        left, right = 76.0, float(self._plot.winfo_width() - 24)
        x_pixel = self._plot.canvasx(event.x)
        if not left <= x_pixel <= right:
            self._crosshair_x = None
            self._draw_plot()
            return
        ratio = (x_pixel - left) / (right - left)
        self._inspect_plot_position(ratio * self.latest_model.length_in)

    def _on_plot_click(self, event: tk.Event[tk.Misc]) -> None:
        if self._plot is not None:
            self._plot.focus_set()
        self._on_plot_motion(event)

    def _on_plot_key(self, event: tk.Event[tk.Misc]) -> str | None:
        if self.latest_model is None:
            return None
        current = self._crosshair_x
        if current is None:
            current = self.latest_model.length_in / 2.0
        step = self.latest_model.length_in / 100.0
        direction = -1.0 if event.keysym == "Left" else 1.0
        self._inspect_plot_position(current + direction * step)
        return "break"

    def _inspect_plot_position(self, x_in: float) -> None:
        if self.latest_model is None or self.latest_result is None:
            return
        x_in = min(max(x_in, 0.0), self.latest_model.length_in)
        self._crosshair_x = x_in
        shear = _interpolate(self.latest_result.samples, x_in, "shear_kip")
        moment = _interpolate(self.latest_result.samples, x_in, "moment_kip_in") / 12.0
        deflection = _interpolate(self.latest_result.samples, x_in, "deflection_in")
        self._readout_var.set(
            f"x = {x_in / 12:.2f} ft · V = {shear:+.2f} kip · "
            f"M = {moment:+.2f} kip-ft · v = {deflection:+.3f} in"
        )
        self._draw_plot()

    def _on_plot_leave(self, event: tk.Event[tk.Misc]) -> None:
        if event.widget is not self._plot:
            return
        self._crosshair_x = None
        self._draw_plot()
        if self.latest_result is not None:
            self._readout_var.set("Move over a diagram to inspect V, M, and deflection.")

    def _draw_plot(self, configured_width: int | None = None) -> None:
        if self._plot is None:
            return
        canvas = self._plot
        canvas.delete("all")
        if self.latest_model is None or self.latest_result is None:
            return
        model = self.latest_model
        result = self.latest_result
        width = max(520.0, float(configured_width or canvas.winfo_width()))
        height = max(560.0, float(canvas.winfo_height()))
        left, right = 76.0, width - 24.0
        beam_y = 92.0
        max_deflection = max(abs(sample.deflection_in) for sample in result.samples)
        deflection_scale = min(42.0 / max_deflection, 500.0) if max_deflection > 1e-8 else 1.0

        canvas.create_text(18, 20, anchor="w", text="BEAM MODEL", fill="#51645a",
                           font=(self.font_family, 9, "bold"))
        canvas.create_text(
            18, 40, anchor="w",
            text=f"{self.section_var.get()} · {model.span_ft:g} ft · "
                 f"{'Simply supported' if model.support == 'simple' else 'Cantilever'}",
            fill="#728078", font=(self.font_family, 9),
        )
        canvas.create_text(
            (left + right) / 2, 20, text="Beam curve is exaggerated; plot values are to scale.",
            fill="#728078", font=(self.font_family, 9),
        )

        def px(x_in: float) -> float:
            return left + (right - left) * x_in / model.length_in

        def beam_y_at(x_in: float) -> float:
            return beam_y - _interpolate(result.samples, x_in, "deflection_in") * deflection_scale

        if model.support == "simple":
            for support_x in (left, right):
                by = beam_y_at((support_x - left) / (right - left) * model.length_in)
                canvas.create_polygon(
                    support_x, by, support_x - 17, by + 23, support_x + 17, by + 23,
                    fill="#fffefa", outline="#52685d", width=2,
                )
                canvas.create_oval(support_x - 10, by + 24, support_x - 4, by + 30,
                                   fill="#fffefa", outline="#52685d")
                canvas.create_oval(support_x + 4, by + 24, support_x + 10, by + 30,
                                   fill="#fffefa", outline="#52685d")
                canvas.create_line(support_x - 27, by + 32, support_x + 27, by + 32,
                                   fill="#84948a")
        else:
            fixed_y = beam_y_at(0.0)
            canvas.create_line(left - 17, fixed_y - 29, left - 17, fixed_y + 31,
                               fill="#52685d", width=4)
            for offset in range(-25, 30, 12):
                canvas.create_line(left - 18, fixed_y + offset, left - 29,
                                   fixed_y + offset - 7, fill="#84948a")

        beam_points = [
            coordinate
            for sample in result.samples
            for coordinate in (px(sample.x_in), beam_y - sample.deflection_in * deflection_scale)
        ]
        canvas.create_line(*beam_points, fill="#334a40", width=7, smooth=True)

        for load in model.points:
            x = px(load.x_in)
            y = beam_y_at(load.x_in)
            start_y, end_y = (y + 35, y + 4) if load.force_kip > 0 else (y - 35, y - 4)
            canvas.create_line(x, start_y, x, end_y, fill="#c6404e", width=2, arrow=tk.LAST)
            canvas.create_text(
                x + 7, start_y + (12 if load.force_kip > 0 else -5), anchor="w",
                text=f"{abs(load.force_kip):.2f} kip", fill="#a23340",
                font=(self.font_family, 8, "bold"),
            )
        for load in result.effective_uniforms:
            start_x, end_x = px(load.start_in), px(load.end_in)
            direction = load.intensity_kip_per_in
            arrow_count = max(3, int((end_x - start_x) / 48) + 1)
            for index in range(arrow_count):
                x = start_x + (end_x - start_x) * index / (arrow_count - 1)
                x_in = (x - left) / (right - left) * model.length_in
                y = beam_y_at(x_in)
                start_y, end_y = (y + 31, y + 4) if direction > 0 else (y - 31, y - 4)
                canvas.create_line(x, start_y, x, end_y, fill="#c6404e", width=1.5, arrow=tk.LAST)
            cap_y = beam_y - 39 if direction < 0 else beam_y + 42
            canvas.create_line(start_x, cap_y, end_x, cap_y, fill="#c6404e", width=1)
            canvas.create_text(
                (start_x + end_x) / 2, cap_y - (8 if direction < 0 else -11),
                text=f"{abs(direction) * 12:.2f} kip/ft uniform",
                fill="#a23340", font=(self.font_family, 8, "bold"),
            )

        def draw_reaction(x: float, y: float, force: float, label: str) -> None:
            if abs(force) < 1e-8:
                return
            start_y, end_y = (y + 30, y + 4) if force > 0 else (y - 30, y - 4)
            canvas.create_line(x, start_y, x, end_y, fill="#277653", width=2, arrow=tk.LAST)
            canvas.create_text(
                x + 10, start_y + (10 if force > 0 else -5), anchor="w",
                text=f"{label} {force:+.2f} kip", fill="#216b4b",
                font=(self.font_family, 8, "bold"),
            )

        draw_reaction(left, beam_y_at(0), result.reaction_a_kip, "Rₐ")
        if model.support == "simple":
            draw_reaction(right, beam_y_at(model.length_in), result.reaction_b_kip, "Rᵦ")
        elif abs(result.reaction_moment_kip_in) > 1e-8:
            canvas.create_arc(
                left - 4, beam_y - 26, left + 27, beam_y + 5,
                start=35, extent=285, style="arc", outline="#277653", width=2,
            )
            canvas.create_text(
                left + 33, beam_y - 16,
                text=f"Mₐ {result.reaction_moment_kip_in / 12:+.2f} kip-ft",
                anchor="w", fill="#216b4b", font=(self.font_family, 8, "bold"),
            )

        chart_top = 178.0
        available_chart_height = max(90.0, (height - chart_top - 28.0) / 3.0)
        charts = (
            ("shear_kip", "SHEAR", "kip", "#7654ae", "#eee9f8"),
            ("moment_kip_in", "MOMENT", "kip-ft", "#d87522", "#fff0e2"),
            ("deflection_in", "DEFLECTED SHAPE", "in", "#277653", "#e5f1e9"),
        )
        for chart_index, (field, title, unit, color, fill) in enumerate(charts):
            top = chart_top + chart_index * available_chart_height
            bottom = top + available_chart_height - 13.0
            base = (top + bottom) / 2
            values = [
                getattr(sample, field) / 12.0 if field == "moment_kip_in"
                else getattr(sample, field)
                for sample in result.samples
            ]
            peak_index = max(range(len(values)), key=lambda index: abs(values[index]))
            peak_value = values[peak_index]
            max_abs = max(1e-9, *(abs(value) for value in values))
            plot_scale = (bottom - top) * 0.39 / max_abs
            coords = [
                coordinate
                for sample, value in zip(result.samples, values)
                for coordinate in (px(sample.x_in), base - value * plot_scale)
            ]
            fill_points = coords + [right, base, left, base]
            canvas.create_polygon(*fill_points, fill=fill, outline="")
            canvas.create_line(left, base, right, base, fill="#9ba89e")
            canvas.create_line(left, top + 5, right, top + 5,
                               fill="#e5eae3", dash=(3, 5))
            canvas.create_line(left, bottom - 5, right, bottom - 5,
                               fill="#e5eae3", dash=(3, 5))
            canvas.create_line(*coords, fill=color, width=2, smooth=True)
            peak_x = px(result.samples[peak_index].x_in)
            peak_y = base - peak_value * plot_scale
            canvas.create_oval(peak_x - 4, peak_y - 4, peak_x + 4, peak_y + 4,
                               fill=color, outline="#fffefa", width=2)
            canvas.create_text(
                17, top + 10, anchor="nw", text=f"{title}\n({unit})",
                fill="#51645a", font=(self.font_family, 8, "bold"),
            )
            canvas.create_text(
                min(right - 5, max(left + 5, peak_x)), peak_y - 10,
                text=f"{peak_value:+.2f} {unit}", fill=color,
                font=(self.font_family, 8, "bold"),
            )
        canvas.create_text(left, height - 12, anchor="w", text="0 ft",
                           fill="#728078", font=(self.font_family, 8))
        canvas.create_text(right, height - 12, anchor="e",
                           text=f"{model.span_ft:g} ft", fill="#728078",
                           font=(self.font_family, 8))
        canvas.create_text((left + right) / 2, height - 12,
                           text="Distance along beam", fill="#728078",
                           font=(self.font_family, 8))
        if self._crosshair_x is not None:
            crosshair_x = px(self._crosshair_x)
            canvas.create_line(
                crosshair_x, chart_top, crosshair_x,
                chart_top + 3 * available_chart_height - 13,
                fill="#263b35", dash=(5, 4), width=1,
            )

    def _export(self) -> None:
        if self.latest_model is None or self.latest_result is None:
            messagebox.showerror("Cannot export", "Correct the input errors before exporting.")
            return
        excel = self.export_format_var.get().startswith("Excel")
        extension = ".xlsx" if excel else ".csv"
        filetypes = (
            [("Excel workbook", "*.xlsx")] if excel else [("CSV file", "*.csv")]
        )
        output = filedialog.asksaveasfilename(
            title="Export Beam Designer results",
            defaultextension=extension,
            filetypes=filetypes,
        )
        if not output:
            return
        try:
            rows = export_rows(self.latest_model, self.latest_result)
            if excel:
                write_xlsx(Path(output), rows)
            else:
                with open(output, "w", newline="", encoding="utf-8") as csv_file:
                    csv.writer(csv_file).writerows(rows)
        except (OSError, csv.Error, ValueError, zipfile.BadZipFile) as exc:
            messagebox.showerror("Export failed", f"Could not export the results:\n{exc}")
            return
        messagebox.showinfo("Export complete", f"Results exported to:\n{output}")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    root = tk.Tk()
    BeamDesignerApp(root).run()


if __name__ == "__main__":
    main()