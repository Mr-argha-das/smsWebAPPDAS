from mongoengine import *
from datetime import datetime
from models.institution import School
from models.student import Student
from models.staff import Staff


class BookCategory(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)
    description = StringField()
    is_active = BooleanField(default=True)

    meta = {'collection': 'book_categories'}


class Book(Document):
    school = ReferenceField(School, required=True)
    title = StringField(required=True)
    author = StringField(required=True)
    class_name = StringField()
    isbn = StringField()
    publisher = StringField()
    edition = StringField()
    year = IntField()
    category = ReferenceField(BookCategory)
    language = StringField(default='English')
    pages = IntField()
    price = FloatField(default=0)
    total_copies = IntField(default=1)
    available_copies = IntField(default=1)
    rack_number = StringField()
    barcode = StringField()
    cover_image = StringField()
    description = StringField()
    is_digital = BooleanField(default=False)
    digital_link = StringField()
    is_active = BooleanField(default=True)
    added_date = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'books',
        'indexes': ['school', 'isbn', 'barcode', 'title', 'author']
    }


class LibraryMember(Document):
    school = ReferenceField(School, required=True)
    member_type = StringField(choices=['Student', 'Staff'], required=True)
    student = ReferenceField(Student)
    staff_ref = ReferenceField(Staff)
    member_id = StringField(required=True, unique=True)
    max_books_allowed = IntField(default=3)
    max_days_allowed = IntField(default=14)
    is_active = BooleanField(default=True)
    joined_date = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'library_members',
        'indexes': ['school', 'member_id']
    }


class BookIssue(Document):
    school = ReferenceField(School, required=True)
    book = ReferenceField(Book, required=True)
    member = ReferenceField(LibraryMember, required=True)
    issue_date = DateTimeField(default=datetime.utcnow)
    due_date = DateTimeField(required=True)
    return_date = DateTimeField()
    fine_per_day = FloatField(default=1.0)
    fine_amount = FloatField(default=0)
    fine_paid = BooleanField(default=False)
    status = StringField(
        choices=['Issued', 'Returned', 'Overdue', 'Lost'],
        default='Issued'
    )
    issued_by = StringField()
    returned_to = StringField()
    remarks = StringField()

    meta = {
        'collection': 'book_issues',
        'indexes': ['school', 'book', 'member', 'status', 'due_date']
    }


class LibrarySettings(Document):
    school = ReferenceField(School, required=True, unique=True)
    max_books_student = IntField(default=3)
    max_books_staff = IntField(default=5)
    loan_period_student = IntField(default=14)  # days
    loan_period_staff = IntField(default=30)
    fine_per_day = FloatField(default=1.0)
    working_days = ListField(StringField(), default=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'])

    meta = {'collection': 'library_settings'}
