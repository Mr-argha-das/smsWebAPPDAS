from mongoengine import *
from datetime import datetime
from models.institution import School
from models.student import Student
from models.staff import Staff


class TransportRoute(Document):
    school = ReferenceField(School, required=True)
    route_name = StringField(required=True)
    route_code = StringField()
    start_point = StringField()
    end_point = StringField()
    stops = ListField(DictField())       # [{name, landmark, time, lat, lng}]
    distance_km = FloatField(default=0)
    estimated_duration_min = IntField(default=0)
    morning_departure = StringField()    # "07:00"
    afternoon_departure = StringField()  # "14:00"
    fee_per_month = FloatField(default=0)
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'transport_routes',
        'indexes': ['school', 'route_code']
    }


class Vehicle(Document):
    school = ReferenceField(School, required=True)
    vehicle_no = StringField(required=True, unique=True)
    vehicle_type = StringField(choices=['Bus', 'Van', 'Mini-Bus', 'Auto'], default='Bus')
    make_model = StringField()
    capacity = IntField(default=40)
    year_of_manufacture = IntField()
    fitness_expiry = DateTimeField()
    insurance_expiry = DateTimeField()
    permit_expiry = DateTimeField()
    route = ReferenceField(TransportRoute)
    driver = StringField()               # Will ref to Staff
    current_lat = FloatField()
    current_lng = FloatField()
    last_location_update = DateTimeField()
    status = StringField(choices=['Active', 'In-Maintenance', 'Inactive'], default='Active')
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'vehicles',
        'indexes': ['school', 'vehicle_no', 'route']
    }


class Driver(Document):
    school = ReferenceField(School, required=True)
    name = StringField(required=True)
    phone = StringField(required=True)
    license_no = StringField(required=True)
    license_expiry = DateTimeField()
    aadhar_number = StringField()
    address = StringField()
    photo = StringField()
    experience_years = IntField(default=0)
    assigned_vehicle = ReferenceField(Vehicle)
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'drivers',
        'indexes': ['school', 'license_no']
    }


class StudentTransport(Document):
    school = ReferenceField(School, required=True)
    student = ReferenceField(Student, required=True)
    route = ReferenceField(TransportRoute, required=True)
    vehicle = ReferenceField(Vehicle)
    pickup_stop = StringField()
    drop_stop = StringField()
    pickup_time = StringField()
    drop_time = StringField()
    academic_year = StringField()
    fee_per_month = FloatField(default=0)
    is_active = BooleanField(default=True)
    assigned_date = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'student_transport',
        'indexes': ['school', 'student', 'route']
    }


class VehicleMaintenance(Document):
    school = ReferenceField(School, required=True)
    vehicle = ReferenceField(Vehicle, required=True)
    maintenance_type = StringField(choices=[
        'Routine Service', 'Repair', 'Tyre Change', 'Oil Change',
        'Brake Service', 'Body Work', 'Other'
    ])
    description = StringField()
    cost = FloatField(default=0)
    vendor = StringField()
    maintenance_date = DateTimeField()
    next_due_date = DateTimeField()
    odometer_reading = IntField()
    is_completed = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'vehicle_maintenance',
        'indexes': ['school', 'vehicle']
    }
