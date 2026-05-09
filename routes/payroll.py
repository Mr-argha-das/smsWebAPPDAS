from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime
from models.payroll import PayrollConfig, StaffSalaryStructure, Payroll, LoanAdvance
from models.institution import School, User
from models.staff import Staff
from utils.auth import get_current_user
from utils.helpers import success_response

router = APIRouter(prefix="/payroll", tags=["HR & Payroll"])


@router.get("/config/{school_id}")
async def get_config(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    cfg = PayrollConfig.objects(school=school).first()
    if not cfg:
        return success_response({
            "pay_day": 1, "epf_employee_pct": 12, "epf_employer_pct": 12,
            "esi_employee_pct": 0.75, "esi_employer_pct": 3.25,
            "professional_tax": 200, "tds_threshold": 250000
        })
    return success_response({
        "id": str(cfg.id), "pay_day": cfg.pay_day,
        "epf_employee_pct": cfg.epf_employee_pct, "epf_employer_pct": cfg.epf_employer_pct,
        "esi_employee_pct": cfg.esi_employee_pct, "esi_employer_pct": cfg.esi_employer_pct,
        "professional_tax": cfg.professional_tax, "tds_threshold": cfg.tds_threshold
    })


@router.post("/config")
async def save_config(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    cfg = PayrollConfig.objects(school=school).first()
    if cfg:
        cfg.update(pay_day=data.get('pay_day', 1), epf_employee_pct=data.get('epf_employee_pct', 12),
                   epf_employer_pct=data.get('epf_employer_pct', 12),
                   esi_employee_pct=data.get('esi_employee_pct', 0.75),
                   esi_employer_pct=data.get('esi_employer_pct', 3.25),
                   professional_tax=data.get('professional_tax', 200),
                   tds_threshold=data.get('tds_threshold', 250000))
    else:
        cfg = PayrollConfig(school=school, pay_day=data.get('pay_day', 1),
                            epf_employee_pct=data.get('epf_employee_pct', 12),
                            epf_employer_pct=data.get('epf_employer_pct', 12),
                            esi_employee_pct=data.get('esi_employee_pct', 0.75),
                            esi_employer_pct=data.get('esi_employer_pct', 3.25),
                            professional_tax=data.get('professional_tax', 200),
                            tds_threshold=data.get('tds_threshold', 250000))
        cfg.save()
    return success_response(message="Payroll config saved")


@router.post("/salary-structure")
async def set_salary_structure(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    staff = Staff.objects.get(id=data['staff_id'])
    basic = data.get('basic_salary', 0)
    hra = data.get('hra', 0)
    da = data.get('da', 0)
    ta = data.get('ta', 0)
    medical = data.get('medical_allowance', 0)
    special = data.get('special_allowance', 0)
    other_earn = sum(a.get('amount', 0) for a in data.get('other_allowances', []))
    gross = basic + hra + da + ta + medical + special + other_earn
    # Get config for deductions
    cfg = PayrollConfig.objects(school=school).first()
    epf = round(basic * (cfg.epf_employee_pct if cfg else 12) / 100, 2)
    pt = (cfg.professional_tax if cfg else 200)
    net = gross - epf - pt - data.get('loan_deduction', 0) - data.get('advance_deduction', 0)

    existing = StaffSalaryStructure.objects(staff=staff).first()
    if existing:
        existing.update(
            basic_salary=basic, hra=hra, da=da, ta=ta,
            medical_allowance=medical, special_allowance=special,
            other_allowances=data.get('other_allowances', []),
            loan_deduction=data.get('loan_deduction', 0),
            advance_deduction=data.get('advance_deduction', 0),
            other_deductions=data.get('other_deductions', []),
            gross_salary=gross, net_salary=net, effective_from=datetime.utcnow()
        )
    else:
        struct = StaffSalaryStructure(
            school=school, staff=staff, basic_salary=basic, hra=hra, da=da, ta=ta,
            medical_allowance=medical, special_allowance=special,
            other_allowances=data.get('other_allowances', []),
            loan_deduction=data.get('loan_deduction', 0),
            advance_deduction=data.get('advance_deduction', 0),
            other_deductions=data.get('other_deductions', []),
            gross_salary=gross, net_salary=net
        )
        struct.save()
    return success_response({"gross": gross, "net": net}, "Salary structure saved")


@router.get("/salary-structure")
async def list_salary_structures(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    structs = StaffSalaryStructure.objects(school=school, is_active=True)
    return success_response([{
        "id": str(s.id),
        "staff_name": s.staff.full_name if s.staff else '-',
        "employee_id": s.staff.employee_id if s.staff else '-',
        "basic_salary": s.basic_salary, "gross_salary": s.gross_salary, "net_salary": s.net_salary
    } for s in structs])


@router.get("/salary-structure/{staff_id}")
async def get_staff_salary(staff_id: str, current_user: User = Depends(get_current_user)):
    try:
        staff = Staff.objects.get(id=staff_id)
        s = StaffSalaryStructure.objects(staff=staff, is_active=True).first()
        if not s: raise HTTPException(404, "Salary structure not found")
        return success_response({
            "basic_salary": s.basic_salary, "hra": s.hra, "da": s.da, "ta": s.ta,
            "medical_allowance": s.medical_allowance, "special_allowance": s.special_allowance,
            "other_allowances": s.other_allowances or [],
            "loan_deduction": s.loan_deduction, "advance_deduction": s.advance_deduction,
            "gross_salary": s.gross_salary, "net_salary": s.net_salary
        })
    except Staff.DoesNotExist:
        raise HTTPException(404, "Staff not found")


@router.post("/generate")
async def generate_payroll(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    month = data['month']
    year = data['year']
    cfg = PayrollConfig.objects(school=school).first()
    structs = StaffSalaryStructure.objects(school=school, is_active=True)
    created = 0; skipped = 0

    for s in structs:
        if Payroll.objects(staff=s.staff, month=month, year=year).first():
            skipped += 1
            continue
        present = data.get('working_days', 26)
        lop = data.get('lop_days', 0)
        actual_days = present - lop
        ratio = actual_days / present if present > 0 else 1

        basic = round(s.basic_salary * ratio, 2)
        hra = round(s.hra * ratio, 2)
        da = round(s.da * ratio, 2)
        ta = round(s.ta * ratio, 2)
        medical = round(s.medical_allowance, 2)
        special = round(s.special_allowance, 2)
        gross = basic + hra + da + ta + medical + special
        epf_e = round(basic * (cfg.epf_employee_pct if cfg else 12) / 100, 2)
        esi_e = round(gross * (cfg.esi_employee_pct if cfg else 0.75) / 100, 2) if gross <= 21000 else 0
        pt = (cfg.professional_tax if cfg else 200)
        total_ded = epf_e + esi_e + pt + s.loan_deduction + s.advance_deduction
        net = gross - total_ded

        pay = Payroll(
            school=school, staff=s.staff, month=month, year=year,
            working_days=present, present_days=actual_days, lop_days=lop,
            basic=basic, hra=hra, da=da, ta=ta, medical=medical, special=special, gross_earnings=gross,
            epf_employee=epf_e, esi_employee=esi_e, professional_tax=pt,
            loan=s.loan_deduction, advance=s.advance_deduction, total_deductions=total_ded,
            net_pay=net, generated_by=current_user.full_name
        )
        pay.save()
        created += 1

    return success_response({"created": created, "skipped": skipped}, f"Payroll generated for {month}/{year}")


@router.get("")
async def list_payroll(school_id: str, month: int = Query(...), year: int = Query(...), current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    payrolls = Payroll.objects(school=school, month=month, year=year).order_by('status')
    result = [{
        "id": str(p.id),
        "staff_name": p.staff.full_name if p.staff else '-',
        "employee_id": p.staff.employee_id if p.staff else '-',
        "designation": p.staff.designation if p.staff else '-',
        "working_days": p.working_days, "present_days": p.present_days, "lop_days": p.lop_days,
        "gross_earnings": p.gross_earnings, "total_deductions": p.total_deductions, "net_pay": p.net_pay,
        "status": p.status, "payment_date": p.payment_date.isoformat() if p.payment_date else None
    } for p in payrolls]
    total_gross = sum(r['gross_earnings'] for r in result)
    total_net = sum(r['net_pay'] for r in result)
    return success_response(result, meta={"total_gross": total_gross, "total_net": total_net, "count": len(result)})


@router.patch("/{payroll_id}/approve")
async def approve_payroll(payroll_id: str, current_user: User = Depends(get_current_user)):
    try:
        Payroll.objects.get(id=payroll_id).update(status='Approved', approved_by=current_user.full_name)
        return success_response(message="Payroll approved")
    except Payroll.DoesNotExist:
        raise HTTPException(404, "Payroll not found")


@router.patch("/{payroll_id}/mark-paid")
async def mark_paid(payroll_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        Payroll.objects.get(id=payroll_id).update(
            status='Paid', payment_date=datetime.utcnow(),
            payment_mode=data.get('payment_mode', 'Bank Transfer'),
            bank_ref=data.get('bank_ref'))
        return success_response(message="Payment recorded")
    except Payroll.DoesNotExist:
        raise HTTPException(404, "Payroll not found")


@router.get("/payslip/{payroll_id}")
async def get_payslip(payroll_id: str, current_user: User = Depends(get_current_user)):
    try:
        p = Payroll.objects.get(id=payroll_id)
        school = p.school
        return success_response({
            "school_name": school.name if school else '-',
            "school_address": school.address if school else '-',
            "school_logo": school.logo if school else None,
            "employee_name": p.staff.full_name if p.staff else '-',
            "employee_id": p.staff.employee_id if p.staff else '-',
            "designation": p.staff.designation if p.staff else '-',
            "department": p.staff.department if p.staff else '-',
            "month": p.month, "year": p.year,
            "working_days": p.working_days, "present_days": p.present_days, "lop_days": p.lop_days,
            "earnings": {"basic": p.basic, "hra": p.hra, "da": p.da, "ta": p.ta, "medical": p.medical, "special": p.special, "gross": p.gross_earnings},
            "deductions": {"epf": p.epf_employee, "esi": p.esi_employee, "pt": p.professional_tax, "loan": p.loan, "advance": p.advance, "total": p.total_deductions},
            "net_pay": p.net_pay, "status": p.status,
            "payment_date": p.payment_date.isoformat() if p.payment_date else None,
            "payment_mode": p.payment_mode
        })
    except Payroll.DoesNotExist:
        raise HTTPException(404, "Payroll record not found")


@router.get("/summary/{school_id}")
async def payroll_summary(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    from datetime import date
    now = date.today()
    current_payrolls = Payroll.objects(school=school, month=now.month, year=now.year)
    return success_response({
        "current_month": f"{now.month}/{now.year}",
        "total_staff": current_payrolls.count(),
        "total_gross": sum(p.gross_earnings for p in current_payrolls),
        "total_net": sum(p.net_pay for p in current_payrolls),
        "paid_count": current_payrolls.filter(status='Paid').count(),
        "pending_count": current_payrolls.filter(status__in=['Draft', 'Approved']).count(),
        "total_epf": sum(p.epf_employee for p in current_payrolls),
        "total_esi": sum(p.esi_employee for p in current_payrolls)
    })
