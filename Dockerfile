FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# Create upload dirs
RUN mkdir -p uploads/student_photos uploads/student_documents \
    uploads/staff_photos uploads/study_materials \
    uploads/notices uploads/assets uploads/certificates

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
