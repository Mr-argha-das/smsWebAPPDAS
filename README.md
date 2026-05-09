# 🏫 EduManage Pro v3.0 — Complete School Management System

A full-stack school management system with **19 modules**, built with FastAPI + MongoDB + Pure HTML/CSS/JS frontend.

---

## 🚀 Quick Start

### Option 1: Simple (Local Setup)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start server
uvicorn main:app --reload

# 3. Open browser
# http://localhost:8000
```

### Option 2: Docker

```bash
docker-compose up
# OR
docker build -t edumanage . && docker run -p 8000:8000 edumanage
```

---

## 🔑 First Login (Create Admin)

After starting server, run this once:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@school.com","password":"admin123","full_name":"School Admin","is_superadmin":true}'
```

Then login at: **http://localhost:8000/login**
- Username: `admin`
- Password: `admin123`

---

## 🗂️ 19 Modules

| Module | Description |
|--------|-------------|
| 🏫 Institution | School, Academic Years, Classes, Subjects |
| 👨‍🎓 Students | Admission, Profile, Documents, TC |
| 👨‍🏫 Staff & HR | Staff, Leave, Assignments |
| 📚 Academics | Timetable, Homework, Study Materials |
| 📝 Examinations | Exams, Marks, Results |
| 💰 Fees | Categories, Invoices, Payments |
| 📅 Attendance | Daily attendance, Reports |
| 🚌 Transport | Routes, Vehicles, Drivers |
| 📖 Library | Books, Issues, Returns |
| 📦 Inventory | Assets, Stock management |
| 🏥 Health | Medical records, Visits |
| 💬 Communication | Notices, Events, Messages |
| 📊 Reports | Analytics, Insights |
| 🏠 Hostel | Rooms, Allocations, Fees |
| 💼 Payroll | Salary structure, Payslips |
| 🎓 Admissions | Online applications |
| 📜 Certificates | Issue & manage certificates |
| 👨‍👩‍👧 Parent Portal | Parent login, Updates |
| 🔐 Auth | JWT auth, Role-based access |

---

## 🛠️ Tech Stack

- **Backend**: FastAPI, MongoEngine, MongoDB Atlas
- **Auth**: JWT (access + refresh tokens)
- **Frontend**: Pure HTML5 + Tailwind CSS + Vanilla JS
- **Fonts**: Sora + Space Grotesk
- **Deployment**: Dockerfile included

---

## 📁 Project Structure

```
edumanage_pro/
├── main.py              # FastAPI app entry point
├── config.py            # Settings (DB URL, JWT secret, etc.)
├── database.py          # MongoDB connection
├── requirements.txt     # Python dependencies
├── Dockerfile
├── setup.sh
├── models/              # MongoEngine document models (19 modules)
├── routes/              # FastAPI route handlers (19 modules)
├── utils/               # Auth helpers, utilities
├── uploads/             # File uploads (photos, documents)
└── frontend/
    ├── login.html
    ├── dashboard.html
    ├── students.html
    ├── staff.html
    ├── ... (19 pages total)
    └── js/
        ├── api.js       # Complete API client
        └── layout.js    # Sidebar + topbar + UI components
```

---

## ⚙️ Configuration (config.py / .env)

```env
MONGODB_URL=mongodb+srv://user:pass@cluster.mongodb.net/school_management
SECRET_KEY=your-secret-key-here
```

---

## 📚 API Docs

After starting server:
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc
# smsWebapp
