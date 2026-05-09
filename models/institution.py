from mongoengine import *
from datetime import datetime


# ─── User & Auth ──────────────────────────────────────────────────────────────

class Permission(EmbeddedDocument):
    module = StringField(required=True)
    can_view = BooleanField(default=True)
    can_create = BooleanField(default=False)
    can_edit = BooleanField(default=False)
    can_delete = BooleanField(default=False)


class Role(Document):
    name = StringField(required=True, unique=True, max_length=100)
    description = StringField()
    permissions = ListField(EmbeddedDocumentField(Permission))
    is_system = BooleanField(default=False)  # system roles can't be deleted
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'roles',
        'indexes': ['name']
    }


class User(Document):
    email = StringField(required=True, unique=True)
    username = StringField(required=True, unique=True)
    hashed_password = StringField(required=True)
    full_name = StringField(required=True)
    role = ReferenceField(Role)
    assigned_school = ReferenceField('School')
    assigned_branch_code = StringField()
    assigned_branch_name = StringField()
    allowed_branch_codes = ListField(StringField())
    phone = StringField()
    avatar = StringField()
    is_active = BooleanField(default=True)
    is_superadmin = BooleanField(default=False)
    last_login = DateTimeField()
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'users',
        'indexes': ['email', 'username', 'role', 'assigned_school', 'assigned_branch_code']
    }


# ─── Institution ──────────────────────────────────────────────────────────────

class Address(EmbeddedDocument):
    line1 = StringField()
    line2 = StringField()
    city = StringField()
    state = StringField()
    country = StringField(default="India")
    pincode = StringField()


class SocialLinks(EmbeddedDocument):
    website = StringField()
    facebook = StringField()
    twitter = StringField()
    instagram = StringField()
    youtube = StringField()


class Branch(EmbeddedDocument):
    name = StringField(required=True)
    code = StringField(required=True)
    logo = StringField()
    address = EmbeddedDocumentField(Address)
    phone = StringField()
    email = StringField()
    principal = StringField()
    is_active = BooleanField(default=True)


class AttendanceGeofence(EmbeddedDocument):
    latitude = FloatField()
    longitude = FloatField()
    radius_meters = FloatField(default=150)
    enforce_for_staff_attendance = BooleanField(default=False)
    updated_at = DateTimeField(default=datetime.utcnow)


class School(Document):
    name = StringField(required=True)
    code = StringField(required=True, unique=True)
    logo = StringField()
    tagline = StringField()
    affiliation_no = StringField()
    affiliation_board = StringField(choices=[
       "RBSE", "CBSE", "ICSE", "State Board", "IB", "IGCSE", "Other"
    ])
    established_year = IntField()
    type = StringField(choices=["Government", "Private", "Aided", "International"], default="Private")
    address = EmbeddedDocumentField(Address)
    phone = StringField()
    email = StringField()
    fax = StringField()
    website = StringField()
    social_links = EmbeddedDocumentField(SocialLinks)
    branches = ListField(EmbeddedDocumentField(Branch))
    attendance_geofence = EmbeddedDocumentField(AttendanceGeofence)
    is_multi_branch = BooleanField(default=False)
    currency = StringField(default="INR")
    timezone = StringField(default="Asia/Kolkata")
    academic_year_format = StringField(default="YYYY-YYYY")  # e.g. 2024-2025
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'schools',
        'indexes': ['code']
    }


# ─── Academic Year ────────────────────────────────────────────────────────────

class AcademicYear(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)          # e.g. "2024-2025"
    start_date = DateTimeField(required=True)
    end_date = DateTimeField(required=True)
    is_current = BooleanField(default=False)
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'academic_years',
        'indexes': ['school', 'is_current']
    }


# ─── Stream ───────────────────────────────────────────────────────────────────

class Stream(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)           # Science, Commerce, Arts
    code = StringField(required=True)
    description = StringField()
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {'collection': 'streams'}


# ─── Class & Section ──────────────────────────────────────────────────────────

class ClassRoom(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    name = StringField(required=True)           # Class 1, Class 2 etc.
    numeric_name = IntField()                    # 1, 2, 3 for ordering
    class_fee = FloatField(default=0)
    stream = ReferenceField(Stream)
    sections = ListField(StringField())         # ['A', 'B', 'C']
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'classrooms',
        'indexes': ['school', 'academic_year']
    }


class Section(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    name = StringField(required=True)           # A, B, C
    class_teacher = StringField()               # Will ref to Staff
    max_students = IntField(default=40)
    room_number = StringField()
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'sections',
        'indexes': ['school', 'academic_year', 'classroom']
    }


# ─── Subjects ─────────────────────────────────────────────────────────────────

class Subject(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)
    code = StringField(required=True)
    description = StringField()
    subject_type = StringField(choices=["Theory", "Practical", "Both"], default="Theory")
    max_theory_marks = FloatField(default=100)
    max_practical_marks = FloatField(default=0)
    passing_marks = FloatField(default=33)
    is_optional = BooleanField(default=False)
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'subjects',
        'indexes': ['school', 'code']
    }


class SubjectMapping(Document):
    """Maps subjects to classes/sections"""
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    section = ReferenceField(Section)
    subject = ReferenceField(Subject, required=True)
    weekly_periods = IntField(default=5)
    is_active = BooleanField(default=True)
    
    meta = {
        'collection': 'subject_mappings',
        'indexes': ['school', 'academic_year', 'classroom']
    }


# ─── Grading System ───────────────────────────────────────────────────────────

class GradeScale(EmbeddedDocument):
    grade = StringField(required=True)          # A+, A, B+...
    min_marks = FloatField(required=True)
    max_marks = FloatField(required=True)
    grade_point = FloatField()
    remarks = StringField()


class GradingSystem(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)
    description = StringField()
    grading_type = StringField(choices=["Marks", "Grades", "CGPA"], default="Marks")
    scales = ListField(EmbeddedDocumentField(GradeScale))
    is_default = BooleanField(default=False)
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'grading_systems',
        'indexes': ['school', 'is_default']
    }
