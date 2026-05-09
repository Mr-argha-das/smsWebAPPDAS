from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from models.examination import Exam, ExamDateSheet, DateSheetEntry, MarksEntry, Result, SubjectResult
from models.academic import Timetable, Homework, StudyMaterial, LessonPlan, Syllabus, OnlineClass, TimetableDay, TimetablePeriod
from models.institution import School, AcademicYear, ClassRoom, Section, Subject, SubjectMapping, User
from models.student import Student
from models.staff import Staff, TeacherAssignment
from models.parent_portal import ParentPortalUser, ParentMessage
from models.communication import Notification
from utils.auth import get_current_user
from utils.helpers import success_response, save_upload_file

exam_router = APIRouter(prefix="/exams", tags=["Examinations"])
academic_router = APIRouter(prefix="/academics", tags=["Academic Management"])

DEFAULT_EXAMS = [
]


# ═══════════════════════════════════════════════════════════════════════════════
#  EXAMINATION ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

class ExamCreate(BaseModel):
    school_id: str
    academic_year_id: str
    name: str
    exam_type: str
    max_marks: Optional[float] = None
    passing_marks: Optional[float] = None
    display_order: Optional[int] = None
    classroom_ids: List[str] = []
    section_ids: List[str] = []
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    schedule: List[dict] = []


@exam_router.post("")
async def create_exam(data: ExamCreate, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data.school_id)
    ay = AcademicYear.objects.get(id=data.academic_year_id)
    
    exam = Exam(
        school=school, academic_year=ay,
        name=data.name, exam_type=data.exam_type,
        max_marks=data.max_marks or 100,
        passing_marks=data.passing_marks or 33,
        display_order=data.display_order or 0,
        start_date=data.start_date, end_date=data.end_date,
        status="Scheduled" if data.start_date or data.end_date else "Draft",
        created_by=current_user.full_name
    )
    
    for cid in data.classroom_ids:
        try:
            exam.classrooms.append(ClassRoom.objects.get(id=cid))
        except ClassRoom.DoesNotExist:
            pass
    
    for sid in data.section_ids:
        try:
            exam.sections.append(Section.objects.get(id=sid))
        except Section.DoesNotExist:
            pass
    
    exam.save()
    return success_response({"id": str(exam.id), "name": exam.name}, "Exam created successfully")


@exam_router.post("/seed-defaults")
async def seed_default_exams(
    school_id: str,
    academic_year_id: str,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    ay = AcademicYear.objects.get(id=academic_year_id)
    created = 0
    for item in DEFAULT_EXAMS:
        exam = Exam.objects(
            school=school,
            academic_year=ay,
            name=item["name"],
            is_active=True
        ).first()
        if exam:
            exam.update(**item, updated_at=datetime.utcnow())
            continue
        Exam(
            school=school,
            academic_year=ay,
            status="Draft",
            created_by=current_user.full_name,
            **item
        ).save()
        created += 1
    return success_response({"created": created}, "Default exam setup saved")


@exam_router.get("")
async def list_exams(
    school_id: str,
    academic_year_id: Optional[str] = None,
    exam_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = Exam.objects(school=school, is_active=True)
    if academic_year_id:
        ay = AcademicYear.objects.get(id=academic_year_id)
        query = query.filter(academic_year=ay)
    if exam_type:
        query = query.filter(exam_type=exam_type)
    if status:
        query = query.filter(status=status)
    
    result = [{
        "id": str(e.id), "name": e.name,
        "exam_type": e.exam_type, "status": e.status,
        "max_marks": e.max_marks,
        "passing_marks": e.passing_marks,
        "display_order": e.display_order,
        "start_date": e.start_date.isoformat() if e.start_date else None,
        "end_date": e.end_date.isoformat() if e.end_date else None,
        "classes": [c.name for c in e.classrooms],
        "classroom_ids": [str(c.id) for c in e.classrooms]
    } for e in query.order_by('display_order', '-created_at')]
    return success_response(result)


@exam_router.put("/{exam_id}")
async def update_exam(exam_id: str, data: ExamCreate, current_user: User = Depends(get_current_user)):
    try:
        exam = Exam.objects.get(id=exam_id, is_active=True)
    except Exam.DoesNotExist:
        raise HTTPException(404, "Exam not found")

    school = School.objects.get(id=data.school_id)
    ay = AcademicYear.objects.get(id=data.academic_year_id)
    exam.school = school
    exam.academic_year = ay
    exam.name = data.name
    exam.exam_type = data.exam_type
    exam.max_marks = data.max_marks or 100
    exam.passing_marks = data.passing_marks or 33
    exam.display_order = data.display_order or 0
    exam.start_date = data.start_date
    exam.end_date = data.end_date
    exam.classrooms = []
    for cid in data.classroom_ids:
        classroom = ClassRoom.objects(id=cid).first()
        if classroom:
            exam.classrooms.append(classroom)
    exam.sections = []
    for sid in data.section_ids:
        section = Section.objects(id=sid).first()
        if section:
            exam.sections.append(section)
    exam.updated_at = datetime.utcnow()
    exam.save()
    return success_response({"id": str(exam.id), "name": exam.name}, "Exam updated successfully")


@exam_router.delete("/{exam_id}")
async def delete_exam(exam_id: str, current_user: User = Depends(get_current_user)):
    try:
        exam = Exam.objects.get(id=exam_id, is_active=True)
        exam.update(is_active=False, updated_at=datetime.utcnow())
        return success_response(message="Exam deleted successfully")
    except Exam.DoesNotExist:
        raise HTTPException(404, "Exam not found")


@exam_router.patch("/{exam_id}/status")
async def update_exam_status(
    exam_id: str, status: str,
    current_user: User = Depends(get_current_user)
):
    valid_statuses = ["Draft", "Scheduled", "Ongoing", "Completed", "Results Published"]
    if status not in valid_statuses:
        raise HTTPException(400, f"Invalid status. Must be one of: {valid_statuses}")
    try:
        exam = Exam.objects.get(id=exam_id)
        exam.update(status=status, updated_at=datetime.utcnow())
        return success_response(message=f"Exam status updated to {status}")
    except Exam.DoesNotExist:
        raise HTTPException(404, "Exam not found")


def _student_row(student: Student):
    return {
        "id": str(student.id),
        "full_name": student.full_name,
        "father_name": student.parent_info.father_name if student.parent_info else "",
        "admission_no": student.admission_no,
        "roll_no": student.roll_no,
        "exam_roll_no": student.exam_roll_no,
    }


def _notify_exam_date_sheet(school: School, ay: AcademicYear, exam: Exam, classroom: ClassRoom, section: Optional[Section], current_user: User):
    title = f"{exam.name} date sheet published"
    section_text = f" - {section.name}" if section else ""
    body = f"Date sheet for {classroom.name}{section_text} has been updated."
    students = list(Student.objects(school=school, classroom=classroom, is_active=True, admission_status="Active"))
    if section:
        students = [student for student in students if student.section == section]

    parent_users = ParentPortalUser.objects(school=school, children__in=students, is_active=True)
    teacher_assignments = TeacherAssignment.objects(
        school=school,
        academic_year=ay,
        classroom=classroom,
        is_active=True
    )
    if section:
        teacher_assignments = teacher_assignments.filter(section=section)

    notified = set()
    for parent in parent_users:
        user_id = f"parent:{parent.id}"
        if user_id in notified:
            continue
        ParentMessage(
            school=school,
            parent=parent,
            subject=title,
            content=body,
            sender="Admin",
        ).save()
        Notification(
            school=school,
            user_id=user_id,
            title=title,
            body=body,
            notification_type="Exam",
            data={"exam_id": str(exam.id), "classroom_id": str(classroom.id), "section_id": str(section.id) if section else None},
        ).save()
        notified.add(user_id)

    for assignment in teacher_assignments:
        if not assignment.teacher or not assignment.teacher.user_account:
            continue
        user_id = str(assignment.teacher.user_account.id)
        if user_id in notified:
            continue
        Notification(
            school=school,
            user_id=user_id,
            title=title,
            body=body,
            notification_type="Exam",
            data={"exam_id": str(exam.id), "classroom_id": str(classroom.id), "section_id": str(section.id) if section else None},
        ).save()
        notified.add(user_id)
    return len(notified)


@exam_router.get("/roll-numbers")
async def get_exam_roll_numbers(
    school_id: str,
    classroom_id: str,
    section_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    classroom = ClassRoom.objects.get(id=classroom_id)
    query = Student.objects(school=school, classroom=classroom, is_active=True, admission_status="Active")
    if section_id:
        query = query.filter(section=Section.objects.get(id=section_id))
    return success_response([_student_row(student) for student in query.order_by('roll_no', 'first_name')])


@exam_router.post("/roll-numbers")
async def save_exam_roll_numbers(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    classroom = ClassRoom.objects.get(id=data['classroom_id'])
    section = Section.objects.get(id=data['section_id']) if data.get('section_id') else None
    mode = data.get('mode', 'manual')
    query = Student.objects(school=school, classroom=classroom, is_active=True, admission_status="Active")
    if section:
        query = query.filter(section=section)
    students = list(query.order_by('roll_no', 'first_name'))

    updated = 0
    if mode in ["admission_no", "roll_no"]:
        for student in students:
            value = student.admission_no if mode == "admission_no" else student.roll_no
            student.update(exam_roll_no=str(value or ""))
            updated += 1
    elif mode == "series":
        start = int(data.get('start_no') or 1)
        for offset, student in enumerate(students):
            student.update(exam_roll_no=str(start + offset))
            updated += 1
    else:
        for entry in data.get('entries', []):
            student = Student.objects(id=entry.get('student_id'), school=school).first()
            if not student:
                continue
            student.update(exam_roll_no=str(entry.get('exam_roll_no') or ""))
            updated += 1
    return success_response({"updated": updated}, "Exam roll numbers saved")


@exam_router.get("/date-sheet")
async def get_exam_date_sheet(
    school_id: str,
    exam_id: str,
    classroom_id: str,
    section_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    exam = Exam.objects.get(id=exam_id)
    classroom = ClassRoom.objects.get(id=classroom_id)
    section = Section.objects.get(id=section_id) if section_id else None
    subjects = _resolve_subjects_for_classroom(school, exam.academic_year, classroom, section)
    sheet = ExamDateSheet.objects(exam=exam, classroom=classroom, section=section).first()
    existing = {}
    if sheet:
        for entry in sheet.entries:
            if entry.subject:
                existing[str(entry.subject.id)] = entry
    rows = []
    for subject in subjects:
        entry = existing.get(str(subject.id))
        rows.append({
            "subject_id": str(subject.id),
            "subject_name": subject.name,
            "exam_date": entry.exam_date.strftime("%Y-%m-%d") if entry and entry.exam_date else "",
            "shift": entry.shift if entry else "Morning",
            "timing": entry.timing if entry else "",
            "syllabus": entry.syllabus if entry else "",
        })
    return success_response({
        "exam": {"id": str(exam.id), "name": exam.name, "exam_type": exam.exam_type},
        "rows": rows,
        "published_at": sheet.published_at.isoformat() if sheet and sheet.published_at else None
    })


@exam_router.post("/date-sheet")
async def save_exam_date_sheet(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    exam = Exam.objects.get(id=data['exam_id'])
    classroom = ClassRoom.objects.get(id=data['classroom_id'])
    section = Section.objects.get(id=data['section_id']) if data.get('section_id') else None
    entries = []
    for row in data.get('entries', []):
        subject = Subject.objects(id=row.get('subject_id'), school=school, is_active=True).first()
        if not subject:
            continue
        raw_date = row.get('exam_date')
        entries.append(DateSheetEntry(
            subject=subject,
            exam_date=datetime.fromisoformat(raw_date) if raw_date else None,
            shift=row.get('shift') or "Morning",
            timing=row.get('timing') or "",
            syllabus=row.get('syllabus') or "",
        ))
    sheet = ExamDateSheet.objects(exam=exam, classroom=classroom, section=section).first()
    payload = {
        "school": school,
        "academic_year": exam.academic_year,
        "exam": exam,
        "classroom": classroom,
        "section": section,
        "entries": entries,
        "published_at": datetime.utcnow(),
        "created_by": current_user.full_name,
        "updated_at": datetime.utcnow(),
    }
    if sheet:
        sheet.update(**payload)
    else:
        ExamDateSheet(**payload).save()
    notified = _notify_exam_date_sheet(school, exam.academic_year, exam, classroom, section, current_user)
    return success_response({"saved": len(entries), "notifications": notified}, "Date sheet saved and notifications sent")


# ─── Marks Entry ──────────────────────────────────────────────────────────────

class MarksBulkEntry(BaseModel):
    school_id: str
    exam_id: str
    classroom_id: str
    section_id: str
    subject_id: str
    entries: List[dict]  # [{student_id, theory_marks, practical_marks, is_absent}]


class MarksMatrixEntry(BaseModel):
    school_id: str
    exam_id: str
    classroom_id: str
    section_id: str
    entries: List[dict]  # [{student_id, marks:{subject_id: marks}}]


@exam_router.post("/marks/bulk")
async def enter_marks_bulk(data: MarksBulkEntry, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data.school_id)
    exam = Exam.objects.get(id=data.exam_id)
    classroom = ClassRoom.objects.get(id=data.classroom_id)
    section = Section.objects.get(id=data.section_id)
    subject = Subject.objects.get(id=data.subject_id)
    
    saved = 0
    for entry in data.entries:
        try:
            student = Student.objects.get(id=entry['student_id'])
            theory = entry.get('theory_marks', 0)
            practical = entry.get('practical_marks', 0)
            total = theory + practical
            max_marks = exam.max_marks or ((subject.max_theory_marks or 0) + (subject.max_practical_marks or 0)) or 100
            if total > max_marks:
                raise HTTPException(400, f"Marks for {student.full_name} cannot exceed {max_marks}")
            
            existing = MarksEntry.objects(exam=exam, student=student, subject=subject).first()
            if existing:
                existing.update(
                    theory_marks=theory, practical_marks=practical,
                    total_marks=total, max_marks=max_marks, passing_marks=exam.passing_marks,
                    is_absent=entry.get('is_absent', False),
                    entered_by=current_user.full_name, entered_at=datetime.utcnow()
                )
            else:
                me = MarksEntry(
                    school=school, exam=exam, student=student,
                    subject=subject, classroom=classroom, section=section,
                    theory_marks=theory, practical_marks=practical,
                    total_marks=total, max_marks=max_marks, passing_marks=exam.passing_marks,
                    is_absent=entry.get('is_absent', False),
                    entered_by=current_user.full_name
                )
                me.save()
            saved += 1
        except Exception:
            continue
    
    return success_response({"saved": saved}, f"Marks saved for {saved} students")


@exam_router.get("/marks")
async def get_marks(
    exam_id: str,
    classroom_id: Optional[str] = None,
    section_id: Optional[str] = None,
    subject_id: Optional[str] = None,
    student_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    exam = Exam.objects.get(id=exam_id)
    query = MarksEntry.objects(exam=exam)
    
    if classroom_id:
        query = query.filter(classroom=ClassRoom.objects.get(id=classroom_id))
    if section_id:
        query = query.filter(section=Section.objects.get(id=section_id))
    if subject_id:
        query = query.filter(subject=Subject.objects.get(id=subject_id))
    if student_id:
        query = query.filter(student=Student.objects.get(id=student_id))
    
    result = [{
        "id": str(m.id),
        "student_name": m.student.full_name if m.student else None,
        "student_id": str(m.student.id) if m.student else None,
        "subject_name": m.subject.name if m.subject else None,
        "theory_marks": m.theory_marks,
        "practical_marks": m.practical_marks,
        "total_marks": m.total_marks,
        "max_marks": m.max_marks,
        "is_absent": m.is_absent
    } for m in query]
    return success_response(result)


def _resolve_subjects_for_classroom(school: School, academic_year: AcademicYear, classroom: ClassRoom, section: Optional[Section] = None):
    subject_ids = []
    mapping_query = SubjectMapping.objects(
        school=school,
        academic_year=academic_year,
        classroom=classroom,
        is_active=True
    )
    if section:
        mappings = list(mapping_query.filter(section=section)) + list(mapping_query.filter(section=None))
    else:
        mappings = list(mapping_query.filter(section=None))
    for mapping in mappings:
        if mapping.subject and str(mapping.subject.id) not in subject_ids:
            subject_ids.append(str(mapping.subject.id))
    if subject_ids:
        return [Subject.objects.get(id=sid) for sid in subject_ids if Subject.objects(id=sid, is_active=True).first()]
    return []


@exam_router.get("/marks/matrix")
async def get_marks_matrix(
    school_id: str,
    exam_id: str,
    classroom_id: str,
    section_id: str,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    exam = Exam.objects.get(id=exam_id)
    classroom = ClassRoom.objects.get(id=classroom_id)
    section = Section.objects.get(id=section_id)
    subjects = _resolve_subjects_for_classroom(school, exam.academic_year, classroom, section)
    subject_map = {str(subject.id): subject for subject in subjects}
    students = list(Student.objects(school=school, classroom=classroom, section=section, is_active=True, admission_status="Active").order_by('exam_roll_no', 'roll_no', 'first_name'))
    existing_marks = MarksEntry.objects(exam=exam, classroom=classroom, section=section, student__in=students, subject__in=subjects)
    marks_lookup = {}
    for mark in existing_marks:
      marks_lookup.setdefault(str(mark.student.id), {})[str(mark.subject.id)] = {
          "theory_marks": mark.theory_marks,
          "practical_marks": mark.practical_marks,
          "total_marks": mark.total_marks,
          "is_absent": mark.is_absent
      }
    return success_response({
        "subjects": [{
            "id": sid,
            "name": subject_map[sid].name,
            "max_marks": exam.max_marks or (subject_map[sid].max_theory_marks or 0) + (subject_map[sid].max_practical_marks or 0),
            "passing_marks": exam.passing_marks
        } for sid in subject_map],
        "students": [{
            "id": str(student.id),
            "full_name": student.full_name,
            "admission_no": student.admission_no,
            "roll_no": student.roll_no,
            "exam_roll_no": student.exam_roll_no,
            "marks": marks_lookup.get(str(student.id), {})
        } for student in students]
    })


@exam_router.post("/marks/matrix")
async def save_marks_matrix(data: MarksMatrixEntry, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data.school_id)
    exam = Exam.objects.get(id=data.exam_id)
    classroom = ClassRoom.objects.get(id=data.classroom_id)
    section = Section.objects.get(id=data.section_id)
    subjects = _resolve_subjects_for_classroom(school, exam.academic_year, classroom, section)
    subject_map = {str(subject.id): subject for subject in subjects}
    saved = 0
    for entry in data.entries:
        student = Student.objects(id=entry.get('student_id')).first()
        if not student:
            continue
        marks = entry.get('marks', {}) or {}
        for subject_id, raw_marks in marks.items():
            if subject_id not in subject_map:
                continue
            if raw_marks in [None, ""]:
                continue
            try:
                obtained = float(raw_marks)
            except (TypeError, ValueError):
                continue
            subject = subject_map[subject_id]
            max_marks = exam.max_marks or (subject.max_theory_marks or 0) + (subject.max_practical_marks or 0) or 100
            if obtained > max_marks:
                raise HTTPException(400, f"Marks for {student.full_name} cannot exceed {max_marks}")
            existing = MarksEntry.objects(exam=exam, student=student, subject=subject).first()
            payload = {
                "theory_marks": obtained,
                "practical_marks": 0,
                "total_marks": obtained,
                "max_marks": max_marks,
                "passing_marks": exam.passing_marks,
                "is_absent": False,
                "entered_by": current_user.full_name,
                "entered_at": datetime.utcnow()
            }
            if existing:
                existing.update(**payload)
            else:
                MarksEntry(
                    school=school,
                    exam=exam,
                    student=student,
                    subject=subject,
                    classroom=classroom,
                    section=section,
                    **payload
                ).save()
            saved += 1
    return success_response({"saved": saved}, f"Marks saved for {saved} subject entries")


@exam_router.post("/{exam_id}/generate-results")
async def generate_results(
    exam_id: str,
    classroom_id: str,
    section_id: str,
    current_user: User = Depends(get_current_user)
):
    """Auto-generate results from marks entries"""
    exam = Exam.objects.get(id=exam_id)
    classroom = ClassRoom.objects.get(id=classroom_id)
    section = Section.objects.get(id=section_id)
    
    students = Student.objects(classroom=classroom, section=section, is_active=True, admission_status="Active")
    results_generated = 0
    
    for student in students:
        marks = MarksEntry.objects(exam=exam, student=student)
        if not marks:
            continue
        
        subject_results = []
        total_max = 0
        total_obtained = 0
        
        for m in marks:
            pct = (m.total_marks / m.max_marks * 100) if m.max_marks and not m.is_absent else 0
            grade, gp = calculate_grade(pct)
            passing_marks = m.passing_marks if m.passing_marks is not None else (exam.passing_marks or 33)
            is_pass = m.total_marks >= passing_marks and not m.is_absent
            
            sr = SubjectResult(
                subject=m.subject,
                subject_name=m.subject.name if m.subject else "",
                subject_code=m.subject.code if m.subject else "",
                max_marks=m.max_marks,
                theory_marks=m.theory_marks,
                practical_marks=m.practical_marks,
                total_marks=m.total_marks if not m.is_absent else 0,
                percentage=round(pct, 2),
                grade=grade,
                grade_point=gp,
                is_absent=m.is_absent,
                is_pass=is_pass
            )
            subject_results.append(sr)
            total_max += m.max_marks or 0
            total_obtained += m.total_marks or 0
        
        overall_pct = (total_obtained / total_max * 100) if total_max > 0 else 0
        overall_grade, overall_gp = calculate_grade(overall_pct)
        overall_pass = all(sr.is_pass for sr in subject_results)
        
        existing_result = Result.objects(exam=exam, student=student).first()
        result_data = dict(
            school=student.school,
            academic_year=student.academic_year,
            exam=exam, student=student,
            classroom=classroom, section=section,
            subject_results=subject_results,
            total_max_marks=total_max,
            total_obtained_marks=total_obtained,
            percentage=round(overall_pct, 2),
            cgpa=round(overall_gp, 2),
            overall_grade=overall_grade,
            is_pass=overall_pass,
            result_status="Pass" if overall_pass else "Fail"
        )
        
        if existing_result:
            existing_result.update(**result_data)
        else:
            Result(**result_data).save()
        
        results_generated += 1
    
    # Calculate ranks
    results = list(Result.objects(exam=exam, classroom=classroom, section=section).order_by('-percentage'))
    for rank, result in enumerate(results, 1):
        result.update(rank_in_section=rank)
    
    return success_response({"generated": results_generated}, "Results generated successfully")


def calculate_grade(percentage: float):
    """Returns (grade, grade_point)"""
    if percentage >= 91:
        return "A+", 10.0
    elif percentage >= 81:
        return "A", 9.0
    elif percentage >= 71:
        return "B+", 8.0
    elif percentage >= 61:
        return "B", 7.0
    elif percentage >= 51:
        return "C+", 6.0
    elif percentage >= 41:
        return "C", 5.0
    elif percentage >= 33:
        return "D", 4.0
    else:
        return "F", 0.0


@exam_router.get("/results")
async def get_results(
    exam_id: str,
    classroom_id: Optional[str] = None,
    section_id: Optional[str] = None,
    student_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    exam = Exam.objects.get(id=exam_id)
    query = Result.objects(exam=exam)
    if classroom_id:
        query = query.filter(classroom=ClassRoom.objects.get(id=classroom_id))
    if section_id:
        query = query.filter(section=Section.objects.get(id=section_id))
    if student_id:
        query = query.filter(student=Student.objects.get(id=student_id))
    
    result = [{
        "id": str(r.id),
        "student_name": r.student.full_name if r.student else None,
        "roll_no": r.student.exam_roll_no or r.student.roll_no if r.student else None,
        "total_obtained": r.total_obtained_marks,
        "total_max": r.total_max_marks,
        "percentage": r.percentage,
        "grade": r.overall_grade,
        "cgpa": r.cgpa,
        "rank": r.rank_in_section,
        "result_status": r.result_status,
        "is_pass": r.is_pass,
        "subjects": [{
            "name": s.subject_name,
            "obtained": s.total_marks,
            "max": s.max_marks,
            "grade": s.grade,
            "is_pass": s.is_pass
        } for s in r.subject_results]
    } for r in query.order_by('rank_in_section')]
    return success_response(result)


# ═══════════════════════════════════════════════════════════════════════════════
#  ACADEMIC MANAGEMENT ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@academic_router.post("/timetable")
async def create_timetable(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    ay = AcademicYear.objects.get(id=data['academic_year_id'])
    classroom = ClassRoom.objects.get(id=data['classroom_id'])
    section = Section.objects.get(id=data['section_id'])
    
    tt = Timetable(
        school=school, academic_year=ay,
        classroom=classroom, section=section,
        name=data.get('name', 'Regular Timetable'),
        created_by=current_user.full_name
    )
    
    for day_data in data.get('days', []):
        day = TimetableDay(day=day_data['day'])
        for p in day_data.get('periods', []):
            period = TimetablePeriod(
                period_no=p['period_no'],
                start_time=p['start_time'],
                end_time=p['end_time'],
                room=p.get('room'),
                is_break=p.get('is_break', False),
                break_name=p.get('break_name')
            )
            if p.get('subject_id'):
                try:
                    period.subject = Subject.objects.get(id=p['subject_id'])
                except Subject.DoesNotExist:
                    pass
            if p.get('teacher_id'):
                try:
                    period.teacher = Staff.objects.get(id=p['teacher_id'])
                except Staff.DoesNotExist:
                    pass
            day.periods.append(period)
        tt.days.append(day)
    
    tt.save()
    return success_response({"id": str(tt.id)}, "Timetable created")


@academic_router.get("/timetable")
async def get_timetable(
    school_id: str, classroom_id: str, section_id: str,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    classroom = ClassRoom.objects.get(id=classroom_id)
    section = Section.objects.get(id=section_id)
    
    tt = Timetable.objects(school=school, classroom=classroom, section=section, is_active=True).first()
    if not tt:
        return success_response(None, "No timetable found")
    
    days_data = []
    for d in tt.days:
        periods_data = []
        for p in d.periods:
            periods_data.append({
                "period_no": p.period_no,
                "start_time": p.start_time,
                "end_time": p.end_time,
                "subject": p.subject.name if p.subject else None,
                "teacher": p.teacher.full_name if p.teacher else None,
                "room": p.room,
                "is_break": p.is_break,
                "break_name": p.break_name
            })
        days_data.append({"day": d.day, "periods": periods_data})
    
    return success_response({"id": str(tt.id), "name": tt.name, "days": days_data})


@academic_router.post("/homework")
async def create_homework(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    ay = AcademicYear.objects.get(id=data['academic_year_id'])
    teacher = Staff.objects.get(id=data['teacher_id'])
    classroom = ClassRoom.objects.get(id=data['classroom_id'])
    subject = Subject.objects.get(id=data['subject_id'])
    
    hw = Homework(
        school=school, academic_year=ay,
        teacher=teacher, classroom=classroom,
        subject=subject,
        title=data['title'],
        description=data['description'],
        due_date=datetime.fromisoformat(data['due_date']),
        max_marks=data.get('max_marks', 10)
    )
    if data.get('section_id'):
        hw.section = Section.objects.get(id=data['section_id'])
    hw.save()
    return success_response({"id": str(hw.id)}, "Homework assigned")


@academic_router.get("/homework")
async def list_homework(
    school_id: str,
    classroom_id: Optional[str] = None,
    teacher_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = Homework.objects(school=school, is_active=True)
    if classroom_id:
        query = query.filter(classroom=ClassRoom.objects.get(id=classroom_id))
    if teacher_id:
        query = query.filter(teacher=Staff.objects.get(id=teacher_id))
    
    result = [{
        "id": str(h.id),
        "title": h.title,
        "description": h.description,
        "subject": h.subject.name if h.subject else None,
        "classroom": h.classroom.name if h.classroom else None,
        "section": h.section.name if h.section else None,
        "assigned_date": h.assigned_date.isoformat() if h.assigned_date else None,
        "due_date": h.due_date.isoformat() if h.due_date else None,
        "max_marks": h.max_marks,
        "teacher": h.teacher.full_name if h.teacher else None,
        "submission_count": len(h.submissions),
        "attachments": h.attachments or []
    } for h in query.order_by('-assigned_date')]
    return success_response(result)


@academic_router.post("/homework/{homework_id}/attachment")
async def upload_homework_attachment(
    homework_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    try:
        homework = Homework.objects.get(id=homework_id, is_active=True)
        file_path = await save_upload_file(file, "homework_attachments")
        attachments = list(homework.attachments or [])
        attachments.append(f"/uploads/{file_path}")
        homework.update(attachments=attachments)
        return success_response({
            "file_path": file_path,
            "file_url": f"/uploads/{file_path}",
            "attachments": attachments
        }, "Homework attachment uploaded")
    except Homework.DoesNotExist:
        raise HTTPException(404, "Homework not found")


@academic_router.post("/study-material")
async def upload_material(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    ay = AcademicYear.objects.get(id=data['academic_year_id'])
    teacher = Staff.objects.get(id=data['teacher_id'])
    classroom = ClassRoom.objects.get(id=data['classroom_id'])
    subject = Subject.objects.get(id=data['subject_id'])
    
    mat = StudyMaterial(
        school=school, academic_year=ay, teacher=teacher,
        classroom=classroom, subject=subject,
        title=data['title'], description=data.get('description'),
        material_type=data.get('material_type', 'Notes'),
        file_path=data.get('file_path'),
        external_link=data.get('external_link')
    )
    mat.save()
    return success_response({"id": str(mat.id)}, "Study material added")


@academic_router.get("/study-material")
async def list_materials(
    school_id: str, classroom_id: Optional[str] = None,
    subject_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = StudyMaterial.objects(school=school, is_visible=True)
    if classroom_id:
        query = query.filter(classroom=ClassRoom.objects.get(id=classroom_id))
    if subject_id:
        query = query.filter(subject=Subject.objects.get(id=subject_id))
    
    result = [{
        "id": str(m.id), "title": m.title,
        "description": m.description,
        "material_type": m.material_type,
        "subject": m.subject.name if m.subject else None,
        "teacher": m.teacher.full_name if m.teacher else None,
        "file_path": m.file_path,
        "external_link": m.external_link,
        "upload_date": m.upload_date.isoformat() if m.upload_date else None
    } for m in query.order_by('-upload_date')]
    return success_response(result)


@academic_router.post("/online-class")
async def schedule_online_class(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    teacher = Staff.objects.get(id=data['teacher_id'])
    classroom = ClassRoom.objects.get(id=data['classroom_id'])
    subject = Subject.objects.get(id=data['subject_id'])
    
    oc = OnlineClass(
        school=school, teacher=teacher,
        classroom=classroom, subject=subject,
        title=data['title'],
        description=data.get('description'),
        platform=data.get('platform', 'Google Meet'),
        meeting_link=data.get('meeting_link'),
        meeting_id=data.get('meeting_id'),
        meeting_password=data.get('meeting_password'),
        scheduled_at=datetime.fromisoformat(data['scheduled_at']),
        duration_minutes=data.get('duration_minutes', 45)
    )
    oc.save()
    return success_response({"id": str(oc.id)}, "Online class scheduled")


@academic_router.get("/online-class")
async def list_online_classes(
    school_id: str, classroom_id: Optional[str] = None,
    upcoming_only: bool = False,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = OnlineClass.objects(school=school)
    if classroom_id:
        query = query.filter(classroom=ClassRoom.objects.get(id=classroom_id))
    if upcoming_only:
        query = query.filter(scheduled_at__gte=datetime.utcnow(), status="Scheduled")
    
    result = [{
        "id": str(c.id), "title": c.title,
        "subject": c.subject.name if c.subject else None,
        "teacher": c.teacher.full_name if c.teacher else None,
        "platform": c.platform,
        "meeting_link": c.meeting_link,
        "scheduled_at": c.scheduled_at.isoformat() if c.scheduled_at else None,
        "duration_minutes": c.duration_minutes,
        "status": c.status
    } for c in query.order_by('-scheduled_at')]
    return success_response(result)
