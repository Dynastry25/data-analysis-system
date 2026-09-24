"""Report export: real XLSX workbooks and PDF documents.

Both writers consume the *saved* JSON results (analysis_runs / charts) so an
exported report is a reproducible snapshot of the chosen analyses and charts.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import pandas as pd

from app.config import REPORTS_DIR
from app.services.chart_service import describe_chart

# Rows shown in the PDF (the XLSX keeps everything).
PDF_TABLE_ROWS = 25


# --------------------------------------------------------------- flattening


def _records_to_frame(records: Sequence[Dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(list(records))
    if not frame.empty:
        frame = frame.fillna("")
    return frame


def _kv_frame(rows: Sequence[Tuple[str, Any]]) -> pd.DataFrame:
    """Key/value table; nested values are rendered as text."""
    return pd.DataFrame(
        [
            {
                "metric": metric,
                "value": value if not isinstance(value, (dict, list)) else str(value),
            }
            for metric, value in rows
            if value is not None and value != ""
        ]
    )


def _table_payload_to_frame(payload: Any) -> pd.DataFrame:
    """Normalise one ``tables`` entry of a standard result into a DataFrame."""
    if isinstance(payload, list):
        return _records_to_frame(payload)
    if isinstance(payload, dict):
        list_columns = {
            key: value for key, value in payload.items() if isinstance(value, list)
        }
        if list_columns:
            return pd.DataFrame(list_columns).fillna("")
    return pd.DataFrame()


def flatten_analysis(
    analysis_type: str, result: Dict[str, Any]
) -> List[Tuple[str, pd.DataFrame]]:
    """Turn one stored standard result into named tables ``(title, frame)``.

    The unified statistics engine (MVP-19) returns the same structure for
    every analysis — status / estimate / test / confidence_interval /
    effect_size / diagnostics / tables — so the export is engine-agnostic
    and automatically supports every analysis type the engine adds.
    """
    tables: List[Tuple[str, pd.DataFrame]] = []

    summary_rows: List[Tuple[str, Any]] = [
        ("Status", result.get("status")),
        ("Sample size", result.get("sample_size")),
    ]
    summary_rows.extend(
        (f"Estimate: {key}", value)
        for key, value in (result.get("estimate") or {}).items()
    )
    summary_rows.extend(
        (f"Test: {key}", value) for key, value in (result.get("test") or {}).items()
    )
    summary_rows.extend(
        (f"Confidence interval: {key}", value)
        for key, value in (result.get("confidence_interval") or {}).items()
    )
    effect = result.get("effect_size") or {}
    if effect:
        summary_rows.append(
            (
                "Effect size",
                f"{effect.get('name')}: {effect.get('value')} "
                f"({effect.get('interpretation')})",
            )
        )
    warnings = [str(warning) for warning in (result.get("warnings") or [])]
    if warnings:
        summary_rows.append(("Warnings", "; ".join(warnings)))
    tables.append(("Summary", _kv_frame(summary_rows)))

    for table_name, payload in (result.get("tables") or {}).items():
        tables.append(
            (str(table_name).replace("_", " ").title(), _table_payload_to_frame(payload))
        )

    diagnostics = result.get("diagnostics") or {}
    if diagnostics:
        tables.append(("Diagnostics", _kv_frame(list(diagnostics.items()))))

    if not tables:
        tables = [(analysis_type, _records_to_frame([result]))]
    return [(title, frame) for title, frame in tables if not frame.empty]


def chart_to_frame(chart: Dict[str, Any]) -> pd.DataFrame:
    """Wide table (x + one column per series) for one saved chart."""
    data = chart.get("chart_data") or {}
    series = data.get("series") or []
    if not series:
        return pd.DataFrame()
    first = series[0]
    frame = pd.DataFrame({data.get("x_label", "x"): list(first.get("x", []))})
    for item in series:
        name = item.get("name") or chart.get("chart_type", "series")
        values = item.get("y") if item.get("y") is not None else item.get("x")
        if values is not None and len(values) == frame.shape[0]:
            frame[str(name)] = list(values)
    return frame


def _dataset_summary_frame(dataset: Dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"field": "Dataset", "value": dataset.get("original_filename")},
            {"field": "File type", "value": dataset.get("file_type")},
            {"field": "Rows", "value": dataset.get("row_count")},
            {"field": "Columns", "value": dataset.get("column_count")},
            {"field": "Status", "value": dataset.get("status")},
            {"field": "Uploaded at", "value": dataset.get("uploaded_at")},
            {
                "field": "Report generated",
                "value": datetime.now().isoformat(timespec="seconds"),
            },
        ]
    )


# ------------------------------------------------------------------- XLSX


def build_xlsx(
    path: Path,
    dataset: Dict[str, Any],
    analyses: Sequence[Dict[str, Any]],
    charts: Sequence[Dict[str, Any]],
) -> Path:
    """Write an Excel workbook with a sheet per analysis and per chart."""
    path.parent.mkdir(parents=True, exist_ok=True)
    contents: List[Dict[str, Any]] = []
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _dataset_summary_frame(dataset).to_excel(
            writer, sheet_name="Summary", index=False
        )

        for index, analysis in enumerate(analyses, start=1):
            base_name = f"A{index}_{analysis['analysis_type']}"[:24]
            contents.append(
                {
                    "item": f"Analysis {index}",
                    "type": analysis["analysis_type"],
                    "sheet": base_name,
                    "created_at": analysis.get("created_at"),
                }
            )
            tables = flatten_analysis(
                analysis["analysis_type"], analysis["result"] or {}
            )
            if not tables:
                pd.DataFrame({"info": ["No table content"]}).to_excel(
                    writer, sheet_name=base_name, index=False
                )
            for offset, (table_title, frame) in enumerate(tables, start=1):
                sheet_frame = frame.copy()
                sheet_frame.insert(0, f"section: {table_title}", "")
                sheet_frame.to_excel(
                    writer, sheet_name=f"{base_name}_{offset}"[:31], index=False
                )

        for index, chart in enumerate(charts, start=1):
            sheet_name = f"C{index}_{chart['chart_type']}"[:31]
            contents.append(
                {
                    "item": f"Chart {index}",
                    "type": chart["chart_type"],
                    "sheet": sheet_name,
                    "created_at": chart.get("created_at"),
                }
            )
            frame = chart_to_frame(chart)
            if frame.empty:
                frame = pd.DataFrame({"info": ["No chart data available"]})
            frame.to_excel(writer, sheet_name=sheet_name, index=False)

        pd.DataFrame(contents).to_excel(writer, sheet_name="Contents", index=False)
    return path


# -------------------------------------------------------------------- PDF


def build_pdf(
    path: Path,
    dataset: Dict[str, Any],
    analyses: Sequence[Dict[str, Any]],
    charts: Sequence[Dict[str, Any]],
) -> Path:
    """Write a formatted PDF report with the selected stats and chart data."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        textColor=colors.HexColor("#1E3A8A"),
        fontSize=20,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#111827"),
        fontSize=13,
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ReportBody", parent=styles["BodyText"], fontSize=9, leading=12
    )

    def as_table(frame: pd.DataFrame, max_rows: int = PDF_TABLE_ROWS) -> Table:
        trimmed = frame.head(max_rows)
        data = [list(trimmed.columns)] + [
            [str(value)[:60] for value in row] for row in trimmed.itertuples(index=False)
        ]
        table = Table(data, repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DBEAFE")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F9FAFB")],
                    ),
                ]
            )
        )
        return table

    story: List[Any] = [
        Paragraph("Data Analysis Report", title_style),
        Paragraph(
            f"Generated on {datetime.now().strftime('%d %b %Y %H:%M')}", body_style
        ),
        Spacer(1, 0.4 * cm),
        Paragraph("Dataset summary", heading_style),
        as_table(_dataset_summary_frame(dataset)),
    ]

    if analyses:
        story.append(Paragraph("Statistical analysis", heading_style))
        for index, analysis in enumerate(analyses, start=1):
            label = analysis["analysis_type"].replace("_", " ").title()
            story.append(
                Paragraph(
                    f"{index}. {label} "
                    f"<font size=8 color='#4B5563'>(saved {analysis.get('created_at') or ''})</font>",
                    heading_style,
                )
            )
            for table_title, frame in flatten_analysis(
                analysis["analysis_type"], analysis["result"] or {}
            ):
                story.append(Paragraph(table_title, body_style))
                if frame.shape[0] > PDF_TABLE_ROWS:
                    story.append(
                        Paragraph(
                            f"Showing the first {PDF_TABLE_ROWS} of {frame.shape[0]} rows "
                            "(full data is in the Excel export).",
                            body_style,
                        )
                    )
                story.append(as_table(frame))
                story.append(Spacer(1, 0.25 * cm))

    if charts:
        story.append(Paragraph("Charts", heading_style))
        for index, chart in enumerate(charts, start=1):
            description = describe_chart(chart["chart_type"], chart.get("config") or {})
            story.append(Paragraph(f"{index}. {description}", heading_style))
            frame = chart_to_frame(chart)
            if frame.empty:
                story.append(Paragraph("No chart data available.", body_style))
            else:
                story.append(as_table(frame))

    if not analyses and not charts:
        story.append(
            Paragraph(
                "No analysis results or charts were selected for this report.",
                body_style,
            )
        )

    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        title="Data Analysis Report",
        author="Data Analysis Platform",
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
    )
    document.build(story)
    return path


def build_report(
    report_id: int,
    file_format: str,
    dataset: Dict[str, Any],
    analyses: Sequence[Dict[str, Any]],
    charts: Sequence[Dict[str, Any]],
) -> Path:
    """Create the report file on disk and return its path."""
    base_name = str(dataset.get("original_filename") or "dataset").rsplit(".", 1)[0]
    safe_name = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in base_name
    )[:40]
    path = REPORTS_DIR / f"report_{report_id}_{safe_name}.{file_format}"
    if file_format == "xlsx":
        return build_xlsx(path, dataset, analyses, charts)
    if file_format == "pdf":
        return build_pdf(path, dataset, analyses, charts)
    raise ValueError("format must be 'pdf' or 'xlsx'")


