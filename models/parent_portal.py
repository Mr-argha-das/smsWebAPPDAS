from mongoengine import *
from datetime import datetime
from models.institution import School
from models.student import Student


class ParentPortalUser(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)
    email = StringField(required=True)
    phone = StringField(required=True)
    password_hash = StringField(required=True)
    relation = StringField(choices=['Father', 'Mother', 'Guardian'], default='Father')
    children = ListField(ReferenceField(Student))   # Linked students
    is_active = BooleanField(default=True)
    last_login = DateTimeField()
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'parent_portal_users',
        'indexes': ['school', 'email', 'phone']
    }


class ParentMessage(Document):
    school = ReferenceField(School, required=True)
    parent = ReferenceField(ParentPortalUser, required=True)
    student = ReferenceField(Student)
    subject = StringField(required=True)
    content = StringField(required=True)
    sender = StringField(choices=['Parent', 'Admin', 'Teacher'], default='Parent')
    is_read = BooleanField(default=False)
    reply_to = ReferenceField('ParentMessage')
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'parent_messages', 'indexes': ['school', 'parent', 'is_read']}
