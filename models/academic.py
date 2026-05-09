from mongoengine import *
from datetime import datetime
from models.institution import School, AcademicYear, ClassRoom, Section, Subject
from models.staff import Staff


class TimetablePeriod(EmbeddedDocument):
    period_no = IntField(required=True)
    start_time = StringField(required=True)    # "08:00"
    end_time = StringField(required=True)      # "08:45"
    subject = ReferenceField(Subject)
    teacher = ReferenceField(Staff)
    room = StringField()
    is_break = BooleanField(default=False)
    break_name = StringField()                 # "Lunch Break", "Short Break"


class TimetableDay(EmbeddedDocument):
    day = StringField(required=True, choices=[
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
    ])
    periods = ListField(EmbeddedDocumentField(TimetablePeriod))


class Timetable(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    section = ReferenceField(Section, required=True)
    name = StringField(default="Regular Timetable")
    days = ListField(EmbeddedDocumentField(TimetableDay))
    effective_from = DateTimeField()
    effective_to = DateTimeField()
    is_active = BooleanField(default=True)
    created_by = StringField()
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'timetables',
        'indexes': ['school', 'academic_year', 'classroom', 'section']
    }


class LessonPlan(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    teacher = ReferenceField(Staff, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    subject = ReferenceField(Subject, required=True)
    
    title = StringField(required=True)
    chapter = StringField()
    topic = StringField(required=True)
    objectives = ListField(StringField())
    methodology = StringField()
    resources = ListField(StringField())
    activities = StringField()
    assessment = StringField()
    homework = StringField()
    
    planned_date = DateTimeField()
    duration_minutes = IntField(default=45)
    
    status = StringField(choices=["Draft", "Approved", "Completed"], default="Draft")
    is_completed = BooleanField(default=False)
    completed_at = DateTimeField()
    remarks = StringField()
    
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'lesson_plans',
        'indexes': ['school', 'teacher', 'classroom', 'subject']
    }


class SyllabusChapter(EmbeddedDocument):
    chapter_no = IntField()
    title = StringField(required=True)
    description = StringField()
    total_periods = IntField(default=0)
    completed_periods = IntField(default=0)
    is_completed = BooleanField(default=False)
    completion_date = DateTimeField()


class Syllabus(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    subject = ReferenceField(Subject, required=True)
    teacher = ReferenceField(Staff)
    
    chapters = ListField(EmbeddedDocumentField(SyllabusChapter))
    total_chapters = IntField(default=0)
    completed_chapters = IntField(default=0)
    completion_percentage = FloatField(default=0)
    
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'syllabi',
        'indexes': ['school', 'academic_year', 'classroom', 'subject']
    }


class HomeworkSubmission(EmbeddedDocument):
    student_id = StringField()
    submission_date = DateTimeField()
    file_path = StringField()
    remarks = StringField()
    marks_obtained = FloatField()
    is_late = BooleanField(default=False)
    status = StringField(choices=["Pending", "Submitted", "Checked"], default="Pending")


class Homework(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    teacher = ReferenceField(Staff, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    section = ReferenceField(Section)
    subject = ReferenceField(Subject, required=True)
    
    title = StringField(required=True)
    description = StringField(required=True)
    assigned_date = DateTimeField(default=datetime.utcnow)
    due_date = DateTimeField(required=True)
    
    max_marks = FloatField(default=10)
    attachments = ListField(StringField())
    
    submissions = ListField(EmbeddedDocumentField(HomeworkSubmission))
    
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'homework',
        'indexes': ['school', 'teacher', 'classroom', 'due_date']
    }


class StudyMaterial(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    teacher = ReferenceField(Staff, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    section = ReferenceField(Section)
    subject = ReferenceField(Subject, required=True)
    
    title = StringField(required=True)
    description = StringField()
    material_type = StringField(choices=[
        "Notes", "Slides", "Video", "Audio", "Link", "Book", "Other"
    ])
    file_path = StringField()
    external_link = StringField()
    
    is_visible = BooleanField(default=True)
    upload_date = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'study_materials',
        'indexes': ['school', 'classroom', 'subject']
    }


class OnlineClass(Document):
    school = ReferenceField(School, required=True)
    teacher = ReferenceField(Staff, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    section = ReferenceField(Section)
    subject = ReferenceField(Subject, required=True)
    
    title = StringField(required=True)
    description = StringField()
    platform = StringField(choices=["Zoom", "Google Meet", "Teams", "Other"])
    meeting_link = StringField()
    meeting_id = StringField()
    meeting_password = StringField()
    
    scheduled_at = DateTimeField(required=True)
    duration_minutes = IntField(default=45)
    
    status = StringField(choices=["Scheduled", "Live", "Completed", "Cancelled"], default="Scheduled")
    recording_link = StringField()
    
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'online_classes',
        'indexes': ['school', 'teacher', 'classroom', 'scheduled_at']
    }
