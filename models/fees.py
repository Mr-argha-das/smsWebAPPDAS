from mongoengine import *
from datetime import datetime
from models.institution import School, AcademicYear, ClassRoom
from models.student import Student


class FeeCategory(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)           # Tuition Fee, Transport, Hostel
    code = StringField(required=True)
    description = StringField()
    is_mandatory = BooleanField(default=True)
    is_active = BooleanField(default=True)
    
    meta = {'collection': 'fee_categories'}


class FeeStructureItem(EmbeddedDocument):
    category = ReferenceField(FeeCategory)
    category_name = StringField()
    amount = FloatField(required=True)
    due_day = IntField()                        # day of month


class FeeStructure(Document):
    school = ReferenceField(School, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    classroom = ReferenceField(ClassRoom, required=True)
    
    name = StringField(required=True)
    items = ListField(EmbeddedDocumentField(FeeStructureItem))
    total_amount = FloatField()
    
    installments = IntField(default=1)          # 1 = annual, 2 = half-yearly, etc.
    installment_dates = ListField(DateTimeField())
    
    late_fee_per_day = FloatField(default=0)
    grace_days = IntField(default=0)
    
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'fee_structures',
        'indexes': [
            'school',
            'academic_year',
            'classroom',
            ('school', 'academic_year', 'classroom', 'is_active')
        ]
    }


class FeeDiscount(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)
    discount_type = StringField(choices=["Percentage", "Fixed"], default="Percentage")
    value = FloatField(required=True)
    applicable_to = StringField()
    criteria = StringField()
    is_active = BooleanField(default=True)
    
    meta = {'collection': 'fee_discounts'}


class FeeInvoice(Document):
    school = ReferenceField(School, required=True)
    student = ReferenceField(Student, required=True)
    academic_year = ReferenceField(AcademicYear, required=True)
    
    invoice_no = StringField(required=True, unique=True)
    invoice_date = DateTimeField(default=datetime.utcnow)
    due_date = DateTimeField()
    
    items = ListField(DictField())              # [{category, description, amount}]
    tuition_months = ListField(StringField())
    transport_months = ListField(StringField())
    transport_route = StringField()
    concession_name = StringField()
    concession_percent = FloatField(default=0)
    emailed_to = ListField(StringField())

    gross_amount = FloatField(default=0)
    discount_amount = FloatField(default=0)
    late_fee = FloatField(default=0)
    net_amount = FloatField(default=0)
    
    paid_amount = FloatField(default=0)
    balance_amount = FloatField(default=0)
    
    status = StringField(choices=[
        "Pending", "Partial", "Paid", "Overdue", "Cancelled"
    ], default="Pending")
    
    remarks = StringField()
    generated_by = StringField()
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'fee_invoices',
        'indexes': [
            'invoice_no',
            'student',
            'school',
            'status',
            'academic_year',
            ('school', 'academic_year', '-created_at'),
            ('school', 'student', 'academic_year'),
            ('school', 'status', 'academic_year')
        ]
    }


class PaymentTransaction(Document):
    school = ReferenceField(School, required=True)
    student = ReferenceField(Student, required=True)
    invoice = ReferenceField(FeeInvoice, required=True)
    
    transaction_no = StringField(required=True, unique=True)
    payment_date = DateTimeField(default=datetime.utcnow)
    amount = FloatField(required=True)
    
    payment_mode = StringField(choices=[
        "Cash", "Online", "Cheque", "DD", "NEFT", "UPI", "Card"
    ], required=True)
    
    # Online payment details
    gateway = StringField()                     # Razorpay, Stripe
    gateway_order_id = StringField()
    gateway_payment_id = StringField()
    gateway_signature = StringField()
    
    # Cheque/DD details
    instrument_no = StringField()
    instrument_date = DateTimeField()
    bank_name = StringField()
    
    status = StringField(choices=[
        "Initiated", "Pending", "Success", "Failed", "Refunded"
    ], default="Success")
    
    collected_by = StringField()
    receipt_no = StringField()
    remarks = StringField()
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'payment_transactions',
        'indexes': ['transaction_no', 'student', 'invoice', 'status']
    }
