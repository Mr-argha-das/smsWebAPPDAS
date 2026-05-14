from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import csv
import io
import re
import os
import tempfile
from models.student import Student, TransferCertificate, ParentInfo
from models.institution import School, AcademicYear, ClassRoom, Section, User
from models.transport import TransportRoute, StudentTransport, Vehicle
from models.attendance import StudentAttendance
from models.fees import FeeInvoice, PaymentTransaction
from models.examination import Result
from utils.auth import get_current_user, resolve_school_access, resolve_branch_scope
from utils.helpers import (
    success_response, paginate_query, generate_admission_no,
    generate_id, generate_tc_no, save_upload_file, doc_to_dict
)
from utils.student_pdf_import import convert_student_pdf_to_csv

router = APIRouter(prefix="/students", tags=["Students"])


def _ensure_student_scope(student: Student, current_user: User):
    resolve_school_access(current_user, str(student.school.id) if student.school else None)
    scoped_branch = resolve_branch_scope(current_user, None)
    if scoped_branch and student.branch_code != scoped_branch:
        raise HTTPException(403, "Access denied for this student")


# ─── Admission ────────────────────────────────────────────────────────────────

class StudentAdmission(BaseModel):
    admission_no: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = ""
    middle_name: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = "Other"
    religion: Optional[str] = None
    caste: Optional[str] = None
    nationality: str = "Indian"
    aadhar_number: Optional[str] = None
    srn_no: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    current_address: Optional[str] = None
    permanent_address: Optional[str] = None
    current_address_details: Optional[dict] = None
    permanent_address_details: Optional[dict] = None
    school_id: str
    academic_year_id: str
    classroom_id: Optional[str] = None
    section_id: Optional[str] = None
    branch_code: Optional[str] = None
    branch_name: Optional[str] = None
    admission_date: Optional[datetime] = None
    admission_type: str = "New"
    registration_type: str = "Manual"
    parent_info: Optional[dict] = None
    medical_info: Optional[dict] = None
    previous_school: Optional[dict] = None
    uses_transport: bool = False
    transport_route_id: Optional[str] = None
    transport_area: Optional[str] = None
    bus_stop: Optional[str] = None
    bus_no: Optional[str] = None
    transport_months: List[str] = []
    migration: bool = False
    lateral_entry: bool = False
    in_hostel: bool = False
    extra_activities: List[str] = []
    remarks: Optional[str] = None
    referral_type: Optional[str] = None
    referral_number: Optional[str] = None
    referral_email: Optional[str] = None
    admission_concession: Optional[str] = None
    admission_concession_percent: float = 0
    sibling_student_ids: List[str] = []


class StudentPromotionRequest(BaseModel):
    academic_year_id: str
    classroom_id: str
    section_id: str
    branch_code: Optional[str] = None
    branch_name: Optional[str] = None
    remarks: Optional[str] = None


def _normalize_address_text(address: Optional[dict], fallback: Optional[str] = None) -> Optional[str]:
    if fallback:
        return fallback
    if not address:
        return None
    parts = [address.get(key) for key in ["address", "village_area", "post_office", "city", "state", "pin_code"]]
    return ", ".join([part for part in parts if part])


def _parse_import_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _split_name(full_name: Optional[str]) -> tuple[str, Optional[str], str]:
    parts = [part for part in re.split(r"\s+", (full_name or "").strip()) if part]
    if not parts:
        return "", None, ""
    if len(parts) == 1:
        return parts[0], None, ""
    if len(parts) == 2:
        return parts[0], None, parts[1]
    return parts[0], " ".join(parts[1:-1]), parts[-1]


def _normalize_gender(value: Optional[str]) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"m", "male"}:
        return "Male"
    if raw in {"f", "female"}:
        return "Female"
    return "Other"


def _csv_value(row: dict, *keys: str) -> Optional[str]:
    normalized = {str(k).strip().lower(): v for k, v in row.items()}
    for key in keys:
        value = normalized.get(key.strip().lower())
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _norm_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _norm_digits(value: Optional[str]) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _norm_date(value: Optional[datetime]) -> str:
    return value.strftime("%Y-%m-%d") if value else ""


def _student_name_key(first_name: Optional[str], middle_name: Optional[str], last_name: Optional[str]) -> str:
    return _norm_text(" ".join(part for part in [first_name, middle_name, last_name] if part))


def _student_existing_name_key(student: Student) -> str:
    return _student_name_key(student.first_name, student.middle_name, student.last_name)


def _same_import_date(left: Optional[datetime], right: Optional[datetime]) -> bool:
    return bool(left and right and left.date() == right.date())


def _student_import_identity_key(
    school_id: str,
    academic_year_id: str,
    branch_code: Optional[str],
    first_name: Optional[str],
    middle_name: Optional[str],
    last_name: Optional[str],
    father_name: Optional[str],
    mother_name: Optional[str],
    dob: Optional[datetime],
    phone: Optional[str],
    aadhar_no: Optional[str],
    srn_no: Optional[str],
) -> str:
    aadhar_digits = _norm_digits(aadhar_no)
    if aadhar_digits:
        return f"aadhar:{school_id}:{aadhar_digits}:{_student_name_key(first_name, middle_name, last_name)}"

    srn_key = _norm_text(srn_no)
    if srn_key:
        return f"srn:{school_id}:{srn_key}:{_student_name_key(first_name, middle_name, last_name)}"

    return "|".join([
        "bio",
        school_id,
        academic_year_id,
        _norm_text(branch_code),
        _student_name_key(first_name, middle_name, last_name),
        _norm_text(father_name),
        _norm_text(mother_name),
        _norm_date(dob),
        _norm_digits(phone),
    ])


def _student_matches_import_data(
    student: Student,
    first_name: Optional[str],
    middle_name: Optional[str],
    last_name: Optional[str],
    father_name: Optional[str],
    mother_name: Optional[str],
    dob: Optional[datetime],
    phone: Optional[str],
) -> bool:
    if _student_existing_name_key(student) != _student_name_key(first_name, middle_name, last_name):
        return False

    parent = student.parent_info or ParentInfo()
    father_matches = bool(father_name and _norm_text(parent.father_name) == _norm_text(father_name))
    mother_matches = bool(mother_name and _norm_text(parent.mother_name) == _norm_text(mother_name))

    phone_digits = _norm_digits(phone)
    phone_matches = bool(phone_digits and phone_digits in {
        _norm_digits(student.phone),
        _norm_digits(parent.father_phone),
        _norm_digits(parent.guardian_phone),
    })
    dob_matches = _same_import_date(student.date_of_birth, dob)

    return (
        (father_matches and (dob_matches or phone_matches))
        or (mother_matches and (dob_matches or phone_matches))
        or (dob_matches and phone_matches)
    )


def _find_matching_import_student(
    school: School,
    ay: AcademicYear,
    branch_code: Optional[str],
    first_name: str,
    middle_name: Optional[str],
    last_name: str,
    father_name: Optional[str],
    mother_name: Optional[str],
    dob: Optional[datetime],
    phone: Optional[str],
    aadhar_no: Optional[str],
    srn_no: Optional[str],
) -> Optional[Student]:
    aadhar_digits = _norm_digits(aadhar_no)
    if aadhar_digits:
        student = Student.objects(school=school, aadhar_number=aadhar_digits, is_active=True).first()
        if student and _student_existing_name_key(student) == _student_name_key(first_name, middle_name, last_name):
            return student

    srn_key = _norm_text(srn_no)
    if srn_key:
        student = Student.objects(school=school, srn_no__iexact=srn_key, is_active=True).first()
        if student and _student_existing_name_key(student) == _student_name_key(first_name, middle_name, last_name):
            return student

    query = Student.objects(school=school, academic_year=ay, is_active=True)
    if branch_code:
        query = query.filter(branch_code=branch_code)

    for student in query:
        if _student_matches_import_data(student, first_name, middle_name, last_name, father_name, mother_name, dob, phone):
            return student

    return None


def _apply_student_import_update(student: Student, update_data: dict, parent_info: dict) -> None:
    for key, value in update_data.items():
        if value is None and key not in {"middle_name", "remarks"}:
            continue
        setattr(student, key, value)

    existing_parent = student.parent_info or ParentInfo()
    for key, value in parent_info.items():
        if value:
            setattr(existing_parent, key, value)
    student.parent_info = existing_parent
    student.updated_at = datetime.utcnow()


def _resolve_class_section(row: dict) -> tuple[Optional[str], Optional[str]]:
    combined = _csv_value(row, "class", "class/sec", "class-section", "class_section")
    section = _csv_value(row, "section", "sec")
    class_name = None
    if combined:
        match = re.match(r"(.+?)\s*-\s*([A-Za-z0-9]+)$", combined)
        if match:
            class_name = match.group(1).strip()
            section = section or match.group(2).strip()
        else:
            class_name = combined.strip()
    return class_name, section


def _infer_numeric_name(class_name: Optional[str]) -> Optional[int]:
    if not class_name:
        return None
    normalized = str(class_name).strip().lower()
    direct_map = {
        "nursery": -2,
        "lkg": -1,
        "ukg": 0,
        "1st": 1,
        "2nd": 2,
        "3rd": 3,
        "4th": 4,
        "5th": 5,
        "6th": 6,
        "7th": 7,
        "8th": 8,
        "9th": 9,
        "10th": 10,
    }
    if normalized in direct_map:
        return direct_map[normalized]
    match = re.search(r"\d+", normalized)
    return int(match.group()) if match else None


def _ensure_class_and_section(school: School, ay: AcademicYear, class_name: str, section_name: str) -> tuple[ClassRoom, Section, bool, bool]:
    class_created = False
    section_created = False

    classroom = ClassRoom.objects(school=school, academic_year=ay, name__iexact=class_name, is_active=True).first()
    if not classroom:
        classroom = ClassRoom(
            school=school,
            academic_year=ay,
            name=class_name,
            numeric_name=_infer_numeric_name(class_name),
            class_fee=0,
            sections=[section_name],
            is_active=True
        )
        classroom.save()
        class_created = True

    section = Section.objects(classroom=classroom, name__iexact=section_name, is_active=True).first()
    if not section:
        section = Section(
            school=school,
            academic_year=ay,
            classroom=classroom,
            name=section_name,
            is_active=True
        )
        section.save()
        section_created = True

    existing_sections = classroom.sections or []
    if section_name not in existing_sections:
        classroom.sections = [*existing_sections, section_name]
        classroom.save()

    return classroom, section, class_created, section_created


def _ensure_default_class_section(school: School, ay: AcademicYear) -> tuple[ClassRoom, Section]:
    classroom, section, _, _ = _ensure_class_and_section(school, ay, "Unassigned", "A")
    return classroom, section


def _resolve_academic_year(school: School, academic_year_id: Optional[str]) -> AcademicYear:
    if academic_year_id:
        try:
            return AcademicYear.objects.get(id=academic_year_id)
        except Exception:
            pass
    current_year = AcademicYear.objects(school=school, is_current=True, is_active=True).first()
    if current_year:
        return current_year
    fallback_year = AcademicYear.objects(school=school, is_active=True).order_by("-created_at").first()
    if fallback_year:
        return fallback_year
    raise HTTPException(404, "Academic year not found")


def _address_details_fallback(details: Optional[dict], raw_address: Optional[str]) -> dict:
    if details:
        return details
    if raw_address:
        return {
            "address": raw_address,
            "village_area": None,
            "post_office": None,
            "city": None,
            "state": None,
            "pin_code": None,
            "phone_no": None,
        }
    return {}


def _sync_student_transport(student: Student, route_id: Optional[str], payload: StudentAdmission):
    StudentTransport.objects(student=student, is_active=True).update(is_active=False)
    if not (payload.uses_transport and route_id):
        student.update(
            uses_transport=False,
            transport_route=None,
            transport_route_name=None,
            transport_fee_per_month=0
        )
        return None

    route = TransportRoute.objects.get(id=route_id)
    vehicle = Vehicle.objects(route=route, is_active=True).first()
    assignment = StudentTransport(
        school=student.school,
        student=student,
        route=route,
        vehicle=vehicle,
        pickup_stop=payload.bus_stop,
        drop_stop=payload.bus_stop,
        pickup_time=route.morning_departure,
        drop_time=route.afternoon_departure,
        academic_year=student.academic_year.name if student.academic_year else None,
        fee_per_month=route.fee_per_month
    )
    assignment.save()
    student.update(
        uses_transport=True,
        transport_route=str(route.id),
        transport_route_name=route.route_name,
        transport_area=payload.transport_area,
        bus_stop=payload.bus_stop,
        bus_no=payload.bus_no or (vehicle.vehicle_no if vehicle else None),
        transport_fee_per_month=route.fee_per_month,
        transport_months=payload.transport_months or []
    )
    return route


@router.post("")
async def admit_student(data: StudentAdmission, current_user: User = Depends(get_current_user)):
    try:
        data.school_id = resolve_school_access(current_user, data.school_id)
        data.branch_code = resolve_branch_scope(current_user, data.branch_code)
        school = School.objects.get(id=data.school_id)
    except Exception as e:
        raise HTTPException(404, f"Reference not found: {str(e)}")
    ay = _resolve_academic_year(school, data.academic_year_id)

    classroom = None
    section = None
    if data.classroom_id and data.section_id:
        try:
            classroom = ClassRoom.objects.get(id=data.classroom_id)
            section = Section.objects.get(id=data.section_id)
        except Exception:
            classroom = None
            section = None
    if not classroom or not section:
        classroom, section = _ensure_default_class_section(school, ay)
    
    admission_no = (data.admission_no or "").strip() or generate_admission_no(school.code)
    if Student.objects(admission_no=admission_no).first():
        raise HTTPException(400, f"Student with admission number {admission_no} already exists")
    student_id = generate_id("STU")
    first_name = (data.first_name or "").strip() or "Student"
    last_name = (data.last_name or "").strip()
    gender = data.gender or "Other"
    
    student = Student(
        admission_no=admission_no,
        student_id=student_id,
        first_name=first_name,
        last_name=last_name,
        middle_name=data.middle_name,
        date_of_birth=data.date_of_birth,
        gender=gender,
        religion=data.religion,
        caste=data.caste,
        admission_concession=data.admission_concession,
        admission_concession_percent=data.admission_concession_percent,
        sibling_student_ids=data.sibling_student_ids or [],
        nationality=data.nationality,
        aadhar_number=data.aadhar_number,
        srn_no=data.srn_no,
        phone=data.phone,
        email=data.email,
        current_address=_normalize_address_text(data.current_address_details, data.current_address),
        permanent_address=_normalize_address_text(data.permanent_address_details, data.permanent_address),
        current_address_details=data.current_address_details,
        permanent_address_details=data.permanent_address_details,
        school=school,
        academic_year=ay,
        classroom=classroom,
        section=section,
        branch_code=data.branch_code,
        branch_name=data.branch_name,
        admission_date=data.admission_date or datetime.utcnow(),
        admission_type=data.admission_type,
        registration_type=data.registration_type,
        uses_transport=data.uses_transport,
        transport_area=data.transport_area,
        bus_stop=data.bus_stop,
        bus_no=data.bus_no,
        transport_months=data.transport_months,
        migration=data.migration,
        lateral_entry=data.lateral_entry,
        in_hostel=data.in_hostel,
        extra_activities=data.extra_activities,
        remarks=data.remarks,
        referral_type=data.referral_type,
        referral_number=data.referral_number,
        referral_email=data.referral_email
    )
    
    if data.parent_info:
        from models.student import ParentInfo
        student.parent_info = ParentInfo(**data.parent_info)
    
    if data.medical_info:
        from models.student import MedicalInfo
        student.medical_info = MedicalInfo(**data.medical_info)
    
    student.save()
    route = None
    if data.transport_route_id:
        route = _sync_student_transport(student, data.transport_route_id, data)
        student.reload()
    
        return success_response({
            "id": str(student.id),
            "admission_no": student.admission_no,
            "student_id": student.student_id,
            "full_name": student.full_name,
            "transport_route_name": route.route_name if route else None
        }, "Student admitted successfully")


@router.get("")
async def list_students(
    school_id: str,
    academic_year_id: Optional[str] = None,
    classroom_id: Optional[str] = None,
    section_id: Optional[str] = None,
    branch_code: Optional[str] = None,
    admission_status: Optional[str] = None,
    student_view: Optional[str] = Query("active"),
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    try:
        school_id = resolve_school_access(current_user, school_id)
        branch_code = resolve_branch_scope(current_user, branch_code)
        school = School.objects.get(id=school_id)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")
    
    query = Student.objects(school=school, is_active=True)
    
    if academic_year_id:
        try:
            ay = AcademicYear.objects.get(id=academic_year_id)
            query = query.filter(academic_year=ay)
        except AcademicYear.DoesNotExist:
            pass
    
    if classroom_id:
        try:
            classroom = ClassRoom.objects.get(id=classroom_id)
            query = query.filter(classroom=classroom)
        except ClassRoom.DoesNotExist:
            pass
    
    if section_id:
        try:
            section = Section.objects.get(id=section_id)
            query = query.filter(section=section)
        except Section.DoesNotExist:
            pass

    if branch_code:
        query = query.filter(branch_code=branch_code)

    if student_view == "transferred":
        query = query.filter(admission_status="Transferred")
    elif student_view != "all":
        query = query.filter(admission_status__ne="Transferred")
    
    if admission_status:
        query = query.filter(admission_status=admission_status)
    
    if search:
        query = query.filter(
            __raw__={"$or": [
                {"first_name": {"$regex": search, "$options": "i"}},
                {"last_name": {"$regex": search, "$options": "i"}},
                {"admission_no": {"$regex": search, "$options": "i"}},
                {"student_id": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}},
                {"parent_info.father_name": {"$regex": search, "$options": "i"}},
                {"parent_info.father_phone": {"$regex": search, "$options": "i"}},
                {"parent_info.mother_phone": {"$regex": search, "$options": "i"}},
                {"parent_info.guardian_phone": {"$regex": search, "$options": "i"}}
            ]}
        )
    
    total = query.count()
    students = query.order_by('first_name').skip((page - 1) * per_page).limit(per_page).select_related(max_depth=2)
    
    result = []
    for s in students:
        result.append({
            "id": str(s.id),
            "admission_no": s.admission_no,
            "student_id": s.student_id,
            "full_name": s.full_name,
            "first_name": s.first_name,
            "last_name": s.last_name,
            "gender": s.gender,
            "date_of_birth": s.date_of_birth.isoformat() if s.date_of_birth else None,
            "classroom_id": str(s.classroom.id) if s.classroom else None,
            "classroom_name": s.classroom.name if s.classroom else None,
            "classroom": s.classroom.name if s.classroom else None,
            "section_id": str(s.section.id) if s.section else None,
            "section_name": s.section.name if s.section else None,
            "section": s.section.name if s.section else None,
            "branch_name": s.branch_name,
            "admission_status": s.admission_status,
            "phone": s.phone,
            "photo": s.photo,
            "current_address": s.current_address,
            "permanent_address": s.permanent_address,
            "address": s.current_address or s.permanent_address,
            "father_name": s.parent_info.father_name if s.parent_info else None,
            "father_phone": s.parent_info.father_phone if s.parent_info else None,
            "route_name": s.transport_route_name,
        })
    
    return success_response(result, meta={
        "total": total, "page": page, "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    })


@router.get("/export/csv")
async def export_students_csv(
    school_id: str,
    academic_year_id: Optional[str] = None,
    classroom_id: Optional[str] = None,
    section_id: Optional[str] = None,
    branch_code: Optional[str] = None,
    admission_status: Optional[str] = None,
    student_view: Optional[str] = Query("active"),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    try:
        school_id = resolve_school_access(current_user, school_id)
        branch_code = resolve_branch_scope(current_user, branch_code)
        school = School.objects.get(id=school_id)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")

    query = Student.objects(school=school, is_active=True)
    if academic_year_id:
        ay = AcademicYear.objects(id=academic_year_id).first()
        if ay:
            query = query.filter(academic_year=ay)
    if classroom_id:
        classroom = ClassRoom.objects(id=classroom_id).first()
        if classroom:
            query = query.filter(classroom=classroom)
    if section_id:
        section = Section.objects(id=section_id).first()
        if section:
            query = query.filter(section=section)
    if branch_code:
        query = query.filter(branch_code=branch_code)
    if student_view == "transferred":
        query = query.filter(admission_status="Transferred")
    elif student_view != "all":
        query = query.filter(admission_status__ne="Transferred")
    if admission_status:
        query = query.filter(admission_status=admission_status)
    if search:
        query = query.filter(__raw__={"$or": [
            {"first_name": {"$regex": search, "$options": "i"}},
            {"last_name": {"$regex": search, "$options": "i"}},
            {"admission_no": {"$regex": search, "$options": "i"}},
            {"student_id": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"parent_info.father_name": {"$regex": search, "$options": "i"}},
            {"parent_info.father_phone": {"$regex": search, "$options": "i"}},
        ]})

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Adm No", "Student Name", "DOB", "Class", "Section", "Gender", "Father Name", "Mother Name", "Phone", "Address", "Status"])
    for s in query.order_by("first_name"):
        writer.writerow([
            s.admission_no or "",
            s.full_name,
            s.date_of_birth.strftime("%d-%b-%Y") if s.date_of_birth else "",
            s.classroom.name if s.classroom else "",
            s.section.name if s.section else "",
            s.gender or "",
            s.parent_info.father_name if s.parent_info else "",
            s.parent_info.mother_name if s.parent_info else "",
            s.phone or (s.parent_info.father_phone if s.parent_info else "") or "",
            s.current_address or s.permanent_address or "",
            s.admission_status or "",
        ])

    response = StreamingResponse(iter([buffer.getvalue().encode("utf-8-sig")]), media_type="text/csv")
    response.headers["Content-Disposition"] = 'attachment; filename="student_list.csv"'
    return response


@router.get("/stats/summary")
async def student_stats(school_id: str, academic_year_id: Optional[str] = None,
                        branch_code: Optional[str] = None,
                        current_user: User = Depends(get_current_user)):
    try:
        school_id = resolve_school_access(current_user, school_id)
        branch_code = resolve_branch_scope(current_user, branch_code)
        school = School.objects.get(id=school_id)
        query = Student.objects(school=school, is_active=True, admission_status="Active")
        if academic_year_id:
            ay = AcademicYear.objects.get(id=academic_year_id)
            query = query.filter(academic_year=ay)
        if branch_code:
            query = query.filter(branch_code=branch_code)

        active_query = query.filter(admission_status="Active")
        transferred_query = query.filter(admission_status="Transferred")

        stats = {
            "total": active_query.count(),
            "by_gender": {
                "male": active_query.filter(gender="Male").count(),
                "female": active_query.filter(gender="Female").count(),
                "other": active_query.filter(gender="Other").count()
            },
            "by_status": {
                "active": active_query.filter(admission_status="Active").count(),
                "transferred": transferred_query.count(),
                "alumni": active_query.filter(admission_status="Alumni").count(),
            }
        }
        return success_response(stats)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")


@router.get("/search-siblings")
async def search_siblings(
    school_id: str,
    classroom_id: Optional[str] = None,
    section_id: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    try:
        school_id = resolve_school_access(current_user, school_id)
        scoped_branch = resolve_branch_scope(current_user, None)
        school = School.objects.get(id=school_id)
        query = Student.objects(school=school, is_active=True)
        if scoped_branch:
            query = query.filter(branch_code=scoped_branch)
        if classroom_id:
            query = query.filter(classroom=ClassRoom.objects.get(id=classroom_id))
        if section_id:
            query = query.filter(section=Section.objects.get(id=section_id))
        if search:
            query = query.filter(__raw__={"$or": [
                {"first_name": {"$regex": search, "$options": "i"}},
                {"last_name": {"$regex": search, "$options": "i"}},
                {"admission_no": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}},
                {"parent_info.father_name": {"$regex": search, "$options": "i"}}
            ]})
        result = [{
            "id": str(s.id),
            "admission_no": s.admission_no,
            "full_name": s.full_name,
            "father_name": s.parent_info.father_name if s.parent_info else None,
            "mother_name": s.parent_info.mother_name if s.parent_info else None,
            "phone": s.phone or (s.parent_info.father_phone if s.parent_info else None),
            "classroom_name": s.classroom.name if s.classroom else None,
            "section_name": s.section.name if s.section else None,
            "address": s.current_address
        } for s in query.order_by('first_name')[:100]]
        return success_response(result)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")


@router.get("/{student_id}")
async def get_student(student_id: str, current_user: User = Depends(get_current_user)):
    try:
        student = Student.objects.get(id=student_id)
        _ensure_student_scope(student, current_user)
        data = {
            "id": str(student.id),
            "admission_no": student.admission_no,
            "student_id": student.student_id,
            "full_name": student.full_name,
            "first_name": student.first_name,
            "middle_name": student.middle_name,
            "last_name": student.last_name,
            "gender": student.gender,
            "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else None,
            "religion": student.religion,
            "caste": student.caste,
            "admission_concession": student.admission_concession,
            "admission_concession_percent": student.admission_concession_percent,
            "sibling_student_ids": student.sibling_student_ids or [],
            "nationality": student.nationality,
            "aadhar_number": student.aadhar_number,
            "srn_no": student.srn_no,
            "phone": student.phone,
            "email": student.email,
            "current_address": student.current_address,
            "permanent_address": student.permanent_address,
            "current_address_details": _address_details_fallback(student.current_address_details, student.current_address),
            "permanent_address_details": _address_details_fallback(student.permanent_address_details, student.permanent_address),
            "photo": student.photo,
            "branch_code": student.branch_code,
            "branch_name": student.branch_name,
            "academic_year_id": str(student.academic_year.id) if student.academic_year else None,
            "classroom_id": str(student.classroom.id) if student.classroom else None,
            "classroom_name": student.classroom.name if student.classroom else None,
            "class_fee": student.classroom.class_fee if student.classroom else 0,
            "section_id": str(student.section.id) if student.section else None,
            "section_name": student.section.name if student.section else None,
            "academic_year": student.academic_year.name if student.academic_year else None,
            "admission_date": student.admission_date.isoformat() if student.admission_date else None,
            "admission_type": student.admission_type,
            "registration_type": student.registration_type,
            "admission_status": student.admission_status,
            "uses_transport": student.uses_transport,
            "transport_route_id": student.transport_route,
            "transport_route": student.transport_route,
            "transport_route_name": student.transport_route_name,
            "transport_area": student.transport_area,
            "bus_stop": student.bus_stop,
            "bus_no": student.bus_no,
            "transport_fee_per_month": student.transport_fee_per_month,
            "transport_months": student.transport_months or [],
            "migration": student.migration,
            "lateral_entry": student.lateral_entry,
            "in_hostel": student.in_hostel,
            "extra_activities": student.extra_activities,
            "remarks": student.remarks,
            "referral_type": student.referral_type,
            "referral_number": student.referral_number,
            "referral_email": student.referral_email,
            "parent_info": {
                "father_name": student.parent_info.father_name if student.parent_info else None,
                "father_phone": student.parent_info.father_phone if student.parent_info else None,
                "father_email": student.parent_info.father_email if student.parent_info else None,
                "father_occupation": student.parent_info.father_occupation if student.parent_info else None,
                "mother_name": student.parent_info.mother_name if student.parent_info else None,
                "mother_phone": student.parent_info.mother_phone if student.parent_info else None,
                "guardian_name": student.parent_info.guardian_name if student.parent_info else None,
                "guardian_phone": student.parent_info.guardian_phone if student.parent_info else None,
            } if student.parent_info else None,
            "medical_info": {
                "blood_group": student.medical_info.blood_group if student.medical_info else None,
                "height": student.medical_info.height if student.medical_info else None,
                "weight": student.medical_info.weight if student.medical_info else None,
                "allergies": student.medical_info.allergies if student.medical_info else [],
                "medical_conditions": student.medical_info.medical_conditions if student.medical_info else [],
            } if student.medical_info else None,
            "documents": [
                {
                    "doc_type": d.doc_type, "doc_number": d.doc_number,
                    "file_path": d.file_path, "is_verified": d.is_verified
                } for d in (student.documents or [])
            ],
            "created_at": student.created_at.isoformat() if student.created_at else None
        }
        return success_response(data)
    except Student.DoesNotExist:
        raise HTTPException(404, "Student not found")


@router.get("/{student_id}/profile-summary")
async def get_student_profile_summary(student_id: str, current_user: User = Depends(get_current_user)):
    try:
        student = Student.objects.get(id=student_id)
        _ensure_student_scope(student, current_user)
    except Student.DoesNotExist:
        raise HTTPException(404, "Student not found")

    attendance_query = StudentAttendance.objects(
        school=student.school,
        classroom=student.classroom,
        section=student.section
    ).order_by('-date')
    total_days = 0
    present_days = 0
    absent_days = 0
    late_days = 0
    recent_attendance = []

    for att in attendance_query:
        for rec in att.records:
            if rec.student and str(rec.student.id) == str(student.id):
                total_days += 1
                if rec.status == "Present":
                    present_days += 1
                elif rec.status == "Absent":
                    absent_days += 1
                elif rec.status == "Late":
                    late_days += 1
                    present_days += 1

                if len(recent_attendance) < 10:
                    recent_attendance.append({
                        "date": att.date.isoformat() if att.date else None,
                        "status": rec.status,
                        "remarks": rec.remarks
                    })
                break

    attendance_percentage = round((present_days / total_days * 100), 2) if total_days else 0

    invoices = list(FeeInvoice.objects(student=student).order_by('-invoice_date')[:10])
    payments = list(PaymentTransaction.objects(student=student, status="Success").order_by('-payment_date')[:10])
    fee_summary = {
        "total_invoices": FeeInvoice.objects(student=student).count(),
        "total_billed": sum(inv.net_amount or 0 for inv in FeeInvoice.objects(student=student)),
        "total_paid": sum(inv.paid_amount or 0 for inv in FeeInvoice.objects(student=student)),
        "total_due": sum(inv.balance_amount or 0 for inv in FeeInvoice.objects(student=student)),
        "recent_invoices": [{
            "id": str(inv.id),
            "invoice_no": inv.invoice_no,
            "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "net_amount": inv.net_amount,
            "paid_amount": inv.paid_amount,
            "balance_amount": inv.balance_amount,
            "status": inv.status
        } for inv in invoices],
        "recent_payments": [{
            "id": str(payment.id),
            "transaction_no": payment.transaction_no,
            "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
            "amount": payment.amount,
            "payment_mode": payment.payment_mode,
            "receipt_no": payment.receipt_no,
            "remarks": payment.remarks
        } for payment in payments]
    }

    results = list(Result.objects(student=student).order_by('-generated_at')[:10])
    result_summary = [{
        "id": str(result.id),
        "exam_name": result.exam.name if result.exam else None,
        "exam_type": result.exam.exam_type if result.exam else None,
        "generated_at": result.generated_at.isoformat() if result.generated_at else None,
        "total_obtained": result.total_obtained_marks,
        "total_max": result.total_max_marks,
        "percentage": result.percentage,
        "grade": result.overall_grade,
        "cgpa": result.cgpa,
        "rank_in_class": result.rank_in_class,
        "rank_in_section": result.rank_in_section,
        "result_status": result.result_status,
        "is_pass": result.is_pass,
        "subjects": [{
            "name": subject.subject_name,
            "obtained": subject.total_marks,
            "max": subject.max_marks,
            "grade": subject.grade,
            "is_pass": subject.is_pass
        } for subject in (result.subject_results or [])]
    } for result in results]

    tcs = list(TransferCertificate.objects(student=student).order_by('-issue_date')[:5])

    student_data = {
        "id": str(student.id),
        "admission_no": student.admission_no,
        "student_id": student.student_id,
        "full_name": student.full_name,
        "first_name": student.first_name,
        "middle_name": student.middle_name,
        "last_name": student.last_name,
        "gender": student.gender,
        "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else None,
        "religion": student.religion,
        "caste": student.caste,
        "admission_concession": student.admission_concession,
        "admission_concession_percent": student.admission_concession_percent,
        "sibling_student_ids": student.sibling_student_ids or [],
        "nationality": student.nationality,
        "aadhar_number": student.aadhar_number,
        "srn_no": student.srn_no,
        "phone": student.phone,
        "email": student.email,
        "current_address": student.current_address,
        "permanent_address": student.permanent_address,
        "current_address_details": student.current_address_details or {},
        "permanent_address_details": student.permanent_address_details or {},
        "photo": student.photo,
        "branch_code": student.branch_code,
        "branch_name": student.branch_name,
        "academic_year_id": str(student.academic_year.id) if student.academic_year else None,
        "classroom_id": str(student.classroom.id) if student.classroom else None,
        "classroom_name": student.classroom.name if student.classroom else None,
        "class_fee": student.classroom.class_fee if student.classroom else 0,
        "section_id": str(student.section.id) if student.section else None,
        "section_name": student.section.name if student.section else None,
        "academic_year": student.academic_year.name if student.academic_year else None,
        "admission_date": student.admission_date.isoformat() if student.admission_date else None,
        "admission_type": student.admission_type,
        "registration_type": student.registration_type,
        "admission_status": student.admission_status,
        "uses_transport": student.uses_transport,
        "transport_route_id": student.transport_route,
        "transport_route_name": student.transport_route_name,
        "transport_area": student.transport_area,
        "bus_stop": student.bus_stop,
        "bus_no": student.bus_no,
        "transport_fee_per_month": student.transport_fee_per_month,
        "transport_months": student.transport_months or [],
        "migration": student.migration,
        "lateral_entry": student.lateral_entry,
        "in_hostel": student.in_hostel,
        "extra_activities": student.extra_activities or [],
        "remarks": student.remarks,
        "referral_type": student.referral_type,
        "referral_number": student.referral_number,
        "referral_email": student.referral_email,
        "parent_info": {
            "father_name": student.parent_info.father_name if student.parent_info else None,
            "father_phone": student.parent_info.father_phone if student.parent_info else None,
            "father_email": student.parent_info.father_email if student.parent_info else None,
            "father_occupation": student.parent_info.father_occupation if student.parent_info else None,
            "mother_name": student.parent_info.mother_name if student.parent_info else None,
            "mother_phone": student.parent_info.mother_phone if student.parent_info else None,
            "mother_email": student.parent_info.mother_email if student.parent_info else None,
            "mother_occupation": student.parent_info.mother_occupation if student.parent_info else None,
            "guardian_name": student.parent_info.guardian_name if student.parent_info else None,
            "guardian_phone": student.parent_info.guardian_phone if student.parent_info else None,
            "guardian_relation": student.parent_info.guardian_relation if student.parent_info else None,
            "guardian_address": student.parent_info.guardian_address if student.parent_info else None,
        } if student.parent_info else None,
        "medical_info": {
            "blood_group": student.medical_info.blood_group if student.medical_info else None,
            "height": student.medical_info.height if student.medical_info else None,
            "weight": student.medical_info.weight if student.medical_info else None,
            "allergies": student.medical_info.allergies if student.medical_info else [],
            "medical_conditions": student.medical_info.medical_conditions if student.medical_info else [],
            "emergency_contact": student.medical_info.emergency_contact if student.medical_info else None,
            "doctor_name": student.medical_info.doctor_name if student.medical_info else None,
            "doctor_phone": student.medical_info.doctor_phone if student.medical_info else None,
        } if student.medical_info else None,
        "documents": [
            {
                "doc_type": d.doc_type,
                "doc_number": d.doc_number,
                "file_path": d.file_path,
                "is_verified": d.is_verified,
                "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None
            } for d in (student.documents or [])
        ],
        "created_at": student.created_at.isoformat() if student.created_at else None
    }

    return success_response({
        "student": student_data,
        "attendance_summary": {
            "total_working_days": total_days,
            "present_days": present_days,
            "absent_days": absent_days,
            "late_days": late_days,
            "attendance_percentage": attendance_percentage,
            "recent_records": recent_attendance
        },
        "fee_summary": fee_summary,
        "results": result_summary,
        "transfer_certificates": [{
            "id": str(tc.id),
            "tc_number": tc.tc_number,
            "issue_date": tc.issue_date.isoformat() if tc.issue_date else None
        } for tc in tcs]
    })


@router.put("/{student_id}")
async def update_student(student_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        student = Student.objects.get(id=student_id)
        _ensure_student_scope(student, current_user)
        if 'school_id' in data:
            data['school_id'] = resolve_school_access(current_user, data.get('school_id'))
        data['branch_code'] = resolve_branch_scope(current_user, data.get('branch_code'))
        
        # Handle nested updates
        parent_info = data.pop('parent_info', None)
        medical_info = data.pop('medical_info', None)
        data.pop('id', None)
        data.pop('school_id', None)
        if 'admission_no' in data:
            admission_no = (data.get('admission_no') or '').strip()
            if not admission_no:
                data.pop('admission_no', None)
            elif Student.objects(admission_no=admission_no, id__ne=student.id).first():
                raise HTTPException(400, f"Student with admission number {admission_no} already exists")
            else:
                data['admission_no'] = admission_no
        data['updated_at'] = datetime.utcnow()
        if 'academic_year_id' in data:
            try:
                ay = AcademicYear.objects.get(id=data.pop('academic_year_id'))
                data['academic_year'] = ay
            except AcademicYear.DoesNotExist:
                data.pop('academic_year_id', None)
        
        # Handle reference fields
        if 'classroom_id' in data:
            try:
                classroom = ClassRoom.objects.get(id=data.pop('classroom_id'))
                data['classroom'] = classroom
            except ClassRoom.DoesNotExist:
                pass
        
        if 'section_id' in data:
            try:
                section = Section.objects.get(id=data.pop('section_id'))
                data['section'] = section
            except Section.DoesNotExist:
                pass

        route_id = data.pop('transport_route_id', None)
        if 'current_address_details' in data and 'current_address' not in data:
            data['current_address'] = _normalize_address_text(data.get('current_address_details'))
        if 'permanent_address_details' in data and 'permanent_address' not in data:
            data['permanent_address'] = _normalize_address_text(data.get('permanent_address_details'))
        
        student.update(**data)
        
        if parent_info:
            from models.student import ParentInfo
            student.reload()
            student.parent_info = ParentInfo(**parent_info)
            student.save()
        
        if medical_info:
            from models.student import MedicalInfo
            student.reload()
            student.medical_info = MedicalInfo(**medical_info)
            student.save()

        student.reload()
        if route_id is not None:
            payload = StudentAdmission(
                first_name=student.first_name,
                last_name=student.last_name,
                gender=student.gender,
                school_id=str(student.school.id),
                academic_year_id=str(student.academic_year.id),
                classroom_id=str(student.classroom.id),
                section_id=str(student.section.id),
                uses_transport=data.get('uses_transport', student.uses_transport),
                transport_area=data.get('transport_area', student.transport_area),
                bus_stop=data.get('bus_stop', student.bus_stop),
                bus_no=data.get('bus_no', student.bus_no),
                transport_months=data.get('transport_months', student.transport_months or [])
            )
            _sync_student_transport(student, route_id, payload)
        
        return success_response(message="Student updated successfully")
    except Student.DoesNotExist:
        raise HTTPException(404, "Student not found")


@router.post("/{student_id}/promote")
async def promote_student(
    student_id: str,
    data: StudentPromotionRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        student = Student.objects.get(id=student_id)
        _ensure_student_scope(student, current_user)
    except Student.DoesNotExist:
        raise HTTPException(404, "Student not found")

    branch_code = resolve_branch_scope(current_user, data.branch_code or student.branch_code)

    try:
        target_academic_year = AcademicYear.objects.get(id=data.academic_year_id)
        target_classroom = ClassRoom.objects.get(id=data.classroom_id)
        target_section = Section.objects.get(id=data.section_id)
    except (AcademicYear.DoesNotExist, ClassRoom.DoesNotExist, Section.DoesNotExist):
        raise HTTPException(404, "Promotion target not found")

    if str(target_academic_year.school.id) != str(student.school.id):
        raise HTTPException(400, "Academic year does not belong to student's school")
    if str(target_classroom.school.id) != str(student.school.id):
        raise HTTPException(400, "Class does not belong to student's school")
    if str(target_section.school.id) != str(student.school.id):
        raise HTTPException(400, "Section does not belong to student's school")
    if str(target_classroom.academic_year.id) != str(target_academic_year.id):
        raise HTTPException(400, "Selected class does not belong to the selected academic year")
    if str(target_section.classroom.id) != str(target_classroom.id):
        raise HTTPException(400, "Selected section does not belong to the selected class")

    branch_name = data.branch_name or student.branch_name
    if branch_code and not branch_name:
        branch_match = next((branch for branch in (student.school.branches or []) if branch.code == branch_code), None)
        branch_name = branch_match.name if branch_match else branch_code

    student.academic_year = target_academic_year
    student.classroom = target_classroom
    student.section = target_section
    student.branch_code = branch_code
    student.branch_name = branch_name
    student.admission_status = "Active"
    student.updated_at = datetime.utcnow()
    if data.remarks:
        existing = (student.remarks or "").strip()
        promotion_note = f"Promoted to {target_classroom.name} / {target_section.name} for {target_academic_year.name}: {data.remarks.strip()}"
        student.remarks = f"{existing}\n{promotion_note}".strip() if existing else promotion_note
    student.save()

    StudentTransport.objects(student=student, is_active=True).update(academic_year=target_academic_year.name)

    return success_response({
        "id": str(student.id),
        "academic_year_id": str(target_academic_year.id),
        "academic_year_name": target_academic_year.name,
        "classroom_id": str(target_classroom.id),
        "classroom_name": target_classroom.name,
        "section_id": str(target_section.id),
        "section_name": target_section.name,
        "branch_code": student.branch_code,
        "branch_name": student.branch_name,
    }, "Student promoted successfully")


@router.post("/import/csv")
async def import_students_csv(
    school_id: str,
    academic_year_id: str,
    file: UploadFile = File(...),
    branch_code: Optional[str] = None,
    branch_name: Optional[str] = None,
    update_existing: bool = Query(False),
    current_user: User = Depends(get_current_user)
):
    try:
        school_id = resolve_school_access(current_user, school_id)
        branch_code = resolve_branch_scope(current_user, branch_code)
        school = School.objects.get(id=school_id)
    except Exception as e:
        raise HTTPException(404, f"Reference not found: {str(e)}")
    ay = _resolve_academic_year(school, academic_year_id)

    raw_bytes = await file.read()
    try:
        decoded = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = raw_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(decoded))
    created = 0
    updated = 0
    skipped = 0
    classes_created = 0
    sections_created = 0
    errors = []
    created_rows = []
    updated_rows = []
    skipped_rows = []
    existing_rows = []
    seen_import_keys = set()
    imported_students_by_key = {}

    for index, row in enumerate(reader, start=2):
        source_admission_no = _csv_value(row, "adm no", "admission no", "admission_no", "adm_no")
        full_name = _csv_value(row, "name", "student name", "student_name") or f"Student {index}"
        class_name, section_name = _resolve_class_section(row)

        class_name = class_name or "Unassigned"
        section_name = section_name or "A"
        classroom, section, class_created, section_created = _ensure_class_and_section(school, ay, class_name, section_name)
        classes_created += 1 if class_created else 0
        sections_created += 1 if section_created else 0

        first_name, middle_name, last_name = _split_name(full_name)
        if not first_name:
            first_name = "Student"
            middle_name = None
            last_name = ""

        address = _csv_value(row, "address", "current_address")
        permanent_address = _csv_value(row, "permanent_address") or address
        contact_no = _csv_value(row, "contact no", "contact_no", "mobile", "phone")
        aadhar_no = _csv_value(row, "aadhar no", "aadhaar no", "aadhar_number", "aadhaar_number")
        srn_no = _csv_value(row, "srn no", "srn_no", "srn")
        father_name = _csv_value(row, "father name", "father_name")
        mother_name = _csv_value(row, "mother name", "mother_name")
        gender = _normalize_gender(_csv_value(row, "gen", "gender") or "Other")
        dob = _parse_import_date(_csv_value(row, "dob", "date of birth", "date_of_birth"))
        admission_date = _parse_import_date(_csv_value(row, "adm date", "admission date", "admission_date"))
        category = _csv_value(row, "category", "caste")

        parent_info = {
            "father_name": father_name,
            "father_phone": contact_no,
            "mother_name": mother_name
        }

        update_data = {
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "date_of_birth": dob,
            "gender": gender,
            "caste": category,
            "nationality": _csv_value(row, "nationality") or "Indian",
            "aadhar_number": aadhar_no,
            "srn_no": srn_no,
            "phone": contact_no,
            "email": _csv_value(row, "email"),
            "current_address": address,
            "permanent_address": permanent_address,
            "current_address_details": _address_details_fallback(None, address),
            "permanent_address_details": _address_details_fallback(None, permanent_address),
            "school": school,
            "academic_year": ay,
            "classroom": classroom,
            "section": section,
            "branch_code": branch_code,
            "branch_name": branch_name or school.name,
            "admission_date": admission_date,
            "admission_type": _csv_value(row, "admission_type") or "New",
            "registration_type": "Manual",
            "updated_at": datetime.utcnow(),
            "remarks": _csv_value(row, "remarks")
        }

        import_key = _student_import_identity_key(
            str(school.id),
            str(ay.id),
            branch_code,
            first_name,
            middle_name,
            last_name,
            father_name,
            mother_name,
            dob,
            contact_no,
            aadhar_no,
            srn_no,
        )

        if import_key in seen_import_keys:
            previous_student = imported_students_by_key.get(import_key)
            skipped += 1
            skipped_rows.append({
                "row": index,
                "name": full_name,
                "source_admission_no": source_admission_no,
                "reason": f"Duplicate row in this upload; already handled as {previous_student.admission_no if previous_student else 'an earlier row'}"
            })
            continue

        seen_import_keys.add(import_key)

        existing_student = _find_matching_import_student(
            school,
            ay,
            branch_code,
            first_name,
            middle_name,
            last_name,
            father_name,
            mother_name,
            dob,
            contact_no,
            aadhar_no,
            srn_no,
        )

        if existing_student:
            _apply_student_import_update(existing_student, update_data, parent_info)
            existing_student.save()
            updated += 1
            imported_students_by_key[import_key] = existing_student
            row_payload = {
                "row": index,
                "admission_no": existing_student.admission_no,
                "source_admission_no": source_admission_no,
                "name": existing_student.full_name,
                "classroom": classroom.name,
                "section": section.name,
                "branch": branch_name or school.name,
                "reason": "Matched existing student data and updated the existing record",
            }
            updated_rows.append(row_payload)
            existing_rows.append(row_payload)
            continue

        admission_no = generate_admission_no(school.code)
        while Student.objects(admission_no=admission_no).first():
            admission_no = generate_admission_no(school.code)

        create_data = {**update_data}
        create_data["admission_date"] = create_data.get("admission_date") or datetime.utcnow()
        student = Student(
            admission_no=admission_no,
            student_id=generate_id("STU"),
            created_at=datetime.utcnow(),
            parent_info=ParentInfo(**parent_info),
            **create_data
        )
        student.save()
        created += 1
        imported_students_by_key[import_key] = student
        created_rows.append({
            "row": index,
            "admission_no": admission_no,
            "source_admission_no": source_admission_no,
            "name": student.full_name,
            "classroom": classroom.name,
            "section": section.name,
            "branch": branch_name or school.name,
        })

    return success_response({
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "existing": len(existing_rows),
        "classes_created": classes_created,
        "sections_created": sections_created,
        "update_existing": update_existing,
        "created_rows": created_rows[:200],
        "updated_rows": updated_rows[:200],
        "skipped_rows": skipped_rows[:200],
        "existing_rows": existing_rows[:200],
        "errors": errors[:100]
    }, "Student CSV import completed")


@router.get("/import/template")
async def download_student_import_template(
    school_id: Optional[str] = None,
    academic_year_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = None
    ay = None
    if school_id:
        school_id = resolve_school_access(current_user, school_id)
        school = School.objects.get(id=school_id)
    if academic_year_id:
        ay = AcademicYear.objects.get(id=academic_year_id)

    sample_class = "LKG"
    sample_section = "A"
    if school and ay:
        classroom = ClassRoom.objects(school=school, academic_year=ay, is_active=True).order_by("numeric_name", "name").first()
        if classroom:
            sample_class = classroom.name
            section = Section.objects(classroom=classroom, is_active=True).order_by("name").first()
            if section:
                sample_section = section.name

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Adm No",
        "Adm Date",
        "Class",
        "Section",
        "Name",
        "Father Name",
        "Mother Name",
        "Gen",
        "DOB",
        "Address",
        "Category",
        "Contact No",
        "Aadhar No",
        "SRN No",
        "Email",
        "Remarks",
    ])
    writer.writerow([
        "1205",
        "04-Jul-2025",
        sample_class,
        sample_section,
        "Radhika Sharma",
        "Rajkumar Sharma",
        "Mamta Sharma",
        "Female",
        "30-Aug-2021",
        "Thada Mode, Alwar, Rajasthan",
        "GENERAL",
        "9602385241",
        "",
        "",
        "",
        "Leave blank if not available",
    ])

    response = StreamingResponse(iter([buffer.getvalue().encode("utf-8")]), media_type="text/csv")
    response.headers["Content-Disposition"] = 'attachment; filename="student_import_template.csv"'
    response.headers["X-Template-Mode"] = "auto-create-class-section"
    return response


@router.post("/import/pdf-to-csv")
async def convert_students_pdf_to_csv(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF file")

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "student_import.pdf")
        with open(pdf_path, "wb") as handle:
            handle.write(await file.read())
        try:
            csv_content, row_count = convert_student_pdf_to_csv(pdf_path)
        except Exception as exc:
            raise HTTPException(500, f"PDF conversion failed: {exc}")

    response = StreamingResponse(iter([csv_content.encode("utf-8")]), media_type="text/csv")
    response.headers["Content-Disposition"] = 'attachment; filename="student_import_from_pdf.csv"'
    response.headers["X-Student-Row-Count"] = str(row_count)
    return response


@router.delete("/{student_id}")
async def delete_student(student_id: str, current_user: User = Depends(get_current_user)):
    try:
        student = Student.objects.get(id=student_id)
        _ensure_student_scope(student, current_user)
        student.update(is_active=False)
        return success_response(message="Student record deactivated")
    except Student.DoesNotExist:
        raise HTTPException(404, "Student not found")


@router.post("/{student_id}/upload-photo")
async def upload_student_photo(
    student_id: str, file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    try:
        student = Student.objects.get(id=student_id)
        _ensure_student_scope(student, current_user)
        file_path = await save_upload_file(file, "student_photos")
        student.update(photo=file_path)
        return success_response({"photo": file_path}, "Photo uploaded successfully")
    except Student.DoesNotExist:
        raise HTTPException(404, "Student not found")

from fastapi import Form
@router.post("/{student_id}/upload-document")
async def upload_student_document(
    student_id: str,
    doc_type: str = Form(...),   # ✅ FIX
    doc_number: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    try:
        student = Student.objects.get(id=student_id)
        _ensure_student_scope(student, current_user)
        file_path = await save_upload_file(file, "student_documents")
        from models.student import StudentDocument
        doc = StudentDocument(doc_type=doc_type, doc_number=doc_number, file_path=file_path)
        student.reload()
        student.documents.append(doc)
        student.save()
        return success_response({"file_path": file_path}, "Document uploaded successfully")
    except Student.DoesNotExist:
        raise HTTPException(404, "Student not found")


# ─── Transfer Certificate ─────────────────────────────────────────────────────

class TCCreate(BaseModel):
    reason: Optional[str] = None
    conduct: str = "Good"
    last_class: Optional[str] = None
    fee_clearance: bool = False
    remarks: Optional[str] = None


@router.post("/{student_id}/transfer-certificate")
async def generate_tc(
    student_id: str, data: TCCreate,
    current_user: User = Depends(get_current_user)
):
    try:
        student = Student.objects.get(id=student_id)
        _ensure_student_scope(student, current_user)
    except Student.DoesNotExist:
        raise HTTPException(404, "Student not found")
    
    tc_no = generate_tc_no(student.school.code)
    tc = TransferCertificate(
        student=student, school=student.school,
        tc_number=tc_no, reason=data.reason,
        conduct=data.conduct,
        last_class=data.last_class or (student.classroom.name if student.classroom else None),
        fee_clearance=data.fee_clearance,
        issued_by=current_user.full_name,
        remarks=data.remarks
    )
    tc.save()
    student.update(admission_status="Transferred")
    
    return success_response({"tc_number": tc_no, "id": str(tc.id)}, "Transfer certificate generated")


@router.get("/{student_id}/transfer-certificate")
async def get_tc(student_id: str, current_user: User = Depends(get_current_user)):
    try:
        student = Student.objects.get(id=student_id)
        _ensure_student_scope(student, current_user)
        tcs = TransferCertificate.objects(student=student).order_by('-created_at')
        result = [{
            "id": str(tc.id), "tc_number": tc.tc_number,
            "issue_date": tc.issue_date.isoformat() if tc.issue_date else None,
            "conduct": tc.conduct, "reason": tc.reason,
            "fee_clearance": tc.fee_clearance, "issued_by": tc.issued_by
        } for tc in tcs]
        return success_response(result)
    except Student.DoesNotExist:
        raise HTTPException(404, "Student not found")
