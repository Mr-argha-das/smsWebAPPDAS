from mongoengine import *
from datetime import datetime
from models.institution import School


class Notice(Document):
    school = ReferenceField(School, required=True)
    title = StringField(required=True)
    content = StringField(required=True)
    notice_type = StringField(choices=[
        'General', 'Exam', 'Holiday', 'Fee', 'Event',
        'Sports', 'Meeting', 'Urgent', 'Other'
    ], default='General')
    target_audience = ListField(StringField())   # ['All','Students','Staff','Parents']
    target_classes = ListField(StringField())
    attachments = ListField(StringField())
    is_pinned = BooleanField(default=False)
    is_published = BooleanField(default=False)
    publish_date = DateTimeField()
    expiry_date = DateTimeField()
    views = IntField(default=0)
    created_by = StringField()
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'notices',
        'indexes': ['school', 'is_published', 'notice_type', 'publish_date']
    }


class Event(Document):
    school = ReferenceField(School, required=True)
    title = StringField(required=True)
    description = StringField()
    event_type = StringField(choices=[
        'Academic', 'Sports', 'Cultural', 'Meeting',
        'Exam', 'Holiday', 'Trip', 'Other'
    ])
    venue = StringField()
    start_datetime = DateTimeField(required=True)
    end_datetime = DateTimeField()
    organizer = StringField()
    target_audience = ListField(StringField())
    registration_required = BooleanField(default=False)
    max_participants = IntField()
    banner_image = StringField()
    status = StringField(choices=['Upcoming', 'Ongoing', 'Completed', 'Cancelled'], default='Upcoming')
    created_by = StringField()
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'events',
        'indexes': ['school', 'start_datetime', 'status']
    }


class Message(Document):
    school = ReferenceField(School, required=True)
    sender_id = StringField(required=True)
    sender_name = StringField()
    sender_type = StringField(choices=['Admin', 'Teacher', 'Parent', 'Student'])
    recipient_id = StringField(required=True)
    recipient_name = StringField()
    recipient_type = StringField(choices=['Admin', 'Teacher', 'Parent', 'Student'])
    subject = StringField()
    content = StringField(required=True)
    attachments = ListField(StringField())
    is_read = BooleanField(default=False)
    read_at = DateTimeField()
    parent_message = ReferenceField('Message')   # For threaded conversations
    is_deleted_by_sender = BooleanField(default=False)
    is_deleted_by_recipient = BooleanField(default=False)
    sent_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'messages',
        'indexes': ['school', 'sender_id', 'recipient_id', 'is_read', 'sent_at']
    }


class Notification(Document):
    school = ReferenceField(School, required=True)
    user_id = StringField(required=True)
    title = StringField(required=True)
    body = StringField(required=True)
    notification_type = StringField(choices=[
        'Attendance', 'Fee', 'Result', 'Homework',
        'Notice', 'Message', 'Leave', 'Alert', 'General', 'Exam'
    ])
    data = DictField()           # Extra metadata
    is_read = BooleanField(default=False)
    read_at = DateTimeField()
    channel = StringField(choices=['App', 'SMS', 'Email', 'All'], default='App')
    sent_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'notifications',
        'indexes': ['school', 'user_id', 'is_read', 'sent_at']
    }


class SMSLog(Document):
    school = ReferenceField(School, required=True)
    phone = StringField(required=True)
    message = StringField(required=True)
    status = StringField(choices=['Sent', 'Failed', 'Pending'], default='Pending')
    provider_response = StringField()
    sent_at = DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'sms_logs', 'indexes': ['school', 'phone', 'sent_at']}
