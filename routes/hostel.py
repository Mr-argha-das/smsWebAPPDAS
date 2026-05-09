from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime
from models.hostel import Hostel, HostelRoom, HostelAllocation, HostelFeeInvoice, HostelLeaveRequest
from models.institution import School, User
from models.student import Student
from utils.auth import get_current_user
from utils.helpers import success_response

router = APIRouter(prefix="/hostel", tags=["Hostel Management"])


# ─── Hostel CRUD ─────────────────────────────────────────────────────────────
@router.post("")
async def create_hostel(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    h = Hostel(
        school=school,
        name=data['name'],
        hostel_type=data.get('hostel_type', 'Boys'),
        address=data.get('address'),
        warden_name=data.get('warden_name'),
        warden_phone=data.get('warden_phone'),
        monthly_fee=data.get('monthly_fee', 0),
        facilities=data.get('facilities', [])
    )
    h.save()
    return success_response({"id": str(h.id), "name": h.name}, "Hostel created")


@router.get("")
async def list_hostels(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    hostels = Hostel.objects(school=school, is_active=True)
    result = []
    for h in hostels:
        rooms = HostelRoom.objects(hostel=h, is_active=True)
        total_cap = sum(r.capacity for r in rooms)
        occupied = sum(r.occupied for r in rooms)
        result.append({
            "id": str(h.id), "name": h.name, "hostel_type": h.hostel_type,
            "warden_name": h.warden_name, "warden_phone": h.warden_phone,
            "monthly_fee": h.monthly_fee, "facilities": h.facilities or [],
            "total_rooms": rooms.count(), "total_capacity": total_cap,
            "occupied": occupied, "available": total_cap - occupied
        })
    return success_response(result)


@router.delete("/{hostel_id}")
async def delete_hostel(hostel_id: str, current_user: User = Depends(get_current_user)):
    try:
        Hostel.objects.get(id=hostel_id).update(is_active=False)
        return success_response(message="Hostel deleted")
    except Hostel.DoesNotExist:
        raise HTTPException(404, "Hostel not found")


# ─── Rooms ─────────────────────────────────────────────────────────────────────
@router.post("/room")
async def create_room(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    hostel = Hostel.objects.get(id=data['hostel_id'])
    room = HostelRoom(
        school=school, hostel=hostel,
        room_number=data['room_number'],
        floor=data.get('floor', 0),
        room_type=data.get('room_type', 'Double'),
        capacity=data.get('capacity', 2),
        monthly_fee=data.get('monthly_fee', hostel.monthly_fee),
        has_ac=data.get('has_ac', False),
        has_attached_bath=data.get('has_attached_bath', False)
    )
    room.save()
    return success_response({"id": str(room.id)}, "Room created")


@router.get("/room")
async def list_rooms(school_id: str, hostel_id: Optional[str] = None, available_only: bool = False, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    query = HostelRoom.objects(school=school, is_active=True)
    if hostel_id:
        query = query.filter(hostel=Hostel.objects.get(id=hostel_id))
    if available_only:
        query = query.filter(status='Available')
    result = [{
        "id": str(r.id), "room_number": r.room_number, "floor": r.floor,
        "room_type": r.room_type, "capacity": r.capacity, "occupied": r.occupied,
        "available_beds": r.capacity - r.occupied, "monthly_fee": r.monthly_fee,
        "has_ac": r.has_ac, "has_attached_bath": r.has_attached_bath, "status": r.status,
        "hostel_name": r.hostel.name if r.hostel else None
    } for r in query]
    return success_response(result)


# ─── Allocations ──────────────────────────────────────────────────────────────
@router.post("/allocate")
async def allocate_room(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    student = Student.objects.get(id=data['student_id'])
    hostel = Hostel.objects.get(id=data['hostel_id'])
    room = HostelRoom.objects.get(id=data['room_id'])

    if HostelAllocation.objects(student=student, status='Active').first():
        raise HTTPException(400, "Student already allocated a room")
    if room.occupied >= room.capacity:
        raise HTTPException(400, "Room is full")

    alloc = HostelAllocation(
        school=school, student=student, hostel=hostel, room=room,
        bed_number=data.get('bed_number'),
        academic_year=data.get('academic_year'),
        check_in_date=datetime.fromisoformat(data['check_in_date']) if data.get('check_in_date') else datetime.utcnow(),
        monthly_fee=room.monthly_fee,
        security_deposit=data.get('security_deposit', 0),
        deposit_paid=data.get('deposit_paid', False)
    )
    alloc.save()
    room.update(occupied=room.occupied + 1, status='Full' if room.occupied + 1 >= room.capacity else 'Available')
    return success_response({"id": str(alloc.id)}, "Room allocated successfully")


@router.get("/allocations")
async def get_allocations(school_id: str, hostel_id: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    query = HostelAllocation.objects(school=school, status='Active')
    if hostel_id:
        query = query.filter(hostel=Hostel.objects.get(id=hostel_id))
    result = [{
        "id": str(a.id),
        "student_name": a.student.full_name if a.student else '-',
        "admission_no": a.student.admission_no if a.student else '-',
        "hostel_name": a.hostel.name if a.hostel else '-',
        "room_number": a.room.room_number if a.room else '-',
        "bed_number": a.bed_number,
        "check_in_date": a.check_in_date.isoformat() if a.check_in_date else None,
        "monthly_fee": a.monthly_fee,
        "security_deposit": a.security_deposit,
        "deposit_paid": a.deposit_paid
    } for a in query]
    return success_response(result)


@router.patch("/checkout/{alloc_id}")
async def checkout_student(alloc_id: str, current_user: User = Depends(get_current_user)):
    try:
        alloc = HostelAllocation.objects.get(id=alloc_id)
        room = alloc.room
        alloc.update(status='Checked Out', check_out_date=datetime.utcnow())
        if room:
            new_occ = max(0, room.occupied - 1)
            room.update(occupied=new_occ, status='Available' if new_occ < room.capacity else 'Full')
        return success_response(message="Student checked out")
    except HostelAllocation.DoesNotExist:
        raise HTTPException(404, "Allocation not found")


# ─── Hostel Fees ──────────────────────────────────────────────────────────────
@router.post("/fee/generate")
async def generate_hostel_fees(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    month = data['month']
    year = data['year']
    allocations = HostelAllocation.objects(school=school, status='Active')
    created = 0
    for alloc in allocations:
        if not HostelFeeInvoice.objects(allocation=alloc, month=month, year=year).first():
            from datetime import date
            due = datetime(year, month + 1 if month < 12 else 1, 10)
            inv = HostelFeeInvoice(
                school=school, allocation=alloc, student=alloc.student,
                month=month, year=year, amount=alloc.monthly_fee,
                balance=alloc.monthly_fee, due_date=due
            )
            inv.save()
            created += 1
    return success_response({"created": created}, f"Generated {created} hostel fee invoices")


@router.get("/fee")
async def get_hostel_fees(school_id: str, month: Optional[int] = None, year: Optional[int] = None, status: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    query = HostelFeeInvoice.objects(school=school)
    if month: query = query.filter(month=month)
    if year: query = query.filter(year=year)
    if status: query = query.filter(status=status)
    result = [{
        "id": str(i.id),
        "student_name": i.student.full_name if i.student else '-',
        "admission_no": i.student.admission_no if i.student else '-',
        "month": i.month, "year": i.year,
        "amount": i.amount, "paid_amount": i.paid_amount, "balance": i.balance,
        "status": i.status,
        "due_date": i.due_date.isoformat() if i.due_date else None
    } for i in query.order_by('-year', '-month')[:100]]
    return success_response(result)


@router.patch("/fee/{invoice_id}/pay")
async def pay_hostel_fee(invoice_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        inv = HostelFeeInvoice.objects.get(id=invoice_id)
        paid = data.get('amount', inv.balance)
        new_paid = inv.paid_amount + paid
        new_balance = max(0, inv.amount - new_paid)
        status = 'Paid' if new_balance == 0 else 'Partial'
        inv.update(paid_amount=new_paid, balance=new_balance, status=status, paid_date=datetime.utcnow())
        return success_response({"balance": new_balance, "status": status}, "Payment recorded")
    except HostelFeeInvoice.DoesNotExist:
        raise HTTPException(404, "Invoice not found")


# ─── Leave Requests ────────────────────────────────────────────────────────────
@router.post("/leave")
async def create_leave(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    leave = HostelLeaveRequest(
        school=school,
        student=Student.objects.get(id=data['student_id']),
        from_date=datetime.fromisoformat(data['from_date']),
        to_date=datetime.fromisoformat(data['to_date']),
        reason=data.get('reason'),
        destination=data.get('destination'),
        guardian_phone=data.get('guardian_phone')
    )
    leave.save()
    return success_response({"id": str(leave.id)}, "Leave request submitted")


@router.get("/leave")
async def get_leaves(school_id: str, status: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    query = HostelLeaveRequest.objects(school=school)
    if status: query = query.filter(status=status)
    result = [{
        "id": str(l.id),
        "student_name": l.student.full_name if l.student else '-',
        "from_date": l.from_date.isoformat(), "to_date": l.to_date.isoformat(),
        "reason": l.reason, "destination": l.destination, "status": l.status
    } for l in query.order_by('-created_at')[:50]]
    return success_response(result)


@router.patch("/leave/{leave_id}/action")
async def action_leave(leave_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        HostelLeaveRequest.objects.get(id=leave_id).update(
            status=data['status'], approved_by=current_user.full_name, remarks=data.get('remarks'))
        return success_response(message=f"Leave {data['status']}")
    except HostelLeaveRequest.DoesNotExist:
        raise HTTPException(404, "Leave not found")


@router.get("/stats/{school_id}")
async def hostel_stats(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    rooms = list(HostelRoom.objects(school=school, is_active=True))
    total_cap = sum(r.capacity for r in rooms)
    occupied = sum(r.occupied for r in rooms)
    return success_response({
        "total_hostels": Hostel.objects(school=school, is_active=True).count(),
        "total_rooms": len(rooms),
        "total_capacity": total_cap,
        "occupied_beds": occupied,
        "available_beds": total_cap - occupied,
        "occupancy_rate": round(occupied / total_cap * 100, 1) if total_cap > 0 else 0,
        "pending_leaves": HostelLeaveRequest.objects(school=school, status='Pending').count(),
        "fee_defaulters": HostelFeeInvoice.objects(school=school, status__in=['Pending', 'Partial', 'Overdue']).count()
    })
