import os
import uuid
import random
import string
from datetime import datetime
from pathlib import Path
from fastapi import UploadFile, HTTPException
from config import settings
import aiofiles


def generate_id(prefix: str = "", length: int = 8) -> str:
    """Generate unique ID like STU-20240001"""
    chars = string.digits
    suffix = ''.join(random.choices(chars, k=length))
    year = datetime.now().year
    return f"{prefix}{year}{suffix}" if prefix else f"{year}{suffix}"


def generate_admission_no(school_code: str = "SCH") -> str:
    year = datetime.now().year
    random_part = ''.join(random.choices(string.digits, k=5))
    return f"{school_code}/{year}/{random_part}"


def generate_employee_id(school_code: str = "SCH") -> str:
    year = datetime.now().year
    random_part = ''.join(random.choices(string.digits, k=4))
    return f"{school_code}/EMP/{year}/{random_part}"


def generate_invoice_no(school_code: str = "SCH") -> str:
    year = datetime.now().year
    month = datetime.now().month
    random_part = ''.join(random.choices(string.digits, k=5))
    return f"INV/{school_code}/{year}{month:02d}/{random_part}"


def generate_transaction_no() -> str:
    return f"TXN{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"


def generate_tc_no(school_code: str = "SCH") -> str:
    year = datetime.now().year
    random_part = ''.join(random.choices(string.digits, k=5))
    return f"TC/{school_code}/{year}/{random_part}"


async def save_upload_file(upload_file: UploadFile, folder: str = "general") -> str:
    """Save uploaded file and return relative path"""
    # Validate extension
    ext = upload_file.filename.split(".")[-1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type .{ext} not allowed")
    
    # Create folder
    upload_path = Path(settings.UPLOAD_DIR) / folder
    upload_path.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    file_path = upload_path / unique_name
    
    # Save file
    content = await upload_file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(400, "File size exceeds 10MB limit")
    
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)
    
    return str(Path(folder) / unique_name)


def success_response(data=None, message: str = "Success", meta: dict = None):
    response = {"success": True, "message": message}
    if data is not None:
        response["data"] = data
    if meta:
        response["meta"] = meta
    return response


def error_response(message: str = "Error", errors=None):
    response = {"success": False, "message": message}
    if errors:
        response["errors"] = errors
    return response


def paginate_query(query, page: int = 1, per_page: int = 20):
    """Paginate a MongoEngine query"""
    total = query.count()
    skip = (page - 1) * per_page
    items = query.skip(skip).limit(per_page)
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }


def doc_to_dict(doc, exclude: list = None) -> dict:
    """Convert MongoEngine document to dict"""
    exclude = exclude or []
    data = {}
    for field_name in doc._fields:
        if field_name in exclude:
            continue
        val = getattr(doc, field_name, None)
        if hasattr(val, 'id'):
            data[field_name] = str(val.id)
            data[f"{field_name}_name"] = str(val) if hasattr(val, '__str__') else None
        elif isinstance(val, list):
            data[field_name] = [
                str(item.id) if hasattr(item, 'id') else item
                for item in val
            ]
        elif isinstance(val, datetime):
            data[field_name] = val.isoformat()
        else:
            data[field_name] = val
    if hasattr(doc, 'id') and doc.id:
        data['id'] = str(doc.id)
    return data
