from mongoengine import *
from datetime import datetime
from models.institution import School


class AdmissionForm(Document):
    school = ReferenceField(School, required=True)
    application_no = StringField(required=True, unique=True)
    academic_year = StringField()
    applied_class = StringField()

    # Applicant Details
    student_name = StringField(required=True)
    dob = DateTimeField()
    gender = StringField(choices=['Male', 'Female', 'Other'])
    religion = StringField()
    category = StringField(choices=['General', 'OBC', 'SC', 'ST', 'EWS'])
    nationality = StringField(default='Indian')
    aadhar_number = StringField()

    # Parent Details
    father_name = StringField()
    father_occupation = StringField()
    father_phone = StringField()
    father_email = StringField()
    mother_name = StringField()
    mother_occupation = StringField()
    mother_phone = StringField()

    # Address
    address = StringField()
    city = StringField()
    state = StringField()
    pincode = StringField()

    # Previous School
    previous_school = StringField()
    previous_class = StringField()
    percentage = FloatField()

    # Documents
    documents = ListField(DictField())   # [{name, url, verified}]

    # Application Status
    status = StringField(choices=[
        'Submitted', 'Under Review', 'Test Scheduled',
        'Shortlisted', 'Interview Scheduled',
        'Selected', 'Waitlisted', 'Rejected', 'Enrolled'
    ], default='Submitted')
    test_date = DateTimeField()
    test_score = FloatField()
    interview_date = DateTimeField()
    interview_notes = StringField()
    selection_remarks = StringField()
    rejection_reason = StringField()
    fee_paid = FloatField(default=0)

    submitted_at = DateTimeField(default=datetime.utcnow)
    reviewed_by = StringField()
    reviewed_at = DateTimeField()

    meta = {
        'collection': 'admission_forms',
        'indexes': ['school', 'status', 'application_no', 'applied_class']
    }


class AdmissionSetting(Document):
    school = ReferenceField(School, required=True, unique=True)
    is_open = BooleanField(default=True)
    academic_year = StringField()
    open_from = DateTimeField()
    open_till = DateTimeField()
    application_fee = FloatField(default=0)
    classes_available = ListField(StringField())
    welcome_message = StringField()
    instructions = StringField()
    required_documents = ListField(StringField())
    has_entrance_test = BooleanField(default=False)
    test_details = StringField()
    contact_phone = StringField()
    contact_email = StringField()

    meta = {'collection': 'admission_settings'}
