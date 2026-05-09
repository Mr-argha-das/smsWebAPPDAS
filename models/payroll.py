from mongoengine import *
from datetime import datetime
from models.institution import School
from models.staff import Staff


class PayrollConfig(Document):
    school = ReferenceField(School, required=True, unique=True)
    pay_day = IntField(default=1)    # Day of month for salary payment
    epf_employee_pct = FloatField(default=12.0)
    epf_employer_pct = FloatField(default=12.0)
    esi_employee_pct = FloatField(default=0.75)
    esi_employer_pct = FloatField(default=3.25)
    professional_tax = FloatField(default=200)
    tds_threshold = FloatField(default=250000)     # Annual
    bonus_month = IntField()
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'payroll_configs'}


class StaffSalaryStructure(Document):
    school = ReferenceField(School, required=True)
    staff = ReferenceField(Staff, required=True, unique=True)
    basic_salary = FloatField(default=0)

    # Allowances
    hra = FloatField(default=0)
    da = FloatField(default=0)
    ta = FloatField(default=0)
    medical_allowance = FloatField(default=0)
    special_allowance = FloatField(default=0)
    other_allowances = ListField(DictField())   # [{name, amount}]

    # Deductions
    loan_deduction = FloatField(default=0)
    advance_deduction = FloatField(default=0)
    other_deductions = ListField(DictField())   # [{name, amount}]

    # Computed
    gross_salary = FloatField(default=0)
    net_salary = FloatField(default=0)

    effective_from = DateTimeField(default=datetime.utcnow)
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'staff_salary_structures', 'indexes': ['school', 'staff']}


class Payroll(Document):
    school = ReferenceField(School, required=True)
    staff = ReferenceField(Staff, required=True)
    month = IntField(required=True)     # 1-12
    year = IntField(required=True)
    working_days = IntField(default=26)
    present_days = IntField(default=26)
    leaves_taken = IntField(default=0)
    lop_days = IntField(default=0)      # Loss of pay

    # Earnings
    basic = FloatField(default=0)
    hra = FloatField(default=0)
    da = FloatField(default=0)
    ta = FloatField(default=0)
    medical = FloatField(default=0)
    special = FloatField(default=0)
    other_earnings = FloatField(default=0)
    gross_earnings = FloatField(default=0)

    # Deductions
    epf_employee = FloatField(default=0)
    esi_employee = FloatField(default=0)
    professional_tax = FloatField(default=0)
    tds = FloatField(default=0)
    loan = FloatField(default=0)
    advance = FloatField(default=0)
    other_deductions = FloatField(default=0)
    total_deductions = FloatField(default=0)

    # Net Pay
    net_pay = FloatField(default=0)

    # Status
    status = StringField(choices=['Draft', 'Approved', 'Paid', 'Cancelled'], default='Draft')
    payment_date = DateTimeField()
    payment_mode = StringField(choices=['Bank Transfer', 'Cash', 'Cheque'])
    bank_ref = StringField()
    generated_by = StringField()
    approved_by = StringField()
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'payrolls',
        'indexes': ['school', 'staff', ('month', 'year'), 'status']
    }


class LoanAdvance(Document):
    school = ReferenceField(School, required=True)
    staff = ReferenceField(Staff, required=True)
    loan_type = StringField(choices=['Loan', 'Advance'], default='Loan')
    amount = FloatField(required=True)
    monthly_emi = FloatField(default=0)
    total_paid = FloatField(default=0)
    balance = FloatField(default=0)
    reason = StringField()
    approved_by = StringField()
    disburse_date = DateTimeField()
    status = StringField(choices=['Active', 'Closed'], default='Active')
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'loan_advances', 'indexes': ['school', 'staff', 'status']}
