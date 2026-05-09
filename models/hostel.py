from mongoengine import *
from datetime import datetime
from models.institution import School
from models.student import Student


class Hostel(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)
    hostel_type = StringField(choices=['Boys', 'Girls', 'Mixed'], default='Boys')
    address = StringField()
    warden_name = StringField()
    warden_phone = StringField()
    total_capacity = IntField(default=0)
    monthly_fee = FloatField(default=0)
    facilities = ListField(StringField())   # ['WiFi','Laundry','Mess','AC']
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'hostels', 'indexes': ['school']}


class HostelRoom(Document):
    school = ReferenceField(School, required=True)
    hostel = ReferenceField(Hostel, required=True)
    room_number = StringField(required=True)
    floor = IntField(default=0)
    room_type = StringField(choices=['Single', 'Double', 'Triple', 'Dormitory'], default='Double')
    capacity = IntField(default=2)
    occupied = IntField(default=0)
    monthly_fee = FloatField(default=0)
    has_ac = BooleanField(default=False)
    has_attached_bath = BooleanField(default=False)
    status = StringField(choices=['Available', 'Full', 'Under Maintenance'], default='Available')
    is_active = BooleanField(default=True)

    meta = {
        'collection': 'hostel_rooms',
        'indexes': ['school', 'hostel', 'status']
    }


class HostelAllocation(Document):
    school = ReferenceField(School, required=True)
    student = ReferenceField(Student, required=True)
    hostel = ReferenceField(Hostel, required=True)
    room = ReferenceField(HostelRoom, required=True)
    bed_number = StringField()
    academic_year = StringField()
    check_in_date = DateTimeField()
    check_out_date = DateTimeField()
    monthly_fee = FloatField(default=0)
    security_deposit = FloatField(default=0)
    deposit_paid = BooleanField(default=False)
    status = StringField(choices=['Active', 'Checked Out', 'Transferred'], default='Active')
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'hostel_allocations',
        'indexes': ['school', 'student', 'room', 'status']
    }


class HostelFeeInvoice(Document):
    school = ReferenceField(School, required=True)
    allocation = ReferenceField(HostelAllocation, required=True)
    student = ReferenceField(Student, required=True)
    month = IntField()      # 1-12
    year = IntField()
    amount = FloatField(default=0)
    paid_amount = FloatField(default=0)
    balance = FloatField(default=0)
    status = StringField(choices=['Pending', 'Paid', 'Partial', 'Overdue'], default='Pending')
    due_date = DateTimeField()
    paid_date = DateTimeField()
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'hostel_fee_invoices',
        'indexes': ['school', 'student', 'status', 'month', 'year']
    }


class HostelLeaveRequest(Document):
    school = ReferenceField(School, required=True)
    student = ReferenceField(Student, required=True)
    hostel = ReferenceField(Hostel)
    from_date = DateTimeField(required=True)
    to_date = DateTimeField(required=True)
    reason = StringField()
    destination = StringField()
    guardian_phone = StringField()
    status = StringField(choices=['Pending', 'Approved', 'Rejected'], default='Pending')
    approved_by = StringField()
    remarks = StringField()
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'hostel_leave_requests', 'indexes': ['school', 'student', 'status']}
