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
            {"field": "Dataset version", "value": dataset.get("current_version")},
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
    if file_format == "docx":
        return build_docx(path, dataset, analyses, charts)
    if file_format == "pptx":
        return build_pptx(path, dataset, analyses, charts)
    if file_format == "html":
        return build_html(path, dataset, analyses, charts)
    raise ValueError(f"format must be one of 'pdf', 'xlsx', 'docx', 'pptx', or 'html'; got '{file_format}'")


# -------------------------------------------------------------------- DOCX


def build_docx(
    path: Path,
    dataset: Dict[str, Any],
    analyses: Sequence[Dict[str, Any]],
    charts: Sequence[Dict[str, Any]],
) -> Path:
    """Write a Microsoft Word document (.docx) with the report content."""
    from docx import Document
    from docx.shared import Inches
    
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    
    # Title
    doc.add_heading(f"Data Analysis Report", 0)
    doc.add_paragraph(f"Generated on {datetime.now().strftime('%d %b %Y %H:%M')}", style="Intense Quote")
    
    # Dataset summary
    doc.add_heading("Dataset Summary", level=1)
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    
    def add_row(table, field, value):
        row = table.add_row().cells
        row[0].text = field
        row[1].text = str(value) if value is not None else ""
    
    add_row(table, "Dataset", dataset.get("original_filename"))
    add_row(table, "File type", dataset.get("file_type"))
    add_row(table, "Dataset version", dataset.get("current_version"))
    add_row(table, "Rows", dataset.get("row_count"))
    add_row(table, "Columns", dataset.get("column_count"))
    add_row(table, "Status", dataset.get("status"))
    add_row(table, "Uploaded at", dataset.get("uploaded_at"))
    add_row(table, "Report generated", datetime.now().isoformat(timespec="seconds"))
    
    # Analyses
    if analyses:
        doc.add_heading("Statistical Analysis", level=1)
        for index, analysis in enumerate(analyses, start=1):
            label = analysis["analysis_type"].replace("_", " ").title()
            doc.add_heading(f"{index}. {label}", level=2)
            doc.add_paragraph(f"(Saved {analysis.get('created_at') or ''})", style="Intense Quote")
            
            for table_title, frame in flatten_analysis(analysis["analysis_type"], analysis["result"] or {}):
                if frame.empty:
                    continue
                doc.add_paragraph(table_title, style="Heading 3")
                # Add table as Word table
                if frame.shape[0] <= PDF_TABLE_ROWS:
                    table = doc.add_table(rows=1, cols=len(frame.columns))
                    table.style = "Table Grid"
                    header_row = table.rows[0].cells
                    for i, col in enumerate(frame.columns):
                        header_row[i].text = col
                    
                    for row_index, row in enumerate(frame.itertuples(index=False), start=1):
                        if row_index > PDF_TABLE_ROWS:
                            break
                        table.add_row()
                        for i, value in enumerate(row):
                            table.cell(row_index, i).text = str(value)[:60]
                else:
                    doc.add_paragraph(f"Showing first {PDF_TABLE_ROWS} of {frame.shape[0]} rows (full data in Excel export).")
                    doc.add_table_from_dataframe(frame.head(PDF_TABLE_ROWS))
    
    # Charts
    if charts:
        doc.add_heading("Charts", level=1)
        for index, chart in enumerate(charts, start=1):
            description = describe_chart(chart["chart_type"], chart.get("config") or {})
            doc.add_heading(f"{index}. {description}", level=2)
            frame = chart_to_frame(chart)
            if frame.empty:
                doc.add_paragraph("No chart data available.")
            else:
                table = doc.add_table(rows=1, cols=len(frame.columns))
                table.style = "Table Grid"
                header_row = table.rows[0].cells
                for i, col in enumerate(frame.columns):
                    header_row[i].text = col
                
                for row_index, row in enumerate(frame.itertuples(index=False), start=1):
                    table.add_row()
                    for i, value in enumerate(row):
                        table.cell(row_index, i).text = str(value)[:60]
    
    if not analyses and not charts:
        doc.add_paragraph("No analysis results or charts were selected for this report.", style="Intense Quote")
    
    doc.save(str(path))
    return path


# -------------------------------------------------------------------- PPTX


def build_pptx(
    path: Path,
    dataset: Dict[str, Any],
    analyses: Sequence[Dict[str, Any]],
    charts: Sequence[Dict[str, Any]],
) -> Path:
    """Write a Microsoft PowerPoint presentation (.pptx) with the report content."""
    from pptx import Presentation
    from pptx.enum.text import MSO_AUTO_SIZE
    
    path.parent.mkdir(parents=True, exist_ok=True)
    prs = Presentation()
    
    # Title slide
    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    slide.shapes.title.text = "Data Analysis Report"
    slide.placeholders[1].text = f"Generated on {datetime.now().strftime('%d %b %Y %H:%M')}"
    
    # Dataset summary slide
    slide_layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = "Dataset Summary"
    
    content = slide.shapes.placeholders[1]
    tf = content.text_frame
    tf.text = ""
    p = tf.add_paragraph()
    p.text = f"Dataset: {dataset.get('original_filename')}"
    p = tf.add_paragraph()
    p.text = f"Type: {dataset.get('file_type')}"
    p = tf.add_paragraph()
    p.text = f"Version: v{dataset.get('current_version')}"
    p = tf.add_paragraph()
    p.text = f"Rows: {dataset.get('row_count')}"
    p = tf.add_paragraph()
    p.text = f"Columns: {dataset.get('column_count')}"
    p = tf.add_paragraph()
    p.text = f"Status: {dataset.get('status')}"
    
    # Analyses slides
    if analyses:
        slide_layout = prs.slide_layouts[2]
        for index, analysis in enumerate(analyses, start=1):
            slide = prs.slides.add_slide(slide_layout)
            label = analysis["analysis_type"].replace("_", " ").title()
            slide.shapes.title.text = f"{index}. {label}"
            slide.placeholders[1].text = f"(Saved {analysis.get('created_at') or ''})"
            
            content = slide.shapes.placeholders[1].text_frame
            content.text = ""
            for table_title, frame in flatten_analysis(analysis["analysis_type"], analysis["result"] or {}):
                if frame.empty:
                    continue
                p = content.add_paragraph(table_title)
                p.font.bold = True
                p = content.add_paragraph()
                p.text = frame.to_string()
    
    # Charts slides
    if charts:
        slide_layout = prs.slide_layouts[3]
        for index, chart in enumerate(charts, start=1):
            slide = prs.slides.add_slide(slide_layout)
            description = describe_chart(chart["chart_type"], chart.get("config") or {})
            slide.shapes.title.text = f"{index}. {description}"
            
            frame = chart_to_frame(chart)
            if not frame.empty:
                content = slide.shapes.placeholders[1].text_frame
                content.text = frame.to_string()
    
    if not analyses and not charts:
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "No Data"
        slide.placeholders[1].text = "No analysis results or charts were selected for this report."
    
    prs.save(str(path))
    return path


# -------------------------------------------------------------------- HTML


def build_html(
    path: Path,
    dataset: Dict[str, Any],
    analyses: Sequence[Dict[str, Any]],
    charts: Sequence[Dict[str, Any]],
) -> Path:
    """Write an HTML report (.html) with the report content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Data Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        h1 {{ color: #1E3A8A; border-bottom: 2px solid #DBEAFE; padding-bottom: 10px; }}
        h2 {{ color: #111827; margin-top: 30px; }}
        h3 {{ color: #4B5563; }}
        .summary {{ background-color: #F9FAFB; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
        th, td {{ border: 1px solid #E5E7EB; padding: 8px; text-align: left; }}
        th {{ background-color: #DBEAFE; color: #1E3A8A; font-weight: bold; }}
        tr:nth-child(even) {{ background-color: #F9FAFB; }}
        .note {{ font-style: italic; color: #6B7280; font-size: 0.9em; }}
    </style>
</head>
<body>
    <h1>Data Analysis Report</h1>
    <p class="note">Generated on {datetime.now().strftime('%d %b %Y %H:%M')}</p>
    
    <div class="summary">
        <h2>Dataset Summary</h2>
        <table>
            <tr><th>Field</th><th>Value</th></tr>
            <tr><td>Dataset</td><td>{dataset.get('original_filename', '')}</td></tr>
            <tr><td>File type</td><td>{dataset.get('file_type', '')}</td></tr>
            <tr><td>Dataset version</td><td>v{dataset.get('current_version', '')}</td></tr>
            <tr><td>Rows</td><td>{dataset.get('row_count', '')}</td></tr>
            <tr><td>Columns</td><td>{dataset.get('column_count', '')}</td></tr>
            <tr><td>Status</td><td>{dataset.get('status', '')}</td></tr>
            <tr><td>Uploaded at</td><td>{dataset.get('uploaded_at', '')}</td></tr>
            <tr><td>Report generated</td><td>{datetime.now().isoformat(timespec='seconds')}</td></tr>
        </table>
    </div>
"""
    
    if analyses:
        html_content += "<h2>Statistical Analysis</h2>\n"
        for index, analysis in enumerate(analyses, start=1):
            label = analysis["analysis_type"].replace("_", " ").title()
            html_content += f"<h3>{index}. {label}</h3>\n"
            html_content += f"<p class='note'>(Saved {analysis.get('created_at') or ''})</p>\n"
            
            for table_title, frame in flatten_analysis(analysis["analysis_type"], analysis["result"] or {}):
                if frame.empty:
                    continue
                html_content += f"<h4>{table_title}</h4>\n"
                html_content += "<table>\n"
                html_content += f"<tr><th>{'</th><th>'.join(frame.columns)}</th></tr>\n"
                for row in frame.itertuples(index=False):
                    html_content += "<tr>"
                    for value in row:
                        html_content += f"<td>{str(value)[:60]}</td>"
                    html_content += "</tr>\n"
                html_content += "</table>\n"
                if frame.shape[0] > PDF_TABLE_ROWS:
                    html_content += f"<p>Showing first {PDF_TABLE_ROWS} of {frame.shape[0]} rows (full data in the Excel export).</p>\n"
    
    if charts:
        html_content += "<h2>Charts</h2>\n"
        for index, chart in enumerate(charts, start=1):
            description = describe_chart(chart["chart_type"], chart.get("config") or {})
            html_content += f"<h3>{index}. {description}</h3>\n"
            
            frame = chart_to_frame(chart)
            if not frame.empty:
                html_content += "<table>\n"
                html_content += f"<tr><th>{'</th><th>'.join(frame.columns)}</th></tr>\n"
                for row in frame.itertuples(index=False):
                    html_content += "<tr>"
                    for value in row:
                        html_content += f"<td>{str(value)[:60]}</td>"
                    html_content += "</tr>\n"
                html_content += "</table>\n"
    
    if not analyses and not charts:
        html_content += "<p class='note'>No analysis results or charts were selected for this report.</p>\n"
    
    html_content += """
</body>
</html>
"""
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return path


