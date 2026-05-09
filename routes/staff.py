from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from models.staff import Staff, TeacherAssignment, LeaveType, LeaveApplication, SalarySlip
from models.institution import School, AcademicYear, ClassRoom, Section, Subject, User, Role, Permission
from utils.auth import get_current_user, resolve_school_access
from utils.auth import get_password_hash
from utils.helpers import success_response, generate_employee_id, save_upload_file

router = APIRouter(prefix="/staff", tags=["Staff & HR"])


def _resolve_current_staff(current_user: User, school: Optional[School] = None) -> Staff:
    staff = Staff.objects(user_account=current_user).first()
    if not staff and current_user.email:
        query = Staff.objects(email=current_user.email)
        if school:
            query = query.filter(school=school)
        staff = query.first()
    if not staff:
        raise HTTPException(404, "Staff profile not linked with this login")
    return staff


def _get_or_create_staff_role(staff_type: str) -> Role:
    role_name = "Teacher" if staff_type == "Teaching" else "Staff"
    role = Role.objects(name=role_name).first()
    if role:
        return role
    modules = ["dashboard", "students", "attendance", "academics", "exams", "communication"]
    role = Role(
        name=role_name,
        description=f"Default {role_name.lower()} portal access",
        is_system=True,
        permissions=[
            Permission(module=module, can_view=True, can_create=module in ["attendance", "academics"], can_edit=module in ["attendance", "academics"], can_delete=False)
            for module in modules
        ]
    )
    role.save()
    return role


def _create_or_update_staff_login(staff: Staff, school: School, data: dict) -> Optional[User]:
    create_login = bool(data.get("create_login_account"))
    login_password = (data.get("login_password") or "").strip()
    login_username = (data.get("login_username") or "").strip()
    if not create_login and not login_password:
        return staff.user_account

    username = login_username or staff.email or staff.employee_id
    email = staff.email or f"{staff.employee_id.lower()}@school.local"
    if not username:
        raise HTTPException(400, "Username or email is required to create staff login")
    if not staff.user_account and not login_password:
        raise HTTPException(400, "Password is required to create staff login")

    user = staff.user_account
    if not user:
        user = User.objects(username=username).first()
        if user and Staff.objects(user_account=user, id__ne=staff.id).first():
            raise HTTPException(400, "This username is already linked with another staff")
        email_user = User.objects(email=email).first()
        if email_user and user and str(email_user.id) != str(user.id):
            raise HTTPException(400, "Email already belongs to another login account")
        user = user or email_user
        if user and Staff.objects(user_account=user, id__ne=staff.id).first():
            raise HTTPException(400, "This email login is already linked with another staff")

    update_data = {
        "username": username,
        "email": email,
        "full_name": staff.full_name,
        "phone": staff.phone,
        "role": _get_or_create_staff_role(staff.staff_type),
        "assigned_school": school,
        "is_active": staff.is_active,
        "updated_at": datetime.utcnow()
    }
    if login_password:
        update_data["hashed_password"] = get_password_hash(login_password)

    if user:
        existing_username = User.objects(username=username, id__ne=user.id).first()
        if existing_username:
            raise HTTPException(400, "Username already taken")
        existing_email = User.objects(email=email, id__ne=user.id).first()
        if existing_email:
            raise HTTPException(400, "Email already registered")
        user.update(**update_data)
        user.reload()
    else:
        user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(login_password),
            full_name=staff.full_name,
            phone=staff.phone,
            role=_get_or_create_staff_role(staff.staff_type),
            assigned_school=school,
            is_active=staff.is_active
        )
        user.save()

    staff.update(user_account=user, updated_at=datetime.utcnow())
    staff.reload()
    return user


class StaffCreate(BaseModel):
    first_name: str
    last_name: Optional[str] = ""
    date_of_birth: Optional[datetime] = None
    gender: str
    blood_group: Optional[str] = None
    nationality: str = "Indian"
    aadhar_number: Optional[str] = None
    phone: str
    email: Optional[str] = None
    current_address: Optional[str] = None
    permanent_address: Optional[str] = None
    emergency_contact: Optional[str] = None
    school_id: str
    department: Optional[str] = None
    designation: str
    staff_type: str
    joining_date: datetime
    employment_type: str = "Permanent"
    basic_salary: float = 0
    hra: float = 0
    da: float = 0
    other_allowances: float = 0
    qualifications: List[dict] = []
    experience_years: float = 0
    subject_ids: List[str] = []
    bank_details: Optional[dict] = None
    remarks: Optional[str] = None
    create_login_account: bool = False
    login_username: Optional[str] = None
    login_password: Optional[str] = None


@router.post("")
async def create_staff(data: StaffCreate, current_user: User = Depends(get_current_user)):
    try:
        data.school_id = resolve_school_access(current_user, data.school_id)
        school = School.objects.get(id=data.school_id)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")
    
    employee_id = generate_employee_id(school.code)
    gross = data.basic_salary + data.hra + data.da + data.other_allowances
    
    staff = Staff(
        employee_id=employee_id,
        first_name=data.first_name,
        last_name=data.last_name,
        date_of_birth=data.date_of_birth,
        gender=data.gender,
        blood_group=data.blood_group,
        nationality=data.nationality,
        aadhar_number=data.aadhar_number,
        phone=data.phone,
        email=data.email,
        current_address=data.current_address,
        permanent_address=data.permanent_address,
        emergency_contact=data.emergency_contact,
        school=school,
        department=data.department,
        designation=data.designation,
        staff_type=data.staff_type,
        joining_date=data.joining_date,
        employment_type=data.employment_type,
        experience_years=data.experience_years,
        basic_salary=data.basic_salary,
        hra=data.hra,
        da=data.da,
        other_allowances=data.other_allowances,
        gross_salary=gross
    )
    
    # Add qualifications
    from models.staff import StaffQualification
    for q in data.qualifications:
        staff.qualifications.append(StaffQualification(**q))
    
    # Add subjects
    for sid in data.subject_ids:
        try:
            subject = Subject.objects.get(id=sid)
            staff.subjects.append(subject)
        except Subject.DoesNotExist:
            pass
    
    if data.bank_details:
        from models.staff import BankDetails
        staff.bank_details = BankDetails(**data.bank_details)
    
    staff.save()
    user = _create_or_update_staff_login(staff, school, data.dict())
    return success_response({
        "id": str(staff.id),
        "employee_id": staff.employee_id,
        "full_name": staff.full_name,
        "login_created": bool(user),
        "login_username": user.username if user else None
    }, "Staff member added successfully")


@router.get("")
async def list_staff(
    school_id: str,
    staff_type: Optional[str] = None,
    department: Optional[str] = None,
    employment_status: Optional[str] = None,
    active_status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    try:
        school_id = resolve_school_access(current_user, school_id)
        school = School.objects.get(id=school_id)
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")
    
    query = Staff.objects(school=school)
    if staff_type:
        query = query.filter(staff_type=staff_type)
    if department:
        query = query.filter(department=department)
    if employment_status:
        query = query.filter(employment_status=employment_status)
    if active_status == "active":
        query = query.filter(is_active=True)
    elif active_status == "inactive":
        query = query.filter(is_active=False)
    if search:
        query = query.filter(__raw__={"$or": [
            {"first_name": {"$regex": search, "$options": "i"}},
            {"last_name": {"$regex": search, "$options": "i"}},
            {"employee_id": {"$regex": search, "$options": "i"}},
        ]})
    
    total = query.count()
    staff_list = query.order_by('first_name').skip((page - 1) * per_page).limit(per_page)
    
    result = [{
        "id": str(s.id),
        "employee_id": s.employee_id,
        "full_name": s.full_name,
        "first_name": s.first_name,
        "last_name": s.last_name,
        "gender": s.gender,
        "phone": s.phone,
        "email": s.email,
        "designation": s.designation,
        "staff_type": s.staff_type,
        "department": s.department,
        "employment_type": s.employment_type,
        "employment_status": s.employment_status,
        "is_active": s.is_active,
        "has_login": bool(s.user_account),
        "login_username": s.user_account.username if s.user_account else None,
        "login_active": s.user_account.is_active if s.user_account else None,
        "joining_date": s.joining_date.isoformat() if s.joining_date else None,
        "gross_salary": s.gross_salary,
        "photo": s.photo
    } for s in staff_list]
    
    return success_response(result, meta={
        "total": total, "page": page, "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    })


@router.get("/assignments")
async def list_assignments(
    school_id: str,
    academic_year_id: Optional[str] = None,
    teacher_id: Optional[str] = None,
    classroom_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=resolve_school_access(current_user, school_id))
    query = TeacherAssignment.objects(school=school, is_active=True)
    
    if academic_year_id:
        ay = AcademicYear.objects.get(id=academic_year_id)
        query = query.filter(academic_year=ay)
    if teacher_id:
        teacher = Staff.objects.get(id=teacher_id)
        query = query.filter(teacher=teacher)
    if classroom_id:
        classroom = ClassRoom.objects.get(id=classroom_id)
        query = query.filter(classroom=classroom)
    
    result = [{
        "id": str(a.id),
        "teacher_id": str(a.teacher.id) if a.teacher else None,
        "teacher_name": a.teacher.full_name if a.teacher else None,
        "classroom_id": str(a.classroom.id) if a.classroom else None,
        "classroom": a.classroom.name if a.classroom else None,
        "section_id": str(a.section.id) if a.section else None,
        "section": a.section.name if a.section else None,
        "subject_id": str(a.subject.id) if a.subject else None,
        "subject": a.subject.name if a.subject else None,
        "is_class_teacher": a.is_class_teacher,
        "assignment_file": a.assignment_file
    } for a in query]
    return success_response(result)


@router.get("/{staff_id}")
async def get_staff(staff_id: str, current_user: User = Depends(get_current_user)):
    try:
        s = Staff.objects.get(id=staff_id)
        resolve_school_access(current_user, str(s.school.id) if s.school else None)
        data = {
            "id": str(s.id),
            "employee_id": s.employee_id,
            "full_name": s.full_name,
            "first_name": s.first_name,
            "last_name": s.last_name,
            "date_of_birth": s.date_of_birth.isoformat() if s.date_of_birth else None,
            "gender": s.gender,
            "blood_group": s.blood_group,
            "nationality": s.nationality,
            "aadhar_number": s.aadhar_number,
            "phone": s.phone,
            "email": s.email,
            "current_address": s.current_address,
            "permanent_address": s.permanent_address,
            "emergency_contact": s.emergency_contact,
            "designation": s.designation,
            "staff_type": s.staff_type,
            "department": s.department,
            "employment_type": s.employment_type,
            "employment_status": s.employment_status,
            "has_login": bool(s.user_account),
            "login_username": s.user_account.username if s.user_account else None,
            "login_active": s.user_account.is_active if s.user_account else None,
            "joining_date": s.joining_date.isoformat() if s.joining_date else None,
            "experience_years": s.experience_years,
            "basic_salary": s.basic_salary,
            "hra": s.hra,
            "da": s.da,
            "other_allowances": s.other_allowances,
            "gross_salary": s.gross_salary,
            "photo": s.photo,
            "qualifications": [
                {"degree": q.degree, "institution": q.institution, "year": q.year}
                for q in (s.qualifications or [])
            ],
            "subjects": [{"id": str(sub.id), "name": sub.name} for sub in (s.subjects or [])],
            "bank_details": {
                "bank_name": s.bank_details.bank_name if s.bank_details else None,
                "account_number": s.bank_details.account_number if s.bank_details else None,
                "ifsc_code": s.bank_details.ifsc_code if s.bank_details else None,
            } if s.bank_details else None,
            "created_at": s.created_at.isoformat()
        }
        return success_response(data)
    except Staff.DoesNotExist:
        raise HTTPException(404, "Staff not found")


@router.put("/{staff_id}")
async def update_staff(staff_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        staff = Staff.objects.get(id=staff_id)
        resolve_school_access(current_user, str(staff.school.id) if staff.school else None)
        data.pop('id', None)
        create_login_data = {
            "create_login_account": data.pop("create_login_account", False),
            "login_username": data.pop("login_username", None),
            "login_password": data.pop("login_password", None)
        }
        school_id = data.pop('school_id', None)
        data.pop('employee_id', None)
        data.pop('full_name', None)
        data['updated_at'] = datetime.utcnow()
        # Recalculate gross salary if salary fields updated
        if any(k in data for k in ['basic_salary', 'hra', 'da', 'other_allowances']):
            staff.reload()
            data['gross_salary'] = (
                data.get('basic_salary', staff.basic_salary) +
                data.get('hra', staff.hra) +
                data.get('da', staff.da) +
                data.get('other_allowances', staff.other_allowances)
            )
        staff.update(**data)
        staff.reload()
        _create_or_update_staff_login(staff, staff.school, create_login_data)
        return success_response(message="Staff updated successfully")
    except Staff.DoesNotExist:
        raise HTTPException(404, "Staff not found")


class StaffActiveToggle(BaseModel):
    is_active: bool


@router.patch("/{staff_id}/active")
async def update_staff_active_status(staff_id: str, data: StaffActiveToggle, current_user: User = Depends(get_current_user)):
    try:
        staff = Staff.objects.get(id=staff_id)
        resolve_school_access(current_user, str(staff.school.id) if staff.school else None)
        staff.update(is_active=data.is_active, updated_at=datetime.utcnow())
        staff.reload()
        if staff.user_account:
            try:
                staff.user_account.update(is_active=data.is_active, updated_at=datetime.utcnow())
            except Exception:
                pass
        if not data.is_active:
            TeacherAssignment.objects(teacher=staff, is_active=True).update(is_active=False)
        return success_response({
            "id": str(staff.id),
            "is_active": data.is_active
        }, f"Staff {'activated' if data.is_active else 'deactivated'} successfully")
    except Staff.DoesNotExist:
        raise HTTPException(404, "Staff not found")


# ─── Teacher Assignments ──────────────────────────────────────────────────────

class AssignmentCreate(BaseModel):
    school_id: str
    academic_year_id: str
    teacher_id: str
    classroom_id: str
    section_id: str
    subject_id: str
    is_class_teacher: bool = False
    assignment_file: Optional[str] = None


@router.post("/assignments")
async def create_assignment(data: AssignmentCreate, current_user: User = Depends(get_current_user)):
    try:
        school = School.objects.get(id=data.school_id)
        ay = AcademicYear.objects.get(id=data.academic_year_id)
        teacher = Staff.objects.get(id=data.teacher_id)
        classroom = ClassRoom.objects.get(id=data.classroom_id)
        section = Section.objects.get(id=data.section_id)
        subject = Subject.objects.get(id=data.subject_id)
    except Exception as e:
        raise HTTPException(404, f"Reference not found: {str(e)}")
    
    existing = TeacherAssignment.objects(
        school=school, academic_year=ay,
        classroom=classroom, section=section, subject=subject, is_active=True
    ).first()
    if existing:
        raise HTTPException(400, "Assignment already exists for this class/section/subject")
    
    assignment = TeacherAssignment(
        school=school, academic_year=ay,
        teacher=teacher, classroom=classroom, section=section, subject=subject,
        is_class_teacher=data.is_class_teacher,
        assignment_file=data.assignment_file
    )
    assignment.save()
    return success_response({"id": str(assignment.id)}, "Teacher assignment created")


@router.put("/assignments/{assignment_id}")
async def update_assignment(assignment_id: str, data: AssignmentCreate, current_user: User = Depends(get_current_user)):
    try:
        assignment = TeacherAssignment.objects.get(id=assignment_id, is_active=True)
        school = School.objects.get(id=data.school_id)
        resolve_school_access(current_user, str(school.id))
        ay = AcademicYear.objects.get(id=data.academic_year_id)
        teacher = Staff.objects.get(id=data.teacher_id)
        classroom = ClassRoom.objects.get(id=data.classroom_id)
        section = Section.objects.get(id=data.section_id)
        subject = Subject.objects.get(id=data.subject_id)
    except TeacherAssignment.DoesNotExist:
        raise HTTPException(404, "Assignment not found")
    except Exception as e:
        raise HTTPException(404, f"Reference not found: {str(e)}")

    existing = TeacherAssignment.objects(
        school=school, academic_year=ay,
        classroom=classroom, section=section, subject=subject,
        is_active=True, id__ne=assignment.id
    ).first()
    if existing:
        raise HTTPException(400, "Assignment already exists for this class/section/subject")

    assignment.update(
        school=school,
        academic_year=ay,
        teacher=teacher,
        classroom=classroom,
        section=section,
        subject=subject,
        is_class_teacher=data.is_class_teacher,
        assignment_file=data.assignment_file or assignment.assignment_file
    )
    return success_response({"id": assignment_id}, "Teacher assignment updated")


@router.delete("/assignments/{assignment_id}")
async def delete_assignment(assignment_id: str, current_user: User = Depends(get_current_user)):
    try:
        assignment = TeacherAssignment.objects.get(id=assignment_id, is_active=True)
        resolve_school_access(current_user, str(assignment.school.id) if assignment.school else None)
        assignment.update(is_active=False)
        return success_response(message="Teacher assignment deleted")
    except TeacherAssignment.DoesNotExist:
        raise HTTPException(404, "Assignment not found")


@router.post("/assignments/{assignment_id}/upload")
async def upload_assignment_file(
    assignment_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    try:
        assignment = TeacherAssignment.objects.get(id=assignment_id)
        resolve_school_access(current_user, str(assignment.school.id) if assignment.school else None)
        file_path = await save_upload_file(file, "teacher_assignments")
        assignment.update(assignment_file=file_path)
        return success_response({"file_path": file_path}, "Assignment file uploaded")
    except TeacherAssignment.DoesNotExist:
        raise HTTPException(404, "Assignment not found")


# ─── Leave Management ─────────────────────────────────────────────────────────

class LeaveApply(BaseModel):
    staff_id: Optional[str] = None
    school_id: str
    leave_type_id: str
    from_date: datetime
    to_date: datetime
    reason: str
    substitute_id: Optional[str] = None


@router.post("/leave/apply")
async def apply_leave(data: LeaveApply, current_user: User = Depends(get_current_user)):
    try:
        school = School.objects.get(id=resolve_school_access(current_user, data.school_id))
        staff = Staff.objects.get(id=data.staff_id) if data.staff_id else _resolve_current_staff(current_user, school)
        leave_type = LeaveType.objects.get(id=data.leave_type_id)
    except Exception as e:
        raise HTTPException(404, f"Reference not found: {str(e)}")

    if staff.school != school:
        raise HTTPException(400, "Selected staff does not belong to this school")

    if data.to_date < data.from_date:
        raise HTTPException(400, "To date cannot be before from date")
    
    total_days = (data.to_date - data.from_date).days + 1
    
    application = LeaveApplication(
        staff=staff, school=school, leave_type=leave_type,
        from_date=data.from_date, to_date=data.to_date,
        total_days=total_days, reason=data.reason
    )
    
    if data.substitute_id:
        try:
            sub = Staff.objects.get(id=data.substitute_id)
            application.substitute = sub
        except Staff.DoesNotExist:
            pass
    
    application.save()
    return success_response({"id": str(application.id), "total_days": total_days}, "Leave application submitted")


@router.get("/leave/types")
async def get_leave_types(school_id: str, current_user: User = Depends(get_current_user)):
    school_id = resolve_school_access(current_user, school_id)
    school = School.objects.get(id=school_id)
    defaults = [
        {"name": "Casual Leave", "code": "CL", "total_days": 12, "is_paid": True, "applicable_to": "All"},
        {"name": "Sick Leave", "code": "SL", "total_days": 10, "is_paid": True, "applicable_to": "All"},
        {"name": "Emergency Leave", "code": "EL", "total_days": 5, "is_paid": False, "applicable_to": "All"},
    ]
    for item in defaults:
        if not LeaveType.objects(school=school, code=item["code"], is_active=True).first():
            LeaveType(school=school, **item).save()
    leave_types = LeaveType.objects(school=school, is_active=True).order_by('name')
    return success_response([{
        "id": str(leave_type.id),
        "name": leave_type.name,
        "code": leave_type.code,
        "total_days": leave_type.total_days,
        "is_paid": leave_type.is_paid,
        "applicable_to": leave_type.applicable_to
    } for leave_type in leave_types])


@router.get("/me/profile")
async def get_my_staff_profile(school_id: str, current_user: User = Depends(get_current_user)):
    school_id = resolve_school_access(current_user, school_id)
    school = School.objects.get(id=school_id)
    staff = _resolve_current_staff(current_user, school)
    return success_response({
        "id": str(staff.id),
        "employee_id": staff.employee_id,
        "full_name": staff.full_name,
        "designation": staff.designation,
        "staff_type": staff.staff_type,
        "department": staff.department,
        "employment_status": staff.employment_status,
        "phone": staff.phone,
        "email": staff.email
    })


@router.get("/leave/applications")
async def get_leave_applications(
    school_id: str,
    staff_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = LeaveApplication.objects(school=school)
    if staff_id:
        staff = Staff.objects.get(id=staff_id)
        query = query.filter(staff=staff)
    if status:
        query = query.filter(status=status)
    
    result = [{
        "id": str(a.id),
        "staff_name": a.staff.full_name if a.staff else None,
        "leave_type": a.leave_type.name if a.leave_type else None,
        "from_date": a.from_date.isoformat() if a.from_date else None,
        "to_date": a.to_date.isoformat() if a.to_date else None,
        "total_days": a.total_days,
        "reason": a.reason,
        "status": a.status,
        "applied_at": a.applied_at.isoformat() if a.applied_at else None
    } for a in query.order_by('-applied_at')]
    return success_response(result)


@router.patch("/leave/{application_id}/action")
async def action_leave(
    application_id: str,
    action: str,  # approve or reject
    rejection_reason: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    try:
        app = LeaveApplication.objects.get(id=application_id)
        if action == "approve":
            app.update(
                status="Approved",
                approved_by=current_user.full_name,
                approved_at=datetime.utcnow()
            )
            # Update staff status
            app.staff.update(employment_status="On-Leave")
        elif action == "reject":
            app.update(
                status="Rejected",
                rejection_reason=rejection_reason
            )
        else:
            raise HTTPException(400, "Invalid action. Use 'approve' or 'reject'")
        return success_response(message=f"Leave application {action}d")
    except LeaveApplication.DoesNotExist:
        raise HTTPException(404, "Application not found")


# ─── Salary Slip ─────────────────────────────────────────────────────────────

@router.post("/salary/generate")
async def generate_salary(data: dict, current_user: User = Depends(get_current_user)):
    try:
        staff = Staff.objects.get(id=data['staff_id'])
        school = School.objects.get(id=data['school_id'])
    except Exception as e:
        raise HTTPException(404, str(e))
    
    month = data.get('month', datetime.now().month)
    year = data.get('year', datetime.now().year)
    
    if SalarySlip.objects(staff=staff, month=month, year=year).first():
        raise HTTPException(400, "Salary slip already generated for this month")
    
    absent_days = data.get('absent_days', 0)
    working_days = data.get('working_days', 26)
    per_day = staff.gross_salary / working_days if working_days else 0
    leave_deduction = absent_days * per_day
    
    pf = staff.basic_salary * 0.12
    esi = staff.gross_salary * 0.0175 if staff.gross_salary <= 21000 else 0
    
    gross = staff.gross_salary - leave_deduction
    total_deductions = pf + esi + leave_deduction
    net = gross - pf - esi
    
    slip = SalarySlip(
        staff=staff, school=school,
        month=month, year=year,
        basic_salary=staff.basic_salary,
        hra=staff.hra, da=staff.da,
        other_allowances=staff.other_allowances,
        gross_earnings=gross,
        pf=round(pf, 2), esi=round(esi, 2),
        absent_days=absent_days,
        leave_deduction=round(leave_deduction, 2),
        total_deductions=round(total_deductions, 2),
        net_salary=round(net, 2),
        working_days=working_days,
        present_days=working_days - absent_days,
        generated_by=current_user.full_name
    )
    slip.save()
    return success_response({"id": str(slip.id), "net_salary": slip.net_salary}, "Salary slip generated")


@router.get("/{staff_id}/salary-slips")
async def get_salary_slips(staff_id: str, current_user: User = Depends(get_current_user)):
    try:
        staff = Staff.objects.get(id=staff_id)
        slips = SalarySlip.objects(staff=staff).order_by('-year', '-month')
        result = [{
            "id": str(s.id),
            "month": s.month, "year": s.year,
            "gross_earnings": s.gross_earnings,
            "total_deductions": s.total_deductions,
            "net_salary": s.net_salary,
            "status": s.status
        } for s in slips]
        return success_response(result)
    except Staff.DoesNotExist:
        raise HTTPException(404, "Staff not found")
