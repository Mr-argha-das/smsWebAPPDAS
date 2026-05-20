from mongoengine import *
from datetime import datetime
from models.institution import School, AcademicYear, ClassRoom, Section


# =========================
# Embedded Documents
# =========================

class ParentInfo(EmbeddedDocument):
    father_name = StringField()
    father_phone = StringField()
    father_email = StringField()
    father_occupation = StringField()
    father_income = FloatField()

    mother_name = StringField()
    mother_phone = StringField()
    mother_email = StringField()
    mother_occupation = StringField()

    guardian_name = StringField()
    guardian_phone = StringField()
    guardian_relation = StringField()
    guardian_address = StringField()


class MedicalInfo(EmbeddedDocument):
    blood_group = StringField(choices=["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-", "Unknown"])
    height = FloatField()   # cm
    weight = FloatField()   # kg
    allergies = ListField(StringField())
    medical_conditions = ListField(StringField())
    emergency_contact = StringField()
    doctor_name = StringField()
    doctor_phone = StringField()


# 🔥 FIXED: renamed from Document → StudentDocument
class StudentDocument(EmbeddedDocument):
    doc_type = StringField(required=True)   # Birth Certificate, Aadhar, etc.
    doc_number = StringField()
    file_path = StringField()
    is_verified = BooleanField(default=False)
    verified_by = StringField()
    verified_at = DateTimeField()
    uploaded_at = DateTimeField(default=datetime.utcnow)


class AcademicHistory(EmbeddedDocument):
    school_name = StringField()
    class_passed = StringField()
    passing_year = IntField()
    percentage = FloatField()
    board = StringField()
    tc_number = StringField()


# =========================
# Main Models
# =========================

class Student(Document):
    # Identification
    admission_no = StringField(required=True)
    roll_no = StringField()
    student_id = StringField(unique=True)

    # Personal
    first_name = StringField(required=True)
    last_name = StringField(required=True)
    middle_name = StringField()
    date_of_birth = DateTimeField()
    gender = StringField(choices=["Male", "Female", "Other"], required=True)
    religion = StringField()
    caste = StringField()
    admission_concession = StringField()
    admission_concession_percent = FloatField(default=0)
    sibling_student_ids = ListField(StringField())
    nationality = StringField(default="Indian")
    aadhar_number = StringField()
    srn_no = StringField()

    # Contact
    phone = StringField()
    email = StringField()
    current_address = StringField()
    permanent_address = StringField()
    current_address_details = DictField()
    permanent_address_details = DictField()

    # Photos
    photo = StringField()

    # Academic
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    section = ReferenceField(Section, required=True)
    exam_roll_no = StringField()
    branch_code = StringField()
    branch_name = StringField()
    registration_type = StringField(choices=["Online", "Manual"], default="Manual")

    # Admission
    admission_date = DateTimeField(default=datetime.utcnow)
    admission_type = StringField(
        choices=["New", "Transfer", "Re-Admission"],
        default="New"
    )
    admission_status = StringField(
        choices=["Active", "Transferred", "Withdrawn", "Graduated", "Alumni"],
        default="Active"
    )

    # Parent/Guardian
    parent_info = EmbeddedDocumentField(ParentInfo)

    # Medical
    medical_info = EmbeddedDocumentField(MedicalInfo)

    # Documents (FIXED)
    documents = ListField(EmbeddedDocumentField(StudentDocument))

    # Previous school
    previous_school = EmbeddedDocumentField(AcademicHistory)

    # Transport
    uses_transport = BooleanField(default=False)
    transport_route = StringField()
    transport_route_name = StringField()
    transport_area = StringField()
    bus_stop = StringField()
    bus_no = StringField()
    transport_fee_per_month = FloatField(default=0)
    transport_months = ListField(StringField())
    migration = BooleanField(default=False)
    lateral_entry = BooleanField(default=False)

    # Hostel
    in_hostel = BooleanField(default=False)
    hostel_room = StringField()

    # Additional
    extra_activities = ListField(StringField())
    remarks = StringField()
    referral_type = StringField()
    referral_number = StringField()
    referral_email = StringField()

    # System
    user_account = ReferenceField('User')
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'students',
        'indexes': [
            'admission_no',
            'school',
            'academic_year',
            'classroom',
            'section',
            'branch_code',
            'admission_status',
            ('first_name', 'last_name'),
            ('school', 'academic_year', 'classroom', 'section', 'admission_status'),
            ('school', 'academic_year', 'branch_code', 'admission_status')
        ]
    }

    @property
    def full_name(self):
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return " ".join(parts)


class TransferCertificate(Document):
    student = ReferenceField(Student, required=True)
    school = ReferenceField(School, required=True)

    tc_number = StringField(required=True, unique=True)
    issue_date = DateTimeField(default=datetime.utcnow)

    reason = StringField()
    conduct = StringField(
        choices=["Excellent", "Good", "Satisfactory", "Poor"]
    )

    last_class = StringField()
    fee_clearance = BooleanField(default=False)

    issued_by = StringField()
    remarks = StringField()
    is_printed = BooleanField(default=False)

    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'transfer_certificates',
        'indexes': ['tc_number', 'student']
    }
