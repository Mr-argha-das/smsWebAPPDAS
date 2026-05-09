from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime
from models.inventory import AssetCategory, Asset, StockItem, StockTransaction
from models.health import HealthRecord, MedicalVisit, HealthAlert, VaccinationRecord
from models.communication import Notice, Event, Message, Notification
from models.institution import School, User
from models.student import Student
from models.staff import Staff
from utils.auth import get_current_user
from utils.helpers import success_response

# ═══════════════════════════════════════════════════════════════════════════════
#  INVENTORY ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
inventory_router = APIRouter(prefix="/inventory", tags=["Inventory & Assets"])


@inventory_router.post("/asset-category")
async def create_asset_category(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    cat = AssetCategory(school=school, name=data['name'], description=data.get('description'), depreciation_rate=data.get('depreciation_rate', 10))
    cat.save()
    return success_response({"id": str(cat.id)}, "Category created")


@inventory_router.get("/asset-category")
async def list_asset_categories(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    cats = AssetCategory.objects(school=school, is_active=True)
    return success_response([{"id": str(c.id), "name": c.name, "depreciation_rate": c.depreciation_rate} for c in cats])


@inventory_router.post("/asset")
async def add_asset(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    from utils.helpers import generate_id
    asset = Asset(
        school=school,
        asset_name=data['asset_name'],
        asset_code=data.get('asset_code') or generate_id("AST"),
        asset_type=data.get('asset_type', 'Other'),
        class_name=data.get('class_name'),
        brand=data.get('brand'),
        model_no=data.get('model_no'),
        serial_no=data.get('serial_no'),
        purchase_date=datetime.fromisoformat(data['purchase_date']) if data.get('purchase_date') else None,
        purchase_price=data.get('purchase_price', 0),
        current_value=data.get('current_value', data.get('purchase_price', 0)),
        vendor=data.get('vendor'),
        warranty_expiry=datetime.fromisoformat(data['warranty_expiry']) if data.get('warranty_expiry') else None,
        location=data.get('location'),
        assigned_to=data.get('assigned_to'),
        condition=data.get('condition', 'Good'),
        status=data.get('status', 'Available')
    )
    if data.get('category_id'):
        asset.category = AssetCategory.objects.get(id=data['category_id'])
    asset.save()
    return success_response({"id": str(asset.id), "asset_code": asset.asset_code}, "Asset added")


@inventory_router.get("/asset")
async def list_assets(
    school_id: str, asset_type: Optional[str] = None,
    status: Optional[str] = None, search: Optional[str] = None,
    class_name: Optional[str] = None,
    page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = Asset.objects(school=school, is_active=True)
    if asset_type: query = query.filter(asset_type=asset_type)
    if status: query = query.filter(status=status)
    if class_name: query = query.filter(class_name=class_name)
    if search:
        query = query.filter(__raw__={"$or": [
            {"asset_name": {"$regex": search, "$options": "i"}},
            {"asset_code": {"$regex": search, "$options": "i"}},
            {"class_name": {"$regex": search, "$options": "i"}}
        ]})
    total = query.count()
    assets = query.skip((page-1)*per_page).limit(per_page)
    result = [{
        "id": str(a.id), "asset_name": a.asset_name, "asset_code": a.asset_code,
        "asset_type": a.asset_type, "class_name": a.class_name,
        "brand": a.brand, "model_no": a.model_no, "serial_no": a.serial_no,
        "purchase_price": a.purchase_price, "current_value": a.current_value,
        "condition": a.condition, "status": a.status, "location": a.location,
        "assigned_to": a.assigned_to,
        "purchase_date": a.purchase_date.isoformat() if a.purchase_date else None,
        "warranty_expiry": a.warranty_expiry.isoformat() if a.warranty_expiry else None
    } for a in assets]
    return success_response(result, meta={"total": total, "page": page})


@inventory_router.put("/asset/{asset_id}")
async def update_asset(asset_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        a = Asset.objects.get(id=asset_id)
        data.pop('id', None); data.pop('school_id', None)
        if 'purchase_date' in data:
            data['purchase_date'] = datetime.fromisoformat(data['purchase_date']) if data.get('purchase_date') else None
        if 'warranty_expiry' in data:
            data['warranty_expiry'] = datetime.fromisoformat(data['warranty_expiry']) if data.get('warranty_expiry') else None
        a.update(**data)
        return success_response(message="Asset updated")
    except Asset.DoesNotExist:
        raise HTTPException(404, "Asset not found")


@inventory_router.delete("/asset/{asset_id}")
async def delete_asset(asset_id: str, current_user: User = Depends(get_current_user)):
    try:
        Asset.objects.get(id=asset_id).update(is_active=False)
        return success_response(message="Asset deleted")
    except Asset.DoesNotExist:
        raise HTTPException(404, "Asset not found")


@inventory_router.post("/stock-item")
async def add_stock_item(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    item = StockItem(
        school=school,
        item_name=data['item_name'],
        item_code=data['item_code'],
        class_name=data.get('class_name'),
        category=data.get('category', 'Other'),
        unit=data.get('unit', 'Nos'),
        current_stock=data.get('current_stock', 0),
        minimum_stock=data.get('minimum_stock', 10),
        maximum_stock=data.get('maximum_stock', 500),
        unit_price=data.get('unit_price', 0),
        location=data.get('location')
    )
    item.save()
    return success_response({"id": str(item.id)}, "Stock item added")


@inventory_router.get("/stock-item")
async def list_stock_items(school_id: str, low_stock: bool = False, search: Optional[str] = None, class_name: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    query = StockItem.objects(school=school, is_active=True)
    if class_name:
        query = query.filter(class_name=class_name)
    if search:
        query = query.filter(__raw__={"$or": [
            {"item_name": {"$regex": search, "$options": "i"}},
            {"item_code": {"$regex": search, "$options": "i"}},
            {"class_name": {"$regex": search, "$options": "i"}}
        ]})
    items = list(query)
    if low_stock:
        items = [i for i in items if i.current_stock <= i.minimum_stock]
    result = [{
        "id": str(i.id), "item_name": i.item_name, "item_code": i.item_code,
        "class_name": i.class_name,
        "category": i.category, "unit": i.unit,
        "current_stock": i.current_stock, "minimum_stock": i.minimum_stock,
        "unit_price": i.unit_price, "location": i.location,
        "is_low_stock": i.current_stock <= i.minimum_stock,
        "stock_value": i.current_stock * i.unit_price
    } for i in items]
    return success_response(result)


@inventory_router.put("/stock-item/{item_id}")
async def update_stock_item(item_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        item = StockItem.objects.get(id=item_id)
        data.pop('id', None)
        data.pop('school_id', None)
        item.update(**data)
        return success_response(message="Stock item updated")
    except StockItem.DoesNotExist:
        raise HTTPException(404, "Stock item not found")


@inventory_router.delete("/stock-item/{item_id}")
async def delete_stock_item(item_id: str, current_user: User = Depends(get_current_user)):
    try:
        StockItem.objects.get(id=item_id).update(is_active=False)
        return success_response(message="Stock item deleted")
    except StockItem.DoesNotExist:
        raise HTTPException(404, "Stock item not found")


@inventory_router.post("/stock-transaction")
async def add_stock_transaction(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    item = StockItem.objects.get(id=data['item_id'])
    qty = data['quantity']
    if data['transaction_type'] == 'Out' and item.current_stock < qty:
        raise HTTPException(400, f"Insufficient stock. Available: {item.current_stock}")
    new_balance = item.current_stock + qty if data['transaction_type'] == 'In' else item.current_stock - qty
    txn = StockTransaction(
        school=school, item=item,
        transaction_type=data['transaction_type'],
        quantity=qty, unit_price=data.get('unit_price', item.unit_price),
        total_price=qty * data.get('unit_price', item.unit_price),
        vendor=data.get('vendor'), invoice_no=data.get('invoice_no'),
        purpose=data.get('purpose'), done_by=current_user.full_name,
        balance_after=new_balance, remarks=data.get('remarks')
    )
    txn.save()
    item.update(current_stock=new_balance)
    return success_response({"id": str(txn.id), "new_balance": new_balance}, "Transaction recorded")


@inventory_router.get("/stock-transactions/{item_id}")
async def get_stock_transactions(item_id: str, current_user: User = Depends(get_current_user)):
    item = StockItem.objects.get(id=item_id)
    txns = StockTransaction.objects(item=item).order_by('-transaction_date')[:50]
    result = [{
        "id": str(t.id), "type": t.transaction_type, "quantity": t.quantity,
        "unit_price": t.unit_price, "total_price": t.total_price,
        "vendor": t.vendor, "purpose": t.purpose, "done_by": t.done_by,
        "balance_after": t.balance_after,
        "date": t.transaction_date.isoformat()
    } for t in txns]
    return success_response(result)


@inventory_router.get("/stats/{school_id}")
async def inventory_stats(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    assets = list(Asset.objects(school=school, is_active=True))
    items = list(StockItem.objects(school=school, is_active=True))
    return success_response({
        "total_assets": len(assets),
        "total_asset_value": sum(a.current_value for a in assets),
        "assets_in_use": sum(1 for a in assets if a.status == 'In-Use'),
        "assets_under_maintenance": sum(1 for a in assets if a.status == 'Under-Maintenance'),
        "total_stock_items": len(items),
        "low_stock_items": sum(1 for i in items if i.current_stock <= i.minimum_stock),
        "total_stock_value": sum(i.current_stock * i.unit_price for i in items)
    })


# ═══════════════════════════════════════════════════════════════════════════════
#  HEALTH ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
health_router = APIRouter(prefix="/health", tags=["Health & Medical"])


@health_router.post("/record")
async def create_health_record(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    # Calculate BMI
    bmi = None
    if data.get('height_cm') and data.get('weight_kg'):
        h = data['height_cm'] / 100
        bmi = round(data['weight_kg'] / (h * h), 2)
    record = HealthRecord(
        school=school,
        member_type=data['member_type'],
        height_cm=data.get('height_cm'),
        weight_kg=data.get('weight_kg'),
        bmi=bmi,
        blood_group=data.get('blood_group'),
        vision_left=data.get('vision_left'),
        vision_right=data.get('vision_right'),
        allergies=data.get('allergies', []),
        chronic_conditions=data.get('chronic_conditions', []),
        current_medications=data.get('current_medications', []),
        disability=data.get('disability'),
        emergency_contact_name=data.get('emergency_contact_name'),
        emergency_contact_phone=data.get('emergency_contact_phone'),
        emergency_contact_relation=data.get('emergency_contact_relation'),
        doctor_name=data.get('doctor_name'),
        doctor_phone=data.get('doctor_phone'),
        hospital_name=data.get('hospital_name'),
        last_checkup_date=datetime.fromisoformat(data['last_checkup_date']) if data.get('last_checkup_date') else None
    )
    if data.get('student_id'):
        record.student = Student.objects.get(id=data['student_id'])
    if data.get('staff_id'):
        record.staff_ref = Staff.objects.get(id=data['staff_id'])
    record.save()
    return success_response({"id": str(record.id), "bmi": bmi}, "Health record created")


@health_router.get("/record/{member_id}")
async def get_health_record(member_id: str, member_type: str = 'Student', current_user: User = Depends(get_current_user)):
    if member_type == 'Student':
        student = Student.objects.get(id=member_id)
        record = HealthRecord.objects(student=student).first()
    else:
        staff = Staff.objects.get(id=member_id)
        record = HealthRecord.objects(staff_ref=staff).first()
    if not record:
        raise HTTPException(404, "Health record not found")
    return success_response({
        "id": str(record.id),
        "height_cm": record.height_cm, "weight_kg": record.weight_kg, "bmi": record.bmi,
        "blood_group": record.blood_group, "vision_left": record.vision_left, "vision_right": record.vision_right,
        "allergies": record.allergies, "chronic_conditions": record.chronic_conditions,
        "current_medications": record.current_medications, "disability": record.disability,
        "emergency_contact_name": record.emergency_contact_name,
        "emergency_contact_phone": record.emergency_contact_phone,
        "doctor_name": record.doctor_name, "doctor_phone": record.doctor_phone,
        "hospital_name": record.hospital_name,
        "vaccinations": [{"vaccine": v.vaccine_name, "dose": v.dose_number, "date": v.date_given.isoformat() if v.date_given else None} for v in record.vaccinations],
        "last_checkup_date": record.last_checkup_date.isoformat() if record.last_checkup_date else None
    })


@health_router.post("/medical-visit")
async def add_medical_visit(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    visit = MedicalVisit(
        school=school, member_type=data.get('member_type', 'Student'),
        complaint=data['complaint'],
        symptoms=data.get('symptoms', []),
        temperature=data.get('temperature'),
        bp_systolic=data.get('bp_systolic'), bp_diastolic=data.get('bp_diastolic'),
        pulse_rate=data.get('pulse_rate'),
        diagnosis=data.get('diagnosis'),
        treatment_given=data.get('treatment_given'),
        medicines_prescribed=data.get('medicines_prescribed', []),
        referred_to=data.get('referred_to'),
        attended_by=data.get('attended_by', current_user.full_name),
        is_emergency=data.get('is_emergency', False),
        is_hospitalized=data.get('is_hospitalized', False),
        notes=data.get('notes'),
        follow_up_date=datetime.fromisoformat(data['follow_up_date']) if data.get('follow_up_date') else None
    )
    if data.get('student_id'):
        visit.student = Student.objects.get(id=data['student_id'])
    if data.get('staff_id'):
        visit.staff_ref = Staff.objects.get(id=data['staff_id'])
    visit.save()
    return success_response({"id": str(visit.id)}, "Medical visit recorded")


@health_router.get("/visits")
async def get_medical_visits(
    school_id: str, student_id: Optional[str] = None,
    is_emergency: Optional[bool] = None,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = MedicalVisit.objects(school=school)
    if student_id:
        query = query.filter(student=Student.objects.get(id=student_id))
    if is_emergency is not None:
        query = query.filter(is_emergency=is_emergency)
    result = [{
        "id": str(v.id),
        "student_name": v.student.full_name if v.student else '-',
        "complaint": v.complaint, "diagnosis": v.diagnosis,
        "temperature": v.temperature,
        "attended_by": v.attended_by,
        "is_emergency": v.is_emergency,
        "visit_date": v.visit_date.isoformat()
    } for v in query.order_by('-visit_date')[:50]]
    return success_response(result)


@health_router.post("/alert")
async def create_health_alert(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    alert = HealthAlert(
        school=school, alert_type=data['alert_type'],
        title=data['title'], description=data.get('description'),
        severity=data.get('severity', 'Medium'),
        affected_count=data.get('affected_count', 0),
        created_by=current_user.full_name
    )
    alert.save()
    return success_response({"id": str(alert.id)}, "Health alert created")


@health_router.get("/alerts/{school_id}")
async def get_health_alerts(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    alerts = HealthAlert.objects(school=school, is_active=True).order_by('-created_at')
    result = [{
        "id": str(a.id), "title": a.title, "alert_type": a.alert_type,
        "severity": a.severity, "description": a.description,
        "affected_count": a.affected_count, "created_by": a.created_by,
        "created_at": a.created_at.isoformat()
    } for a in alerts]
    return success_response(result)


# ═══════════════════════════════════════════════════════════════════════════════
#  COMMUNICATION ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
communication_router = APIRouter(prefix="/communication", tags=["Communication"])


@communication_router.post("/notice")
async def create_notice(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    notice = Notice(
        school=school, title=data['title'], content=data['content'],
        notice_type=data.get('notice_type', 'General'),
        target_audience=data.get('target_audience', ['All']),
        target_classes=data.get('target_classes', []),
        attachments=data.get('attachments', []),
        is_pinned=data.get('is_pinned', False),
        is_published=data.get('is_published', True),
        publish_date=datetime.utcnow(),
        expiry_date=datetime.fromisoformat(data['expiry_date']) if data.get('expiry_date') else None,
        created_by=current_user.full_name
    )
    notice.save()
    return success_response({"id": str(notice.id)}, "Notice created")


@communication_router.get("/notice")
async def list_notices(
    school_id: str, notice_type: Optional[str] = None,
    page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = Notice.objects(school=school, is_published=True)
    if notice_type:
        query = query.filter(notice_type=notice_type)
    total = query.count()
    notices = query.order_by('-is_pinned', '-created_at').skip((page-1)*per_page).limit(per_page)
    result = [{
        "id": str(n.id), "title": n.title, "content": n.content,
        "notice_type": n.notice_type, "is_pinned": n.is_pinned,
        "target_audience": n.target_audience, "views": n.views,
        "created_by": n.created_by,
        "publish_date": n.publish_date.isoformat() if n.publish_date else None,
        "expiry_date": n.expiry_date.isoformat() if n.expiry_date else None
    } for n in notices]
    return success_response(result, meta={"total": total, "page": page})


@communication_router.post("/event")
async def create_event(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    event = Event(
        school=school, title=data['title'], description=data.get('description'),
        event_type=data.get('event_type', 'Academic'),
        venue=data.get('venue'),
        start_datetime=datetime.fromisoformat(data['start_datetime']),
        end_datetime=datetime.fromisoformat(data['end_datetime']) if data.get('end_datetime') else None,
        organizer=data.get('organizer', current_user.full_name),
        target_audience=data.get('target_audience', ['All']),
        max_participants=data.get('max_participants'),
        created_by=current_user.full_name
    )
    event.save()
    return success_response({"id": str(event.id)}, "Event created")


@communication_router.get("/event")
async def list_events(
    school_id: str, upcoming_only: bool = False,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = Event.objects(school=school)
    if upcoming_only:
        query = query.filter(start_datetime__gte=datetime.utcnow(), status='Upcoming')
    result = [{
        "id": str(e.id), "title": e.title, "description": e.description,
        "event_type": e.event_type, "venue": e.venue,
        "start_datetime": e.start_datetime.isoformat(),
        "end_datetime": e.end_datetime.isoformat() if e.end_datetime else None,
        "organizer": e.organizer, "status": e.status,
        "target_audience": e.target_audience
    } for e in query.order_by('start_datetime')[:50]]
    return success_response(result)


@communication_router.post("/message")
async def send_message(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    msg = Message(
        school=school,
        sender_id=str(current_user.id),
        sender_name=current_user.full_name,
        sender_type=data.get('sender_type', 'Admin'),
        recipient_id=data['recipient_id'],
        recipient_name=data.get('recipient_name'),
        recipient_type=data.get('recipient_type'),
        subject=data.get('subject'),
        content=data['content'],
        attachments=data.get('attachments', [])
    )
    msg.save()
    # Create notification for recipient
    Notification(
        school=school, user_id=data['recipient_id'],
        title=f"New message from {current_user.full_name}",
        body=data['content'][:100],
        notification_type='Message',
        data={"message_id": str(msg.id)}
    ).save()
    return success_response({"id": str(msg.id)}, "Message sent")


@communication_router.get("/messages/{user_id}")
async def get_messages(user_id: str, school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    inbox = Message.objects(school=school, recipient_id=user_id, is_deleted_by_recipient=False).order_by('-sent_at')[:30]
    sent = Message.objects(school=school, sender_id=user_id, is_deleted_by_sender=False).order_by('-sent_at')[:30]
    def fmt(m):
        return {"id": str(m.id), "subject": m.subject, "content": m.content,
                "sender_name": m.sender_name, "recipient_name": m.recipient_name,
                "is_read": m.is_read, "sent_at": m.sent_at.isoformat()}
    return success_response({"inbox": [fmt(m) for m in inbox], "sent": [fmt(m) for m in sent]})


@communication_router.get("/notifications/{user_id}")
async def get_notifications(user_id: str, school_id: str, unread_only: bool = False, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    query = Notification.objects(school=school, user_id=user_id)
    if unread_only:
        query = query.filter(is_read=False)
    notifs = query.order_by('-sent_at')[:50]
    result = [{
        "id": str(n.id), "title": n.title, "body": n.body,
        "type": n.notification_type, "is_read": n.is_read,
        "sent_at": n.sent_at.isoformat()
    } for n in notifs]
    unread_count = Notification.objects(school=school, user_id=user_id, is_read=False).count()
    return success_response(result, meta={"unread_count": unread_count})


@communication_router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, current_user: User = Depends(get_current_user)):
    try:
        Notification.objects.get(id=notification_id).update(is_read=True, read_at=datetime.utcnow())
        return success_response(message="Marked as read")
    except Notification.DoesNotExist:
        raise HTTPException(404, "Notification not found")
