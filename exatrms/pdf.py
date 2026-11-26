"""PDF generation with ReportLab (digital marksheets and result reports)."""

from __future__ import annotations

from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .utils import round2, to_float

NAVY = colors.HexColor("#0f172a")
ACCENT = colors.HexColor("#4f46e5")
LIGHT = colors.HexColor("#eef2ff")
MUTED = colors.HexColor("#64748b")
GREEN = colors.HexColor("#0f9f6e")
RED = colors.HexColor("#dc2626")


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ExamTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "ExamSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#c7d2fe"),
            alignment=TA_CENTER,
        ),
        "normal": ParagraphStyle(
            "ExamNormal", parent=base["Normal"], fontName="Helvetica", fontSize=9, leading=12
        ),
        "small": ParagraphStyle(
            "ExamSmall", parent=base["Normal"], fontName="Helvetica", fontSize=7.6, leading=10
        ),
        "label": ParagraphStyle(
            "ExamLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=MUTED,
        ),
        "value": ParagraphStyle(
            "ExamValue", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=12
        ),
        "note": ParagraphStyle(
            "ExamNote", parent=base["Normal"], fontName="Helvetica-Oblique", fontSize=7.5, leading=10, textColor=MUTED
        ),
        "cell": ParagraphStyle(
            "ExamCell", parent=base["Normal"], fontName="Helvetica", fontSize=7.6, leading=9.5
        ),
        "cell_center": ParagraphStyle(
            "ExamCellCenter", parent=base["Normal"], fontName="Helvetica", fontSize=7.6, leading=9.5, alignment=TA_CENTER
        ),
    }


def _page_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
    canvas.line(15 * mm, 14 * mm, A4[0] - 15 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(15 * mm, 9 * mm, "ExamTrack · Examination & Student Result Management System")
    canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _document(buffer: BytesIO, title: str):
    return SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=20 * mm,
        title=title,
        author="ExamTrack",
        subject=title,
    )


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text if text is not None else "-")), style)


def _header(styles: dict, title: str, subtitle: str) -> Table:
    data = [[_p(title, styles["title"])], [_p(subtitle, styles["subtitle"])]]
    table = Table(data, colWidths=[180 * mm], rowHeights=[13 * mm, 8 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _info_table(rows, styles: dict) -> Table:
    data = []
    for left_label, left_value, right_label, right_value in rows:
        data.append(
            [
                _p(left_label, styles["label"]),
                _p(left_value, styles["value"]),
                _p(right_label, styles["label"]),
                _p(right_value, styles["value"]),
            ]
        )
    table = Table(data, colWidths=[28 * mm, 62 * mm, 28 * mm, 62 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def generate_marksheet_pdf(student, examination, result, marks) -> bytes:
    """Build a digital marksheet for one student and one examination."""
    styles = _styles()
    buffer = BytesIO()
    doc = _document(buffer, f"Marksheet - {student.full_name} - {examination.name}")

    story = [
        _header(
            styles,
            "DIGITAL MARKSHEET",
            f"{examination.name} · {examination.academic_year} · {examination.course.name}",
        ),
        Spacer(1, 6 * mm),
        _info_table(
            [
                ("Student Name", student.full_name, "Student Code", student.student_code),
                ("Course", examination.course.name, "Semester", f"Semester {examination.semester.number}"),
                ("Examination", f"{examination.name} ({examination.exam_type})", "Maximum Marks", to_float(examination.max_marks)),
                ("Admission Date", student.admission_date, "Published On", result.published_at.strftime("%d %b %Y") if result.published_at else "Not published"),
            ],
            styles,
        ),
        Spacer(1, 6 * mm),
    ]

    ordered_marks = sorted(marks, key=lambda m: m.subject.name)
    table_data = [
        [
            "Subject",
            "Credits",
            "Max",
            "Obtained",
            "%",
            "Grade",
            "Points",
            "Status",
        ]
    ]
    for mark in ordered_marks:
        table_data.append(
            [
                _p(f"{mark.subject.code} - {mark.subject.name}", styles["cell"]),
                _p(mark.subject.credits, styles["cell_center"]),
                _p(to_float(mark.max_marks), styles["cell_center"]),
                _p(to_float(mark.marks_obtained), styles["cell_center"]),
                _p(round2(mark.percentage), styles["cell_center"]),
                _p(mark.grade, styles["cell_center"]),
                _p(to_float(mark.grade_points), styles["cell_center"]),
                _p(mark.status.upper(), styles["cell_center"]),
            ]
        )

    marks_table = Table(
        table_data,
        colWidths=[52 * mm, 16 * mm, 16 * mm, 19 * mm, 15 * mm, 15 * mm, 16 * mm, 19 * mm],
        repeatRows=1,
    )
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.8),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for index, mark in enumerate(ordered_marks, start=1):
        if mark.status == "fail":
            style.append(("TEXTCOLOR", (7, index), (7, index), RED))
        else:
            style.append(("TEXTCOLOR", (7, index), (7, index), GREEN))
    marks_table.setStyle(TableStyle(style))
    story.extend([marks_table, Spacer(1, 5 * mm)])

    summary = Table(
        [
            [
                "Total Marks",
                f"{round2(result.obtained_marks)} / {round2(result.total_marks)}",
                "Percentage",
                f"{round2(result.percentage)}%",
            ],
            [
                "Grade",
                result.grade,
                "GPA (10-point)",
                f"{to_float(result.gpa):.2f}",
            ],
            [
                "Result",
                result.status.upper(),
                "Rank",
                result.rank if result.rank else "-",
            ],
        ],
        colWidths=[32 * mm, 58 * mm, 32 * mm, 58 * mm],
    )
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.6, ACCENT),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c7d2fe")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), NAVY),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([summary, Spacer(1, 10 * mm)])

    signature = Table(
        [
            [
                _p("Prepared by Examination Cell", styles["small"]),
                _p("Authorised Signature", styles["small"]),
            ],
            [
                _p("ExamTrack Auto-Generated Record", styles["small"]),
                _p("_________________________", styles["small"]),
            ],
        ],
        colWidths=[90 * mm, 90 * mm],
    )
    signature.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.extend(
        [
            signature,
            Spacer(1, 6 * mm),
            _p(
                "This marksheet is computer-generated from the ExamTrack database and is valid without a manual signature unless stated otherwise by the institution.",
                styles["note"],
            ),
        ]
    )

    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buffer.getvalue()


def generate_exam_report_pdf(examination, results) -> bytes:
    """Build a consolidated result report for one examination."""
    styles = _styles()
    buffer = BytesIO()
    doc = _document(buffer, f"Result Report - {examination.name}")

    story = [
        _header(
            styles,
            "EXAMINATION RESULT REPORT",
            f"{examination.name} · {examination.academic_year} · {examination.course.name} · Semester {examination.semester.number}",
        ),
        Spacer(1, 6 * mm),
    ]

    passed = sum(1 for r in results if r.status == "pass")
    summary = Table(
        [
            [
                "Students Appeared",
                len(results),
                "Passed",
                passed,
                "Failed",
                len(results) - passed,
                "Pass %",
                round((passed / len(results) * 100), 2) if results else 0,
            ]
        ],
        colWidths=[30 * mm, 15 * mm, 20 * mm, 15 * mm, 20 * mm, 15 * mm, 20 * mm, 20 * mm],
    )
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.6, ACCENT),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c7d2fe")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([summary, Spacer(1, 5 * mm)])

    data = [
        [
            "Code",
            "Student Name",
            "Obtained",
            "Total",
            "%",
            "Grade",
            "GPA",
            "Status",
            "Rank",
        ]
    ]
    ordered = sorted(
        results,
        key=lambda r: (-(to_float(r.percentage)), r.rank or 9999, r.student.full_name),
    )
    for result in ordered:
        data.append(
            [
                _p(result.student.student_code, styles["cell"]),
                _p(result.student.full_name, styles["cell"]),
                _p(round2(result.obtained_marks), styles["cell_center"]),
                _p(round2(result.total_marks), styles["cell_center"]),
                _p(round2(result.percentage), styles["cell_center"]),
                _p(result.grade, styles["cell_center"]),
                _p(to_float(result.gpa), styles["cell_center"]),
                _p(result.status.upper(), styles["cell_center"]),
                _p(result.rank or "-", styles["cell_center"]),
            ]
        )

    table = Table(
        data,
        colWidths=[24 * mm, 44 * mm, 20 * mm, 18 * mm, 15 * mm, 15 * mm, 14 * mm, 18 * mm, 12 * mm],
        repeatRows=1,
    )
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    for index, result in enumerate(ordered, start=1):
        if result.status == "fail":
            style.append(("TEXTCOLOR", (7, index), (7, index), RED))
        else:
            style.append(("TEXTCOLOR", (7, index), (7, index), GREEN))
    table.setStyle(TableStyle(style))
    story.append(table)

    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buffer.getvalue()
