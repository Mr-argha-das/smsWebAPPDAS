from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime
from passlib.context import CryptContext
import re

from models.parent_portal import ParentPortalUser, ParentMessage
from models.institution import School, User
from models.student import Student
from models.attendance import StudentAttendance
from models.fees import FeeInvoice
from models.examination import ExamDateSheet, Result
from models.academic import Homework
from models.communication import Notice, Event
from utils.auth import get_current_user, create_access_token
from utils.helpers import success_response

router = APIRouter(prefix="/parent", tags=["Parent Portal"])

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(pwd: str) -> str:
    return _pwd_ctx.hash(pwd)


def verify_password(pwd: str, hashed: str) -> bool:
    try:
        return _pwd_ctx.verify(pwd, hashed)
    except Exception:
        return False


def get_parent_from_token(token: str) -> ParentPortalUser:
    from jose import jwt, JWTError
    from config import settings
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "parent":
            raise HTTPException(401, "Invalid token type")
        return ParentPortalUser.objects.get(id=payload["sub"], is_active=True)
    except (JWTError, ParentPortalUser.DoesNotExist):
        raise HTTPException(401, "Invalid or expired token")


def _serialize_date_sheet(sheet: ExamDateSheet):
    return {
        "id": str(sheet.id),
        "exam_name": sheet.exam.name if sheet.exam else "-",
        "exam_type": sheet.exam.exam_type if sheet.exam else "-",
        "classroom": sheet.classroom.name if sheet.classroom else "-",
        "section": sheet.section.name if sheet.section else "All",
        "published_at": sheet.published_at.isoformat() if sheet.published_at else None,
        "rows": [{
            "subject": entry.subject.name if entry.subject else "-",
            "exam_date": entry.exam_date.strftime("%Y-%m-%d") if entry.exam_date else "",
            "shift": entry.shift or "",
            "timing": entry.timing or "",
            "syllabus": entry.syllabus or "",
        } for entry in (sheet.entries or [])]
    }


def _normalize_admission_no(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).upper()


def _normalize_phone(value: str) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _parent_login_identifier(data: dict) -> str:
    return str(data.get("identifier") or data.get("email") or data.get("phone") or "").strip()


def _find_student_by_admission_no(admission_no: str, school: Optional[School] = None) -> Optional[Student]:
    raw = str(admission_no or "").strip()
    if not raw:
        return None

    query = Student.objects(is_active=True)
    if school:
        query = query.filter(school=school)

    student = query.filter(admission_no=raw).first()
    if student:
        return student

    student = query.filter(admission_no__iexact=raw).first()
    if student:
        return student

    normalized = _normalize_admission_no(raw)
    for candidate in query:
        if _normalize_admission_no(candidate.admission_no) == normalized:
            return candidate
    return None


def _resolve_parent_school(data: dict, *, for_login: bool = False) -> School:
    admission_numbers = [str(adm).strip() for adm in data.get("admission_numbers", []) if str(adm).strip()]
    school_id = data.get("school_id") or data.get("school")
    requested_school = None
    if school_id:
        try:
            requested_school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            raise HTTPException(404, "School not found")

    if requested_school and (not admission_numbers or any(_find_student_by_admission_no(adm, requested_school) for adm in admission_numbers)):
        return requested_school

    if for_login and _parent_login_identifier(data):
        identifier = _parent_login_identifier(data)
        phone_digits = _normalize_phone(identifier)
        parents = list(ParentPortalUser.objects(email=identifier.lower().strip(), is_active=True))
        if phone_digits:
            parents += list(ParentPortalUser.objects(phone__in=[identifier.strip(), phone_digits], is_active=True))
        schools = {str(parent.school.id): parent.school for parent in parents if parent.school}
        if len(schools) == 1:
            return next(iter(schools.values()))
        if len(schools) > 1:
            raise HTTPException(400, "Multiple schools found for this login. Open the parent login link from your school.")

    if admission_numbers:
        schools = {}
        for adm in admission_numbers:
            student = _find_student_by_admission_no(adm)
            if student and student.school:
                schools[str(student.school.id)] = student.school
        if len(schools) == 1:
            return next(iter(schools.values()))
        if len(schools) > 1:
            raise HTTPException(400, "Admission numbers match multiple schools. Open the parent login link from your school.")

    if requested_school:
        return requested_school

    active_schools = list(School.objects(is_active=True).limit(2))
    if len(active_schools) == 1:
        return active_schools[0]
    raise HTTPException(400, "School is required. Open the parent login link from your school.")


# ── Public: Register ──────────────────────────────────────────────────────────
@router.post("/register")
async def register_parent(data: dict):
    school = _resolve_parent_school(data)
    required_fields = ["name", "phone", "email", "password"]
    if any(not str(data.get(field, "")).strip() for field in required_fields):
        raise HTTPException(400, "Name, phone, email and password are required")
    email = data['email'].lower().strip()
    phone = str(data['phone']).strip()
    phone_digits = _normalize_phone(phone)
    if ParentPortalUser.objects(school=school, email=email).first():
        raise HTTPException(400, "Email already registered")
    if ParentPortalUser.objects(school=school, phone__in=[phone, phone_digits]).first():
        raise HTTPException(400, "Phone number already registered")

    linked_children = []
    linked_ids = set()
    for adm in data.get('admission_numbers', []):
        admission_no = str(adm).strip()
        if not admission_no:
            continue
        student = _find_student_by_admission_no(admission_no, school)
        if student and str(student.id) not in linked_ids:
            linked_children.append(student)
            linked_ids.add(str(student.id))
    if not linked_children:
        raise HTTPException(400, "No student found for the admission number in this school")

    parent = ParentPortalUser(
        school=school,
        name=data['name'],
        email=email,
        phone=phone_digits or phone,
        password_hash=hash_password(data['password']),
        relation=data.get('relation', 'Father')
    )
    parent.children = linked_children
    parent.save()

    token = create_access_token({"sub": str(parent.id), "type": "parent"})
    return success_response({
        "token": token, "parent_id": str(parent.id),
        "name": parent.name, "children_linked": len(parent.children)
    }, "Registration successful!")


# ── Public: Login ─────────────────────────────────────────────────────────────
@router.post("/login")
async def parent_login(data: dict):
    school = _resolve_parent_school(data, for_login=True)
    identifier = _parent_login_identifier(data)
    if not identifier or not str(data.get('password', '')).strip():
        raise HTTPException(400, "Email/phone and password are required")
    phone_digits = _normalize_phone(identifier)
    parent = ParentPortalUser.objects(school=school, email=identifier.lower().strip(), is_active=True).first()
    if not parent and phone_digits:
        parent = ParentPortalUser.objects(school=school, phone__in=[identifier.strip(), phone_digits], is_active=True).first()
    if not parent or not verify_password(data['password'], parent.password_hash):
        raise HTTPException(401, "Invalid email/phone or password")
    parent.update(last_login=datetime.utcnow())
    token = create_access_token({"sub": str(parent.id), "type": "parent"})
    return success_response({
        "token": token, "parent_id": str(parent.id),
        "name": parent.name, "relation": parent.relation,
        "children": [{
            "id": str(c.id), "name": c.full_name,
            "admission_no": c.admission_no,
            "class": c.classroom.name if c.classroom else None
        } for c in parent.children]
    }, "Login successful!")


# ── Dashboard ─────────────────────────────────────────────────────────────────
@router.get("/dashboard/{parent_id}")
async def parent_dashboard(parent_id: str, school_id: str, token: str = Query(...)):
    parent = get_parent_from_token(token)
    if str(parent.id) != parent_id:
        raise HTTPException(403, "Access denied")

    children_data = []
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    for student in parent.children:
        # Today's attendance
        att_status = "Not Marked"
        try:
            today_att = StudentAttendance.objects(
                school=parent.school, classroom=student.classroom, date=today
            ).first()
            if today_att:
                for rec in (today_att.records or []):
                    if rec.student and str(rec.student.id) == str(student.id):
                        att_status = rec.status
                        break
        except Exception:
            pass

        # Fee dues
        try:
            fee_dues = sum(i.balance_amount for i in FeeInvoice.objects(student=student, status__in=['Pending', 'Partial', 'Overdue']))
        except Exception:
            fee_dues = 0

        # Pending homework
        try:
            pending_hw = Homework.objects(classroom=student.classroom, due_date__gte=today).count() if student.classroom else 0
        except Exception:
            pending_hw = 0

        # Latest result
        latest_result = None
        try:
            r = Result.objects(student=student).order_by('-created_at').first()
            if r:
                latest_result = {"percentage": r.percentage, "grade": r.overall_grade, "rank": r.rank_in_class}
        except Exception:
            pass

        children_data.append({
            "id": str(student.id), "name": student.full_name,
            "admission_no": student.admission_no,
            "class": student.classroom.name if student.classroom else '-',
            "photo": student.photo, "today_attendance": att_status,
            "fee_dues": fee_dues, "pending_homework": pending_hw,
            "latest_result": latest_result
        })

    # Notices (last 5)
    try:
        notices = [{"title": n.title, "type": n.notice_type, "date": n.publish_date.isoformat() if n.publish_date else None}
                   for n in Notice.objects(school=parent.school, is_published=True).order_by('-created_at')[:5]]
    except Exception:
        notices = []

    # Upcoming events
    try:
        events = [{"title": e.title, "date": e.start_datetime.isoformat(), "venue": e.venue}
                  for e in Event.objects(school=parent.school, start_datetime__gte=datetime.utcnow(), status='Upcoming').order_by('start_datetime')[:3]]
    except Exception:
        events = []

    unread = 0
    try:
        unread = ParentMessage.objects(school=parent.school, parent=parent, is_read=False, sender='Admin').count()
    except Exception:
        pass

    return success_response({
        "parent_name": parent.name, "children": children_data,
        "notices": notices, "events": events, "unread_messages": unread
    })


# ── Child: Attendance ─────────────────────────────────────────────────────────
@router.get("/child/{student_id}/attendance")
async def child_attendance(student_id: str, school_id: str, month: int = None, year: int = None, token: str = Query(...)):
    parent = get_parent_from_token(token)
    if not any(str(c.id) == student_id for c in parent.children):
        raise HTTPException(403, "Student not linked to your account")
    student = Student.objects.get(id=student_id)
    now = datetime.utcnow()
    m = month or now.month; y = year or now.year
    start = datetime(y, m, 1)
    end   = datetime(y, m+1, 1) if m < 12 else datetime(y+1, 1, 1)
    att_records = StudentAttendance.objects(school=parent.school, classroom=student.classroom, date__gte=start, date__lt=end)
    records = []
    for att in att_records:
        for rec in (att.records or []):
            if rec.student and str(rec.student.id) == student_id:
                records.append({"date": att.date.strftime('%Y-%m-%d'), "status": rec.status, "remarks": getattr(rec, 'remarks', '')})
                break
    present = sum(1 for r in records if r['status'] == 'Present')
    absent  = sum(1 for r in records if r['status'] == 'Absent')
    late    = sum(1 for r in records if r['status'] == 'Late')
    return success_response({
        "records": sorted(records, key=lambda x: x['date'], reverse=True),
        "summary": {"present": present, "absent": absent, "late": late, "total": len(records),
                    "percentage": round(present / len(records) * 100, 1) if records else 0}
    })


# ── Child: Fees ───────────────────────────────────────────────────────────────
@router.get("/child/{student_id}/fees")
async def child_fees(student_id: str, school_id: str, token: str = Query(...)):
    parent = get_parent_from_token(token)

    if not any(str(c.id) == student_id for c in parent.children):
        raise HTTPException(403, "Student not linked to your account")

    student = Student.objects.get(id=student_id)

    invoices = list(
        FeeInvoice.objects(student=student)
        .order_by('-created_at')[:24]
    )

    result = [{
        "invoice_id": str(i.id),

        "invoice_no": i.invoice_no,

        "student_name": student.full_name,
        "admission_no": student.admission_no,

        "classroom": student.classroom.name if student.classroom else "-",

        "fee_type": "Tuition Fee",

        "amount": float(i.net_amount or 0),

        "paid": float(i.paid_amount or 0),

        "balance": float(i.balance_amount or 0),

        "due_date": i.due_date.isoformat() if i.due_date else None,

        "status": i.status,

        "pdf_url": f"/api/v1/fees/invoice/{str(i.id)}/public-pdf"

    } for i in invoices]

    total_due = sum(
        i.balance_amount
        for i in invoices
        if i.balance_amount > 0
    )

    return success_response(
        result,
        meta={"total_due": total_due}
    )
# ── Child: Results ────────────────────────────────────────────────────────────
@router.get("/child/{student_id}/results")
async def child_results(student_id: str, school_id: str, token: str = Query(...)):
    parent = get_parent_from_token(token)
    if not any(str(c.id) == student_id for c in parent.children):
        raise HTTPException(403, "Student not linked to your account")
    student = Student.objects.get(id=student_id)
    results = Result.objects(student=student).order_by('-created_at')[:10]
    return success_response([{
        "exam_name": r.exam.name if r.exam else '-',
        "percentage": r.percentage, "grade": r.overall_grade,
        "rank": r.rank_in_class, "is_pass": r.is_pass,
        "date": r.created_at.isoformat()
    } for r in results])


# ── Child: Date Sheet ─────────────────────────────────────────────────────────
@router.get("/child/{student_id}/date-sheet")
async def child_date_sheet(student_id: str, school_id: str, token: str = Query(...)):
    parent = get_parent_from_token(token)
    if not any(str(c.id) == student_id for c in parent.children):
        raise HTTPException(403, "Student not linked to your account")
    student = Student.objects.get(id=student_id)
    if not student.classroom:
        return success_response([])

    sheets = []
    class_sheets = list(ExamDateSheet.objects(
        school=parent.school,
        classroom=student.classroom,
        section=None,
        published_at__ne=None
    ).order_by('-updated_at'))
    section_sheets = []
    if student.section:
        section_sheets = list(ExamDateSheet.objects(
            school=parent.school,
            classroom=student.classroom,
            section=student.section,
            published_at__ne=None
        ).order_by('-updated_at'))

    seen_exam_ids = set()
    for sheet in section_sheets + class_sheets:
        exam_id = str(sheet.exam.id) if sheet.exam else str(sheet.id)
        if exam_id in seen_exam_ids:
            continue
        seen_exam_ids.add(exam_id)
        sheets.append(_serialize_date_sheet(sheet))
    return success_response(sheets)


# ── Child: Homework ───────────────────────────────────────────────────────────
@router.get("/child/{student_id}/homework")
async def child_homework(student_id: str, school_id: str, token: str = Query(...)):
    parent = get_parent_from_token(token)
    if not any(str(c.id) == student_id for c in parent.children):
        raise HTTPException(403, "Student not linked to your account")
    student = Student.objects.get(id=student_id)
    if not student.classroom:
        return success_response([])
    hw_list = Homework.objects(classroom=student.classroom).order_by('-assigned_date')[:20]
    return success_response([{
        "subject": h.subject.name if h.subject else '-',
        "title": h.title, "description": h.description,
        "given_date": h.assigned_date.isoformat() if h.assigned_date else None,
        "due_date": h.due_date.isoformat() if h.due_date else None,
        "is_overdue": bool(h.due_date and h.due_date < datetime.utcnow()),
        "attachments": h.attachments or []
    } for h in hw_list])


# ── Message to School ─────────────────────────────────────────────────────────
@router.post("/message")
async def send_message(data: dict, token: str = Query(...)):
    parent = get_parent_from_token(token)
    school = School.objects.get(id=data['school_id'])
    msg = ParentMessage(school=school, parent=parent, subject=data['subject'], content=data['content'], sender='Parent')
    if data.get('student_id'):
        try:
            msg.student = Student.objects.get(id=data['student_id'])
        except Exception:
            pass
    msg.save()
    return success_response({"id": str(msg.id)}, "Message sent to school")


@router.get("/messages/{parent_id}")
async def get_messages(parent_id: str, school_id: str, token: str = Query(...)):
    parent = get_parent_from_token(token)
    school = School.objects.get(id=school_id)
    msgs = ParentMessage.objects(school=school, parent=parent).order_by('-created_at')[:30]
    return success_response([{
        "id": str(m.id), "subject": m.subject, "content": m.content,
        "sender": m.sender, "is_read": m.is_read,
        "student": m.student.full_name if m.student else None,
        "date": m.created_at.isoformat()
    } for m in msgs])


# ── Admin: View messages from parents ────────────────────────────────────────
@router.get("/admin/messages")
async def admin_view_messages(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    msgs = ParentMessage.objects(school=school, sender='Parent').order_by('-created_at')[:50]
    return success_response([{
        "id": str(m.id),
        "parent_name": m.parent.name if m.parent else '-',
        "parent_phone": m.parent.phone if m.parent else '-',
        "student": m.student.full_name if m.student else '-',
        "subject": m.subject, "content": m.content,
        "is_read": m.is_read, "date": m.created_at.isoformat()
    } for m in msgs])


@router.patch("/admin/messages/{msg_id}/read")
async def mark_read(msg_id: str, current_user: User = Depends(get_current_user)):
    try:
        ParentMessage.objects.get(id=msg_id).update(is_read=True)
        return success_response(message="Marked as read")
    except ParentMessage.DoesNotExist:
        raise HTTPException(404, "Message not found")


# ── Admin: List parents ───────────────────────────────────────────────────────
@router.get("/admin/parents")
async def list_parents(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    parents = ParentPortalUser.objects(school=school, is_active=True)
    return success_response([{
        "id": str(p.id), "name": p.name, "email": p.email, "phone": p.phone,
        "relation": p.relation,
        "children": [{"name": c.full_name, "admission_no": c.admission_no} for c in (p.children or [])],
        "last_login": p.last_login.isoformat() if p.last_login else None,
        "created_at": p.created_at.isoformat()
    } for p in parents])
