from mongoengine import *
from datetime import datetime
from models.institution import School, AcademicYear, ClassRoom, Section, Subject, GradingSystem
from models.student import Student


class ExamSchedule(EmbeddedDocument):
    subject = ReferenceField(Subject, required=True)
    exam_date = DateTimeField()
    start_time = StringField()
    end_time = StringField()
    duration_minutes = IntField()
    venue = StringField()
    max_marks = FloatField(default=100)
    passing_marks = FloatField(default=33)
    invigilators = ListField(StringField())


class DateSheetEntry(EmbeddedDocument):
    subject = ReferenceField(Subject, required=True)
    exam_date = DateTimeField()
    shift = StringField(default="Morning")
    timing = StringField()
    syllabus = StringField()


class Exam(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    
    name = StringField(required=True)               # "Unit Test 1", "Mid Term", "Final Exam"
    exam_type = StringField(choices=[
        "Test", "Exam", "Unit Test", "Mid Term", "Final", "Pre-Board", "Board", "Internal", "Custom"
    ], required=True)
    max_marks = FloatField(default=100)
    passing_marks = FloatField(default=33)
    display_order = IntField(default=0)
    
    classrooms = ListField(ReferenceField(ClassRoom))
    sections = ListField(ReferenceField(Section))
    
    start_date = DateTimeField()
    end_date = DateTimeField()
    
    schedule = ListField(EmbeddedDocumentField(ExamSchedule))
    
    grading_system = ReferenceField(GradingSystem)
    
    status = StringField(choices=[
        "Draft", "Scheduled", "Ongoing", "Completed", "Results Published"
    ], default="Draft")
    
    is_active = BooleanField(default=True)
    created_by = StringField()
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'exams',
        'indexes': ['school', 'academic_year', 'exam_type', 'status', 'display_order']
    }


class ExamDateSheet(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    exam = ReferenceField(Exam, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    section = ReferenceField(Section)
    entries = ListField(EmbeddedDocumentField(DateSheetEntry))
    published_at = DateTimeField()
    created_by = StringField()
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'exam_date_sheets',
        'indexes': ['school', 'academic_year', 'exam', 'classroom', 'section']
    }


class MarksEntry(Document):
    school = ReferenceField(School, required=True)
    exam = ReferenceField(Exam, required=True)
    student = ReferenceField(Student, required=True)
    subject = ReferenceField(Subject, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    section = ReferenceField(Section, required=True)
    
    theory_marks = FloatField()
    practical_marks = FloatField()
    total_marks = FloatField()
    max_marks = FloatField()
    passing_marks = FloatField()
    
    is_absent = BooleanField(default=False)
    is_exempted = BooleanField(default=False)
    remarks = StringField()
    
    entered_by = StringField()
    entered_at = DateTimeField(default=datetime.utcnow)
    verified_by = StringField()
    verified_at = DateTimeField()
    
    meta = {
        'collection': 'marks_entries',
        'indexes': ['school', 'exam', 'student', 'subject']
    }


class SubjectResult(EmbeddedDocument):
    subject = ReferenceField(Subject)
    subject_name = StringField()
    subject_code = StringField()
    max_marks = FloatField()
    theory_marks = FloatField()
    practical_marks = FloatField()
    total_marks = FloatField()
    percentage = FloatField()
    grade = StringField()
    grade_point = FloatField()
    is_absent = BooleanField(default=False)
    is_pass = BooleanField(default=False)
    remarks = StringField()


class Result(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    exam = ReferenceField(Exam, required=True)
    student = ReferenceField(Student, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    section = ReferenceField(Section, required=True)
    
    subject_results = ListField(EmbeddedDocumentField(SubjectResult))
    
    total_max_marks = FloatField()
    total_obtained_marks = FloatField()
    percentage = FloatField()
    cgpa = FloatField()
    overall_grade = StringField()
    
    rank_in_class = IntField()
    rank_in_section = IntField()
    
    is_pass = BooleanField(default=False)
    is_promoted = BooleanField(default=False)
    result_status = StringField(choices=[
        "Pass", "Fail", "Compartment", "Absent", "Withheld"
    ])
    
    remarks = StringField()
    is_published = BooleanField(default=False)
    published_at = DateTimeField()
    
    generated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'results',
        'indexes': ['school', 'exam', 'student', 'academic_year']
    }
