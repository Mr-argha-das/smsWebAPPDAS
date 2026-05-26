from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from io import BytesIO
import os
import re
import smtplib
from email.message import EmailMessage
from mongoengine.errors import NotUniqueError
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from models.fees import FeeCategory, FeeStructure, FeeInvoice, PaymentTransaction, FeeDiscount
from models.institution import School, AcademicYear, ClassRoom, User
from models.student import Student
from models.transport import TransportRoute
from utils.auth import get_current_user, resolve_school_access, resolve_branch_scope
from utils.helpers import success_response, generate_transaction_no
from config import settings
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus.flowables import HRFlowable
from io import BytesIO
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT


router = APIRouter(prefix="/fees", tags=["Fees Management"])

ALLOWED_FEE_STRUCTURE_CATEGORIES = [
    {"name": "Registration Fee", "code": "REG"},
    {"name": "Admission Fee", "code": "ADM"},
    {"name": "Annual Examination Fee", "code": "EXAM"},
    {"name": "Stationary kit / Activity Charge", "code": "ACT"},
    {"name": "Uniform Fee", "code": "UNI"},
    {"name": "Tuition Fee Mly", "code": "TUI"},
    {"name": "Books Fee", "code": "BOOK"},
    {"name": "Note Book Fee", "code": "NOTE"},
    {"name": "Dairy Fee", "code": "DAIRY"},
]
YEARLY_TUITION_LABEL = "Tuition Fee Yearly Upto 30th April 2027"

ALLOWED_CATEGORY_BY_CODE = {item["code"]: item for item in ALLOWED_FEE_STRUCTURE_CATEGORIES}
ALLOWED_CATEGORY_BY_NAME = {item["name"].lower(): item for item in ALLOWED_FEE_STRUCTURE_CATEGORIES}
ALLOWED_CATEGORY_ALIASES = {
    "tuition fee monthly": "TUI",
    "tuition fee yearly": "TUI",
    "uniform fee": "UNI",
    "books fee": "BOOK",
    "note book fee": "NOTE",
    "notebook fee": "NOTE",
    "dairy fee": "DAIRY",
}


def _normalize_fee_category(name: str, code: str):
    normalized_name = (name or "").strip()
    normalized_code = (code or "").strip().upper()
    alias_code = ALLOWED_CATEGORY_ALIASES.get(normalized_name.lower())
    allowed = ALLOWED_CATEGORY_BY_CODE.get(normalized_code or alias_code or "") or ALLOWED_CATEGORY_BY_NAME.get(normalized_name.lower())
    if not allowed:
        raise HTTPException(
            status_code=400,
            detail="Only these fee structure categories are allowed: Registration Fee, Admission Fee, Annual Examination Fee, Stationary kit / Activity Charge, Uniform Fee, Tuition Fee Mly, Books Fee, Note Book Fee, Dairy Fee",
        )
    return allowed["name"], allowed["code"]


def _is_allowed_fee_category(category: FeeCategory) -> bool:
    if not category:
        return False
    return bool(
        ALLOWED_CATEGORY_BY_CODE.get((category.code or "").strip().upper()) or
        ALLOWED_CATEGORY_BY_NAME.get((category.name or "").strip().lower())
    )


def _build_fee_breakdown(items: List) -> dict:
    breakdown = {item["code"]: 0 for item in ALLOWED_FEE_STRUCTURE_CATEGORIES}
    for entry in items or []:
        category_obj = getattr(entry, "category", None)
        category_name = getattr(entry, "category_name", None)
        code = (getattr(category_obj, "code", "") or "").strip().upper()
        if not code:
            matched = ALLOWED_CATEGORY_BY_NAME.get((category_name or "").strip().lower())
            code = matched["code"] if matched else ""
        if code in breakdown:
            breakdown[code] = float(getattr(entry, "amount", 0) or 0)
    breakdown["TUIY"] = breakdown["REG"] + breakdown["ADM"] + breakdown["EXAM"] + breakdown["ACT"] + breakdown["UNI"] + breakdown["BOOK"] + breakdown["NOTE"] + breakdown["DAIRY"] + (breakdown["TUI"] * 12)
    return breakdown


# ─── Fee Category ─────────────────────────────────────────────────────────────

@router.post("/category")
async def create_fee_category(data: dict, current_user: User = Depends(get_current_user)):
    data['school_id'] = resolve_school_access(current_user, data.get('school_id'))
    school = School.objects.get(id=data['school_id'])
    name = (data.get('name') or '').strip()
    code = (data.get('code') or '').strip().upper()
    if not name or not code:
        raise HTTPException(status_code=400, detail="Name and code are required")
    name, code = _normalize_fee_category(name, code)

    existing = FeeCategory.objects(
        school=school,
        is_active=True
    ).filter(__raw__={
        "$or": [
            {"name": {"$regex": f"^{name}$", "$options": "i"}},
            {"code": {"$regex": f"^{code}$", "$options": "i"}}
        ]
    }).first()
    if existing:
        return success_response({"id": str(existing.id)}, "Fee category already exists")

    cat = FeeCategory(
        school=school, name=name, code=code,
        description=data.get('description'),
        is_mandatory=data.get('is_mandatory', True)
    )
    cat.save()
    return success_response({"id": str(cat.id)}, "Fee category created")


@router.get("/category")
async def list_fee_categories(school_id: str, current_user: User = Depends(get_current_user)):
    school_id = resolve_school_access(current_user, school_id)
    school = School.objects.get(id=school_id)
    cats = FeeCategory.objects(school=school, is_active=True)
    result = [
        {"id": str(c.id), "name": c.name, "code": c.code, "is_mandatory": c.is_mandatory}
        for c in cats if _is_allowed_fee_category(c)
    ]
    return success_response(result)


# ─── Fee Structure ────────────────────────────────────────────────────────────

class FeeStructureCreate(BaseModel):
    school_id: str
    academic_year_id: Optional[str] = None
    classroom_id: str
    name: str
    items: List[dict]
    installments: int = 1
    late_fee_per_day: float = 0
    grace_days: int = 0


def _build_fee_structure_items(items: List[dict]):
    from models.fees import FeeStructureItem

    fee_items_by_code = {}
    for item in items:
        cat = FeeCategory.objects.get(id=item['category_id'])
        if not _is_allowed_fee_category(cat):
            raise HTTPException(
                status_code=400,
                detail=f"{cat.name} is not allowed in fee structure. Use only the approved fee fields."
            )
        code = (cat.code or cat.name or str(cat.id)).strip().upper()
        fee_items_by_code[code] = FeeStructureItem(category=cat, category_name=cat.name, amount=item['amount'])
    return list(fee_items_by_code.values())


def _fee_structure_signature(items: List) -> tuple:
    return tuple(sorted(
        (
            (getattr(getattr(item, "category", None), "code", "") or getattr(item, "category_name", "") or "").strip().upper(),
            round(float(getattr(item, "amount", 0) or 0), 2)
        )
        for item in items or []
    ))


def _resolve_academic_year(school: School, academic_year_id: Optional[str] = None) -> AcademicYear:
    if academic_year_id:
        try:
            academic_year = AcademicYear.objects.get(id=academic_year_id)
            if academic_year.school and str(academic_year.school.id) != str(school.id):
                raise HTTPException(400, "Academic year does not belong to this school")
            return academic_year
        except HTTPException:
            raise
        except Exception:
            pass

    current_year = AcademicYear.objects(school=school, is_current=True, is_active=True).first()
    if current_year:
        return current_year

    fallback_year = AcademicYear.objects(school=school, is_active=True).order_by("-created_at").first()
    if fallback_year:
        return fallback_year

    raise HTTPException(404, "Configure school and academic year")


@router.post("/structure")
async def create_fee_structure(data: FeeStructureCreate, current_user: User = Depends(get_current_user)):
    data.school_id = resolve_school_access(current_user, data.school_id)
    school = School.objects.get(id=data.school_id)
    ay = _resolve_academic_year(school, data.academic_year_id)
    classroom = ClassRoom.objects.get(id=data.classroom_id)
    
    fee_items = _build_fee_structure_items(data.items)
    incoming_signature = _fee_structure_signature(fee_items)
    existing_structure = FeeStructure.objects(
        school=school,
        academic_year=ay,
        classroom=classroom,
        name=data.name,
        is_active=True
    ).first()
    if existing_structure and _fee_structure_signature(existing_structure.items) == incoming_signature:
        return success_response({
            "id": str(existing_structure.id),
            "total_amount": existing_structure.total_amount,
            "fee_breakdown": _build_fee_breakdown(existing_structure.items)
        }, "Fee structure already exists")

    fs = FeeStructure(
        school=school, academic_year=ay, classroom=classroom,
        name=data.name, installments=data.installments,
        late_fee_per_day=data.late_fee_per_day,
        grace_days=data.grace_days
    )

    fs.items = fee_items
    fs.total_amount = _build_fee_breakdown(fs.items)["TUIY"]
    fs.save()
    return success_response({"id": str(fs.id), "total_amount": fs.total_amount, "fee_breakdown": _build_fee_breakdown(fs.items)}, "Fee structure created")


@router.get("/structure")
async def list_fee_structures(
    school_id: str,
    academic_year_id: Optional[str] = None,
    classroom_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school_id = resolve_school_access(current_user, school_id)
    school = School.objects.get(id=school_id)
    query = FeeStructure.objects(school=school, is_active=True)
    if academic_year_id:
        ay = AcademicYear.objects.get(id=academic_year_id)
        query = query.filter(academic_year=ay)
    if classroom_id:
        cls = ClassRoom.objects.get(id=classroom_id)
        query = query.filter(classroom=cls)
    
    result = [{
        "id": str(f.id),
        "name": f.name,
        "classroom": f.classroom.name if f.classroom else None,
        "classroom_id": str(f.classroom.id) if f.classroom else None,
        "total_amount": f.total_amount,
        "installments": f.installments,
        "late_fee_per_day": f.late_fee_per_day,
        "items": [{"category": i.category_name, "amount": i.amount} for i in f.items],
        "fee_breakdown": _build_fee_breakdown(f.items),
        "yearly_label": YEARLY_TUITION_LABEL,
    } for f in query]
    return success_response(result)


@router.put("/structure/{structure_id}")
async def update_fee_structure(structure_id: str, data: FeeStructureCreate, current_user: User = Depends(get_current_user)):
    fee_structure = FeeStructure.objects(id=structure_id, is_active=True).first()
    if not fee_structure:
        raise HTTPException(404, "Fee structure not found")

    data.school_id = resolve_school_access(current_user, data.school_id)
    if str(fee_structure.school.id) != data.school_id:
        raise HTTPException(403, "Access denied")

    school = School.objects.get(id=data.school_id)
    ay = _resolve_academic_year(school, data.academic_year_id)
    classroom = ClassRoom.objects.get(id=data.classroom_id)
    fee_items = _build_fee_structure_items(data.items)
    total_amount = _build_fee_breakdown(fee_items)["TUIY"]

    fee_structure.update(
        academic_year=ay,
        classroom=classroom,
        name=data.name,
        items=fee_items,
        installments=data.installments,
        late_fee_per_day=data.late_fee_per_day,
        grace_days=data.grace_days,
        total_amount=total_amount
    )
    return success_response({"id": str(fee_structure.id), "total_amount": total_amount}, "Fee structure updated")


@router.delete("/structure/{structure_id}")
async def delete_fee_structure(structure_id: str, current_user: User = Depends(get_current_user)):
    fee_structure = FeeStructure.objects(id=structure_id, is_active=True).first()
    if not fee_structure:
        raise HTTPException(404, "Fee structure not found")
    resolve_school_access(current_user, str(fee_structure.school.id))
    fee_structure.update(is_active=False)
    return success_response(message="Fee structure deleted")


# ─── Invoice ──────────────────────────────────────────────────────────────────

class InvoiceCreate(BaseModel):
    school_id: str
    student_id: str
    academic_year_id: Optional[str] = None
    fee_structure_id: Optional[str] = None
    selected_fee_heads: Optional[List[str]] = None
    items: List[dict] = []
    due_date: Optional[datetime] = None
    discount_amount: float = 0
    remarks: Optional[str] = None
    tuition_months: List[str] = []
    include_transport: bool = False
    transport_months: List[str] = []
    concession_name: Optional[str] = None
    concession_percent: float = 0


class InvoiceEmailRequest(BaseModel):
    recipient_type: str = "parent"
    email: Optional[str] = None


def _generate_invoice_no() -> str:
    year_suffix = str(datetime.now().year)[-2:]
    prefix = f"INV-{year_suffix}"
    pattern = f"^{re.escape(prefix)}\\d+$"
    max_seq = 0
    for invoice in FeeInvoice.objects(invoice_no__regex=pattern).only("invoice_no"):
        suffix = (invoice.invoice_no or "")[len(prefix):]
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    return f"{prefix}{max_seq + 1:02d}"


def _build_invoice_items(student: Student, fee_structure_id: Optional[str], items: List[dict], include_transport: bool, transport_months: List[str], tuition_months: Optional[List[str]] = None, selected_fee_heads: Optional[List[str]] = None, concession_percent: float = 0):
    built_items = []
    manual_items_by_category = {}
    for item in items or []:
        category = (item.get("category") or item.get("description") or "").strip()
        if not category:
            continue
        amount = float(item.get("amount") or 0)
        if amount <= 0:
            continue
        manual_items_by_category[category.lower()] = {
            **item,
            "category": category,
            "description": (item.get("description") or category).strip(),
            "amount": amount
        }
    built_items.extend(manual_items_by_category.values())
    concession_percent = concession_percent or 0
    selected_tuition_months = tuition_months or []
    selected_transport_months = transport_months or []
    selected_fee_heads_set = set(selected_fee_heads) if selected_fee_heads is not None else None
    tuition_month_count = len(selected_tuition_months)

    if fee_structure_id:
        structure = FeeStructure.objects.get(id=fee_structure_id)
        for item in structure.items:
            is_tuition_like = bool(item.category_name and "tuition" in item.category_name.lower())
            if is_tuition_like and tuition_month_count <= 0:
                continue
            if not is_tuition_like and selected_fee_heads_set is not None and item.category_name not in selected_fee_heads_set:
                continue
            months_label = f" ({', '.join(selected_tuition_months)})" if is_tuition_like and selected_tuition_months else ""
            base_amount = float(item.amount or 0)
            if is_tuition_like:
                base_amount = base_amount * tuition_month_count
            amount = base_amount
            discount_amount = 0
            if concession_percent > 0 and is_tuition_like:
                discount_amount = round(amount * concession_percent / 100, 2)
                amount = max(0, amount - discount_amount)
            built_items.append({
                "category": item.category_name,
                "description": f"{item.category_name}{months_label}",
                "base_amount": base_amount,
                "concession_percent": concession_percent if discount_amount else 0,
                "discount_amount": discount_amount,
                "amount": amount,
                "months": selected_tuition_months if is_tuition_like and selected_tuition_months else []
            })
    elif student.classroom and getattr(student.classroom, "class_fee", 0) and tuition_month_count > 0:
        months_label = f" ({', '.join(selected_tuition_months)})" if selected_tuition_months else ""
        base_amount = float(student.classroom.class_fee or 0) * tuition_month_count
        discount_amount = round(base_amount * concession_percent / 100, 2) if concession_percent > 0 else 0
        built_items.append({
            "category": "Class Fee",
            "description": f"{student.classroom.name} Class Fee{months_label}",
            "base_amount": base_amount,
            "concession_percent": concession_percent if discount_amount else 0,
            "discount_amount": discount_amount,
            "amount": max(0, base_amount - discount_amount),
            "months": selected_tuition_months if selected_tuition_months else []
        })

    selected_transport_months = selected_transport_months or (student.transport_months or [])
    if include_transport and student.transport_route and selected_transport_months:
        route = TransportRoute.objects(id=student.transport_route).first()
        monthly_fee = route.fee_per_month if route else (student.transport_fee_per_month or 0)
        if monthly_fee > 0:
            built_items.append({
                "category": "Transport Fee",
                "description": f"Transport Fee ({', '.join(selected_transport_months)})",
                "amount": monthly_fee * len(selected_transport_months),
                "monthly_fee": monthly_fee,
                "months": selected_transport_months,
                "route_name": route.route_name if route else student.transport_route_name
            })

    return built_items, selected_tuition_months, selected_transport_months


def _normalize_invoice_items_for_compare(items: List[dict]) -> tuple:
    normalized = []
    for item in items or []:
        normalized.append((
            (item.get("category") or "").strip().lower(),
            (item.get("description") or "").strip().lower(),
            round(float(item.get("amount") or 0), 2),
            tuple(item.get("months") or []),
        ))
    return tuple(sorted(normalized))


def _find_recent_duplicate_invoice(school: School, student: Student, ay: AcademicYear, items: List[dict], due_date, discount_amount: float, net: float):
    cutoff = datetime.utcnow() - timedelta(seconds=30)
    incoming_items = _normalize_invoice_items_for_compare(items)
    incoming_due_date = due_date.date().isoformat() if due_date else ""
    for invoice in FeeInvoice.objects(
        school=school,
        student=student,
        academic_year=ay,
        status__ne="Cancelled",
        created_at__gte=cutoff
    ).order_by("-created_at"):
        invoice_due_date = invoice.due_date.date().isoformat() if invoice.due_date else ""
        if invoice_due_date != incoming_due_date:
            continue
        if round(float(invoice.discount_amount or 0), 2) != round(float(discount_amount or 0), 2):
            continue
        if round(float(invoice.net_amount or 0), 2) != round(float(net or 0), 2):
            continue
        if _normalize_invoice_items_for_compare(invoice.items) == incoming_items:
            return invoice
    return None


def _ensure_months_not_already_invoiced(
    school: School,
    student: Student,
    ay: AcademicYear,
    tuition_months: Optional[List[str]],
    transport_months: Optional[List[str]],
    *,
    exclude_invoice_id: Optional[str] = None,
):
    requested_tuition = set(tuition_months or [])
    requested_transport = set(transport_months or [])
    if not requested_tuition and not requested_transport:
        return

    query = FeeInvoice.objects(
        school=school,
        student=student,
        academic_year=ay,
        status__ne="Cancelled"
    )
    if exclude_invoice_id:
        query = query.filter(id__ne=exclude_invoice_id)

    billed_tuition = set()
    billed_transport = set()
    for invoice in query:
        billed_tuition.update(_invoice_tuition_months(invoice))
        billed_transport.update(_invoice_transport_months(invoice))

    duplicate_tuition = sorted(requested_tuition & billed_tuition)
    duplicate_transport = sorted(requested_transport & billed_transport)
    if duplicate_tuition or duplicate_transport:
        parts = []
        if duplicate_tuition:
            parts.append(f"Tuition already invoiced for: {', '.join(duplicate_tuition)}")
        if duplicate_transport:
            parts.append(f"Transport already invoiced for: {', '.join(duplicate_transport)}")
        raise HTTPException(400, " | ".join(parts))


MONTH_NAMES = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]


def _is_tuition_invoice_item(item: dict) -> bool:
    label = f"{item.get('category') or ''} {item.get('description') or ''}".lower()
    return "tuition" in label or "class fee" in label


def _is_transport_invoice_item(item: dict) -> bool:
    label = f"{item.get('category') or ''} {item.get('description') or ''}".lower()
    return "transport" in label


def _extract_months_from_invoice_item(item: dict) -> List[str]:
    existing_months = item.get("months") if isinstance(item, dict) else []
    if isinstance(existing_months, list) and existing_months:
        return [month for month in MONTH_NAMES if month in existing_months]
    text = f"{item.get('description') or ''} {item.get('category') or ''}" if isinstance(item, dict) else ""
    return [month for month in MONTH_NAMES if re.search(rf"\b{re.escape(month)}\b", text, re.IGNORECASE)]


def _invoice_tuition_months(invoice: FeeInvoice) -> List[str]:
    months = list(invoice.tuition_months or [])
    if not months:
        for item in invoice.items or []:
            if _is_tuition_invoice_item(item):
                months.extend(_extract_months_from_invoice_item(item))
    return [month for month in MONTH_NAMES if month in set(months)]


def _invoice_transport_months(invoice: FeeInvoice) -> List[str]:
    months = list(invoice.transport_months or [])
    if not months:
        for item in invoice.items or []:
            if _is_transport_invoice_item(item):
                months.extend(_extract_months_from_invoice_item(item))
    return [month for month in MONTH_NAMES if month in set(months)]


def _successful_invoice_paid_amount(invoice: FeeInvoice) -> float:
    transactions = list(PaymentTransaction.objects(invoice=invoice, status="Success").only("amount"))
    transaction_paid = sum(float(txn.amount or 0) for txn in transactions)
    saved_paid = float(invoice.paid_amount or 0)
    return transaction_paid if transactions else saved_paid


def _invoice_collection_summary(invoice: FeeInvoice) -> dict:
    payable_amount = max(0, float(invoice.net_amount or 0) + float(invoice.late_fee or 0))
    collected_amount = max(0, _successful_invoice_paid_amount(invoice))
    paid_amount = min(collected_amount, payable_amount)
    balance_amount = max(0, payable_amount - paid_amount)
    excess_amount = max(0, collected_amount - payable_amount)
    status = "Paid" if balance_amount <= 0 else ("Partial" if paid_amount > 0 else "Pending")
    return {
        "payable_amount": payable_amount,
        "collected_amount": collected_amount,
        "paid_amount": paid_amount,
        "balance_amount": balance_amount,
        "excess_amount": excess_amount,
        "status": status,
    }


def _student_invoice_payload(student: Optional[Student]) -> dict:
    if not student:
        return {}
    classroom = student.classroom
    section = student.section
    return {
        "id": str(student.id),
        "full_name": student.full_name,
        "admission_no": student.admission_no,
        "father_name": student.parent_info.father_name if student.parent_info else None,
        "classroom_id": str(classroom.id) if classroom else None,
        "classroom_name": classroom.name if classroom else None,
        "class_fee": classroom.class_fee if classroom else 0,
        "section_id": str(section.id) if section else None,
        "section_name": section.name if section else None,
        "branch_code": student.branch_code,
        "branch_name": student.branch_name,
        "academic_year_id": str(student.academic_year.id) if student.academic_year else None,
        "transport_route": student.transport_route,
        "transport_route_id": student.transport_route,
        "transport_route_name": student.transport_route_name,
        "transport_fee_per_month": student.transport_fee_per_month,
        "transport_months": student.transport_months or [],
        "admission_concession": student.admission_concession,
        "admission_concession_percent": student.admission_concession_percent or 0,
    }


def _get_invoice_recipient_email(invoice: FeeInvoice, recipient_type: str, fallback_email: Optional[str] = None) -> str:
    if fallback_email:
        return fallback_email
    student = invoice.student
    if not student:
        raise HTTPException(404, "Student not found for this invoice")
    recipient_type = (recipient_type or "parent").lower()
    if recipient_type == "student":
        if student.email:
            return student.email
        raise HTTPException(400, "Student email not found")
    parent_info = student.parent_info
    if parent_info and parent_info.father_email:
        return parent_info.father_email
    if student.email:
        return student.email
    raise HTTPException(400, "Parent email not found")


# def _generate_invoice_pdf_bytes(invoice: FeeInvoice) -> bytes:
#     buffer = BytesIO()
#     pdf = canvas.Canvas(buffer, pagesize=A4)
#     width, height = A4
#     y = height - 48

#     school = invoice.school
#     student = invoice.student
#     address_parts = []
#     if school and school.address:
#         address_parts = [
#             school.address.line1,
#             school.address.line2,
#             school.address.city,
#             school.address.state,
#             school.address.pincode,
#         ]
#     school_address = ", ".join([part for part in address_parts if part])

#     logo_path = None
#     if school and school.logo:
#         candidate = school.logo.strip()
#         if candidate.startswith("/uploads/"):
#             logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), candidate.lstrip("/"))
#         elif candidate.startswith("uploads/"):
#             logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), candidate)
#         elif os.path.isabs(candidate):
#             logo_path = candidate
#         else:
#             logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), candidate.lstrip("/"))
#         if logo_path and not os.path.exists(logo_path):
#             logo_path = None

#     pdf.setFillColorRGB(0.97, 0.98, 1)
#     pdf.roundRect(30, height - 145, width - 60, 105, 18, stroke=0, fill=1)

#     if logo_path:
#         try:
#             pdf.drawImage(ImageReader(logo_path), 42, height - 122, width=54, height=54, preserveAspectRatio=True, mask='auto')
#         except Exception:
#             pass

#     left_start_x = 108 if logo_path else 42

#     pdf.setFont("Helvetica-Bold", 18)
#     pdf.setFillColorRGB(0.06, 0.09, 0.16)
#     pdf.drawString(left_start_x, height - 68, school.name if school else "School Invoice")
#     pdf.setFont("Helvetica", 9)
#     pdf.setFillColorRGB(0.39, 0.45, 0.55)
#     if school_address:
#         pdf.drawString(left_start_x, height - 84, school_address[:88])
#     if school and school.phone:
#         pdf.drawString(left_start_x, height - 98, f"Phone: {school.phone}")
#     if school and school.email:
#         pdf.drawString(left_start_x, height - 112, f"Email: {school.email}")

#     pdf.setFont("Helvetica-Bold", 11)
#     pdf.setFillColorRGB(0.17, 0.24, 0.39)
#     pdf.drawRightString(width - 42, height - 68, f"Invoice No: {invoice.invoice_no}")
#     pdf.setFont("Helvetica", 10)
#     pdf.drawRightString(width - 42, height - 84, f"Invoice Date: {invoice.invoice_date.strftime('%d-%m-%Y') if invoice.invoice_date else '-'}")
#     pdf.drawRightString(width - 42, height - 98, f"Due Date: {invoice.due_date.strftime('%d-%m-%Y') if invoice.due_date else '-'}")
#     y = height - 165

#     pdf.setFont("Helvetica-Bold", 12)
#     pdf.drawString(40, y, "Student Details")
#     y -= 16
#     pdf.setFont("Helvetica", 10)
#     pdf.drawString(40, y, f"Student: {student.full_name if student else '-'}")
#     y -= 14
#     pdf.drawString(40, y, f"Admission No: {student.admission_no if student else '-'}")
#     y -= 14
#     pdf.drawString(40, y, f"Class / Section: {(student.classroom.name if student and student.classroom else '-') } / {(student.section.name if student and student.section else '-')}")
#     y -= 14
#     pdf.drawString(40, y, f"Branch: {student.branch_name if student and student.branch_name else '-'}")
#     y -= 18

#     pdf.setFillColorRGB(0.96, 0.98, 1)
#     pdf.roundRect(40, y - 58, width - 80, 52, 12, stroke=0, fill=1)
#     pdf.setFillColorRGB(0.06, 0.09, 0.16)
#     pdf.setFont("Helvetica-Bold", 10)
#     pdf.drawString(52, y - 28, "Total Amount")
#     pdf.drawCentredString(width / 2, y - 28, "Paid Amount")
#     pdf.drawRightString(width - 52, y - 28, "Pending Amount")
#     pdf.setFont("Helvetica-Bold", 13)
#     pdf.drawString(52, y - 44, f"Rs. {invoice.net_amount:.2f}")
#     pdf.drawCentredString(width / 2, y - 44, f"Rs. {invoice.paid_amount:.2f}")
#     pdf.drawRightString(width - 52, y - 44, f"Rs. {invoice.balance_amount:.2f}")
#     y -= 82

#     pdf.setFont("Helvetica-Bold", 12)
#     pdf.drawString(40, y, "Fee Breakdown")
#     y -= 18
#     pdf.setFont("Helvetica-Bold", 10)
#     pdf.drawString(40, y, "Description")
#     pdf.drawRightString(width - 40, y, "Amount")
#     y -= 10
#     pdf.line(40, y, width - 40, y)
#     y -= 16
#     pdf.setFont("Helvetica", 10)
#     for item in invoice.items or []:
#         if y < 120:
#             pdf.showPage()
#             y = height - 48
#             pdf.setFont("Helvetica", 10)
#         pdf.drawString(40, y, str(item.get("description") or item.get("category") or "Fee Item")[:80])
#         pdf.drawRightString(width - 40, y, f"Rs. {float(item.get('amount', 0) or 0):.2f}")
#         y -= 14

#     y -= 8
#     pdf.line(40, y, width - 40, y)
#     y -= 18
#     pdf.setFont("Helvetica", 10)
#     if invoice.concession_name:
#         pdf.drawString(40, y, f"Concession: {invoice.concession_name} ({invoice.concession_percent:.0f}%)")
#         y -= 16
#     pdf.drawString(40, y, "Gross Amount")
#     pdf.drawRightString(width - 40, y, f"Rs. {invoice.gross_amount:.2f}")
#     y -= 14
#     pdf.drawString(40, y, "Manual Discount")
#     pdf.drawRightString(width - 40, y, f"Rs. {invoice.discount_amount:.2f}")
#     y -= 14
#     pdf.setFont("Helvetica-Bold", 11)
#     pdf.drawString(40, y, "Total Amount")
#     pdf.drawRightString(width - 40, y, f"Rs. {invoice.net_amount:.2f}")
#     y -= 14
#     pdf.drawString(40, y, "Paid Amount")
#     pdf.drawRightString(width - 40, y, f"Rs. {invoice.paid_amount:.2f}")
#     y -= 14
#     pdf.drawString(40, y, "Pending Amount")
#     pdf.drawRightString(width - 40, y, f"Rs. {invoice.balance_amount:.2f}")
#     y -= 22
#     pdf.setFont("Helvetica", 9)
#     pdf.drawString(40, y, f"Generated by: {invoice.generated_by or '-'}")
#     if invoice.remarks:
#         y -= 14
#         pdf.drawString(40, y, f"Remarks: {invoice.remarks[:90]}")

#     pdf.save()
#     buffer.seek(0)
#     return buffer.getvalue()

def _generate_invoice_pdf_bytes(invoice) -> bytes:
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=12,
        leftMargin=12,
        topMargin=12,
        bottomMargin=12,
    )

    elements = []

    # --- Custom Paragraph Styles ---
    p_center = ParagraphStyle(
        "p_center",
        fontName="Helvetica",
        fontSize=9,
        alignment=TA_CENTER,
        leading=12
    )

    normal_10 = ParagraphStyle(
        "normal_10",
        fontName="Helvetica",
        fontSize=9,
        leading=12
    )

    bold_10 = ParagraphStyle(
        "bold_10",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12
    )

    right_bold_10 = ParagraphStyle(
        "right_bold_10",
        fontName="Helvetica-Bold",
        fontSize=9,
        alignment=TA_RIGHT,
        leading=12
    )

    right_normal_10 = ParagraphStyle(
        "right_normal_10",
        fontName="Helvetica",
        fontSize=9,
        alignment=TA_RIGHT,
        leading=12
    )

    school = invoice.school
    student = invoice.student

    def get_logo_source():
        if school and hasattr(school, 'logo') and school.logo:
            candidate = school.logo.strip()

            if candidate.startswith(("http://", "https://")):
                return candidate

            base_dir = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )

            if candidate.startswith("/uploads/"):
                path = os.path.join(base_dir, candidate.lstrip("/"))

            elif candidate.startswith("uploads/"):
                path = os.path.join(base_dir, candidate)

            elif os.path.isabs(candidate):
                path = candidate

            else:
                path = os.path.join(base_dir, candidate.lstrip("/"))

            if os.path.exists(path):
                return path

        return None

    logo_src = get_logo_source()

    def build_logo():
        if not logo_src:
            return ""
        try:
            ImageReader(logo_src).getSize()
            return Image(logo_src, width=70, height=70)
        except Exception:
            return ""

    def money(val):
        return f"Rs. {float(val or 0):.2f}"

    collection_summary = _invoice_collection_summary(invoice)
    display_paid_amount = collection_summary["paid_amount"]
    display_balance_amount = collection_summary["balance_amount"]
    excess_amount = collection_summary["excess_amount"]

    school_name = (
        school.name.upper()
        if school and school.name
        else 'R.S MEMORIAL PUBLIC SCHOOL'
    )

    school_phone = (
        school.phone
        if school and school.phone
        else '9214014070'
    )

    father_name = (
        student.parent_info.father_name
        if student and hasattr(student, 'parent_info') and student.parent_info
        else "-"
    )

    father_phone = (
        student.parent_info.father_phone
        if student and hasattr(student, 'parent_info') and student.parent_info
        else "-"
    )

    class_sec = (
        f"{student.classroom.name if student and student.classroom else '-'} "
        f"- "
        f"{student.section.name if student and student.section else '-'}"
    )

    def build_copy(copy_name="STUDENT COPY"):

        logo = build_logo()

        # =========================
        # HEADER TABLE
        # =========================

        student_data = [
            [
                logo,

                Paragraph(
                    f"<font size='14'><b>{school_name}</b></font><br/><br/>"
                    f"<font size='10'>Village Tatarpur, Teh. Tapukara, Distt. Khairthal Tijara(Raj.)</font><br/><br/>"
                    f"<font size='10'>Phone No. : {school_phone}</font>",
                    p_center
                ),

                "",

                Paragraph(
                    f"<h3>{copy_name}</h3>",
                    right_bold_10
                )
            ],

            [
                Paragraph("<b>Invoice No.</b>", bold_10),
                Paragraph(str(invoice.invoice_no or "-"), normal_10),

                Paragraph("<b>Invoice Date</b>", bold_10),

                Paragraph(
                    invoice.invoice_date.strftime("%d-%m-%Y")
                    if invoice.invoice_date else "-",
                    normal_10
                )
            ],

            [
                Paragraph("<b>Name of the Student</b>", bold_10),

                Paragraph(
                    student.full_name if student else "-",
                    normal_10
                ),

                Paragraph("<b>Class & Section</b>", bold_10),

                Paragraph(class_sec, normal_10)
            ],

            [
                Paragraph("<b>Admission No</b>", bold_10),

                Paragraph(
                    str(student.admission_no if student else "-"),
                    normal_10
                ),

                Paragraph("<b>Mobile No.</b>", bold_10),

                Paragraph(str(father_phone), normal_10)
            ],

            [
                Paragraph("<b>Father's Name</b>", bold_10),

                Paragraph(str(father_name), normal_10),

                Paragraph("<b>Fee for</b>", bold_10),

                Paragraph(
                    ", ".join(invoice.tuition_months or []) or "-",
                    normal_10
                )
            ],
        ]

        details_table = Table(
            student_data,
            colWidths=[130, 155, 130, 155]
        )

        details_table.setStyle(TableStyle([
            ("SPAN", (1, 0), (2, 0)),
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("GRID", (0, 1), (-1, -1), 1, colors.black),
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (2, 0), "CENTER"),
            ("ALIGN", (3, 0), (3, 0), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))

        elements.append(details_table)
        elements.append(Spacer(1, 10))

        # =========================
        # AMOUNT SUMMARY
        # =========================

        amount_table = Table([
            [
                Paragraph(
                    f"<font size='10'><b>Total Amount</b></font><br/><br/>"
                    f"<font size='12'><b>{money(invoice.net_amount)}</b></font>",
                    p_center
                ),

                Paragraph(
                    f"<font size='10'><b>Paid Amount</b></font><br/><br/>"
                    f"<font size='12'><b>{money(display_paid_amount)}</b></font>",
                    p_center
                ),

                Paragraph(
                    f"<font size='10'><b>Pending Amount</b></font><br/><br/>"
                    f"<font size='12'><b>{money(display_balance_amount)}</b></font>",
                    p_center
                ),
            ]
        ], colWidths=[190, 190, 190])

        amount_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 1, HexColor("#dddddd")),
            ("BACKGROUND", (0, 0), (-1, -1), HexColor("#f1f3f5")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
        ]))

        elements.append(amount_table)
        elements.append(Spacer(1, 10))

        # =========================
        # FEE BREAKDOWN
        # =========================

        fee_rows = [
            [
                Paragraph("<b>Fee Breakdown</b>", bold_10),
                ""
            ],

            [
                Paragraph("<b>Description</b>", bold_10),
                Paragraph("<b>Amount</b>", right_bold_10)
            ]
        ]

        for item in invoice.items or []:
            fee_rows.append([
                Paragraph(
                    str(item.get("description") or "-"),
                    normal_10
                ),

                Paragraph(
                    money(item.get("amount")),
                    right_normal_10
                )
            ])

        fee_rows.extend([
            [
                Paragraph("<b>Total Amount</b>", bold_10),
                Paragraph(money(invoice.net_amount), right_bold_10)
            ],

            [
                Paragraph("<b>Paid Amount</b>", bold_10),
                Paragraph(money(display_paid_amount), right_bold_10)
            ],

            [
                Paragraph("<b>Pending Amount</b>", bold_10),
                Paragraph(money(display_balance_amount), right_bold_10)
            ],
        ])

        if excess_amount > 0:
            fee_rows.append([
                Paragraph("<b>Excess / Credit Amount</b>", bold_10),
                Paragraph(money(excess_amount), right_bold_10)
            ])

        fee_table = Table(
            fee_rows,
            colWidths=[450, 120]
        )

        fee_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ("SPAN", (0, 0), (1, 0)),
            ("BACKGROUND", (0, 0), (1, 0), HexColor("#f5f5f5")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))

        elements.append(fee_table)
        elements.append(Spacer(1, 10))

        # =========================
        # PAYMENT HISTORY
        # =========================

        transactions = list(
            PaymentTransaction.objects(
                invoice=invoice,
                status="Success"
            ).order_by("-payment_date")
        )

        if len(transactions) > 0:

            elements.append(
                Paragraph(
                    "<b>Payment History</b>",
                    bold_10
                )
            )

            elements.append(Spacer(1, 6))

            payment_rows = [
                [
                    Paragraph("<b>Date</b>", bold_10),
                    Paragraph("<b>Amount</b>", bold_10),
                    Paragraph("<b>Mode</b>", bold_10),
                    Paragraph("<b>Receipt No</b>", bold_10),
                    Paragraph("<b>Collected By</b>", bold_10),
                ]
            ]

            total_paid_history = 0

            for txn in transactions:

                total_paid_history += float(txn.amount or 0)

                payment_rows.append([
                    Paragraph(
                        txn.payment_date.strftime("%d-%m-%Y")
                        if txn.payment_date else "-",
                        normal_10
                    ),

                    Paragraph(
                        money(txn.amount),
                        right_normal_10
                    ),

                    Paragraph(
                        str(txn.payment_mode or "-"),
                        normal_10
                    ),

                    Paragraph(
                        str(txn.receipt_no or "-"),
                        normal_10
                    ),

                    Paragraph(
                        str(txn.collected_by or "-"),
                        normal_10
                    ),
                ])

            payment_rows.append([
                Paragraph("<b>Total Collected</b>", bold_10),

                Paragraph(
                    f"<b>{money(total_paid_history)}</b>",
                    right_bold_10
                ),

                "",
                "",
                "",
            ])

            if excess_amount > 0:
                payment_rows.append([
                    Paragraph("<b>Applied To Invoice</b>", bold_10),
                    Paragraph(f"<b>{money(display_paid_amount)}</b>", right_bold_10),
                    "",
                    "",
                    "",
                ])
                payment_rows.append([
                    Paragraph("<b>Excess / Credit Amount</b>", bold_10),
                    Paragraph(f"<b>{money(excess_amount)}</b>", right_bold_10),
                    "",
                    "",
                    "",
                ])

            payment_table = Table(
                payment_rows,
                colWidths=[90, 100, 110, 120, 150]
            )

            payment_table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f5f5f5")),
                ("BACKGROUND", (0, -1), (-1, -1), HexColor("#eeeeee")),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))

            elements.append(payment_table)
            elements.append(Spacer(1, 10))

        else:

            elements.append(
                Paragraph(
                    "<b>No Payment History Available</b>",
                    normal_10
                )
            )

            elements.append(Spacer(1, 10))

        # =========================
        # FOOTER
        # =========================

        footer_table = Table([
            [
                Paragraph(
                    "<b>NOTE :</b><br/><br/>"
                    "1. Fee once paid is not refundable.<br/>"
                    "2. Keep this receipt safely.",
                    normal_10
                ),

                Paragraph(
                    "<br/><br/><br/><b>(Signature)</b>",
                    p_center
                )
            ]
        ], colWidths=[430, 140])

        footer_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))

        elements.append(footer_table)

    # STUDENT COPY
    build_copy("STUDENT COPY")

    elements.append(Spacer(1, 20))

    elements.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=colors.grey,
            dash=(3, 3)
        )
    )

    elements.append(Spacer(1, 20))

    # OFFICE COPY
    build_copy("OFFICE COPY")

    doc.build(elements)

    pdf = buffer.getvalue()

    buffer.close()

    return pdf
def _send_invoice_email(invoice: FeeInvoice, recipient_email: str):
    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise HTTPException(400, "SMTP is not configured. Add SMTP_HOST, SMTP_PORT, SMTP_USER and SMTP_PASSWORD in .env")

    student = invoice.student
    school = invoice.school
    pdf_bytes = _generate_invoice_pdf_bytes(invoice)

    msg = EmailMessage()
    msg["Subject"] = f"Fee Invoice {invoice.invoice_no}"
    msg["From"] = settings.SMTP_USER
    msg["To"] = recipient_email
    msg.set_content(
        f"Dear Parent/Student,\n\nPlease find attached fee invoice {invoice.invoice_no} for {student.full_name if student else 'student'}.\n"
        f"Net Amount: Rs. {invoice.net_amount:.2f}\n"
        f"Due Date: {invoice.due_date.strftime('%d-%m-%Y') if invoice.due_date else '-'}\n\n"
        f"Regards,\n{school.name if school else 'School'}"
    )
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=f"{invoice.invoice_no}.pdf")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)


@router.post("/invoice")
async def create_invoice(data: InvoiceCreate, current_user: User = Depends(get_current_user)):
    data.school_id = resolve_school_access(current_user, data.school_id)
    school = School.objects.get(id=data.school_id)
    student = Student.objects.get(id=data.student_id)
    scoped_branch = resolve_branch_scope(current_user, None)
    if scoped_branch and student.branch_code != scoped_branch:
        raise HTTPException(403, "Access denied for this branch")
    ay = _resolve_academic_year(school, data.academic_year_id or (str(student.academic_year.id) if student.academic_year else None))
    _ensure_months_not_already_invoiced(
        school,
        student,
        ay,
        data.tuition_months,
        data.transport_months,
    )
    
    items, selected_tuition_months, selected_transport_months = _build_invoice_items(
        student,
        data.fee_structure_id,
        data.items,
        data.include_transport,
        data.transport_months,
        data.tuition_months,
        data.selected_fee_heads,
        data.concession_percent
    )
    if not items:
        raise HTTPException(400, "Add at least one fee item or select a fee structure")
    gross = sum(item['amount'] for item in items)
    net = gross - data.discount_amount
    duplicate_invoice = _find_recent_duplicate_invoice(school, student, ay, items, data.due_date, data.discount_amount, net)
    if duplicate_invoice:
        return success_response({
            "id": str(duplicate_invoice.id),
            "invoice_no": duplicate_invoice.invoice_no,
            "net_amount": duplicate_invoice.net_amount,
            "gross_amount": duplicate_invoice.gross_amount,
            "items": duplicate_invoice.items,
            "concession_name": duplicate_invoice.concession_name,
            "concession_percent": duplicate_invoice.concession_percent
        }, "Invoice already exists")
    
    invoice = None
    for _ in range(5):
        invoice_no = _generate_invoice_no()
        if data.concession_name:
            student.admission_concession = data.concession_name

            student.admission_concession_percent = (
              data.concession_percent or 0
            )

            student.save()
        invoice = FeeInvoice(
            school=school, student=student, academic_year=ay,
            invoice_no=invoice_no,
            due_date=data.due_date,
            items=items,
            tuition_months=selected_tuition_months,
            transport_months=selected_transport_months,
            transport_route=student.transport_route_name,
            concession_name=data.concession_name,
            concession_percent=data.concession_percent or 0,
            gross_amount=gross,
            discount_amount=data.discount_amount,
            net_amount=net,
            balance_amount=net,
            remarks=data.remarks,
            generated_by=current_user.full_name
        )
        try:
            invoice.save()
            break
        except NotUniqueError:
            invoice = None
    if not invoice:
        raise HTTPException(409, "Could not generate a unique invoice number. Please try again.")
    return success_response({
        "id": str(invoice.id),
        "invoice_no": invoice.invoice_no,
        "net_amount": net,
        "gross_amount": gross,
        "items": items,
        "concession_name": invoice.concession_name,
        "concession_percent": invoice.concession_percent
    }, "Invoice created successfully")


@router.put("/invoice/{invoice_id}")
async def update_invoice(invoice_id: str, data: InvoiceCreate, current_user: User = Depends(get_current_user)):
    invoice = FeeInvoice.objects(id=invoice_id).first()
    if not invoice:
        raise HTTPException(404, "Invoice not found")

    data.school_id = resolve_school_access(current_user, data.school_id)
    if str(invoice.school.id) != data.school_id:
        raise HTTPException(403, "Access denied")

    student = Student.objects.get(id=data.student_id)
    scoped_branch = resolve_branch_scope(current_user, None)
    if scoped_branch and student.branch_code != scoped_branch:
        raise HTTPException(403, "Access denied for this branch")

    ay = _resolve_academic_year(invoice.school, data.academic_year_id or (str(student.academic_year.id) if student.academic_year else None))
    _ensure_months_not_already_invoiced(
        invoice.school,
        student,
        ay,
        data.tuition_months,
        data.transport_months,
        exclude_invoice_id=str(invoice.id),
    )
    items, selected_tuition_months, selected_transport_months = _build_invoice_items(
        student,
        data.fee_structure_id,
        data.items,
        data.include_transport,
        data.transport_months,
        data.tuition_months,
        data.selected_fee_heads,
        data.concession_percent
    )
    if not items:
        raise HTTPException(400, "Add at least one fee item or select a fee structure")

    gross = sum(item['amount'] for item in items)
    net = gross - data.discount_amount
    already_paid = _successful_invoice_paid_amount(invoice)
    payable_amount = max(0, net + float(invoice.late_fee or 0))
    if already_paid > payable_amount:
        raise HTTPException(
            400,
            f"Invoice total cannot be less than collected payment. Collected: {already_paid}, new total: {payable_amount}"
        )
    balance_amount = max(0, net - already_paid)
    status = "Paid" if balance_amount <= 0 else ("Partial" if already_paid > 0 else "Pending")
    # Update saved student concession
    if data.concession_name:

       student.admission_concession = data.concession_name

       student.admission_concession_percent = (
        data.concession_percent or 0
       )

       student.save()
    invoice.update(
        student=student,
        academic_year=ay,
        due_date=data.due_date,
        items=items,
        tuition_months=selected_tuition_months,
        transport_months=selected_transport_months,
        transport_route=student.transport_route_name,
        concession_name=data.concession_name,
        concession_percent=data.concession_percent or 0,
        gross_amount=gross,
        discount_amount=data.discount_amount,
        net_amount=net,
        paid_amount=already_paid,
        balance_amount=balance_amount,
        remarks=data.remarks,
        status=status
    )
    return success_response({"id": str(invoice.id), "net_amount": net, "paid_amount": already_paid, "balance_amount": balance_amount}, "Invoice updated successfully")


@router.delete("/invoice/{invoice_id}")
async def delete_invoice(invoice_id: str, current_user: User = Depends(get_current_user)):
    invoice = FeeInvoice.objects(id=invoice_id).first()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    resolve_school_access(current_user, str(invoice.school.id))
    if (invoice.paid_amount or 0) > 0:
        raise HTTPException(400, "Paid invoice cannot be deleted")
    invoice.update(status="Cancelled", balance_amount=0)
    invoice.delete()
    return success_response(message="Invoice deleted")


@router.get("/invoice")
async def list_invoices(
    school_id: str,
    student_id: Optional[str] = None,
    academic_year_id: Optional[str] = None,
    branch_code: Optional[str] = None,
    classroom_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    include_items: bool = Query(True),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    school_id = resolve_school_access(current_user, school_id)
    branch_code = resolve_branch_scope(current_user, branch_code)
    school = School.objects.get(id=school_id)
    query = FeeInvoice.objects(school=school)
    
    if student_id:
        student = Student.objects.get(id=student_id)
        query = query.filter(student=student)
    if academic_year_id:
        ay = _resolve_academic_year(school, academic_year_id)
        query = query.filter(academic_year=ay)
    if branch_code:
        students = list(Student.objects(school=school, branch_code=branch_code, is_active=True))
        query = query.filter(student__in=students)
    if classroom_id:
        classroom = ClassRoom.objects.get(id=classroom_id)
        students = list(Student.objects(school=school, classroom=classroom, is_active=True))
        query = query.filter(student__in=students)
    if status:
        if status == "Due":
            query = query.filter(status__in=["Pending", "Partial", "Overdue"])
        elif status == "Completed":
            query = query.filter(status="Paid")
        else:
            query = query.filter(status=status)
    if search:
        students = list(Student.objects(
        school=school,
        is_active=True,
        __raw__={
            "$or": [
                {"parent_info.father_name": {"$regex": search, "$options": "i"}},
                {"full_name": {"$regex": search, "$options": "i"}},
                {"first_name": {"$regex": search, "$options": "i"}},
                {"last_name": {"$regex": search, "$options": "i"}},
            ]
        }
        ))
        query = query.filter(student__in=students)
    
    total = query.count()
    invoices = query.order_by('-created_at').skip((page - 1) * per_page).limit(per_page).select_related(max_depth=2)
    
    result = []
    for inv in invoices:
        collection_summary = _invoice_collection_summary(inv)
        row = {
            "id": str(inv.id),
            "invoice_no": inv.invoice_no,
            "academic_year_id": str(inv.academic_year.id) if inv.academic_year else None,
            "student_name": inv.student.full_name if inv.student else None,
            "student_id": str(inv.student.id) if inv.student else None,
            "student": _student_invoice_payload(inv.student),
            "father_name": inv.student.parent_info.father_name if inv.student and inv.student.parent_info else None,
            "classroom_id": str(inv.student.classroom.id) if inv.student and inv.student.classroom else None,
            "classroom_name": inv.student.classroom.name if inv.student and inv.student.classroom else None,
            "section_id": str(inv.student.section.id) if inv.student and inv.student.section else None,
            "section_name": inv.student.section.name if inv.student and inv.student.section else None,
            "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "gross_amount": inv.gross_amount,
            "discount_amount": inv.discount_amount,
            "concession_name": inv.concession_name,
            "concession_percent": inv.concession_percent,
            "net_amount": inv.net_amount,
            "paid_amount": collection_summary["paid_amount"],
            "balance_amount": collection_summary["balance_amount"],
            "collected_amount": collection_summary["collected_amount"],
            "excess_amount": collection_summary["excess_amount"],
            "status": collection_summary["status"]
        }
        row["tuition_months"] = _invoice_tuition_months(inv)
        row["transport_months"] = _invoice_transport_months(inv)
        if include_items:
            row["items"] = inv.items
        result.append(row)
    
    return success_response(result, meta={
        "total": total, "page": page, "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    })


@router.get("/invoice/{invoice_id}")
async def get_invoice(invoice_id: str, current_user: User = Depends(get_current_user)):
    try:
        inv = FeeInvoice.objects.get(id=invoice_id)
        resolve_school_access(current_user, str(inv.school.id) if inv.school else None)
        scoped_branch = resolve_branch_scope(current_user, None)
        if scoped_branch and inv.student and inv.student.branch_code != scoped_branch:
            raise HTTPException(403, "Access denied for this branch")
        # Get transactions
        transactions = PaymentTransaction.objects(invoice=inv).order_by('-payment_date')
        collection_summary = _invoice_collection_summary(inv)
        
        data = {
            "id": str(inv.id),
            "invoice_no": inv.invoice_no,
            "academic_year_id": str(inv.academic_year.id) if inv.academic_year else None,
            "student_name": inv.student.full_name if inv.student else None,
            "student_id": str(inv.student.id) if inv.student else None,
            "student": _student_invoice_payload(inv.student),
            "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "items": inv.items,
            "tuition_months": _invoice_tuition_months(inv),
            "transport_months": _invoice_transport_months(inv),
            "concession_name": inv.concession_name,
            "concession_percent": inv.concession_percent,
            "gross_amount": inv.gross_amount,
            "discount_amount": inv.discount_amount,
            "late_fee": inv.late_fee,
            "net_amount": inv.net_amount,
            "paid_amount": collection_summary["paid_amount"],
            "balance_amount": collection_summary["balance_amount"],
            "collected_amount": collection_summary["collected_amount"],
            "excess_amount": collection_summary["excess_amount"],
            "status": collection_summary["status"],
            "remarks": inv.remarks,
            "transactions": [{
                "id": str(t.id),
                "transaction_no": t.transaction_no,
                "amount": t.amount,
                "payment_date": t.payment_date.isoformat() if t.payment_date else None,
                "payment_mode": t.payment_mode,
                "status": t.status,
                "collected_by": t.collected_by
            } for t in transactions]
        }
        return success_response(data)
    except FeeInvoice.DoesNotExist:
        raise HTTPException(404, "Invoice not found")


@router.get("/invoice/{invoice_id}/pdf")
async def download_invoice_pdf(invoice_id: str, current_user: User = Depends(get_current_user)):
    try:
        inv = FeeInvoice.objects.get(id=invoice_id)
        resolve_school_access(current_user, str(inv.school.id) if inv.school else None)
        scoped_branch = resolve_branch_scope(current_user, None)
        if scoped_branch and inv.student and inv.student.branch_code != scoped_branch:
            raise HTTPException(403, "Access denied for this branch")
        pdf_bytes = _generate_invoice_pdf_bytes(inv)
        filename = f"{inv.invoice_no}.pdf"
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except FeeInvoice.DoesNotExist:
        raise HTTPException(404, "Invoice not found")


@router.post("/invoice/{invoice_id}/send-email")
async def send_invoice_email(invoice_id: str, data: InvoiceEmailRequest, current_user: User = Depends(get_current_user)):
    try:
        inv = FeeInvoice.objects.get(id=invoice_id)
        resolve_school_access(current_user, str(inv.school.id) if inv.school else None)
        scoped_branch = resolve_branch_scope(current_user, None)
        if scoped_branch and inv.student and inv.student.branch_code != scoped_branch:
            raise HTTPException(403, "Access denied for this branch")
        recipient_email = _get_invoice_recipient_email(inv, data.recipient_type, data.email)
        _send_invoice_email(inv, recipient_email)
        emailed_to = list(inv.emailed_to or [])
        if recipient_email not in emailed_to:
            emailed_to.append(recipient_email)
            inv.update(emailed_to=emailed_to)
        return success_response({"invoice_id": str(inv.id), "email": recipient_email}, "Invoice emailed successfully")
    except FeeInvoice.DoesNotExist:
        raise HTTPException(404, "Invoice not found")


# ─── Payment ──────────────────────────────────────────────────────────────────

class PaymentCreate(BaseModel):
    school_id: str
    student_id: str
    invoice_id: str
    amount: float
    payment_mode: str
    payment_date: Optional[datetime] = None
    instrument_no: Optional[str] = None
    bank_name: Optional[str] = None
    collected_by_name: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/payment")
async def record_payment(data: PaymentCreate, current_user: User = Depends(get_current_user)):
    data.school_id = resolve_school_access(current_user, data.school_id)
    school = School.objects.get(id=data.school_id)
    student = Student.objects.get(id=data.student_id)
    invoice = FeeInvoice.objects.get(id=data.invoice_id)
    if str(invoice.school.id) != str(school.id) or str(invoice.student.id) != str(student.id):
        raise HTTPException(400, "Selected invoice does not belong to this student/school")
    scoped_branch = resolve_branch_scope(current_user, None)
    if scoped_branch and student.branch_code != scoped_branch:
        raise HTTPException(403, "Access denied for this branch")
    
    if data.amount <= 0:
        raise HTTPException(400, "Payment amount must be positive")
    current_paid = _successful_invoice_paid_amount(invoice)
    payable_amount = float(invoice.net_amount or 0) + float(invoice.late_fee or 0)
    current_balance = max(0, payable_amount - current_paid)
    if data.amount > current_balance:
        raise HTTPException(400, f"Payment amount exceeds balance: {current_balance}")
    
    txn_no = generate_transaction_no()
    
    txn = PaymentTransaction(
        school=school, student=student, invoice=invoice,
        transaction_no=txn_no,
        payment_date=data.payment_date or datetime.utcnow(),
        amount=data.amount,
        payment_mode=data.payment_mode,
        instrument_no=data.instrument_no,
        bank_name=data.bank_name,
        remarks=data.remarks,
        collected_by=(data.collected_by_name or current_user.full_name),
        receipt_no=f"RCP-{txn_no[-8:]}"
    )
    txn.save()
    
    # Update invoice
    new_paid = current_paid + data.amount
    new_balance = payable_amount - new_paid
    
    if new_balance <= 0:
        new_status = "Paid"
    elif new_paid > 0:
        new_status = "Partial"
    else:
        new_status = "Pending"
    
    invoice.update(
        paid_amount=new_paid,
        balance_amount=max(0, new_balance),
        status=new_status
    )
    
    return success_response({
        "transaction_no": txn_no,
        "receipt_no": txn.receipt_no,
        "amount": data.amount,
        "balance": max(0, new_balance),
        "status": new_status
    }, "Payment recorded successfully")


@router.get("/payment/history")
async def payment_history(
    school_id: str,
    academic_year_id: Optional[str] = None,
    branch_code: Optional[str] = None,
    classroom_id: Optional[str] = None,
    student_id: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user)
):
    school_id = resolve_school_access(current_user, school_id)
    branch_code = resolve_branch_scope(current_user, branch_code)
    school = School.objects.get(id=school_id)
    query = PaymentTransaction.objects(school=school, status="Success")

    if academic_year_id:
        ay = _resolve_academic_year(school, academic_year_id)
        invoices = list(FeeInvoice.objects(school=school, academic_year=ay))
        query = query.filter(invoice__in=invoices)
    if branch_code:
        students = list(Student.objects(school=school, branch_code=branch_code, is_active=True))
        query = query.filter(student__in=students)
    if classroom_id:
        classroom = ClassRoom.objects.get(id=classroom_id)
        students = list(Student.objects(school=school, classroom=classroom, is_active=True))
        query = query.filter(student__in=students)
    if student_id:
        student = Student.objects.get(id=student_id)
        query = query.filter(student=student)
    if search:
        students = list(Student.objects(
            school=school,
            is_active=True,
            __raw__={"$or": [
                {"first_name": {"$regex": search, "$options": "i"}},
                {"last_name": {"$regex": search, "$options": "i"}},
                {"admission_no": {"$regex": search, "$options": "i"}},
                {"parent_info.father_name": {"$regex": search, "$options": "i"}},
            ]}
        ))
        query = query.filter(student__in=students)

    total = query.count()
    transactions = query.order_by("-payment_date").skip((page - 1) * per_page).limit(per_page).select_related(max_depth=2)
    result = []
    for txn in transactions:
        student = txn.student
        invoice = txn.invoice
        result.append({
            "id": str(txn.id),
            "student_id": str(student.id) if student else None,
            "student_name": student.full_name if student else None,
            "father_name": student.parent_info.father_name if student and student.parent_info else None,
            "invoice_no": invoice.invoice_no if invoice else None,
            "amount": txn.amount,
            "payment_date": txn.payment_date.isoformat() if txn.payment_date else None,
            "balance_amount": invoice.balance_amount if invoice else 0,
            "collected_by": txn.collected_by,
            "payment_mode": txn.payment_mode,
            "receipt_no": txn.receipt_no,
        })
    return success_response(result, meta={
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    })


@router.get("/dues")
async def get_fee_dues(
    school_id: str,
    academic_year_id: Optional[str] = None,
    branch_code: Optional[str] = None,
    classroom_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school_id = resolve_school_access(current_user, school_id)
    branch_code = resolve_branch_scope(current_user, branch_code)
    school = School.objects.get(id=school_id)
    query = FeeInvoice.objects(school=school, status__in=["Pending", "Partial", "Overdue"])
    
    if academic_year_id:
        ay = _resolve_academic_year(school, academic_year_id)
        query = query.filter(academic_year=ay)
    if branch_code:
        students = list(Student.objects(school=school, branch_code=branch_code, is_active=True))
        query = query.filter(student__in=students)
    if classroom_id:
        classroom = ClassRoom.objects.get(id=classroom_id)
        students = list(Student.objects(school=school, classroom=classroom, is_active=True))
        query = query.filter(student__in=students)
    
    total_due = sum(inv.balance_amount for inv in query)
    count = query.count()
    
    return success_response({
        "total_pending_invoices": count,
        "total_due_amount": total_due,
        "invoices": [{
            "invoice_id": str(inv.id),
            "invoice_no": inv.invoice_no,
            "student_name": inv.student.full_name if inv.student else None,
            "classroom_name": inv.student.classroom.name if inv.student and inv.student.classroom else None,
            "section_name": inv.student.section.name if inv.student and inv.student.section else None,
            "parent_phone": (
                inv.student.parent_info.father_phone
                if inv.student and inv.student.parent_info and inv.student.parent_info.father_phone else
                inv.student.parent_info.mother_phone
                if inv.student and inv.student.parent_info and inv.student.parent_info.mother_phone else
                inv.student.parent_info.guardian_phone
                if inv.student and inv.student.parent_info and inv.student.parent_info.guardian_phone else
                inv.student.phone if inv.student else None
            ),
            "net_amount": inv.net_amount,
            "paid_amount": inv.paid_amount,
            "balance": inv.balance_amount,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "status": inv.status
        } for inv in query.order_by('due_date')[:50]]
    })


@router.get("/reports/summary")
async def fee_summary(
    school_id: str,
    academic_year_id: Optional[str] = None,
    branch_code: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    school_id = resolve_school_access(current_user, school_id)
    branch_code = resolve_branch_scope(current_user, branch_code)
    school = School.objects.get(id=school_id)
    query = FeeInvoice.objects(school=school)
    
    if academic_year_id:
        ay = _resolve_academic_year(school, academic_year_id)
        query = query.filter(academic_year=ay)
    if branch_code:
        students = list(Student.objects(school=school, branch_code=branch_code, is_active=True))
        query = query.filter(student__in=students)
    
    total_billed = sum(inv.net_amount for inv in query)
    total_collected = sum(inv.paid_amount for inv in query)
    total_due = total_billed - total_collected
    
    return success_response({
        "total_billed": total_billed,
        "total_collected": total_collected,
        "total_due": total_due,
        "collection_rate": round((total_collected / total_billed * 100) if total_billed > 0 else 0, 2),
        "by_status": {
            "paid": query.filter(status="Paid").count(),
            "partial": query.filter(status="Partial").count(),
            "pending": query.filter(status="Pending").count(),
            "overdue": query.filter(status="Overdue").count()
        }
    })
