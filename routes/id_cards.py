# ─────────────────────────────────────────────────────────────────────────────
#  ID Card Generation Module
#  - Single / multiple / class / section wise generation
#  - Admin-configurable card size (mm) — cards auto-arranged multiple per page
#  - Design replicates the classic school ID card (yellow/blue header, photo,
#    bold label rows) like R.S. Memorial sample
# ─────────────────────────────────────────────────────────────────────────────
import io
import os
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from reportlab.lib.pagesizes import A4, A3, letter, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.colors import HexColor, white

from models.institution import School, AcademicYear, ClassRoom, Section, User
from models.student import Student
from utils.auth import get_current_user, resolve_school_access, resolve_branch_scope
from utils.helpers import success_response
from config import settings

router = APIRouter(prefix="/id-cards", tags=["ID Cards"])

# ── Colors (sampled from the reference card) ─────────────────────────────────
C_YELLOW = HexColor("#f5c518")
C_BLUE = HexColor("#1e40af")
C_SKY = HexColor("#38bdf8")
C_RED = HexColor("#dc2626")
C_PHOTO_BG = HexColor("#bfdbfe")
C_TEXT = HexColor("#111827")
C_BORDER = HexColor("#9ca3af")

PAGE_SIZES = {"A4": A4, "A3": A3, "LETTER": letter}


class IDCardRequest(BaseModel):
    school_id: str
    academic_year_id: Optional[str] = None
    # Selection — any one of these:
    student_ids: List[str] = []           # explicit students (single or multiple)
    classroom_id: Optional[str] = None    # whole class
    section_id: Optional[str] = None      # (optionally) specific section
    # Card size — admin configurable (in mm)
    card_width_mm: float = 54
    card_height_mm: float = 86
    # Page layout
    page_size: str = "A4"                 # A4 | A3 | LETTER
    orientation: str = "portrait"         # portrait | landscape
    margin_mm: float = 8
    gap_mm: float = 4
    show_cut_lines: bool = True
    session_label: Optional[str] = None   # e.g. "Session 2025-26"


# ── Text helpers ──────────────────────────────────────────────────────────────
def _wrap(text: str, font: str, size: float, max_w: float) -> List[str]:
    """Greedy word-wrap that also hard-breaks overlong words."""
    lines: List[str] = []
    cur = ""
    for word in (text or "").split():
        trial = (cur + " " + word).strip()
        if stringWidth(trial, font, size) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        while stringWidth(word, font, size) > max_w and len(word) > 1:
            k = len(word)
            while k > 1 and stringWidth(word[:k], font, size) > max_w:
                k -= 1
            lines.append(word[:k])
            word = word[k:]
        cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit_font(text: str, font: str, size: float, max_w: float, min_size: float = 4.0) -> float:
    """Shrink font size until text fits in max_w."""
    while size > min_size and stringWidth(text, font, size) > max_w:
        size -= 0.25
    return size


def _upload_path(rel: Optional[str]) -> Optional[str]:
    """Resolve a stored file reference (relative path or /uploads/... URL) to a real file path."""
    if not rel:
        return None
    if rel.startswith(("http://", "https://")):
        return None  # remote URLs not supported for embedding
    r = rel
    if r.startswith("/uploads/"):
        r = r[len("/uploads/"):]
    r = r.lstrip("/")
    p = os.path.join(settings.UPLOAD_DIR, r)
    return p if os.path.exists(p) else None


# ── Card drawing ──────────────────────────────────────────────────────────────
def draw_id_card(c: canvas.Canvas, x: float, y: float, w: float, h: float,
                 school: dict, student: dict, show_cut_lines: bool = True,
                 session_label: Optional[str] = None):
    """Draw one ID card with bottom-left corner at (x, y), size w × h points."""
    s = min(w / 153.0, h / 244.0)   # scale factor vs 54×86mm reference card
    r = 6 * s                        # corner radius

    c.saveState()

    # Card background + cut line
    c.setFillColor(white)
    c.setStrokeColor(C_BORDER if show_cut_lines else white)
    c.setLineWidth(0.6)
    c.roundRect(x, y, w, h, r, stroke=1, fill=1)

    # Clip everything inside the card
    p = c.beginPath()
    p.rect(x + 0.8, y + 0.8, w - 1.6, h - 1.6)
    c.clipPath(p, stroke=0, fill=0)

    # ── Header: yellow band ──────────────────────────────────────────────────
    head_h = 0.165 * h
    head_y = y + h - head_h
    c.setFillColor(C_YELLOW)
    c.rect(x, head_y, w, head_h, stroke=0, fill=1)

    # white swoosh at the bottom of the yellow band
    c.setFillColor(white)
    pth = c.beginPath()
    pth.moveTo(x, head_y)
    pth.curveTo(x + w * 0.3, head_y + head_h * 0.45,
                x + w * 0.6, head_y - head_h * 0.15,
                x + w, head_y + head_h * 0.25)
    pth.lineTo(x + w, head_y - 2)
    pth.lineTo(x, head_y - 2)
    pth.close()
    c.drawPath(pth, stroke=0, fill=1)
    # blue wave stroke
    c.setStrokeColor(C_SKY)
    c.setLineWidth(1.6 * s)
    pth = c.beginPath()
    pth.moveTo(x, head_y + head_h * 0.08)
    pth.curveTo(x + w * 0.3, head_y + head_h * 0.5,
                x + w * 0.6, head_y - head_h * 0.1,
                x + w, head_y + head_h * 0.3)
    c.drawPath(pth, stroke=1, fill=0)

    # Logo (left, inside header)
    logo_d = head_h * 0.78
    logo_cx = x + 6 * s + logo_d / 2
    logo_cy = y + h - 4 * s - logo_d / 2
    logo_path = school.get("logo_path")
    if logo_path:
        try:
            c.saveState()
            cp = c.beginPath()
            cp.circle(logo_cx, logo_cy, logo_d / 2)
            c.clipPath(cp, stroke=0, fill=0)
            c.drawImage(ImageReader(logo_path), logo_cx - logo_d / 2, logo_cy - logo_d / 2,
                        logo_d, logo_d, preserveAspectRatio=True, anchor='c', mask='auto')
            c.restoreState()
        except Exception:
            logo_path = None
    if not logo_path:
        c.setFillColor(white)
        c.setStrokeColor(C_BLUE)
        c.setLineWidth(0.8)
        c.circle(logo_cx, logo_cy, logo_d / 2, stroke=1, fill=1)
        initials = "".join(wd[0] for wd in (school.get("name") or "S").split()[:3]).upper()
        fs = _fit_font(initials, "Helvetica-Bold", logo_d * 0.38, logo_d * 0.8)
        c.setFillColor(C_BLUE)
        c.setFont("Helvetica-Bold", fs)
        c.drawCentredString(logo_cx, logo_cy - fs * 0.35, initials)

    # School name (blue, bold) — centered in the space right of the logo
    name_x0 = x + 10 * s + logo_d
    name_w = w - (name_x0 - x) - 4 * s
    name = (school.get("name") or "SCHOOL NAME").upper()
    fs = 13 * s
    lines = _wrap(name, "Helvetica-Bold", fs, name_w)
    while len(lines) > 2 and fs > 6 * s:
        fs -= 0.5
        lines = _wrap(name, "Helvetica-Bold", fs, name_w)
    c.setFillColor(C_BLUE)
    c.setFont("Helvetica-Bold", fs)
    total_th = len(lines) * fs * 1.12
    ty = y + h - 5 * s - (head_h * 0.72 - total_th) / 2 - fs
    for ln in lines:
        c.drawCentredString(name_x0 + name_w / 2, ty, ln)
        ty -= fs * 1.15

    # ── Address + contact (red, small, centered) ────────────────────────────
    cy_ = head_y - 8 * s
    c.setFillColor(C_RED)
    addr = school.get("address") or ""
    if addr:
        fs = 5.6 * s
        for ln in _wrap("Add: " + addr, "Helvetica-Bold", fs, w - 10 * s)[:2]:
            c.setFont("Helvetica-Bold", fs)
            c.drawCentredString(x + w / 2, cy_, ln)
            cy_ -= fs * 1.25
    contact = school.get("phone") or ""
    if contact:
        fs = 5.6 * s
        c.setFont("Helvetica-Bold", fs)
        c.drawCentredString(x + w / 2, cy_, f"Contact No.: {contact}")
        cy_ -= fs * 1.3

    # ── Student photo ────────────────────────────────────────────────────────
    ph_w = 0.40 * w
    ph_h = 0.26 * h
    ph_x = x + (w - ph_w) / 2
    ph_y = cy_ - 2 * s - ph_h
    c.setFillColor(C_PHOTO_BG)
    c.setStrokeColor(C_BORDER)
    c.setLineWidth(0.7)
    c.rect(ph_x, ph_y, ph_w, ph_h, stroke=1, fill=1)
    photo_path = student.get("photo_path")
    if photo_path:
        try:
            c.drawImage(ImageReader(photo_path), ph_x + 1, ph_y + 1, ph_w - 2, ph_h - 2,
                        preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            photo_path = None
    if not photo_path:
        # simple placeholder silhouette
        c.saveState()
        cp = c.beginPath()
        cp.rect(ph_x + 1, ph_y + 1, ph_w - 2, ph_h - 2)
        c.clipPath(cp, stroke=0, fill=0)
        c.setFillColor(HexColor("#64748b"))
        c.circle(ph_x + ph_w / 2, ph_y + ph_h * 0.62, ph_w * 0.16, stroke=0, fill=1)
        c.ellipse(ph_x + ph_w * 0.2, ph_y - ph_h * 0.25,
                  ph_x + ph_w * 0.8, ph_y + ph_h * 0.42, stroke=0, fill=1)
        c.restoreState()

    # ── Footer: yellow band + blue wave (drawn before fields so text wins) ──
    foot_h = 0.055 * h
    c.setFillColor(C_YELLOW)
    c.rect(x, y, w, foot_h, stroke=0, fill=1)
    c.setStrokeColor(C_SKY)
    c.setLineWidth(1.6 * s)
    pth = c.beginPath()
    pth.moveTo(x, y + foot_h + 2 * s)
    pth.curveTo(x + w * 0.35, y + foot_h + 8 * s,
                x + w * 0.65, y + foot_h - 2 * s,
                x + w, y + foot_h + 4 * s)
    c.drawPath(pth, stroke=1, fill=0)
    if session_label:
        fs = _fit_font(session_label, "Helvetica-Bold", 5.5 * s, w - 8 * s)
        c.setFillColor(C_BLUE)
        c.setFont("Helvetica-Bold", fs)
        c.drawCentredString(x + w / 2, y + foot_h / 2 - fs * 0.35, session_label)

    # ── Field rows ───────────────────────────────────────────────────────────
    fields = [
        ("STUDENT'S NAME", student.get("name") or ""),
        ("FATHER'S NAME", student.get("father_name") or ""),
        ("MOTHER'S NAME", student.get("mother_name") or ""),
        ("D.O.B.", student.get("dob") or ""),
        ("CLASS", student.get("class_name") or ""),
        ("MOB. NO.", student.get("phone") or ""),
        ("ADDRESS", student.get("address") or ""),
    ]
    fy_top = ph_y - 6 * s
    fy_bottom = y + foot_h + 10 * s
    avail_h = fy_top - fy_bottom

    fs = 6.2 * s
    label_w = 0.40 * (w - 12 * s)
    val_x = x + 6 * s + label_w + 4 * s
    val_w = x + w - 5 * s - val_x

    # Pre-compute total rows (address may wrap up to 3 lines)
    rows: List[tuple] = []
    for label, value in fields:
        vfs = fs
        vlines = _wrap(str(value).upper(), "Helvetica-Bold", vfs, val_w)
        if label != "ADDRESS":
            if len(vlines) > 1:
                vfs = _fit_font(str(value).upper(), "Helvetica-Bold", fs, val_w, min_size=4.2)
                vlines = _wrap(str(value).upper(), "Helvetica-Bold", vfs, val_w)[:1]
        else:
            vlines = vlines[:3]
        rows.append((label, vlines, vfs))

    n_lines = sum(max(len(vl), 1) for _, vl, _ in rows)
    line_h = min(fs * 1.75, avail_h / max(n_lines, 1))

    ty = fy_top - fs
    c.setFillColor(C_TEXT)
    for label, vlines, vfs in rows:
        c.setFont("Helvetica-Bold", fs)
        c.drawString(x + 6 * s, ty, label)
        c.drawString(x + 6 * s + label_w, ty, ":")
        c.setFont("Helvetica-Bold", vfs)
        if not vlines:
            ty -= line_h
        for i, vl in enumerate(vlines):
            c.drawString(val_x, ty, vl)
            ty -= line_h

    c.restoreState()


# ── PDF builder ───────────────────────────────────────────────────────────────
def build_pdf(students: List[dict], school: dict, req: IDCardRequest) -> io.BytesIO:
    size = PAGE_SIZES.get((req.page_size or "A4").upper(), A4)
    if (req.orientation or "portrait").lower() == "landscape":
        size = landscape(size)
    page_w, page_h = size

    card_w = req.card_width_mm * mm
    card_h = req.card_height_mm * mm
    margin = req.margin_mm * mm
    gap = req.gap_mm * mm

    cols = int((page_w - 2 * margin + gap) // (card_w + gap))
    rows = int((page_h - 2 * margin + gap) // (card_h + gap))
    if cols < 1 or rows < 1:
        raise HTTPException(400, "Card size is too big for the selected page. Reduce card size or margins.")
    per_page = cols * rows

    grid_w = cols * card_w + (cols - 1) * gap
    grid_h = rows * card_h + (rows - 1) * gap
    x0 = (page_w - grid_w) / 2
    y_top = (page_h + grid_h) / 2

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size)
    c.setTitle("Student ID Cards")

    for idx, st in enumerate(students):
        pos = idx % per_page
        if pos == 0 and idx > 0:
            c.showPage()
        rr, cc = divmod(pos, cols)
        cx = x0 + cc * (card_w + gap)
        cy = y_top - (rr + 1) * card_h - rr * gap
        draw_id_card(c, cx, cy, card_w, card_h, school, st,
                     show_cut_lines=req.show_cut_lines, session_label=req.session_label)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf


# ── Data helpers ──────────────────────────────────────────────────────────────
def _school_dict(school: School) -> dict:
    addr = ""
    if school.address:
        parts = [school.address.line1, school.address.line2, school.address.city,
                 school.address.state, school.address.pincode]
        addr = ", ".join([p for p in parts if p])
    return {
        "name": school.name,
        "address": addr,
        "phone": school.phone or "",
        "logo_path": _upload_path(school.logo),
    }


def _student_dict(s: Student) -> dict:
    name = " ".join([p for p in [s.first_name, s.middle_name, s.last_name] if p])
    father = s.parent_info.father_name if s.parent_info else ""
    mother = s.parent_info.mother_name if s.parent_info else ""
    father_phone = s.parent_info.father_phone if s.parent_info else ""
    cls = ""
    try:
        cls = s.classroom.name if s.classroom else ""
        if s.section and s.section.name:
            cls = f"{cls} - {s.section.name}" if cls else s.section.name
    except Exception:
        pass
    return {
        "name": name,
        "father_name": father or "",
        "mother_name": mother or "",
        "dob": s.date_of_birth.strftime("%d.%m.%Y") if s.date_of_birth else "",
        "class_name": cls,
        "phone": s.phone or father_phone or "",
        "address": s.current_address or s.permanent_address or "",
        "photo_path": _upload_path(s.photo),
        "admission_no": s.admission_no or "",
    }


def _collect_students(req: IDCardRequest, current_user: User) -> List[Student]:
    school_id = resolve_school_access(current_user, req.school_id)
    branch_code = resolve_branch_scope(current_user, None)
    try:
        school = School.objects.get(id=school_id)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")

    if req.student_ids:
        students = []
        for sid in req.student_ids:
            st = Student.objects(id=sid, school=school).first()
            if st:
                students.append(st)
        if not students:
            raise HTTPException(404, "No matching students found")
        return school, students

    query = Student.objects(school=school, is_active=True, admission_status="Active")
    if req.academic_year_id:
        try:
            ay = AcademicYear.objects.get(id=req.academic_year_id)
            query = query.filter(academic_year=ay)
        except AcademicYear.DoesNotExist:
            pass
    if req.classroom_id:
        try:
            cls = ClassRoom.objects.get(id=req.classroom_id)
            query = query.filter(classroom=cls)
        except ClassRoom.DoesNotExist:
            raise HTTPException(404, "Class not found")
    if req.section_id:
        try:
            sec = Section.objects.get(id=req.section_id)
            query = query.filter(section=sec)
        except Section.DoesNotExist:
            raise HTTPException(404, "Section not found")
    if branch_code:
        query = query.filter(branch_code=branch_code)

    students = list(query.order_by("first_name"))
    if not students:
        raise HTTPException(404, "No students found for the selected class/section")
    return school, students


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/generate")
async def generate_id_cards(req: IDCardRequest, current_user: User = Depends(get_current_user)):
    """Generate a PDF of ID cards — single, multiple, class or section wise."""
    school, students = _collect_students(req, current_user)
    pdf = build_pdf([_student_dict(s) for s in students], _school_dict(school), req)
    filename = f"id_cards_{len(students)}.pdf"
    return StreamingResponse(pdf, media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/layout-info")
async def layout_info(card_width_mm: float = 54, card_height_mm: float = 86,
                      page_size: str = "A4", orientation: str = "portrait",
                      margin_mm: float = 8, gap_mm: float = 4,
                      current_user: User = Depends(get_current_user)):
    """How many cards fit on one page with the given settings."""
    size = PAGE_SIZES.get(page_size.upper(), A4)
    if orientation.lower() == "landscape":
        size = landscape(size)
    page_w, page_h = size
    cols = int((page_w - 2 * margin_mm * mm + gap_mm * mm) // (card_width_mm * mm + gap_mm * mm))
    rows = int((page_h - 2 * margin_mm * mm + gap_mm * mm) // (card_height_mm * mm + gap_mm * mm))
    cols, rows = max(cols, 0), max(rows, 0)
    return success_response({
        "columns": cols, "rows": rows, "cards_per_page": cols * rows,
        "fits": cols >= 1 and rows >= 1
    })
