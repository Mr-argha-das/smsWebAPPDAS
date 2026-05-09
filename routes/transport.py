from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from models.transport import TransportRoute, Vehicle, Driver, StudentTransport, VehicleMaintenance
from models.institution import School, User
from models.student import Student
from utils.auth import get_current_user, resolve_school_access, resolve_branch_scope
from utils.helpers import success_response

router = APIRouter(prefix="/transport", tags=["Transport"])


# ─── Routes ──────────────────────────────────────────────────────────────────
@router.post("/route")
async def create_route(data: dict, current_user: User = Depends(get_current_user)):
    data['school_id'] = resolve_school_access(current_user, data.get('school_id'))
    school = School.objects.get(id=data['school_id'])
    route_name = (data.get('route_name') or '').strip()
    if not route_name:
        raise HTTPException(400, "Route name is required")
    if data.get('fee_per_month') in (None, ''):
        raise HTTPException(400, "Route price is required")
    route = TransportRoute(
        school=school,
        route_name=route_name,
        route_code=(data.get('route_code') or '').strip() or None,
        start_point=(data.get('start_point') or '').strip() or None,
        end_point=(data.get('end_point') or '').strip() or None,
        stops=data.get('stops', []),
        distance_km=data.get('distance_km', 0),
        estimated_duration_min=data.get('estimated_duration_min', 0),
        morning_departure=data.get('morning_departure'),
        afternoon_departure=data.get('afternoon_departure'),
        fee_per_month=float(data.get('fee_per_month', 0) or 0)
    )
    route.save()
    return success_response({"id": str(route.id), "route_name": route.route_name}, "Route created")


@router.get("/route")
async def list_routes(school_id: str, branch_code: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school_id = resolve_school_access(current_user, school_id)
    branch_code = resolve_branch_scope(current_user, branch_code)
    school = School.objects.get(id=school_id)
    routes = TransportRoute.objects(school=school, is_active=True)
    result = []
    for r in routes:
        student_query = StudentTransport.objects(route=r, is_active=True)
        if branch_code:
            branch_students = list(Student.objects(school=school, branch_code=branch_code, is_active=True))
            student_query = student_query.filter(student__in=branch_students)
        student_count = student_query.count()
        result.append({
            "id": str(r.id),
            "route_name": r.route_name,
            "route_code": r.route_code,
            "start_point": r.start_point,
            "end_point": r.end_point,
            "stops": r.stops or [],
            "distance_km": r.distance_km,
            "morning_departure": r.morning_departure,
            "afternoon_departure": r.afternoon_departure,
            "fee_per_month": r.fee_per_month,
            "student_count": student_count
        })
    return success_response(result)


@router.put("/route/{route_id}")
async def update_route(route_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        route = TransportRoute.objects.get(id=route_id)
        data.pop('id', None); data.pop('school_id', None)
        if 'route_name' in data:
            data['route_name'] = (data.get('route_name') or '').strip()
            if not data['route_name']:
                raise HTTPException(400, "Route name is required")
        if 'route_code' in data:
            data['route_code'] = (data.get('route_code') or '').strip() or None
        if 'start_point' in data:
            data['start_point'] = (data.get('start_point') or '').strip() or None
        if 'end_point' in data:
            data['end_point'] = (data.get('end_point') or '').strip() or None
        if 'fee_per_month' in data and data.get('fee_per_month') in (None, ''):
            raise HTTPException(400, "Route price is required")
        route.update(**data)
        return success_response(message="Route updated")
    except TransportRoute.DoesNotExist:
        raise HTTPException(404, "Route not found")


@router.delete("/route/{route_id}")
async def delete_route(route_id: str, current_user: User = Depends(get_current_user)):
    try:
        TransportRoute.objects.get(id=route_id).update(is_active=False)
        return success_response(message="Route deleted")
    except TransportRoute.DoesNotExist:
        raise HTTPException(404, "Route not found")


# ─── Vehicles ─────────────────────────────────────────────────────────────────
@router.post("/vehicle")
async def create_vehicle(data: dict, current_user: User = Depends(get_current_user)):
    data['school_id'] = resolve_school_access(current_user, data.get('school_id'))
    school = School.objects.get(id=data['school_id'])
    if Vehicle.objects(vehicle_no=data['vehicle_no']).first():
        raise HTTPException(400, "Vehicle number already registered")
    v = Vehicle(
        school=school,
        vehicle_no=data['vehicle_no'],
        vehicle_type=data.get('vehicle_type', 'Bus'),
        make_model=data.get('make_model'),
        capacity=data.get('capacity', 40),
        year_of_manufacture=data.get('year_of_manufacture'),
        fitness_expiry=datetime.fromisoformat(data['fitness_expiry']) if data.get('fitness_expiry') else None,
        insurance_expiry=datetime.fromisoformat(data['insurance_expiry']) if data.get('insurance_expiry') else None,
        permit_expiry=datetime.fromisoformat(data['permit_expiry']) if data.get('permit_expiry') else None,
        driver=data.get('driver'),
        status=data.get('status', 'Active')
    )
    if data.get('route_id'):
        v.route = TransportRoute.objects.get(id=data['route_id'])
    v.save()
    return success_response({"id": str(v.id), "vehicle_no": v.vehicle_no}, "Vehicle added")


@router.get("/vehicle")
async def list_vehicles(school_id: str, current_user: User = Depends(get_current_user)):
    school_id = resolve_school_access(current_user, school_id)
    school = School.objects.get(id=school_id)
    vehicles = Vehicle.objects(school=school, is_active=True)
    result = [{
        "id": str(v.id),
        "vehicle_no": v.vehicle_no,
        "vehicle_type": v.vehicle_type,
        "make_model": v.make_model,
        "capacity": v.capacity,
        "route_name": v.route.route_name if v.route else None,
        "driver": v.driver,
        "status": v.status,
        "fitness_expiry": v.fitness_expiry.isoformat() if v.fitness_expiry else None,
        "insurance_expiry": v.insurance_expiry.isoformat() if v.insurance_expiry else None,
    } for v in vehicles]
    return success_response(result)


@router.patch("/vehicle/{vehicle_id}/location")
async def update_vehicle_location(vehicle_id: str, lat: float, lng: float, current_user: User = Depends(get_current_user)):
    try:
        v = Vehicle.objects.get(id=vehicle_id)
        v.update(current_lat=lat, current_lng=lng, last_location_update=datetime.utcnow())
        return success_response({"lat": lat, "lng": lng}, "Location updated")
    except Vehicle.DoesNotExist:
        raise HTTPException(404, "Vehicle not found")


# ─── Drivers ──────────────────────────────────────────────────────────────────
@router.post("/driver")
async def create_driver(data: dict, current_user: User = Depends(get_current_user)):
    data['school_id'] = resolve_school_access(current_user, data.get('school_id'))
    school = School.objects.get(id=data['school_id'])
    d = Driver(
        school=school,
        name=data['name'],
        phone=data['phone'],
        license_no=data['license_no'],
        license_expiry=datetime.fromisoformat(data['license_expiry']) if data.get('license_expiry') else None,
        aadhar_number=data.get('aadhar_number'),
        address=data.get('address'),
        experience_years=data.get('experience_years', 0)
    )
    if data.get('vehicle_id'):
        d.assigned_vehicle = Vehicle.objects.get(id=data['vehicle_id'])
    d.save()
    return success_response({"id": str(d.id), "name": d.name}, "Driver added")


@router.get("/driver")
async def list_drivers(school_id: str, current_user: User = Depends(get_current_user)):
    school_id = resolve_school_access(current_user, school_id)
    school = School.objects.get(id=school_id)
    drivers = Driver.objects(school=school, is_active=True)
    result = [{
        "id": str(d.id),
        "name": d.name,
        "phone": d.phone,
        "license_no": d.license_no,
        "license_expiry": d.license_expiry.isoformat() if d.license_expiry else None,
        "experience_years": d.experience_years,
        "assigned_vehicle": d.assigned_vehicle.vehicle_no if d.assigned_vehicle else None
    } for d in drivers]
    return success_response(result)


# ─── Student Transport ────────────────────────────────────────────────────────
@router.post("/student-transport")
async def assign_student_transport(data: dict, current_user: User = Depends(get_current_user)):
    data['school_id'] = resolve_school_access(current_user, data.get('school_id'))
    school = School.objects.get(id=data['school_id'])
    student = Student.objects.get(id=data['student_id'])
    scoped_branch = resolve_branch_scope(current_user, None)
    if scoped_branch and student.branch_code != scoped_branch:
        raise HTTPException(403, "Access denied for this branch")
    route = TransportRoute.objects.get(id=data['route_id'])
    if StudentTransport.objects(student=student, is_active=True).first():
        raise HTTPException(400, "Student already assigned to a route")
    st = StudentTransport(
        school=school, student=student, route=route,
        pickup_stop=data.get('pickup_stop'),
        drop_stop=data.get('drop_stop'),
        pickup_time=data.get('pickup_time'),
        drop_time=data.get('drop_time'),
        fee_per_month=route.fee_per_month,
        academic_year=data.get('academic_year')
    )
    if data.get('vehicle_id'):
        st.vehicle = Vehicle.objects.get(id=data['vehicle_id'])
    st.save()
    student.update(uses_transport=True, transport_route=data['route_id'])
    return success_response({"id": str(st.id)}, "Student assigned to transport")


@router.get("/student-transport")
async def list_student_transport(school_id: str, route_id: Optional[str] = None, branch_code: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school_id = resolve_school_access(current_user, school_id)
    branch_code = resolve_branch_scope(current_user, branch_code)
    school = School.objects.get(id=school_id)
    query = StudentTransport.objects(school=school, is_active=True)
    if route_id:
        query = query.filter(route=TransportRoute.objects.get(id=route_id))
    if branch_code:
        branch_students = list(Student.objects(school=school, branch_code=branch_code, is_active=True))
        query = query.filter(student__in=branch_students)
    result = [{
        "id": str(st.id),
        "student_name": st.student.full_name if st.student else None,
        "admission_no": st.student.admission_no if st.student else None,
        "route_name": st.route.route_name if st.route else None,
        "pickup_stop": st.pickup_stop,
        "drop_stop": st.drop_stop,
        "pickup_time": st.pickup_time,
        "fee_per_month": st.fee_per_month
    } for st in query]
    return success_response(result)


# ─── Maintenance ─────────────────────────────────────────────────────────────
@router.post("/maintenance")
async def add_maintenance(data: dict, current_user: User = Depends(get_current_user)):
    data['school_id'] = resolve_school_access(current_user, data.get('school_id'))
    school = School.objects.get(id=data['school_id'])
    vehicle = Vehicle.objects.get(id=data['vehicle_id'])
    m = VehicleMaintenance(
        school=school, vehicle=vehicle,
        maintenance_type=data['maintenance_type'],
        description=data.get('description'),
        cost=data.get('cost', 0),
        vendor=data.get('vendor'),
        maintenance_date=datetime.fromisoformat(data['maintenance_date']) if data.get('maintenance_date') else datetime.utcnow(),
        next_due_date=datetime.fromisoformat(data['next_due_date']) if data.get('next_due_date') else None,
        odometer_reading=data.get('odometer_reading'),
        is_completed=data.get('is_completed', False)
    )
    m.save()
    if data.get('is_completed') is False:
        vehicle.update(status='In-Maintenance')
    return success_response({"id": str(m.id)}, "Maintenance record added")


@router.get("/maintenance/{vehicle_id}")
async def get_maintenance(vehicle_id: str, current_user: User = Depends(get_current_user)):
    vehicle = Vehicle.objects.get(id=vehicle_id)
    records = VehicleMaintenance.objects(vehicle=vehicle).order_by('-maintenance_date')
    result = [{
        "id": str(r.id),
        "maintenance_type": r.maintenance_type,
        "description": r.description,
        "cost": r.cost,
        "vendor": r.vendor,
        "maintenance_date": r.maintenance_date.isoformat() if r.maintenance_date else None,
        "next_due_date": r.next_due_date.isoformat() if r.next_due_date else None,
        "is_completed": r.is_completed
    } for r in records]
    return success_response(result)


@router.get("/stats/{school_id}")
async def transport_stats(school_id: str, branch_code: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    student_transport_query = StudentTransport.objects(school=school, is_active=True)
    if branch_code:
        branch_students = list(Student.objects(school=school, branch_code=branch_code, is_active=True))
        student_transport_query = student_transport_query.filter(student__in=branch_students)
    return success_response({
        "total_routes": TransportRoute.objects(school=school, is_active=True).count(),
        "total_vehicles": Vehicle.objects(school=school, is_active=True).count(),
        "active_vehicles": Vehicle.objects(school=school, is_active=True, status='Active').count(),
        "total_drivers": Driver.objects(school=school, is_active=True).count(),
        "students_using_transport": student_transport_query.count(),
    })
