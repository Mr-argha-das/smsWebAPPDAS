#!/bin/bash
echo "🏫 Scholar Desk v1.0 — Setup"
echo "=============================="

cd "$(dirname "$0")"

echo "📦 Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "✅ Done! Starting server..."
echo ""
echo "🌐 Open in browser: http://localhost:8000"
echo "📚 API Docs:        http://localhost:8000/api/docs"
echo ""
echo "⚠️  First time setup — create admin user:"
echo '   curl -X POST http://localhost:8000/api/v1/auth/register \'
echo '     -H "Content-Type: application/json" \'
echo '     -d '"'"'{"username":"admin","email":"admin@school.com","password":"admin123","full_name":"Admin","is_superadmin":true}'"'"
echo ""

uvicorn main:app --reload --host 0.0.0.0 --port 8060
