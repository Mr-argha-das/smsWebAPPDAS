from mongoengine import *
from datetime import datetime
from models.institution import School, AcademicYear, ClassRoom, Section, Subject
from models.student import Student
from models.staff import Staff


class StudentAttendanceRecord(EmbeddedDocument):
    student = ReferenceField(Student, required=True)
    student_name = StringField()
    roll_no = StringField()
    status = StringField(choices=["Present", "Absent", "Late", "Excused", "Holiday"], required=True)
    remarks = StringField()
    check_in_time = StringField()


class StudentAttendance(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    section = ReferenceField(Section, required=True)
    subject = ReferenceField(Subject)          # For period-wise attendance
    
    date = DateTimeField(required=True)
    period_no = IntField()                     # None = daily attendance
    
    attendance_type = StringField(choices=["Daily", "Period"], default="Daily")
    
    records = ListField(EmbeddedDocumentField(StudentAttendanceRecord))
    
    total_students = IntField()
    present_count = IntField(default=0)
    absent_count = IntField(default=0)
    late_count = IntField(default=0)
    
    marked_by = StringField()
    marked_at = DateTimeField(default=datetime.utcnow)
    is_finalized = BooleanField(default=False)
    
    meta = {
        'collection': 'student_attendance',
        'indexes': [
            'school', 'academic_year', 'classroom', 'section', 'date',
            ('classroom', 'section', 'date')
        ]
    }


class StaffAttendanceRecord(EmbeddedDocument):
    staff = ReferenceField(Staff, required=True)
    staff_name = StringField()
    designation = StringField()
    status = StringField(choices=["Present", "Absent", "Late", "Half-Day", "On-Leave", "Holiday"])
    check_in_time = StringField()
    check_out_time = StringField()
    remarks = StringField()
    biometric_in = StringField()
    biometric_out = StringField()
    marked_via = StringField(choices=["Admin", "Teacher Panel", "Mobile App", "Biometric"], default="Admin")
    mark_latitude = FloatField()
    mark_longitude = FloatField()
    location_accuracy_meters = FloatField()
    distance_from_school_meters = FloatField()
    location_status = StringField(choices=["Not Checked", "Within Range", "Outside Range", "Admin Override"], default="Not Checked")
    location_note = StringField()


class StaffAttendance(Document):
    school = ReferenceField(School, required=True)
    date = DateTimeField(required=True)
    records = ListField(EmbeddedDocumentField(StaffAttendanceRecord))
    
    total_staff = IntField()
    present_count = IntField(default=0)
    absent_count = IntField(default=0)
    on_leave_count = IntField(default=0)
    
    marked_by = StringField()
    marked_at = DateTimeField(default=datetime.utcnow)
    is_finalized = BooleanField(default=False)
    
    meta = {
        'collection': 'staff_attendance',
        'indexes': ['school', 'date']
    }


class Holiday(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    name = StringField(required=True)
    date = DateTimeField(required=True)
    holiday_type = StringField(choices=[
        "National", "Regional", "School", "Exam", "Other"
    ])
    description = StringField()
    is_active = BooleanField(default=True)
    
    meta = {
        'collection': 'holidays',
        'indexes': ['school', 'academic_year', 'date']
    }


class AttendanceSummary(Document):
    """Monthly summary for quick reporting"""
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    student = ReferenceField(Student, required=True)
    month = IntField(required=True)
    year = IntField(required=True)
    
    total_working_days = IntField(default=0)
    present_days = IntField(default=0)
    absent_days = IntField(default=0)
    late_days = IntField(default=0)
    excused_days = IntField(default=0)
    attendance_percentage = FloatField(default=0)
    
    updated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'attendance_summary',
        'indexes': ['student', 'school', 'month', 'year']
    }
