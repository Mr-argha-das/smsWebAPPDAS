from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime
import random, string
from models.admissions import AdmissionForm, AdmissionSetting
from models.certificates import CertificateTemplate, CertificateIssued
from models.institution import School, User
from models.student import Student
from utils.auth import get_current_user
from utils.helpers import success_response

# ═══════════════════════════════════════════════════════════════════════════════
#  ADMISSIONS ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
admissions_router = APIRouter(prefix="/admissions", tags=["Online Admissions"])


@admissions_router.get("/settings/{school_id}")
async def get_settings(school_id: str):
    try:
        school = School.objects.get(id=school_id)
        s = AdmissionSetting.objects(school=school).first()
        if not s:
            return success_response({"is_open": False, "message": "Admissions not configured"})
        return success_response({
            "is_open": s.is_open,
            "academic_year": s.academic_year,
            "open_from": s.open_from.isoformat() if s.open_from else None,
            "open_till": s.open_till.isoformat() if s.open_till else None,
            "application_fee": s.application_fee,
            "classes_available": s.classes_available or [],
            "welcome_message": s.welcome_message,
            "instructions": s.instructions,
            "required_documents": s.required_documents or [],
            "has_entrance_test": s.has_entrance_test,
            "test_details": s.test_details,
            "contact_phone": s.contact_phone,
            "contact_email": s.contact_email
        })
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")


@admissions_router.post("/settings")
async def save_settings(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    s = AdmissionSetting.objects(school=school).first()
    fields = {k: v for k, v in data.items() if k != 'school_id'}
    if 'open_from' in fields and fields['open_from']:
        fields['open_from'] = datetime.fromisoformat(fields['open_from'])
    if 'open_till' in fields and fields['open_till']:
        fields['open_till'] = datetime.fromisoformat(fields['open_till'])
    if s:
        s.update(**fields)
    else:
        s = AdmissionSetting(school=school, **fields)
        s.save()
    return success_response(message="Admission settings saved")


@admissions_router.post("/apply")
async def submit_application(data: dict):
    """Public endpoint — no auth required"""
    try:
        school = School.objects.get(id=data['school_id'])
    except School.DoesNotExist:
        raise HTTPException(404, "School not found")

    settings = AdmissionSetting.objects(school=school).first()
    if settings and not settings.is_open:
        raise HTTPException(400, "Admissions are currently closed")

    app_no = "APP" + datetime.utcnow().strftime("%Y%m") + ''.join(random.choices(string.digits, k=4))
    form = AdmissionForm(
        school=school,
        application_no=app_no,
        academic_year=data.get('academic_year'),
        applied_class=data.get('applied_class'),
        student_name=data['student_name'],
        dob=datetime.fromisoformat(data['dob']) if data.get('dob') else None,
        gender=data.get('gender'),
        religion=data.get('religion'),
        category=data.get('category', 'General'),
        aadhar_number=data.get('aadhar_number'),
        father_name=data.get('father_name'),
        father_occupation=data.get('father_occupation'),
        father_phone=data.get('father_phone'),
        father_email=data.get('father_email'),
        mother_name=data.get('mother_name'),
        mother_phone=data.get('mother_phone'),
        address=data.get('address'),
        city=data.get('city'),
        state=data.get('state'),
        pincode=data.get('pincode'),
        previous_school=data.get('previous_school'),
        previous_class=data.get('previous_class'),
        percentage=data.get('percentage')
    )
    form.save()
    return success_response({"application_no": app_no}, "Application submitted successfully!")


@admissions_router.get("")
async def list_applications(
    school_id: str, status: Optional[str] = None,
    applied_class: Optional[str] = None,
    page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = AdmissionForm.objects(school=school)
    if status: query = query.filter(status=status)
    if applied_class: query = query.filter(applied_class=applied_class)
    total = query.count()
    forms = query.order_by('-submitted_at').skip((page-1)*per_page).limit(per_page)
    result = [{
        "id": str(f.id), "application_no": f.application_no,
        "student_name": f.student_name, "applied_class": f.applied_class,
        "gender": f.gender, "category": f.category,
        "father_name": f.father_name, "father_phone": f.father_phone,
        "previous_school": f.previous_school, "percentage": f.percentage,
        "status": f.status, "test_score": f.test_score,
        "submitted_at": f.submitted_at.isoformat()
    } for f in forms]
    return success_response(result, meta={"total": total, "page": page, "per_page": per_page})


@admissions_router.get("/{application_id}")
async def get_application(application_id: str, current_user: User = Depends(get_current_user)):
    try:
        f = AdmissionForm.objects.get(id=application_id)
        return success_response({
            "id": str(f.id), "application_no": f.application_no,
            "applied_class": f.applied_class, "status": f.status,
            "student_name": f.student_name, "dob": f.dob.isoformat() if f.dob else None,
            "gender": f.gender, "religion": f.religion, "category": f.category,
            "father_name": f.father_name, "father_occupation": f.father_occupation,
            "father_phone": f.father_phone, "father_email": f.father_email,
            "mother_name": f.mother_name, "mother_phone": f.mother_phone,
            "address": f.address, "city": f.city, "state": f.state, "pincode": f.pincode,
            "previous_school": f.previous_school, "previous_class": f.previous_class, "percentage": f.percentage,
            "test_date": f.test_date.isoformat() if f.test_date else None,
            "test_score": f.test_score,
            "interview_date": f.interview_date.isoformat() if f.interview_date else None,
            "interview_notes": f.interview_notes,
            "selection_remarks": f.selection_remarks,
            "rejection_reason": f.rejection_reason,
            "submitted_at": f.submitted_at.isoformat()
        })
    except AdmissionForm.DoesNotExist:
        raise HTTPException(404, "Application not found")


@admissions_router.patch("/{application_id}/status")
async def update_status(application_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        f = AdmissionForm.objects.get(id=application_id)
        update_data = {
            'status': data['status'],
            'reviewed_by': current_user.full_name,
            'reviewed_at': datetime.utcnow()
        }
        if data.get('test_score'): update_data['test_score'] = data['test_score']
        if data.get('test_date'): update_data['test_date'] = datetime.fromisoformat(data['test_date'])
        if data.get('interview_date'): update_data['interview_date'] = datetime.fromisoformat(data['interview_date'])
        if data.get('interview_notes'): update_data['interview_notes'] = data['interview_notes']
        if data.get('selection_remarks'): update_data['selection_remarks'] = data['selection_remarks']
        if data.get('rejection_reason'): update_data['rejection_reason'] = data['rejection_reason']
        f.update(**update_data)
        return success_response(message=f"Application status updated to {data['status']}")
    except AdmissionForm.DoesNotExist:
        raise HTTPException(404, "Application not found")


@admissions_router.get("/stats/{school_id}")
async def admission_stats(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    all_apps = AdmissionForm.objects(school=school)
    return success_response({
        "total_applications": all_apps.count(),
        "submitted": all_apps.filter(status='Submitted').count(),
        "under_review": all_apps.filter(status='Under Review').count(),
        "shortlisted": all_apps.filter(status='Shortlisted').count(),
        "selected": all_apps.filter(status='Selected').count(),
        "enrolled": all_apps.filter(status='Enrolled').count(),
        "rejected": all_apps.filter(status='Rejected').count(),
        "waitlisted": all_apps.filter(status='Waitlisted').count(),
    })


# ═══════════════════════════════════════════════════════════════════════════════
#  CERTIFICATES ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
cert_router = APIRouter(prefix="/certificates", tags=["Certificates"])

CERT_TEMPLATES = {
    "Bonafide Certificate": """
<p>This is to certify that <strong>{student_name}</strong>, Son/Daughter of <strong>{father_name}</strong>,
is/was a bonafide student of <strong>{school_name}</strong> studying in Class <strong>{class_name}</strong>
during the Academic Year <strong>{academic_year}</strong>.</p>
<p>This certificate is issued for the purpose of {purpose}.</p>
""",
    "Character Certificate": """
<p>This is to certify that <strong>{student_name}</strong>, Son/Daughter of <strong>{father_name}</strong>,
was a student of <strong>{school_name}</strong> from <strong>{from_year}</strong> to <strong>{to_year}</strong>.</p>
<p>During their tenure at our institution, they maintained an excellent character and conduct.
They were sincere in their studies and disciplined in behavior.</p>
<p>This certificate is issued as per the request of the student for {purpose}.</p>
""",
    "Transfer Certificate": """
<p>This is to certify that <strong>{student_name}</strong>, Admission No. <strong>{admission_no}</strong>,
Son/Daughter of <strong>{father_name}</strong>, was a student of <strong>{school_name}</strong>.</p>
<ul>
  <li>Date of Admission: {admission_date}</li>
  <li>Class last studied: {class_name}</li>
  <li>Result: {result}</li>
  <li>Date of Leaving: {leaving_date}</li>
  <li>Reason for leaving: {reason}</li>
</ul>
<p>Conduct and character during stay in school: <strong>Good</strong></p>
""",
    "Study Certificate": """
<p>This is to certify that <strong>{student_name}</strong>, Admission No. <strong>{admission_no}</strong>,
is studying in Class <strong>{class_name}</strong> at <strong>{school_name}</strong>
during the Academic Year <strong>{academic_year}</strong>.</p>
<p>This certificate is issued for {purpose}.</p>
"""
}


@cert_router.get("/templates")
async def list_templates(school_id: str, current_user: User = Depends(get_current_user)):
    built_in = [{"id": k, "name": k, "cert_type": k, "is_builtin": True} for k in CERT_TEMPLATES.keys()]
    school = School.objects.get(id=school_id)
    custom = CertificateTemplate.objects(school=school, is_active=True)
    custom_list = [{"id": str(t.id), "name": t.name, "cert_type": t.cert_type, "is_builtin": False} for t in custom]
    return success_response(built_in + custom_list)


@cert_router.post("/issue")
async def issue_certificate(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    student = Student.objects.get(id=data['student_id'])
    cert_type = data.get('cert_type', 'Bonafide Certificate')

    cert_no = "CERT" + datetime.utcnow().strftime("%Y%m%d") + ''.join(random.choices(string.digits, k=4))

    # Build content
    template_html = CERT_TEMPLATES.get(cert_type, CERT_TEMPLATES['Bonafide Certificate'])
    placeholders = {
        'student_name': student.full_name,
        'father_name': student.parent_info.father_name if student.parent_info else 'N/A',
        'school_name': school.name,
        'class_name': student.classroom.name if student.classroom else data.get('class_name', 'N/A'),
        'academic_year': data.get('academic_year', 'N/A'),
        'admission_no': student.admission_no,
        'purpose': data.get('purpose', 'official purpose'),
        'from_year': data.get('from_year', 'N/A'),
        'to_year': data.get('to_year', 'N/A'),
        'admission_date': student.admission_date.strftime('%d/%m/%Y') if student.admission_date else 'N/A',
        'leaving_date': data.get('leaving_date', datetime.utcnow().strftime('%d/%m/%Y')),
        'result': data.get('result', 'Passed'),
        'reason': data.get('reason', 'Personal')
    }
    try:
        content = template_html.format(**placeholders)
    except KeyError:
        content = template_html

    # Full HTML certificate
    full_html = f"""
<html><head><style>
  body{{font-family:Georgia,serif;max-width:750px;margin:0 auto;padding:40px;}}
  .header{{text-align:center;border-bottom:3px double #1a1a1a;padding-bottom:20px;margin-bottom:30px;}}
  h1{{margin:0;font-size:24px;color:#1a1a1a}} h2{{margin:5px 0;font-size:14px;color:#555;font-weight:normal}}
  .title{{text-align:center;font-size:18px;font-weight:bold;text-decoration:underline;margin:25px 0;letter-spacing:1px}}
  .content{{line-height:1.9;font-size:14px;text-align:justify;margin:20px 0}}
  .footer{{margin-top:60px;display:flex;justify-content:space-between;align-items:flex-end}}
  .cert-no{{font-size:11px;color:#666}} .sign{{text-align:center}}
  .sign strong{{display:block;margin-top:5px;font-size:13px}}
  .sign small{{color:#666;font-size:11px}} .date{{font-size:13px;color:#444}}
</style></head><body>
<div class="header">
  <h1>{school.name}</h1>
  <h2>{school.address or ''}</h2>
  <h2>Phone: {school.phone or ''} | Email: {school.email or ''}</h2>
</div>
<div class="title">{cert_type.upper()}</div>
<div class="cert-no">Certificate No: {cert_no}</div>
<div class="content">{content}</div>
<div class="footer">
  <div class="date">Date: {datetime.utcnow().strftime('%d/%m/%Y')}</div>
  <div class="sign">
    <div style="border-top:1px solid #333;width:150px;padding-top:5px;">
      <strong>{data.get('signatory_name', 'Principal')}</strong>
      <small>{data.get('signatory_designation', 'Principal')}</small>
    </div>
  </div>
</div>
</body></html>"""

    cert = CertificateIssued(
        school=school, student=student, cert_type=cert_type,
        cert_number=cert_no, purpose=data.get('purpose'),
        issued_by=current_user.full_name, content=full_html
    )
    cert.save()
    return success_response({
        "id": str(cert.id), "cert_number": cert_no,
        "html": full_html, "student_name": student.full_name
    }, "Certificate issued successfully")


@cert_router.get("/issued")
async def list_issued(school_id: str, student_id: Optional[str] = None, cert_type: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    query = CertificateIssued.objects(school=school, is_active=True)
    if student_id: query = query.filter(student=Student.objects.get(id=student_id))
    if cert_type: query = query.filter(cert_type=cert_type)
    result = [{
        "id": str(c.id),
        "cert_number": c.cert_number,
        "student_name": c.student.full_name if c.student else '-',
        "admission_no": c.student.admission_no if c.student else '-',
        "cert_type": c.cert_type,
        "purpose": c.purpose,
        "issued_by": c.issued_by,
        "issue_date": c.issue_date.isoformat()
    } for c in query.order_by('-issue_date')[:100]]
    return success_response(result)


@cert_router.get("/preview/{cert_id}")
async def preview_certificate(cert_id: str, current_user: User = Depends(get_current_user)):
    try:
        cert = CertificateIssued.objects.get(id=cert_id)
        return success_response({"html": cert.content, "cert_number": cert.cert_number})
    except CertificateIssued.DoesNotExist:
        raise HTTPException(404, "Certificate not found")
