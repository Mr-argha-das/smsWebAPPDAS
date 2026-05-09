from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime, timedelta
from models.library import Book, BookCategory, LibraryMember, BookIssue, LibrarySettings
from models.institution import School, User
from models.student import Student
from models.staff import Staff
from utils.auth import get_current_user
from utils.helpers import success_response

router = APIRouter(prefix="/library", tags=["Library"])


# ─── Books ────────────────────────────────────────────────────────────────────
@router.post("/book")
async def add_book(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    book = Book(
        school=school,
        title=data['title'],
        author=data['author'],
        class_name=data.get('class_name'),
        isbn=data.get('isbn'),
        publisher=data.get('publisher'),
        edition=data.get('edition'),
        year=data.get('year'),
        language=data.get('language', 'English'),
        pages=data.get('pages'),
        price=data.get('price', 0),
        total_copies=data.get('total_copies', 1),
        available_copies=data.get('total_copies', 1),
        rack_number=data.get('rack_number'),
        barcode=data.get('barcode'),
        description=data.get('description'),
        is_digital=data.get('is_digital', False),
        digital_link=data.get('digital_link')
    )
    if data.get('category_id'):
        book.category = BookCategory.objects.get(id=data['category_id'])
    book.save()
    return success_response({"id": str(book.id), "title": book.title}, "Book added")


@router.get("/book")
async def list_books(
    school_id: str,
    search: Optional[str] = None,
    class_name: Optional[str] = None,
    category_id: Optional[str] = None,
    available_only: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = Book.objects(school=school, is_active=True)
    if search:
        query = query.filter(__raw__={"$or": [
            {"title": {"$regex": search, "$options": "i"}},
            {"author": {"$regex": search, "$options": "i"}},
            {"isbn": {"$regex": search, "$options": "i"}}
        ]})
    if category_id:
        query = query.filter(category=BookCategory.objects.get(id=category_id))
    if class_name:
        query = query.filter(class_name=class_name)
    if available_only:
        query = query.filter(available_copies__gt=0)

    total = query.count()
    books = query.order_by('title').skip((page-1)*per_page).limit(per_page)
    result = [{
        "id": str(b.id), "title": b.title, "author": b.author,
        "class_name": b.class_name,
        "isbn": b.isbn, "publisher": b.publisher,
        "price": b.price,
        "total_copies": b.total_copies, "available_copies": b.available_copies,
        "rack_number": b.rack_number, "is_digital": b.is_digital,
        "category": b.category.name if b.category else None,
        "language": b.language, "year": b.year
    } for b in books]
    return success_response(result, meta={"total": total, "page": page, "per_page": per_page})


@router.put("/book/{book_id}")
async def update_book(book_id: str, data: dict, current_user: User = Depends(get_current_user)):
    try:
        b = Book.objects.get(id=book_id)
        data.pop('id', None); data.pop('school_id', None)
        b.update(**data)
        return success_response(message="Book updated")
    except Book.DoesNotExist:
        raise HTTPException(404, "Book not found")


@router.delete("/book/{book_id}")
async def delete_book(book_id: str, current_user: User = Depends(get_current_user)):
    try:
        Book.objects.get(id=book_id).update(is_active=False)
        return success_response(message="Book deleted")
    except Book.DoesNotExist:
        raise HTTPException(404, "Book not found")


# ─── Library Members ──────────────────────────────────────────────────────────
@router.post("/member")
async def add_member(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    import random, string
    member_id = "LIB" + ''.join(random.choices(string.digits, k=6))
    m = LibraryMember(
        school=school,
        member_type=data['member_type'],
        member_id=member_id,
        max_books_allowed=data.get('max_books_allowed', 3),
        max_days_allowed=data.get('max_days_allowed', 14)
    )
    if data.get('student_id'):
        m.student = Student.objects.get(id=data['student_id'])
    if data.get('staff_id'):
        m.staff_ref = Staff.objects.get(id=data['staff_id'])
    m.save()
    return success_response({"id": str(m.id), "member_id": member_id}, "Member registered")


@router.get("/member")
async def list_members(school_id: str, member_type: Optional[str] = None, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    query = LibraryMember.objects(school=school, is_active=True)
    if member_type:
        query = query.filter(member_type=member_type)
    result = []
    for m in query:
        issued = BookIssue.objects(member=m, status='Issued').count()
        overdue = BookIssue.objects(member=m, status='Overdue').count()
        result.append({
            "id": str(m.id), "member_id": m.member_id,
            "member_type": m.member_type,
            "name": m.student.full_name if m.student else (m.staff_ref.full_name if m.staff_ref else '-'),
            "books_issued": issued,
            "overdue_books": overdue,
            "max_books_allowed": m.max_books_allowed,
            "max_days_allowed": m.max_days_allowed
        })
    return success_response(result)


# ─── Issue/Return ─────────────────────────────────────────────────────────────
@router.post("/issue")
async def issue_book(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    book = Book.objects.get(id=data['book_id'])
    member = LibraryMember.objects.get(id=data['member_id'])

    if book.available_copies <= 0:
        raise HTTPException(400, "No copies available")

    active_issues = BookIssue.objects(member=member, status__in=['Issued', 'Overdue']).count()
    if active_issues >= member.max_books_allowed:
        raise HTTPException(400, f"Member has reached max limit of {member.max_books_allowed} books")

    settings = LibrarySettings.objects(school=school).first()
    loan_days = settings.loan_period_student if settings and member.member_type == 'Student' else (settings.loan_period_staff if settings else 14)
    fine_per_day = settings.fine_per_day if settings else 1.0

    due_date = datetime.utcnow() + timedelta(days=loan_days)

    issue = BookIssue(
        school=school, book=book, member=member,
        due_date=due_date, fine_per_day=fine_per_day,
        issued_by=current_user.full_name
    )
    issue.save()
    book.update(available_copies=book.available_copies - 1)

    return success_response({
        "id": str(issue.id),
        "due_date": due_date.isoformat(),
        "fine_per_day": fine_per_day
    }, "Book issued successfully")


@router.patch("/return/{issue_id}")
async def return_book(issue_id: str, current_user: User = Depends(get_current_user)):
    try:
        issue = BookIssue.objects.get(id=issue_id)
        if issue.status == 'Returned':
            raise HTTPException(400, "Book already returned")

        return_date = datetime.utcnow()
        overdue_days = 0
        fine = 0

        if return_date > issue.due_date:
            overdue_days = (return_date - issue.due_date).days
            fine = overdue_days * issue.fine_per_day

        issue.update(
            return_date=return_date,
            status='Returned',
            fine_amount=fine,
            returned_to=current_user.full_name
        )
        issue.book.update(available_copies=issue.book.available_copies + 1)

        return success_response({
            "overdue_days": overdue_days,
            "fine_amount": fine
        }, "Book returned successfully")
    except BookIssue.DoesNotExist:
        raise HTTPException(404, "Issue record not found")


@router.get("/issued")
async def get_issued_books(
    school_id: str,
    status: Optional[str] = None,
    member_id: Optional[str] = None,
    overdue_only: bool = False,
    current_user: User = Depends(get_current_user)
):
    school = School.objects.get(id=school_id)
    query = BookIssue.objects(school=school)
    if status:
        query = query.filter(status=status)
    if member_id:
        query = query.filter(member=LibraryMember.objects.get(id=member_id))
    if overdue_only:
        query = query.filter(due_date__lt=datetime.utcnow(), status='Issued')
        query.update(status='Overdue')
        query = BookIssue.objects(school=school, status='Overdue')

    result = []
    for i in query.order_by('-issue_date')[:100]:
        days_overdue = max(0, (datetime.utcnow() - i.due_date).days) if i.status != 'Returned' else 0
        result.append({
            "id": str(i.id),
            "book_title": i.book.title if i.book else '-',
            "book_author": i.book.author if i.book else '-',
            "member_name": (i.member.student.full_name if i.member.student else
                           (i.member.staff_ref.full_name if i.member.staff_ref else '-')) if i.member else '-',
            "member_id": i.member.member_id if i.member else '-',
            "issue_date": i.issue_date.isoformat(),
            "due_date": i.due_date.isoformat(),
            "return_date": i.return_date.isoformat() if i.return_date else None,
            "status": i.status,
            "days_overdue": days_overdue,
            "fine_amount": i.fine_amount,
            "fine_paid": i.fine_paid
        })
    return success_response(result)


@router.post("/category")
async def add_category(data: dict, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=data['school_id'])
    cat = BookCategory(school=school, name=data['name'], description=data.get('description'))
    cat.save()
    return success_response({"id": str(cat.id)}, "Category added")


@router.get("/category")
async def list_categories(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    cats = BookCategory.objects(school=school, is_active=True)
    return success_response([{"id": str(c.id), "name": c.name} for c in cats])


@router.get("/stats/{school_id}")
async def library_stats(school_id: str, current_user: User = Depends(get_current_user)):
    school = School.objects.get(id=school_id)
    total_books = Book.objects(school=school, is_active=True)
    total_copies = sum(b.total_copies for b in total_books)
    available = sum(b.available_copies for b in total_books)
    overdue = BookIssue.objects(school=school, due_date__lt=datetime.utcnow(), status='Issued').count()
    return success_response({
        "total_titles": total_books.count(),
        "total_copies": total_copies,
        "available_copies": available,
        "issued_copies": total_copies - available,
        "overdue_books": overdue,
        "total_members": LibraryMember.objects(school=school, is_active=True).count(),
        "total_fines": sum(i.fine_amount for i in BookIssue.objects(school=school, fine_amount__gt=0))
    })
