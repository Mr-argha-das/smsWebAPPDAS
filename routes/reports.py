from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime, timedelta
from models.institution import School, AcademicYear, ClassRoom, User
from models.student import Student
from models.staff import Staff
from models.attendance import StudentAttendance, StaffAttendance
from models.fees import FeeInvoice, PaymentTransaction
from models.examination import Result
from utils.auth import get_current_user
from utils.helpers import success_response

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])


@router.get("/overview/{school_id}")
async def school_overview(school_id: str, academic_year_id: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    ay = AcademicYear.objects.get(id=academic_year_id) if academic_year_id else AcademicYear.objects(school=school, is_current=True).first()

    students = Student.objects(school=school, is_active=True)
    if ay: students = students.filter(academic_year=ay)
    total_students = students.count()

    staff = Staff.objects(school=school, is_active=True)
    total_staff = staff.count()

    invoices = FeeInvoice.objects(school=school)
    if ay: invoices = invoices.filter(academic_year=ay)
    total_billed = sum(i.net_amount for i in invoices)
    total_collected = sum(i.paid_amount for i in invoices)

    # Last 7 days attendance avg
    week_ago = datetime.utcnow() - timedelta(days=7)
    week_att = StudentAttendance.objects(school=school, date__gte=week_ago)
    att_pct = 0
    if week_att.count() > 0:
        total_p = sum(a.present_count for a in week_att)
        total_s = sum(a.total_students or 0 for a in week_att)
        att_pct = round(total_p / total_s * 100, 1) if total_s > 0 else 0

    return success_response({
        "total_students": total_students,
        "total_staff": total_staff,
        "total_teaching_staff": Staff.objects(school=school, staff_type='Teaching', is_active=True).count(),
        "total_classes": ClassRoom.objects(school=school, is_active=True).count(),
        "fee_stats": {
            "total_billed": total_billed,
            "total_collected": total_collected,
            "total_due": total_billed - total_collected,
            "collection_rate": round(total_collected / total_billed * 100, 2) if total_billed > 0 else 0
        },
        "attendance_stats": {
            "avg_last_7_days": att_pct
        },
        "gender_distribution": {
            "male": students.filter(gender='Male').count(),
            "female": students.filter(gender='Female').count(),
            "other": students.filter(gender='Other').count()
        },
        "staff_type_distribution": {
            "teaching": Staff.objects(school=school, staff_type='Teaching', is_active=True).count(),
            "non_teaching": Staff.objects(school=school, staff_type='Non-Teaching', is_active=True).count(),
            "administrative": Staff.objects(school=school, staff_type='Administrative', is_active=True).count()
        }
    })


@router.get("/attendance/class-wise")
async def attendance_class_wise(school_id: str, date: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    target_date = datetime.fromisoformat(date) if date else datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    atts = StudentAttendance.objects(school=school, date=target_date)
    result = []
    for a in atts:
        result.append({
            "classroom": a.classroom.name if a.classroom else '-',
            "section": a.section.name if a.section else '-',
            "total": a.total_students or 0,
            "present": a.present_count or 0,
            "absent": a.absent_count or 0,
            "late": a.late_count or 0,
            "percentage": round(a.present_count / a.total_students * 100, 1) if a.total_students else 0
        })
    return success_response(result)


@router.get("/attendance/monthly-trend")
async def attendance_monthly_trend(school_id: str, year: int = None, month: int = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    now = datetime.utcnow()
    yr = year or now.year
    mo = month or now.month
    start = datetime(yr, mo, 1)
    end = datetime(yr, mo+1, 1) if mo < 12 else datetime(yr+1, 1, 1)
    atts = StudentAttendance.objects(school=school, date__gte=start, date__lt=end).order_by('date')
    daily = {}
    for a in atts:
        d = a.date.strftime('%Y-%m-%d')
        if d not in daily:
            daily[d] = {'present': 0, 'absent': 0, 'total': 0}
        daily[d]['present'] += a.present_count or 0
        daily[d]['absent'] += a.absent_count or 0
        daily[d]['total'] += a.total_students or 0
    result = []
    for d, v in sorted(daily.items()):
        result.append({
            "date": d,
            "present": v['present'],
            "absent": v['absent'],
            "total": v['total'],
            "percentage": round(v['present'] / v['total'] * 100, 1) if v['total'] > 0 else 0
        })
    return success_response(result)


@router.get("/fees/monthly-collection")
async def fees_monthly_collection(
    school_id: str,
    year: int = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        if end < start:
            raise HTTPException(400, "End date must be after start date")
        txns = PaymentTransaction.objects(school=school, payment_date__gte=start, payment_date__lt=end + timedelta(days=1), status='Success').order_by('payment_date')
        range_days = max((end.date() - start.date()).days + 1, 1)
        buckets = {}
        if range_days <= 45:
            for txn in txns:
                key = txn.payment_date.strftime('%Y-%m-%d')
                buckets.setdefault(key, {"label": txn.payment_date.strftime('%d %b'), "collected": 0, "transaction_count": 0})
                buckets[key]["collected"] += txn.amount or 0
                buckets[key]["transaction_count"] += 1
        else:
            for txn in txns:
                key = txn.payment_date.strftime('%Y-%m')
                buckets.setdefault(key, {"label": txn.payment_date.strftime('%b %Y'), "collected": 0, "transaction_count": 0})
                buckets[key]["collected"] += txn.amount or 0
                buckets[key]["transaction_count"] += 1
        result = []
        for key in sorted(buckets.keys()):
            result.append({
                "bucket": key,
                "label": buckets[key]["label"],
                "collected": buckets[key]["collected"],
                "transaction_count": buckets[key]["transaction_count"]
            })
        return success_response(result)

    yr = year or datetime.utcnow().year
    monthly = []
    for m in range(1, 13):
        start = datetime(yr, m, 1)
        end = datetime(yr, m+1, 1) if m < 12 else datetime(yr+1, 1, 1)
        txns = PaymentTransaction.objects(school=school, payment_date__gte=start, payment_date__lt=end, status='Success')
        collected = sum(t.amount for t in txns)
        monthly.append({
            "month": m,
            "month_name": ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m],
            "label": ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m],
            "collected": collected,
            "transaction_count": txns.count()
        })
    return success_response(monthly)


@router.get("/fees/defaulters")
async def fee_defaulters(school_id: str, academic_year_id: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    query = FeeInvoice.objects(school=school, status__in=['Pending', 'Partial', 'Overdue'])
    if academic_year_id:
        ay = AcademicYear.objects.get(id=academic_year_id)
        query = query.filter(academic_year=ay)
    result = []
    for inv in query.order_by('-balance_amount')[:100]:
        result.append({
            "student_name": inv.student.full_name if inv.student else '-',
            "admission_no": inv.student.admission_no if inv.student else '-',
            "class": inv.student.classroom.name if inv.student and inv.student.classroom else '-',
            "invoice_no": inv.invoice_no,
            "net_amount": inv.net_amount,
            "paid_amount": inv.paid_amount,
            "balance": inv.balance_amount,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "status": inv.status
        })
    return success_response(result, meta={"total_defaulters": len(result), "total_due": sum(r['balance'] for r in result)})


@router.get("/students/class-wise-count")
async def students_class_wise(school_id: str, academic_year_id: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    classes = ClassRoom.objects(school=school, is_active=True).order_by('numeric_name')
    result = []
    for cls in classes:
        query = Student.objects(school=school, classroom=cls, is_active=True, admission_status='Active')
        if academic_year_id:
            ay = AcademicYear.objects.get(id=academic_year_id)
            query = query.filter(academic_year=ay)
        total = query.count()
        result.append({
            "class_name": cls.name,
            "class_id": str(cls.id),
            "total": total,
            "male": query.filter(gender='Male').count(),
            "female": query.filter(gender='Female').count()
        })
    return success_response(result)


@router.get("/exams/result-analysis")
async def result_analysis(school_id: str, exam_id: str, classroom_id: Optional[str] = None, current_user: User = Depends(get_current_user)):
    from models.examination import Exam
    school = School.objects.get(id=school_id)
    exam = Exam.objects.get(id=exam_id)
    query = Result.objects(school=school, exam=exam)
    if classroom_id:
        query = query.filter(classroom=ClassRoom.objects.get(id=classroom_id))
    results = list(query)
    if not results:
        return success_response({"message": "No results found"})
    percentages = [r.percentage for r in results if r.percentage]
    grade_dist = {}
    for r in results:
        g = r.overall_grade or 'F'
        grade_dist[g] = grade_dist.get(g, 0) + 1
    return success_response({
        "total_students": len(results),
        "passed": sum(1 for r in results if r.is_pass),
        "failed": sum(1 for r in results if not r.is_pass),
        "pass_percentage": round(sum(1 for r in results if r.is_pass) / len(results) * 100, 2),
        "average_percentage": round(sum(percentages) / len(percentages), 2) if percentages else 0,
        "highest_percentage": max(percentages) if percentages else 0,
        "lowest_percentage": min(percentages) if percentages else 0,
        "grade_distribution": grade_dist,
        "topper": {
            "name": results[0].student.full_name if results[0].student else '-',
            "percentage": results[0].percentage,
            "rank": results[0].rank_in_class
        } if results else None
    })


@router.get("/staff/attendance-summary")
async def staff_attendance_summary(school_id: str, month: int = None, year: int = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    now = datetime.utcnow()
    m = month or now.month; y = year or now.year
    start = datetime(y, m, 1)
    end = datetime(y, m+1, 1) if m < 12 else datetime(y+1, 1, 1)
    atts = StaffAttendance.objects(school=school, date__gte=start, date__lt=end)
    summary = {}
    for att in atts:
        for rec in (att.records or []):
            if not rec.staff:
                continue
            sid = str(rec.staff.id)
            if sid not in summary:
                summary[sid] = {"name": rec.staff.full_name, "present": 0, "absent": 0, "late": 0, "on_leave": 0}
            if rec.status == 'Present': summary[sid]['present'] += 1
            elif rec.status == 'Absent': summary[sid]['absent'] += 1
            elif rec.status == 'Late': summary[sid]['late'] += 1
            elif rec.status == 'On-Leave': summary[sid]['on_leave'] += 1
    result = list(summary.values())
    return success_response(result, meta={"month": m, "year": y})
