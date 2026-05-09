from mongoengine import *
from datetime import datetime
from models.institution import School
from models.student import Student
from models.staff import Staff


class VaccinationRecord(EmbeddedDocument):
    vaccine_name = StringField(required=True)
    dose_number = IntField(default=1)
    date_given = DateTimeField()
    next_due = DateTimeField()
    given_by = StringField()
    batch_no = StringField()
    is_completed = BooleanField(default=True)


class HealthRecord(Document):
    school = ReferenceField(School, required=True)
    member_type = StringField(choices=['Student', 'Staff'], required=True)
    student = ReferenceField(Student)
    staff_ref = ReferenceField(Staff)

    # Physical stats
    height_cm = FloatField()
    weight_kg = FloatField()
    bmi = FloatField()
    blood_group = StringField(choices=['A+','A-','B+','B-','O+','O-','AB+','AB-','Unknown'])
    vision_left = StringField()
    vision_right = StringField()
    hearing = StringField(choices=['Normal','Impaired'])

    # Medical info
    allergies = ListField(StringField())
    chronic_conditions = ListField(StringField())
    current_medications = ListField(StringField())
    disability = StringField()

    # Emergency
    emergency_contact_name = StringField()
    emergency_contact_phone = StringField()
    emergency_contact_relation = StringField()
    doctor_name = StringField()
    doctor_phone = StringField()
    hospital_name = StringField()

    # Vaccinations
    vaccinations = ListField(EmbeddedDocumentField(VaccinationRecord))

    last_checkup_date = DateTimeField()
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'health_records',
        'indexes': ['school', 'student', 'staff_ref', 'member_type']
    }


class MedicalVisit(Document):
    school = ReferenceField(School, required=True)
    member_type = StringField(choices=['Student', 'Staff'])
    student = ReferenceField(Student)
    staff_ref = ReferenceField(Staff)

    visit_date = DateTimeField(default=datetime.utcnow)
    complaint = StringField(required=True)
    symptoms = ListField(StringField())
    temperature = FloatField()  # Celsius
    bp_systolic = IntField()
    bp_diastolic = IntField()
    pulse_rate = IntField()

    diagnosis = StringField()
    treatment_given = StringField()
    medicines_prescribed = ListField(DictField())   # [{name, dosage, duration}]
    referred_to = StringField()
    follow_up_date = DateTimeField()

    attended_by = StringField()
    is_emergency = BooleanField(default=False)
    is_hospitalized = BooleanField(default=False)
    notes = StringField()
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'medical_visits',
        'indexes': ['school', 'student', 'visit_date', 'is_emergency']
    }


class HealthAlert(Document):
    school = ReferenceField(School, required=True)
    alert_type = StringField(choices=[
        'Epidemic', 'Outbreak', 'Allergy Alert',
        'Vaccination Drive', 'General Advisory'
    ])
    title = StringField(required=True)
    description = StringField()
    severity = StringField(choices=['Low', 'Medium', 'High', 'Critical'], default='Medium')
    affected_count = IntField(default=0)
    is_active = BooleanField(default=True)
    created_by = StringField()
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'health_alerts', 'indexes': ['school', 'is_active']}
