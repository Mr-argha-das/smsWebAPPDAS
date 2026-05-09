from mongoengine import *
from datetime import datetime
from models.institution import School
from models.student import Student


class CertificateTemplate(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)
    cert_type = StringField(choices=[
        'Transfer Certificate', 'Bonafide Certificate',
        'Character Certificate', 'Study Certificate',
        'Migration Certificate', 'Custom'
    ])
    header_text = StringField()
    body_template = StringField()  # HTML template with {placeholders}
    footer_text = StringField()
    signatory_name = StringField()
    signatory_designation = StringField()
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'certificate_templates', 'indexes': ['school', 'cert_type']}


class CertificateIssued(Document):
    school = ReferenceField(School, required=True)
    student = ReferenceField(Student, required=True)
    template = ReferenceField(CertificateTemplate)
    cert_type = StringField()
    cert_number = StringField(unique=True)
    issue_date = DateTimeField(default=datetime.utcnow)
    purpose = StringField()
    issued_by = StringField()
    content = StringField()    # Rendered HTML
    is_active = BooleanField(default=True)

    meta = {
        'collection': 'certificates_issued',
        'indexes': ['school', 'student', 'cert_type', 'cert_number']
    }
