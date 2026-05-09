from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
from math import radians, cos, sin, asin, sqrt
from models.attendance import StudentAttendance, StaffAttendance, Holiday, AttendanceSummary, StudentAttendanceRecord, StaffAttendanceRecord
from models.institution import School, AcademicYear, ClassRoom, Section, Subject, User
from models.student import Student
from models.staff import Staff, TeacherAssignment
from utils.auth import get_current_user, resolve_school_access
from utils.helpers import success_response

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return 6371000 * c


def _recount_staff(records: List[StaffAttendanceRecord]):
    present_count = sum(1 for record in records if record.status in ["Present", "Late", "Half-Day"])
    absent_count = sum(1 for record in records if record.status == "Absent")
    on_leave_count = sum(1 for record in records if record.status == "On-Leave")
    return present_count, absent_count, on_leave_count


def _serialize_staff_record(record: StaffAttendanceRecord):
    return {
        "staff_id": str(record.staff.id) if record.staff else None,
        "staff_name": record.staff_name or (record.staff.full_name if record.staff else None),
        "designation": record.designation or (record.staff.designation if record.staff else None),
        "status": record.status,
        "check_in_time": record.check_in_time,
        "check_out_time": record.check_out_time,
        "remarks": record.remarks,
        "marked_via": record.marked_via,
        "mark_latitude": record.mark_latitude,
        "mark_longitude": record.mark_longitude,
        "location_accuracy_meters": record.location_accuracy_meters,
        "distance_from_school_meters": round(record.distance_from_school_meters or 0, 2) if record.distance_from_school_meters is not None else None,
        "location_status": record.location_status,
        "location_note": record.location_note,
    }


def _normalize_day(value: Optional[datetime] = None) -> datetime:
    base = value or datetime.utcnow()
    return base.replace(hour=0, minute=0, second=0, microsecond=0)


def _role_name(user: User) -> str:
    return str(user.role.name if user.role else "").strip().lower()


def _is_teacher_like_user(user: User) -> bool:
    role_name = _role_name(user)
    return "teacher" in role_name or "faculty" in role_name


def _current_staff_profile(user: User, school: School) -> Optional[Staff]:
    return Staff.objects(user_account=user, school=school, is_active=True).first()


def _ensure_teacher_student_attendance_scope(
    current_user: User,
    school: School,
    academic_year: Optional[AcademicYear],
    classroom: ClassRoom,
    section: Section,
) -> None:
    if not _is_teacher_like_user(current_user):
        return

    staff = _current_staff_profile(current_user, school)
    if not staff:
        raise HTTPException(403, "This teacher login is not linked to an active staff profile")

    query = TeacherAssignment.objects(
        school=school,
        teacher=staff,
        classroom=classroom,
        section=section,
        is_active=True,
    )
    if academic_year:
        query = query.filter(academic_year=academic_year)
    if not query.first():
        raise HTTPException(403, "You can mark attendance only for classes assigned to you")


class AttendanceRecord(BaseModel):
    student_id: str
    status: str  # Present, Absent, Late, Excused
    remarks: Optional[str] = None
    check_in_time: Optional[str] = None


class MarkStudentAttendance(BaseModel):
    school_id: str
    academic_year_id: str
    classroom_id: str
    section_id: str
    date: datetime
    subject_id: Optional[str] = None
    period_no: Optional[int] = None
    attendance_type: str = "Daily"
    records: List[AttendanceRecord]


@router.post("/student/mark")
async def mark_student_attendance(
    data: MarkStudentAttendance,
    current_user: User = Depends(get_current_user)
):
    try:
        school = School.objects.get(id=data.school_id)
        ay = AcademicYear.objects.get(id=data.academic_year_id)
        classroom = ClassRoom.objects.get(id=data.classroom_id)
        section = Section.objects.get(id=data.section_id)
    except Exception as e:
        raise HTTPException(404, f"Reference not found: {str(e)}")
    resolve_school_access(current_user, str(school.id))
    _ensure_teacher_student_attendance_scope(current_user, school, ay, classroom, section)
    
    att_date = data.date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Check if already marked
    existing = StudentAttendance.objects(
        school=school, classroom=classroom, section=section,
        date=att_date, period_no=data.period_no
    ).first()
    
    records = []
    present_count = 0
    absent_count = 0
    late_count = 0
    
    for rec in data.records:
        try:
            student = Student.objects.get(id=rec.student_id)
            record = StudentAttendanceRecord(
                student=student,
                student_name=student.full_name,
                roll_no=student.roll_no,
                status=rec.status,
                remarks=rec.remarks,
                check_in_time=rec.check_in_time
            )
            records.append(record)
            if rec.status in ["Present", "Late", "Half-Day"]:
                present_count += 1
            elif rec.status == "Absent":
                absent_count += 1
            elif rec.status == "Late":
                late_count += 1
        except Student.DoesNotExist:
            continue
    
    if existing:
        existing.records = records
        existing.present_count = present_count
        existing.absent_count = absent_count
        existing.late_count = late_count
        existing.marked_by = current_user.full_name
        existing.marked_at = datetime.utcnow()
        existing.save()
        attendance = existing
    else:
        subject = None
        if data.subject_id:
            try:
                subject = Subject.objects.get(id=data.subject_id)
            except Subject.DoesNotExist:
                pass
        
        attendance = StudentAttendance(
            school=school, academic_year=ay,
            classroom=classroom, section=section,
            subject=subject,
            date=att_date, period_no=data.period_no,
            attendance_type=data.attendance_type,
            records=records,
            total_students=len(records),
            present_count=present_count,
            absent_count=absent_count,
            late_count=late_count,
            marked_by=current_user.full_name
        )
        attendance.save()
    
    return success_response({
        "id": str(attendance.id),
        "total": len(records),
        "present": present_count,
        "absent": absent_count,
        "late": late_count
    }, "Attendance marked successfully")


@router.get("/student")
async def get_student_attendance(
    school_id: str,
    classroom_id: str,
    section_id: str,
    date: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    classroom = ClassRoom.objects.get(id=classroom_id)
    section = Section.objects.get(id=section_id)
    resolve_school_access(current_user, str(school.id))
    _ensure_teacher_student_attendance_scope(current_user, school, None, classroom, section)
    
    query = StudentAttendance.objects(school=school, classroom=classroom, section=section)
    
    if date:
        dt = datetime.fromisoformat(date).replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.filter(date=dt)
    elif from_date and to_date:
        fd = datetime.fromisoformat(from_date)
        td = datetime.fromisoformat(to_date)
        query = query.filter(date__gte=fd, date__lte=td)
    
    result = []
    for att in query.order_by('-date'):
        records = [{
            "student_id": str(r.student.id) if r.student else None,
            "student_name": r.student_name,
            "roll_no": r.roll_no,
            "status": r.status,
            "remarks": r.remarks,
            "check_in_time": r.check_in_time
        } for r in att.records]
        
        result.append({
            "id": str(att.id),
            "date": att.date.isoformat(),
            "attendance_type": att.attendance_type,
            "total_students": att.total_students,
            "present_count": att.present_count,
            "absent_count": att.absent_count,
            "late_count": att.late_count,
            "records": records,
            "marked_by": att.marked_by,
            "marked_at": att.marked_at.isoformat() if att.marked_at else None
        })
    
    return success_response(result)


@router.get("/student/report/{student_id}")
async def get_student_attendance_report(
    student_id: str,
    academic_year_id: Optional[str] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    current_user: User = Depends(get_current_user)
):
    try:
        student = Student.objects.get(id=student_id)
    except Student.DoesNotExist:
        raise HTTPException(404, "Student not found")
    
    # Get all attendance for this student
    query = StudentAttendance.objects(
        school=student.school,
        classroom=student.classroom,
        section=student.section
    )
    
    if month and year:
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)
        query = query.filter(date__gte=start, date__lt=end)
    
    total_days = 0
    present_days = 0
    absent_days = 0
    late_days = 0
    daily_records = []
    
    for att in query.order_by('date'):
        for rec in att.records:
            if rec.student and str(rec.student.id) == student_id:
                total_days += 1
                if rec.status == "Present":
                    present_days += 1
                elif rec.status == "Absent":
                    absent_days += 1
                elif rec.status == "Late":
                    late_days += 1
                    present_days += 1  # Late counts as present
                
                daily_records.append({
                    "date": att.date.isoformat(),
                    "status": rec.status,
                    "remarks": rec.remarks
                })
                break
    
    attendance_pct = (present_days / total_days * 100) if total_days > 0 else 0
    
    return success_response({
        "student_id": student_id,
        "student_name": student.full_name,
        "total_working_days": total_days,
        "present_days": present_days,
        "absent_days": absent_days,
        "late_days": late_days,
        "attendance_percentage": round(attendance_pct, 2),
        "daily_records": daily_records
    })


@router.get("/summary/{school_id}")
async def get_attendance_summary(
    school_id: str,
    date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    target_date = datetime.fromisoformat(date).replace(hour=0, minute=0, second=0, microsecond=0) if date else datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    student_atts = StudentAttendance.objects(school=school, date=target_date)
    staff_att = StaffAttendance.objects(school=school, date=target_date).first()

    total_students_marked = sum(att.total_students or 0 for att in student_atts)
    total_present = sum(att.present_count or 0 for att in student_atts)
    total_absent = sum(att.absent_count or 0 for att in student_atts)
    total_late = sum(att.late_count or 0 for att in student_atts)

    staff_present = staff_att.present_count if staff_att else 0
    staff_absent = staff_att.absent_count if staff_att else 0
    staff_on_leave = staff_att.on_leave_count if staff_att else 0
    total_staff_marked = staff_att.total_staff if staff_att else 0

    return success_response({
        "date": target_date.isoformat(),
        "students": {
            "total_marked": total_students_marked,
            "present": total_present,
            "absent": total_absent,
            "late": total_late,
            "attendance_percentage": round(total_present / total_students_marked * 100, 2) if total_students_marked else 0
        },
        "staff": {
            "total_marked": total_staff_marked,
            "present": staff_present,
            "absent": staff_absent,
            "on_leave": staff_on_leave
        }
    })


# ─── Staff Attendance ─────────────────────────────────────────────────────────

class StaffAttRecord(BaseModel):
    staff_id: str
    status: str
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    remarks: Optional[str] = None


class MarkStaffAttendance(BaseModel):
    school_id: str
    date: datetime
    records: List[StaffAttRecord]


class StaffSelfCheckin(BaseModel):
    school_id: str
    date: Optional[datetime] = None
    status: str = "Present"
    check_in_time: Optional[str] = None
    remarks: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy_meters: Optional[float] = None


class StaffSelfCheckout(BaseModel):
    school_id: str
    date: Optional[datetime] = None
    check_out_time: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/staff/mark")
async def mark_staff_attendance(
    data: MarkStaffAttendance,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=data.school_id)
    att_date = data.date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    existing = StaffAttendance.objects(school=school, date=att_date).first()
    
    records = []
    present_count = absent_count = on_leave_count = 0
    
    for rec in data.records:
        try:
            staff = Staff.objects.get(id=rec.staff_id)
            record = StaffAttendanceRecord(
                staff=staff,
                staff_name=staff.full_name,
                designation=staff.designation,
                status=rec.status,
                check_in_time=rec.check_in_time,
                check_out_time=rec.check_out_time,
                remarks=rec.remarks,
                marked_via="Admin",
                location_status="Admin Override"
            )
            records.append(record)
            if rec.status == "Present":
                present_count += 1
            elif rec.status == "Absent":
                absent_count += 1
            elif rec.status == "On-Leave":
                on_leave_count += 1
        except Staff.DoesNotExist:
            continue
    
    if existing:
        existing.records = records
        existing.total_staff = len(records)
        existing.present_count = present_count
        existing.absent_count = absent_count
        existing.on_leave_count = on_leave_count
        existing.marked_by = current_user.full_name
        existing.save()
    else:
        att = StaffAttendance(
            school=school, date=att_date,
            records=records, total_staff=len(records),
            present_count=present_count,
            absent_count=absent_count,
            on_leave_count=on_leave_count,
            marked_by=current_user.full_name
        )
        att.save()
    
    return success_response({
        "total": len(records),
        "present": present_count,
        "absent": absent_count,
        "on_leave": on_leave_count
    }, "Staff attendance marked")


@router.get("/staff")
async def get_staff_attendance(
    school_id: str,
    date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school_id = resolve_school_access(current_user, school_id)
    school = School.objects.get(id=school_id)
    target_date = datetime.fromisoformat(date).replace(hour=0, minute=0, second=0, microsecond=0) if date else datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    attendance = StaffAttendance.objects(school=school, date=target_date).first()
    if not attendance:
        return success_response({
            "date": target_date.isoformat(),
            "total_staff": 0,
            "present_count": 0,
            "absent_count": 0,
            "on_leave_count": 0,
            "records": []
        })
    return success_response({
        "id": str(attendance.id),
        "date": attendance.date.isoformat(),
        "total_staff": attendance.total_staff or 0,
        "present_count": attendance.present_count or 0,
        "absent_count": attendance.absent_count or 0,
        "on_leave_count": attendance.on_leave_count or 0,
        "marked_by": attendance.marked_by,
        "marked_at": attendance.marked_at.isoformat() if attendance.marked_at else None,
        "records": [_serialize_staff_record(record) for record in (attendance.records or [])]
    })


@router.get("/staff/self")
async def get_my_staff_attendance(
    school_id: str,
    date: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user)
):
    school_id = resolve_school_access(current_user, school_id)
    school = School.objects.get(id=school_id)
    staff = Staff.objects(user_account=current_user, school=school, is_active=True).first()
    if not staff:
        raise HTTPException(403, "This user is not linked to any active staff profile")

    target_date = _normalize_day(date)
    attendance = StaffAttendance.objects(school=school, date=target_date).first()
    if not attendance:
        return success_response({
            "date": target_date.isoformat(),
            "staff_id": str(staff.id),
            "record": None
        })

    record = next(
        (item for item in (attendance.records or []) if item.staff and str(item.staff.id) == str(staff.id)),
        None
    )
    return success_response({
        "date": target_date.isoformat(),
        "staff_id": str(staff.id),
        "record": _serialize_staff_record(record) if record else None
    })


@router.get("/teacher/classes")
async def get_my_attendance_classes(
    school_id: str,
    academic_year_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school_id = resolve_school_access(current_user, school_id)
    school = School.objects.get(id=school_id)
    staff = _current_staff_profile(current_user, school)
    if not staff:
        raise HTTPException(403, "This teacher login is not linked to any active staff profile")

    query = TeacherAssignment.objects(school=school, teacher=staff, is_active=True)
    if academic_year_id:
        ay = AcademicYear.objects.get(id=academic_year_id)
        query = query.filter(academic_year=ay)

    seen = set()
    classes = []
    for assignment in query.order_by("created_at"):
        if not assignment.classroom or not assignment.section:
            continue
        key = f"{assignment.classroom.id}:{assignment.section.id}"
        if key in seen:
            continue
        seen.add(key)
        classes.append({
            "classroom_id": str(assignment.classroom.id),
            "classroom_name": assignment.classroom.name,
            "section_id": str(assignment.section.id),
            "section_name": assignment.section.name,
            "academic_year_id": str(assignment.academic_year.id) if assignment.academic_year else None,
            "is_class_teacher": bool(assignment.is_class_teacher),
        })

    return success_response(classes)


@router.post("/staff/self-checkin")
async def mark_my_staff_attendance(
    data: StaffSelfCheckin,
    current_user: User = Depends(get_current_user)
):
    school_id = resolve_school_access(current_user, data.school_id)
    school = School.objects.get(id=school_id)
    staff = Staff.objects(user_account=current_user, school=school, is_active=True).first()
    if not staff:
        raise HTTPException(403, "This user is not linked to any active staff profile")

    geofence = getattr(school, "attendance_geofence", None)
    enforce_geofence = bool(geofence and geofence.enforce_for_staff_attendance and geofence.latitude is not None and geofence.longitude is not None)
    if enforce_geofence and (data.latitude is None or data.longitude is None):
        raise HTTPException(400, "Location is required for staff attendance at this school")

    distance_from_school = None
    location_status = "Not Checked"
    location_note = None
    if geofence and geofence.latitude is not None and geofence.longitude is not None and data.latitude is not None and data.longitude is not None:
        distance_from_school = _haversine_meters(float(data.latitude), float(data.longitude), float(geofence.latitude), float(geofence.longitude))
        allowed_radius = float(geofence.radius_meters or 150)
        if distance_from_school <= allowed_radius:
            location_status = "Within Range"
            location_note = f"Attendance marked within {allowed_radius:.0f}m school radius"
        else:
            location_status = "Outside Range"
            location_note = f"Outside allowed school radius by {max(distance_from_school - allowed_radius, 0):.0f}m"
            if enforce_geofence:
                raise HTTPException(400, location_note)

    att_date = _normalize_day(data.date)
    today = _normalize_day()
    if att_date != today:
        raise HTTPException(400, "Self attendance can only be marked for the current day")
    attendance = StaffAttendance.objects(school=school, date=att_date).first()
    check_in_time = data.check_in_time or datetime.now().strftime("%H:%M")
    record = StaffAttendanceRecord(
        staff=staff,
        staff_name=staff.full_name,
        designation=staff.designation,
        status=data.status,
        check_in_time=check_in_time,
        remarks=data.remarks,
        marked_via="Teacher Panel",
        mark_latitude=data.latitude,
        mark_longitude=data.longitude,
        location_accuracy_meters=data.accuracy_meters,
        distance_from_school_meters=distance_from_school,
        location_status=location_status,
        location_note=location_note
    )

    if attendance:
        records = []
        replaced = False
        for existing_record in attendance.records or []:
            if existing_record.staff and str(existing_record.staff.id) == str(staff.id):
                record.check_out_time = existing_record.check_out_time
                records.append(record)
                replaced = True
            else:
                records.append(existing_record)
        if not replaced:
            records.append(record)
        attendance.records = records
        present_count, absent_count, on_leave_count = _recount_staff(records)
        attendance.total_staff = len(records)
        attendance.present_count = present_count
        attendance.absent_count = absent_count
        attendance.on_leave_count = on_leave_count
        attendance.marked_by = current_user.full_name
        attendance.marked_at = datetime.utcnow()
        attendance.save()
    else:
        present_count, absent_count, on_leave_count = _recount_staff([record])
        attendance = StaffAttendance(
            school=school,
            date=att_date,
            records=[record],
            total_staff=1,
            present_count=present_count,
            absent_count=absent_count,
            on_leave_count=on_leave_count,
            marked_by=current_user.full_name
        )
        attendance.save()

    return success_response({
        "staff_id": str(staff.id),
        "staff_name": staff.full_name,
        "status": data.status,
        "check_in_time": check_in_time,
        "check_out_time": None,
        "location_status": location_status,
        "distance_from_school_meters": round(distance_from_school, 2) if distance_from_school is not None else None,
        "geofence_enforced": enforce_geofence
    }, "Your attendance has been marked")


@router.post("/staff/self-checkout")
async def punch_out_my_staff_attendance(
    data: StaffSelfCheckout,
    current_user: User = Depends(get_current_user)
):
    school_id = resolve_school_access(current_user, data.school_id)
    school = School.objects.get(id=school_id)
    staff = Staff.objects(user_account=current_user, school=school, is_active=True).first()
    if not staff:
        raise HTTPException(403, "This user is not linked to any active staff profile")

    att_date = _normalize_day(data.date)
    today = _normalize_day()
    if att_date != today:
        raise HTTPException(400, "Self attendance can only be updated for the current day")

    attendance = StaffAttendance.objects(school=school, date=att_date).first()
    if not attendance:
        raise HTTPException(400, "Please punch in before punch out")

    record = next(
        (item for item in (attendance.records or []) if item.staff and str(item.staff.id) == str(staff.id)),
        None
    )
    if not record:
        raise HTTPException(400, "Please punch in before punch out")

    check_out_time = data.check_out_time or datetime.now().strftime("%H:%M")
    if data.remarks:
        record.remarks = data.remarks
    record.check_out_time = check_out_time
    attendance.marked_by = current_user.full_name
    attendance.marked_at = datetime.utcnow()
    attendance.save()

    return success_response({
        "staff_id": str(staff.id),
        "staff_name": staff.full_name,
        "status": record.status,
        "check_in_time": record.check_in_time,
        "check_out_time": check_out_time,
    }, "Punch out saved")


# ─── Holidays ─────────────────────────────────────────────────────────────────

@router.post("/holiday")
async def add_holiday(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    ay = AcademicYear.objects.get(id=data['academic_year_id'])
    holiday = Holiday(
        school=school, academic_year=ay,
        name=data['name'],
        date=datetime.fromisoformat(data['date']),
        holiday_type=data.get('holiday_type', 'School'),
        description=data.get('description')
    )
    holiday.save()
    return success_response({"id": str(holiday.id)}, "Holiday added")


@router.get("/holiday")
async def list_holidays(
    school_id: str, academic_year_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = Holiday.objects(school=school, is_active=True)
    if academic_year_id:
        ay = AcademicYear.objects.get(id=academic_year_id)
        query = query.filter(academic_year=ay)
    result = [{
        "id": str(h.id), "name": h.name,
        "date": h.date.isoformat(),
        "holiday_type": h.holiday_type,
        "description": h.description
    } for h in query.order_by('date')]
    return success_response(result)
