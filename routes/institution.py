from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from models.institution import (
    School, AcademicYear, ClassRoom, Section, Subject,
    SubjectMapping, GradingSystem, GradeScale, User, Role, Permission, AttendanceGeofence
)
from utils.auth import get_current_user, require_permission, resolve_school_access, resolve_branch_scope
from utils.helpers import success_response, error_response, paginate_query, doc_to_dict, save_upload_file

router = APIRouter(prefix="/institution", tags=["Institution"])


def _normalize_logo_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if value.startswith(("http://", "https://", "/uploads/")):
        return value
    return f"/uploads/{value.lstrip('/')}"


# ─── School CRUD ──────────────────────────────────────────────────────────────

class SchoolCreate(BaseModel):
    name: str
    code: str
    tagline: Optional[str] = None
    affiliation_no: Optional[str] = None
    affiliation_board: Optional[str] = None
    established_year: Optional[int] = None
    type: str = "Private"
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    currency: str = "INR"
    logo: Optional[str] = None
    address: Optional[dict] = None
    branches: List[dict] = []


def _build_address(data: Optional[dict]):
    if not data:
        return None
    from models.institution import Address
    return Address(**data)


def _build_branches(branches: List[dict]):
    from models.institution import Branch
    if len(branches or []) > 3:
        raise HTTPException(400, "Maximum 3 branches are allowed per school")
    result = []
    for branch in branches or []:
        address = _build_address(branch.get("address"))
        result.append(Branch(
            name=branch.get("name"),
            code=branch.get("code"),
            logo=_normalize_logo_url(branch.get("logo")),
            address=address,
            phone=branch.get("phone"),
            email=branch.get("email"),
            principal=branch.get("principal"),
            is_active=branch.get("is_active", True)
        ))
    return result


def _serialize_address(address):
    if not address:
        return None
    return {
        "line1": address.line1,
        "line2": address.line2,
        "city": address.city,
        "state": address.state,
        "country": address.country,
        "pincode": address.pincode,
    }


def _serialize_school(school: School):
    return {
        "id": str(school.id),
        "name": school.name,
        "code": school.code,
        "logo": _normalize_logo_url(school.logo),
        "tagline": school.tagline,
        "affiliation_no": school.affiliation_no,
        "affiliation_board": school.affiliation_board,
        "established_year": school.established_year,
        "type": school.type,
        "phone": school.phone,
        "email": school.email,
        "website": school.website,
        "currency": school.currency,
        "address": _serialize_address(school.address),
        "attendance_geofence": {
            "latitude": school.attendance_geofence.latitude,
            "longitude": school.attendance_geofence.longitude,
            "radius_meters": school.attendance_geofence.radius_meters,
            "enforce_for_staff_attendance": school.attendance_geofence.enforce_for_staff_attendance,
            "updated_at": school.attendance_geofence.updated_at.isoformat() if school.attendance_geofence and school.attendance_geofence.updated_at else None
        } if school.attendance_geofence else None,
        "branches": [{
            "name": branch.name,
            "code": branch.code,
            "logo": _normalize_logo_url(branch.logo),
            "phone": branch.phone,
            "email": branch.email,
            "principal": branch.principal,
            "is_active": branch.is_active,
            "address": _serialize_address(branch.address),
        } for branch in (school.branches or [])]
    }


@router.post("/school")
async def create_school(data: SchoolCreate, current_user: User = Depends(get_current_user)):
    if School.objects(code=data.code).first():
        raise HTTPException(400, "School code already exists")
    payload = data.model_dump()
    payload["logo"] = _normalize_logo_url(payload.get("logo"))
    payload["address"] = _build_address(payload.get("address"))
    payload["branches"] = _build_branches(payload.get("branches", []))
    payload["is_multi_branch"] = len(payload["branches"]) > 0
    school = School(**payload)
    school.save()
    return success_response({"id": str(school.id), "name": school.name}, "School created successfully")


@router.get("/school")
async def list_schools(current_user: User = Depends(get_current_user)):
    schools = School.objects(is_active=True)
    result = []
    for s in schools:
        result.append({
            "id": str(s.id), "name": s.name, "code": s.code,
            "type": s.type, "affiliation_board": s.affiliation_board,
            "phone": s.phone, "email": s.email, "logo": s.logo,
            "branch_count": len(s.branches or [])
        })
    return success_response(result)


@router.get("/school/{school_id}")
async def get_school(school_id: str, current_user: User = Depends(get_current_user)):
    try:
        school = School.objects.get(id=school_id)
        return success_response(_serialize_school(school))
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")


@router.put("/school/{school_id}")
async def update_school(school_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        school = School.objects.get(id=school_id)
        data.pop('id', None)
        if 'logo' in data:
            data['logo'] = _normalize_logo_url(data.get('logo'))
        if 'address' in data:
            data['address'] = _build_address(data.get('address'))
        if 'attendance_geofence' in data:
            geofence = data.get('attendance_geofence') or {}
            latitude = geofence.get('latitude')
            longitude = geofence.get('longitude')
            radius_meters = geofence.get('radius_meters', 150)
            enforce = geofence.get('enforce_for_staff_attendance', False)
            if latitude in ('', None) or longitude in ('', None):
                data['attendance_geofence'] = None
            else:
                data['attendance_geofence'] = AttendanceGeofence(
                    latitude=float(latitude),
                    longitude=float(longitude),
                    radius_meters=float(radius_meters or 150),
                    enforce_for_staff_attendance=bool(enforce),
                    updated_at=datetime.utcnow()
                )
        if 'branches' in data:
            data['branches'] = _build_branches(data.get('branches', []))
            data['is_multi_branch'] = len(data['branches']) > 0
        data['updated_at'] = datetime.utcnow()
        school.update(**data)
        return success_response(message="School updated successfully")
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")


@router.post("/upload-logo")
async def upload_institution_logo(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    path = await save_upload_file(file, "institution_logos")
    return success_response({
        "file_path": path,
        "file_url": f"/uploads/{path}"
    }, "Logo uploaded successfully")


# ─── Academic Year ────────────────────────────────────────────────────────────

class AcademicYearCreate(BaseModel):
    school_id: str
    name: str
    start_date: datetime
    end_date: datetime
    is_current: bool = False


@router.post("/academic-year")
async def create_academic_year(data: AcademicYearCreate, current_user: User = Depends(get_current_user)):
    try:
        school = School.objects.get(id=data.school_id)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")
    
    if data.is_current:
        AcademicYear.objects(school=school, is_current=True).update(is_current=False)
    
    ay = AcademicYear(
        school=school, name=data.name,
        start_date=data.start_date, end_date=data.end_date,
        is_current=data.is_current
    )
    ay.save()
    return success_response({"id": str(ay.id), "name": ay.name}, "Academic year created")


@router.get("/academic-year")
async def list_academic_years(school_id: str, current_user: User = Depends(get_current_user)):
    try:
        school = School.objects.get(id=school_id)
        years = AcademicYear.objects(school=school, is_active=True).order_by('-start_date')
        result = [{
            "id": str(y.id), "name": y.name,
            "start_date": y.start_date.isoformat() if y.start_date else None,
            "end_date": y.end_date.isoformat() if y.end_date else None,
            "is_current": y.is_current
        } for y in years]
        return success_response(result)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")


@router.put("/academic-year/{year_id}")
async def update_academic_year(year_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        ay = AcademicYear.objects.get(id=year_id)
        if data.get('is_current'):
            AcademicYear.objects(school=ay.school, is_current=True).update(is_current=False)
        data.pop('id', None)
        data.pop('school_id', None)
        if data.get('start_date'):
            data['start_date'] = datetime.fromisoformat(str(data['start_date']).replace('Z', '+00:00'))
        if data.get('end_date'):
            data['end_date'] = datetime.fromisoformat(str(data['end_date']).replace('Z', '+00:00'))
        ay.update(**data)
        return success_response(message="Academic year updated")
    except AcademicYear.DoesNotExist:
        raise HTTPException(404, "Academic year not found")


@router.delete("/academic-year/{year_id}")
async def delete_academic_year(year_id: str, current_user: User = Depends(get_current_user)):
    try:
        ay = AcademicYear.objects.get(id=year_id)
        ay.update(is_active=False, is_current=False)
        return success_response(message="Academic year deleted")
    except AcademicYear.DoesNotExist:
        raise HTTPException(404, "Academic year not found")


@router.patch("/academic-year/{year_id}/set-current")
async def set_current_year(year_id: str, current_user: User = Depends(get_current_user)):
    try:
        ay = AcademicYear.objects.get(id=year_id)
        AcademicYear.objects(school=ay.school, is_current=True).update(is_current=False)
        ay.update(is_current=True)
        return success_response(message="Academic year set as current")
    except AcademicYear.DoesNotExist:
        raise HTTPException(404, "Academic year not found")


# ─── ClassRoom ────────────────────────────────────────────────────────────────

class ClassRoomCreate(BaseModel):
    school_id: str
    academic_year_id: str
    name: str
    numeric_name: Optional[int] = None
    class_fee: float = 0
    stream_id: Optional[str] = None
    sections: List[str] = []


@router.post("/class")
async def create_class(data: ClassRoomCreate, current_user: User = Depends(get_current_user)):
    try:
        school = School.objects.get(id=data.school_id)
        ay = AcademicYear.objects.get(id=data.academic_year_id)
    except Exception:
        raise HTTPException(404, "School or Academic Year not found")
    
    classroom = ClassRoom(
        school=school, academic_year=ay,
        name=data.name, numeric_name=data.numeric_name,
        class_fee=data.class_fee or 0,
        sections=data.sections
    )
    classroom.save()
    
    # Auto-create sections
    for sec_name in data.sections:
        sec = Section(school=school, academic_year=ay, classroom=classroom, name=sec_name)
        sec.save()
    
    return success_response({"id": str(classroom.id), "name": classroom.name}, "Class created successfully")


@router.get("/class")
async def list_classes(
    school_id: str, academic_year_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    try:
        school = School.objects.get(id=school_id)
        query = ClassRoom.objects(school=school, is_active=True)
        if academic_year_id:
            ay = AcademicYear.objects.get(id=academic_year_id)
            query = query.filter(academic_year=ay)
        
        result = []
        for c in query.order_by('numeric_name'):
            sections = Section.objects(classroom=c, is_active=True)
            result.append({
                "id": str(c.id), "name": c.name,
                "numeric_name": c.numeric_name,
                "class_fee": c.class_fee or 0,
                "sections": [{"id": str(s.id), "name": s.name} for s in sections]
            })
        return success_response(result)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")


@router.put("/class/{classroom_id}")
async def update_class(classroom_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        classroom = ClassRoom.objects.get(id=classroom_id)
        data.pop('id', None)
        data.pop('school_id', None)
        data.pop('academic_year_id', None)
        section_names = data.pop('sections', None)
        classroom.update(**{k: v for k, v in data.items() if k in ['name', 'numeric_name', 'class_fee']})
        if section_names is not None:
            Section.objects(classroom=classroom, is_active=True).update(is_active=False)
            for sec_name in section_names:
                if not sec_name:
                    continue
                Section(
                    school=classroom.school,
                    academic_year=classroom.academic_year,
                    classroom=classroom,
                    name=sec_name
                ).save()
        return success_response(message="Class updated")
    except ClassRoom.DoesNotExist:
        raise HTTPException(404, "Class not found")


@router.delete("/class/{classroom_id}")
async def delete_class(classroom_id: str, current_user: User = Depends(get_current_user)):
    try:
        classroom = ClassRoom.objects.get(id=classroom_id)
        classroom.update(is_active=False)
        Section.objects(classroom=classroom, is_active=True).update(is_active=False)
        return success_response(message="Class deleted")
    except ClassRoom.DoesNotExist:
        raise HTTPException(404, "Class not found")


# ─── Section ──────────────────────────────────────────────────────────────────

@router.get("/section")
async def list_sections(
    classroom_id: str,
    current_user: User = Depends(get_current_user)
):
    try:
        classroom = ClassRoom.objects.get(id=classroom_id)
        sections = Section.objects(classroom=classroom, is_active=True)
        result = [{"id": str(s.id), "name": s.name, "room_number": s.room_number} for s in sections]
        return success_response(result)
    except ClassRoom.DoesNotExist:
        raise HTTPException(404, "Class not found")


# ─── Subject CRUD ─────────────────────────────────────────────────────────────

class SubjectCreate(BaseModel):
    school_id: str
    name: str
    code: str
    description: Optional[str] = None
    subject_type: str = "Theory"
    max_theory_marks: float = 100
    max_practical_marks: float = 0
    passing_marks: float = 33
    is_optional: bool = False


class SubjectMappingSave(BaseModel):
    school_id: str
    academic_year_id: str
    classroom_id: str
    section_id: Optional[str] = None
    subject_ids: List[str] = []


@router.post("/subject")
async def create_subject(data: SubjectCreate, current_user: User = Depends(get_current_user)):
    try:
        school = School.objects.get(id=data.school_id)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")
    
    if Subject.objects(school=school, code=data.code).first():
        raise HTTPException(400, "Subject code already exists")
    
    subject = Subject(school=school, **{k: v for k, v in data.model_dump().items() if k != 'school_id'})
    subject.save()
    return success_response({"id": str(subject.id), "name": subject.name}, "Subject created")


def _serialize_subject(s: Subject):
    return {
        "id": str(s.id), "name": s.name, "code": s.code,
        "subject_type": s.subject_type, "max_theory_marks": s.max_theory_marks,
        "max_practical_marks": s.max_practical_marks, "passing_marks": s.passing_marks,
        "is_optional": s.is_optional
    }


def _mapped_subjects(school: School, academic_year: AcademicYear, classroom: ClassRoom, section: Optional[Section] = None):
    mapping_query = SubjectMapping.objects(
        school=school,
        academic_year=academic_year,
        classroom=classroom,
        is_active=True
    )
    mappings = list(mapping_query.filter(section=section)) if section else list(mapping_query.filter(section=None))
    if section:
        mappings += list(mapping_query.filter(section=None))
    subject_ids = []
    subjects = []
    for mapping in mappings:
        if mapping.subject and str(mapping.subject.id) not in subject_ids and mapping.subject.is_active:
            subject_ids.append(str(mapping.subject.id))
            subjects.append(mapping.subject)
    return subjects


@router.get("/subject")
async def list_subjects(
    school_id: str,
    academic_year_id: Optional[str] = None,
    classroom_id: Optional[str] = None,
    section_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    try:
        school = School.objects.get(id=school_id)
        if classroom_id:
            if not academic_year_id:
                raise HTTPException(400, "academic_year_id is required for class-wise subjects")
            ay = AcademicYear.objects.get(id=academic_year_id)
            classroom = ClassRoom.objects.get(id=classroom_id)
            section = Section.objects.get(id=section_id) if section_id else None
            subjects = _mapped_subjects(school, ay, classroom, section)
        else:
            subjects = Subject.objects(school=school, is_active=True).order_by('name')
        result = [_serialize_subject(s) for s in subjects]
        return success_response(result)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")


@router.get("/subject-mapping")
async def get_subject_mapping(
    school_id: str,
    academic_year_id: str,
    classroom_id: str,
    section_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    ay = AcademicYear.objects.get(id=academic_year_id)
    classroom = ClassRoom.objects.get(id=classroom_id)
    section = Section.objects.get(id=section_id) if section_id else None
    mapped = _mapped_subjects(school, ay, classroom, section)
    return success_response({
        "subject_ids": [str(subject.id) for subject in mapped],
        "subjects": [_serialize_subject(subject) for subject in mapped]
    })


@router.post("/subject-mapping")
async def save_subject_mapping(data: SubjectMappingSave, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data.school_id)
    ay = AcademicYear.objects.get(id=data.academic_year_id)
    classroom = ClassRoom.objects.get(id=data.classroom_id)
    section = Section.objects.get(id=data.section_id) if data.section_id else None

    existing_query = SubjectMapping.objects(
        school=school,
        academic_year=ay,
        classroom=classroom,
        section=section,
        is_active=True
    )
    existing_query.update(is_active=False)

    saved = 0
    for subject_id in data.subject_ids:
        subject = Subject.objects(id=subject_id, school=school, is_active=True).first()
        if not subject:
            continue
        mapping = SubjectMapping.objects(
            school=school,
            academic_year=ay,
            classroom=classroom,
            section=section,
            subject=subject
        ).first()
        if mapping:
            mapping.update(is_active=True)
        else:
            SubjectMapping(
                school=school,
                academic_year=ay,
                classroom=classroom,
                section=section,
                subject=subject
            ).save()
        saved += 1
    return success_response({"saved": saved}, "Class-wise subjects saved")


@router.put("/subject/{subject_id}")
async def update_subject(subject_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        subject = Subject.objects.get(id=subject_id)
        data.pop('id', None)
        data.pop('school_id', None)
        subject.update(**data)
        return success_response(message="Subject updated")
    except Subject.DoesNotExist:
        raise HTTPException(404, "Subject not found")


@router.delete("/subject/{subject_id}")
async def delete_subject(subject_id: str, current_user: User = Depends(get_current_user)):
    try:
        subject = Subject.objects.get(id=subject_id)
        subject.update(is_active=False)
        return success_response(message="Subject deleted")
    except Subject.DoesNotExist:
        raise HTTPException(404, "Subject not found")


# ─── Grading System ───────────────────────────────────────────────────────────

@router.post("/grading-system")
async def create_grading_system(data: dict, current_user: User = Depends(get_current_user)):
    try:
        school = School.objects.get(id=data['school_id'])
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")
    
    if data.get('is_default'):
        GradingSystem.objects(school=school, is_default=True).update(is_default=False)
    
    gs = GradingSystem(
        school=school,
        name=data['name'],
        grading_type=data.get('grading_type', 'Marks'),
        is_default=data.get('is_default', False)
    )
    
    for scale in data.get('scales', []):
        gs.scales.append(GradeScale(**scale))
    
    gs.save()
    return success_response({"id": str(gs.id)}, "Grading system created")


@router.get("/grading-system")
async def list_grading_systems(school_id: str, current_user: User = Depends(get_current_user)):
    try:
        school = School.objects.get(id=school_id)
        systems = GradingSystem.objects(school=school, is_active=True)
        result = []
        for gs in systems:
            result.append({
                "id": str(gs.id), "name": gs.name,
                "grading_type": gs.grading_type,
                "is_default": gs.is_default,
                "scales": [{"grade": s.grade, "min": s.min_marks, "max": s.max_marks, "gp": s.grade_point} for s in gs.scales]
            })
        return success_response(result)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")


@router.put("/grading-system/{grading_id}")
async def update_grading_system(grading_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        grading = GradingSystem.objects.get(id=grading_id, is_active=True)
    except GradingSystem.DoesNotExist:
        raise HTTPException(404, "Grading system not found")

    school_id = resolve_school_access(current_user, data.get('school_id') or (str(grading.school.id) if grading.school else None))
    if grading.school and str(grading.school.id) != school_id:
        raise HTTPException(403, "Access denied")

    if data.get('is_default'):
        GradingSystem.objects(school=grading.school, is_default=True, id__ne=grading.id).update(is_default=False)

    grading.name = data.get('name', grading.name)
    grading.grading_type = data.get('grading_type', grading.grading_type)
    grading.is_default = data.get('is_default', grading.is_default)
    grading.scales = [GradeScale(**scale) for scale in data.get('scales', [])] or grading.scales
    grading.updated_at = datetime.utcnow()
    grading.save()
    return success_response({"id": str(grading.id)}, "Grading system updated")


@router.delete("/grading-system/{grading_id}")
async def delete_grading_system(grading_id: str, current_user: User = Depends(get_current_user)):
    try:
        grading = GradingSystem.objects.get(id=grading_id, is_active=True)
        resolve_school_access(current_user, str(grading.school.id) if grading.school else None)
        grading.update(is_active=False)
        return success_response(message="Grading system deleted")
    except GradingSystem.DoesNotExist:
        raise HTTPException(404, "Grading system not found")


# ─── Dashboard Stats ──────────────────────────────────────────────────────────

@router.get("/dashboard/{school_id}")
async def get_dashboard_stats(school_id: str, branch_code: Optional[str] = None, current_user: User = Depends(get_current_user)):
    from models.student import Student
    from models.staff import Staff
    from models.fees import FeeInvoice
    from models.attendance import StudentAttendance
    
    try:
        school_id = resolve_school_access(current_user, school_id)
        branch_code = resolve_branch_scope(current_user, branch_code)
        school = School.objects.get(id=school_id)
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        student_query = Student.objects(school=school, is_active=True, admission_status="Active")
        if branch_code:
            student_query = student_query.filter(branch_code=branch_code)

        all_invoice_query = FeeInvoice.objects(school=school)
        fee_query = FeeInvoice.objects(school=school, status__in=["Pending", "Partial", "Overdue"])
        if branch_code:
            branch_students = list(student_query)
            fee_query = fee_query.filter(student__in=branch_students)
            all_invoice_query = all_invoice_query.filter(student__in=branch_students)

        recent_students = []
        for student in student_query.order_by('-created_at')[:5]:
            recent_students.append({
                "id": str(student.id),
                "full_name": student.full_name,
                "first_name": student.first_name,
                "admission_no": student.admission_no,
                "classroom": student.classroom.name if student.classroom else None,
                "classroom_name": student.classroom.name if student.classroom else None,
                "section_name": student.section.name if student.section else None,
                "branch_name": student.branch_name,
            })

        total_billed = sum(inv.net_amount or 0 for inv in all_invoice_query)
        total_collected = sum(inv.paid_amount or 0 for inv in all_invoice_query)
        total_due = sum(inv.balance_amount or 0 for inv in all_invoice_query)

        stats = {
            "total_students": student_query.count(),
            "total_staff": Staff.objects(school=school, is_active=True).count(),
            "total_classes": ClassRoom.objects(school=school, is_active=True).count(),
            "pending_fees": fee_query.count(),
            "today_student_attendance": StudentAttendance.objects(school=school, date=today).count(),
            "fee_summary": {
                "total_billed": total_billed,
                "total_collected": total_collected,
                "total_due": total_due,
                "collection_rate": round(total_collected / total_billed * 100, 2) if total_billed > 0 else 0
            },
            "recent_students": recent_students
        }
        return success_response(stats)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")
