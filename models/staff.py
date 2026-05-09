from mongoengine import *
from datetime import datetime
from models.institution import School, AcademicYear, ClassRoom, Section, Subject


class StaffQualification(EmbeddedDocument):
    degree = StringField(required=True)
    institution = StringField()
    year = IntField()
    percentage = FloatField()


class BankDetails(EmbeddedDocument):
    bank_name = StringField()
    account_number = StringField()
    ifsc_code = StringField()
    branch = StringField()
    account_type = StringField(choices=["Savings", "Current"])
    pan_number = StringField()


class Staff(Document):
    # Identification
    employee_id = StringField(required=True, unique=True)
    
    # Personal
    first_name = StringField(required=True)
    last_name = StringField(default="")
    date_of_birth = DateTimeField()
    gender = StringField(choices=["Male", "Female", "Other"], required=True)
    blood_group = StringField()
    nationality = StringField(default="Indian")
    religion = StringField()
    aadhar_number = StringField()
    pan_number = StringField()
    photo = StringField()
    
    # Contact
    phone = StringField(required=True)
    email = StringField()
    current_address = StringField()
    permanent_address = StringField()
    emergency_contact = StringField()
    
    # Job Details
    school = ReferenceField(School, required=True)
    department = StringField()
    designation = StringField(required=True)
    staff_type = StringField(
        choices=["Teaching", "Non-Teaching", "Administrative", "Support"],
        required=True
    )
    joining_date = DateTimeField(required=True)
    employment_type = StringField(
        choices=["Permanent", "Contract", "Part-Time", "Visiting"],
        default="Permanent"
    )
    employment_status = StringField(
        choices=["Active", "On-Leave", "Resigned", "Terminated", "Retired"],
        default="Active"
    )
    
    # Qualifications
    qualifications = ListField(EmbeddedDocumentField(StaffQualification))
    experience_years = FloatField(default=0)
    
    # Subjects (for teachers)
    subjects = ListField(ReferenceField(Subject))
    
    # Salary
    basic_salary = FloatField(default=0)
    hra = FloatField(default=0)
    da = FloatField(default=0)
    other_allowances = FloatField(default=0)
    gross_salary = FloatField(default=0)
    
    # Bank
    bank_details = EmbeddedDocumentField(BankDetails)
    
    # Documents
    documents = ListField(DictField())
    
    # User account
    user_account = ReferenceField('User')
    
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'staff',
        'indexes': ['employee_id', 'school', 'staff_type', 'employment_status']
    }
    
    @property
    def full_name(self):
        return " ".join([part for part in [self.first_name, self.last_name] if part]).strip()


class TeacherAssignment(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    teacher = ReferenceField(Staff, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    section = ReferenceField(Section, required=True)
    subject = ReferenceField(Subject, required=True)
    is_class_teacher = BooleanField(default=False)
    assignment_file = StringField()
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'teacher_assignments',
        'indexes': ['school', 'academic_year', 'teacher', 'classroom']
    }


class LeaveType(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)
    code = StringField(required=True)
    total_days = IntField(required=True)
    is_paid = BooleanField(default=True)
    applicable_to = StringField(choices=["All", "Teaching", "Non-Teaching"], default="All")
    is_active = BooleanField(default=True)
    
    meta = {'collection': 'leave_types'}


class LeaveApplication(Document):
    staff = ReferenceField(Staff, required=True)
    school = ReferenceField(School, required=True)
    leave_type = ReferenceField(LeaveType, required=True)
    from_date = DateTimeField(required=True)
    to_date = DateTimeField(required=True)
    total_days = FloatField()
    reason = StringField(required=True)
    status = StringField(
        choices=["Pending", "Approved", "Rejected", "Cancelled"],
        default="Pending"
    )
    approved_by = StringField()
    approved_at = DateTimeField()
    rejection_reason = StringField()
    substitute = ReferenceField(Staff)
    applied_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'leave_applications',
        'indexes': ['staff', 'school', 'status', 'from_date']
    }


class SalarySlip(Document):
    staff = ReferenceField(Staff, required=True)
    school = ReferenceField(School, required=True)
    month = IntField(required=True)            # 1-12
    year = IntField(required=True)
    
    # Earnings
    basic_salary = FloatField(default=0)
    hra = FloatField(default=0)
    da = FloatField(default=0)
    other_allowances = FloatField(default=0)
    gross_earnings = FloatField(default=0)
    
    # Deductions
    pf = FloatField(default=0)
    esi = FloatField(default=0)
    tds = FloatField(default=0)
    loan_deduction = FloatField(default=0)
    other_deductions = FloatField(default=0)
    total_deductions = FloatField(default=0)
    
    # Leave deductions
    absent_days = FloatField(default=0)
    leave_deduction = FloatField(default=0)
    
    # Net
    net_salary = FloatField(default=0)
    
    working_days = IntField()
    present_days = FloatField()
    
    status = StringField(choices=["Draft", "Generated", "Paid"], default="Draft")
    paid_date = DateTimeField()
    payment_mode = StringField(choices=["Bank Transfer", "Cash", "Cheque"])
    transaction_id = StringField()
    
    generated_by = StringField()
    generated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'salary_slips',
        'indexes': ['staff', 'school', 'month', 'year', 'status']
    }
