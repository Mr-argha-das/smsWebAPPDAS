from mongoengine import *
from datetime import datetime
from models.institution import School


class AssetCategory(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)
    description = StringField()
    depreciation_rate = FloatField(default=10)  # % per year
    is_active = BooleanField(default=True)

    meta = {'collection': 'asset_categories'}


class Asset(Document):
    school = ReferenceField(School, required=True)
    asset_name = StringField(required=True)
    asset_code = StringField(required=True, unique=True)
    category = ReferenceField(AssetCategory)
    asset_type = StringField(choices=[
        'Furniture', 'Electronics', 'Lab Equipment', 'Sports',
        'Vehicle', 'Building', 'Computer', 'Library', 'Book', 'Note Book', 'Other'
    ])
    class_name = StringField()
    brand = StringField()
    model_no = StringField()
    serial_no = StringField()
    purchase_date = DateTimeField()
    purchase_price = FloatField(default=0)
    current_value = FloatField(default=0)
    vendor = StringField()
    warranty_expiry = DateTimeField()
    location = StringField()
    assigned_to = StringField()
    condition = StringField(
        choices=['Excellent', 'Good', 'Fair', 'Poor', 'Damaged'],
        default='Good'
    )
    status = StringField(
        choices=['Available', 'In-Use', 'Under-Maintenance', 'Disposed'],
        default='Available'
    )
    photo = StringField()
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'assets',
        'indexes': ['school', 'asset_code', 'category', 'status']
    }


class StockItem(Document):
    school = ReferenceField(School, required=True)
    item_name = StringField(required=True)
    item_code = StringField(required=True)
    class_name = StringField()
    category = StringField(choices=[
        'Stationery', 'Cleaning', 'Lab Consumable',
        'Sports', 'Food', 'Electrical', 'Books', 'Other'
    ])
    unit = StringField(default='Nos')  # Nos, Kg, Litre, Box
    current_stock = FloatField(default=0)
    minimum_stock = FloatField(default=10)
    maximum_stock = FloatField(default=500)
    unit_price = FloatField(default=0)
    location = StringField()
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'stock_items',
        'indexes': ['school', 'item_code']
    }


class StockTransaction(Document):
    school = ReferenceField(School, required=True)
    item = ReferenceField(StockItem, required=True)
    transaction_type = StringField(choices=['In', 'Out', 'Adjustment'])
    quantity = FloatField(required=True)
    unit_price = FloatField(default=0)
    total_price = FloatField(default=0)
    vendor = StringField()
    invoice_no = StringField()
    purpose = StringField()
    transaction_date = DateTimeField(default=datetime.utcnow)
    done_by = StringField()
    remarks = StringField()
    balance_after = FloatField(default=0)

    meta = {
        'collection': 'stock_transactions',
        'indexes': ['school', 'item', 'transaction_date']
    }
