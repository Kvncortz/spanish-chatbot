import os
import json
import base64
import sqlite3
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI
import asyncio
from dotenv import load_dotenv
from datetime import datetime
import uuid
from pydantic import BaseModel
from typing import List, Optional

# Import database models
from database import db

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NARAKEET_API_KEY = os.getenv("NARAKEET_API_KEY")  # Optional: for best Spanish voices
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")  # Optional: for better Spanish voices
TTS_SERVICE = os.getenv("TTS_SERVICE", "openai")  # Options: "openai", "elevenlabs", "narakeet"

# Debug environment variables
print(f"=== TTS Configuration ===")
print(f"OPENAI_API_KEY present: {bool(OPENAI_API_KEY)}")
print(f"ELEVENLABS_API_KEY present: {bool(ELEVENLABS_API_KEY)}")
print(f"TTS_SERVICE: {TTS_SERVICE}")
print(f"========================")

@app.get("/home")
async def smart_home_redirect(request: Request):
    """Smart home redirect - checks authentication and redirects appropriately"""
    # For now, we'll just redirect to the landing page
    # In a real app, you'd check session cookies/tokens here
    return RedirectResponse(url="/")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/teacher", response_class=HTMLResponse)
async def teacher_dashboard(request: Request):
    return templates.TemplateResponse("teacher.html", {"request": request})

@app.get("/teacher-login", response_class=HTMLResponse)
async def teacher_login_page(request: Request):
    return templates.TemplateResponse("teacher_login.html", {"request": request})

@app.get("/teacher-signup", response_class=HTMLResponse)
async def teacher_signup_page(request: Request):
    return templates.TemplateResponse("teacher_signup.html", {"request": request})

@app.get("/student-login", response_class=HTMLResponse)
async def student_login_page(request: Request):
    return templates.TemplateResponse("student_login.html", {"request": request})

@app.get("/student-signup", response_class=HTMLResponse)
async def student_signup_page(request: Request):
    return templates.TemplateResponse("student_signup.html", {"request": request})

@app.get("/student", response_class=HTMLResponse)
async def student_assignment(request: Request):
    return templates.TemplateResponse("student.html", {"request": request})

@app.get("/student-dashboard", response_class=HTMLResponse)
async def student_dashboard(request: Request):
    return templates.TemplateResponse("student_dashboard.html", {"request": request})

@app.get("/practice", response_class=HTMLResponse)
async def practice_mode(request: Request):
    return templates.TemplateResponse("simple.html", {"request": request})

# Pydantic models for API requests
class TeacherCreate(BaseModel):
    name: str
    email: str

class ClassroomCreate(BaseModel):
    name: str
    description: str = ""
    grade_level: str = ""
    subject: str = ""

class ClassroomUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    grade_level: Optional[str] = None
    subject: Optional[str] = None

class StudentCreate(BaseModel):
    name: str
    email: Optional[str] = None
    grade_level: Optional[str] = None

class EnrollmentRequest(BaseModel):
    join_code: str
    student_name: str
    student_email: Optional[str] = None
    student_grade: Optional[str] = None

class AssignmentCreate(BaseModel):
    classroom_id: str
    title: str
    description: str
    instructions: str
    level: str
    duration: int
    due_date: Optional[str] = None
    prompt: Optional[str] = None
    vocab: Optional[List[str]] = None
    min_vocab_words: int = 0

class AssignmentUpdate(BaseModel):
    title: str
    description: str
    instructions: str
    level: str
    duration: int
    due_date: Optional[str] = None
    prompt: Optional[str] = None
    vocab: Optional[List[str]] = None
    min_vocab_words: int = 0

# API endpoints for assignments and logs
@app.post("/api/assignments")
async def create_assignment(request: Request):
    """Create a new assignment (legacy endpoint - redirects to classroom assignment)"""
    try:
        data = await request.json()
        # For backward compatibility, create without classroom if not provided
        classroom_id = data.get("classroom_id")
        if not classroom_id:
            # Create a default classroom for backward compatibility
            assignment = {
                "id": str(uuid.uuid4()),
                "title": data.get("title"),
                "level": data.get("level"),
                "duration": data.get("duration"),
                "prompt": data.get("prompt", ""),
                "description": data.get("description"),
                "instructions": data.get("instructions"),
                "createdAt": datetime.now().isoformat(),
                "studentCount": 0,
                "completionCount": 0
            }
            return {"assignment": assignment}
        
        # Create with classroom
        assignment_id = db.create_assignment(
            classroom_id=classroom_id,
            title=data.get("title"),
            description=data.get("description"),
            instructions=data.get("instructions"),
            level=data.get("level"),
            duration=data.get("duration"),
            due_date=data.get("due_date"),
            prompt=data.get("prompt"),
            vocab=data.get("vocab", [])
        )
        assignment = db.get_assignment_by_id(assignment_id)
        return {"assignment": assignment}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/assignments")
async def get_assignments():
    """Get all assignments"""
    try:
        assignments = db.get_all_assignments()
        return {"assignments": assignments}
    except Exception as e:
        print(f"Error fetching assignments: {e}")
        return {"error": str(e), "assignments": []}

@app.post("/api/logs")
async def submit_log(request: Request):
    """Submit student activity log"""
    try:
        log_data = await request.json()
        
        # Save to database using the database module
        session_id = db.create_assignment_session(
            assignment_id=log_data.get("assignmentId"),
            student_id=log_data.get("studentId"),  # This might need to be looked up by name
            start_time=log_data.get("startTime"),
            end_time=log_data.get("endTime"),
            completed=log_data.get("completed", False),
            message_count=log_data.get("messageCount", 0),
            voice_used=log_data.get("voiceUsed", False),
            transcript_used=log_data.get("transcriptUsed", False)
        )
        
        # Save conversation logs if provided
        if "conversation" in log_data and log_data["conversation"]:
            for msg in log_data["conversation"]:
                db.log_conversation_message(
                    session_id=session_id,
                    message_type=msg.get("sender", "unknown"),
                    content=msg.get("content", ""),
                    timestamp=msg.get("timestamp")
                )
        
        return {"success": True, "sessionId": session_id}
    except Exception as e:
        print(f"Error saving log: {e}")
        return {"error": str(e)}

@app.get("/api/logs")
async def get_logs(assignment_id: str = None):
    """Get activity logs, optionally filtered by assignment"""
    try:
        # Get all assignment sessions by querying all students
        # For now, we'll get all sessions and filter on the server side
        # In a larger system, you might want a more efficient method
        
        # Get all students first
        all_students = db.get_all_students()
        
        logs = []
        for student in all_students:
            # Get sessions for this student
            student_sessions = db.get_student_sessions(student["id"])
            
            for session in student_sessions:
                # Filter by assignment if specified
                if assignment_id and session["assignment_id"] != assignment_id:
                    continue
                
                # Get conversation logs for this session
                conversations = db.get_conversation_logs_by_session(session["id"])
                
                # Get assignment details
                assignment = db.get_assignment_by_id(session["assignment_id"])
                
                # Extract vocabulary used from conversation
                usedVocabCount = 0
                if assignment and assignment.get("vocab"):
                    assignment_vocab = assignment["vocab"]
                    used_vocab_words = set()  # Use set to track unique words
                    for msg in conversations:
                        if msg.get("message_type") == "user":
                            # Check which vocabulary words were used
                            for vocab_word in assignment_vocab:
                                if vocab_word.lower() in msg.get("content", "").lower():
                                    used_vocab_words.add(vocab_word)
                    usedVocabCount = len(used_vocab_words)
                
                log_entry = {
                    "id": session["id"],
                    "assignmentId": session["assignment_id"],
                    "assignmentTitle": session.get("assignment_title", "Unknown Assignment"),
                    "studentId": session["student_id"],
                    "studentName": student["name"],
                    "startTime": session["start_time"],
                    "endTime": session["end_time"],
                    "completed": session["completed"],
                    "messageCount": session["message_count"],
                    "voiceUsed": session["voice_used"],
                    "transcriptUsed": session["transcript_used"],
                    "level": session.get("level", "unknown"),
                    "conversation": conversations,
                    "createdAt": session["created_at"],
                    "dueDate": assignment.get("due_date") if assignment else None,
                    "usedVocabCount": usedVocabCount,
                    "minVocabWords": assignment.get("min_vocab_words") if assignment else 0,
                    "attemptNumber": session.get("attempt_number", 1),
                    "submitted_for_grading": session.get("submitted_for_grading", False)
                }
                
                logs.append(log_entry)
        
        # Sort by creation date, newest first (no filtering here - let frontend handle it)
        logs.sort(key=lambda x: x["createdAt"], reverse=True)
        
        return {"logs": logs}
    except Exception as e:
        print(f"Error fetching logs: {e}")
        return {"error": str(e), "logs": []}

@app.get("/api/logs/all")
async def get_all_logs():
    """Get all logs without filtering (for history modal)"""
    try:
        # Get all students
        students = db.get_all_students()
        
        # Get all assignment sessions
        all_sessions = []
        for student in students:
            sessions = db.get_student_sessions(student["id"])
            for session in sessions:
                session["studentName"] = student["name"]
                session["studentId"] = student["id"]
                # Debug: Check if submitted_for_grading exists
                print(f"Session {session.get('id')}: submitted_for_grading = {session.get('submitted_for_grading')}")
                all_sessions.append(session)
        
        logs = []
        for session in all_sessions:
            # Get assignment details
            assignment = db.get_assignment_by_id(session["assignment_id"])
            
            # Get conversation logs for this session
            conversations = db.get_conversation_logs_by_session(session["id"])
            
            # Get assignment details
            assignment = db.get_assignment_by_id(session["assignment_id"])
            
            # Extract vocabulary used from conversation
            usedVocabCount = 0
            if assignment and assignment.get("vocab"):
                assignment_vocab = assignment["vocab"]
                used_vocab_words = set()  # Use set to track unique words
                for msg in conversations:
                    if msg.get("message_type") == "user":
                        # Check which vocabulary words were used
                        for vocab_word in assignment_vocab:
                            if vocab_word.lower() in msg.get("content", "").lower():
                                used_vocab_words.add(vocab_word)
                usedVocabCount = len(used_vocab_words)
            
            log_entry = {
                "id": session["id"],
                "assignmentId": session["assignment_id"],
                "assignmentTitle": session.get("assignment_title", "Unknown Assignment"),
                "studentId": session["student_id"],
                "studentName": session["studentName"],
                "startTime": session["start_time"],
                "endTime": session["end_time"],
                "completed": session["completed"],
                "messageCount": session["message_count"],
                "voiceUsed": session["voice_used"],
                "transcriptUsed": session["transcript_used"],
                "level": session.get("level", "unknown"),
                "conversation": conversations,
                "createdAt": session["created_at"],
                "dueDate": assignment.get("due_date") if assignment else None,
                "usedVocabCount": usedVocabCount,
                "minVocabWords": assignment.get("min_vocab_words") if assignment else 0,
                "attemptNumber": session.get("attempt_number", 1),
                "submitted_for_grading": session.get("submitted_for_grading", False)
            }
            
            logs.append(log_entry)
        
        # Sort by creation date, newest first (no filtering - keep all attempts for previous attempts feature)
        logs.sort(key=lambda x: x["createdAt"], reverse=True)
        
        return {"logs": logs}
    except Exception as e:
        print(f"Error fetching all logs: {e}")
        return {"error": str(e), "logs": []}

@app.get("/api/students/{student_id}/sessions")
async def get_student_sessions(student_id: str):
    """Get all assignment sessions for a specific student"""
    try:
        # Use the existing database method
        sessions = db.get_student_sessions(student_id)
        
        return {"sessions": sessions}
    except Exception as e:
        print(f"Error fetching student sessions: {e}")
        return {"error": str(e), "sessions": []}

@app.get("/api/students/{student_id}/submitted-sessions")
async def get_submitted_sessions(student_id: str):
    """Get only submitted assignment sessions for a specific student"""
    try:
        # Get all sessions first
        all_sessions = db.get_student_sessions(student_id)
        
        # Filter to only submitted sessions (one per assignment)
        submitted_sessions = {}
        for session in all_sessions:
            if session.get("submitted_for_grading"):
                assignment_id = session["assignment_id"]
                # Keep only the submitted session for each assignment
                submitted_sessions[assignment_id] = session
        
        return {"sessions": list(submitted_sessions.values())}
    except Exception as e:
        print(f"Error fetching submitted sessions: {e}")
        return {"error": str(e), "sessions": []}

@app.get("/api/sessions/{session_id}/conversation")
async def get_session_conversation(session_id: str):
    """Get conversation logs for a specific session"""
    try:
        conversation = db.get_conversation_logs_by_session(session_id)
        return {"conversation": conversation}
    except Exception as e:
        print(f"Error fetching conversation: {e}")
        return {"error": str(e), "conversation": []}

@app.post("/api/sessions/{session_id}/submit")
async def submit_session_for_grading(session_id: str):
    """Submit a session for grading"""
    try:
        success = db.submit_session_for_grading(session_id)
        if success:
            return {"success": True, "message": "Session submitted for grading"}
        else:
            return {"success": False, "error": "Failed to submit session"}
    except Exception as e:
        print(f"Error submitting session: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/analytics")
async def get_analytics():
    """Get analytics data"""
    # In production, calculate from database
    # For now, return empty stats
    return {
        "totalAssignments": 0,
        "totalStudents": 0,
        "avgCompletion": 0,
        "voiceUsage": 0
    }

# Classroom Management Endpoints
@app.post("/api/teachers")
async def create_teacher(teacher: TeacherCreate):
    """Create a new teacher"""
    try:
        # Check if teacher already exists
        existing = db.get_teacher_by_email(teacher.email)
        if existing:
            raise HTTPException(status_code=400, detail="Teacher with this email already exists")
        
        teacher_id = db.create_teacher(teacher.name, teacher.email)
        teacher_data = db.get_teacher_by_id(teacher_id)
        return {"teacher": teacher_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/teachers/{teacher_id}")
async def get_teacher(teacher_id: str):
    """Get teacher by ID"""
    teacher = db.get_teacher_by_id(teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return {"teacher": teacher}

@app.put("/api/teachers/{teacher_id}")
async def update_teacher(teacher_id: str, teacher_data: dict):
    """Update teacher profile"""
    try:
        success = db.update_teacher(
            teacher_id=teacher_id,
            name=teacher_data.get("name"),
            email=teacher_data.get("email"),
            school=teacher_data.get("school"),
            title=teacher_data.get("title"),
            bio=teacher_data.get("bio")
        )
        if not success:
            raise HTTPException(status_code=404, detail="Teacher not found")
        
        updated_teacher = db.get_teacher_by_id(teacher_id)
        return {"teacher": updated_teacher}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Authentication Endpoints
@app.post("/api/teachers/signup")
async def teacher_signup(teacher_data: dict):
    """Teacher sign-up"""
    try:
        name = teacher_data.get("name")
        email = teacher_data.get("email")
        password = teacher_data.get("password")
        school = teacher_data.get("school")
        title = teacher_data.get("title")
        
        if not name or not email or not password:
            raise HTTPException(status_code=400, detail="Name, email, and password required")
        
        # Check if teacher already exists
        existing = db.get_teacher_by_email(email)
        if existing:
            raise HTTPException(status_code=400, detail="Teacher with this email already exists")
        
        # Create teacher with hashed password
        teacher_id = db.create_teacher(name, email, password, school, title)
        teacher = db.get_teacher_by_id(teacher_id)
        
        # Don't return password hash
        if teacher and 'password_hash' in teacher:
            del teacher['password_hash']
        
        return {"teacher": teacher}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/students/signup")
async def student_signup(student_data: dict):
    """Student sign-up"""
    try:
        name = student_data.get("name")
        email = student_data.get("email")
        password = student_data.get("password")
        grade_level = student_data.get("grade_level")
        
        if not name or not email or not password:
            raise HTTPException(status_code=400, detail="Name, email, and password required")
        
        # Check if student already exists
        existing = db.get_student_by_email(email)
        if existing:
            raise HTTPException(status_code=400, detail="Student with this email already exists")
        
        # Create student with hashed password
        student_id = db.create_student(name, email, password, grade_level)
        student = db.get_student_by_id(student_id)
        
        # Don't return password hash
        if student and 'password_hash' in student:
            del student['password_hash']
        
        return {"student": student}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/teachers/login")
async def teacher_login(credentials: dict):
    """Teacher login"""
    try:
        email = credentials.get("email")
        password = credentials.get("password")
        
        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password required")
        
        # Authenticate teacher with proper password verification
        teacher = db.authenticate_teacher(email, password)
        if not teacher:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        return {"teacher": teacher}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/students/login")
async def student_login(credentials: dict):
    """Student login"""
    try:
        email = credentials.get("email")
        password = credentials.get("password")
        
        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password required")
        
        # Authenticate student with proper password verification
        student = db.authenticate_student(email, password)
        if not student:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        return {"student": student}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/classrooms")
async def create_classroom(classroom: ClassroomCreate, teacher_id: str, spanish_level: str = "", is_advanced: bool = False):
    """Create a new classroom"""
    try:
        classroom_id = db.create_classroom(
            teacher_id=teacher_id,
            name=classroom.name,
            description=classroom.description,
            grade_level=classroom.grade_level,
            subject=classroom.subject,
            spanish_level=spanish_level,
            is_advanced=is_advanced
        )
        classroom_data = db.get_classroom_by_id(classroom_id)
        return {"classroom": classroom_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/classrooms/{classroom_id}")
async def get_classroom(classroom_id: str):
    """Get classroom by ID"""
    classroom = db.get_classroom_by_id(classroom_id)
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")
    return {"classroom": classroom}

@app.get("/api/classrooms/join/{join_code}")
async def get_classroom_by_join_code(join_code: str):
    """Get classroom by join code for student enrollment"""
    classroom = db.get_classroom_by_join_code(join_code)
    if not classroom:
        raise HTTPException(status_code=404, detail="Invalid join code")
    return {"classroom": classroom}

@app.put("/api/classrooms/{classroom_id}")
async def update_classroom(classroom_id: str, classroom: ClassroomUpdate):
    """Update classroom details"""
    try:
        success = db.update_classroom(
            classroom_id=classroom_id,
            name=classroom.name,
            description=classroom.description,
            grade_level=classroom.grade_level,
            subject=classroom.subject
        )
        if not success:
            raise HTTPException(status_code=404, detail="Classroom not found")
        
        updated_classroom = db.get_classroom_by_id(classroom_id)
        return {"classroom": updated_classroom}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/classrooms/{classroom_id}")
async def delete_classroom(classroom_id: str):
    """Delete a classroom"""
    try:
        success = db.delete_classroom(classroom_id)
        if not success:
            raise HTTPException(status_code=404, detail="Classroom not found")
        return {"message": "Classroom deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/teachers/{teacher_id}/classrooms")
async def get_teacher_classrooms(teacher_id: str):
    """Get all classrooms for a teacher"""
    try:
        classrooms = db.get_teacher_classrooms(teacher_id)
        return {"classrooms": classrooms}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/classrooms/{classroom_id}/students")
async def get_classroom_students(classroom_id: str):
    """Get all students enrolled in a classroom"""
    try:
        students = db.get_classroom_students(classroom_id)
        return {"students": students}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/enroll")
async def enroll_student(enrollment: EnrollmentRequest):
    """Enroll a student in a classroom using join code"""
    try:
        # Get classroom by join code
        classroom = db.get_classroom_by_join_code(enrollment.join_code)
        if not classroom:
            raise HTTPException(status_code=404, detail="Invalid join code")
        
        # Create or get student - for enrollment without authentication, create with default password
        student = db.get_student_by_email(enrollment.student_email) if enrollment.student_email else None
        if not student:
            # For enrollment via join code, create student with a default password
            # They can change it later when they log in
            default_password = "temp123"  # They should change this when they first log in
            student_id = db.create_student(
                name=enrollment.student_name,
                email=enrollment.student_email,
                password=default_password,
                grade_level=enrollment.student_grade
            )
        else:
            student_id = student['id']
        
        # Enroll student
        enrollment_id = db.enroll_student(student_id, classroom['id'])
        
        return {
            "message": "Successfully enrolled in classroom",
            "classroom": classroom,
            "student_id": student_id,
            "temp_password": default_password if not student else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/students/{student_id}/classrooms")
async def get_student_classrooms(student_id: str):
    """Get all classrooms a student is enrolled in"""
    try:
        classrooms = db.get_student_classrooms(student_id)
        return {"classrooms": classrooms}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/students/classrooms/leave")
async def leave_classroom(request: Request):
    """Student leaves a classroom"""
    try:
        data = await request.json()
        student_id = data.get("student_id")
        classroom_id = data.get("classroom_id")
        
        if not student_id or not classroom_id:
            raise HTTPException(status_code=400, detail="student_id and classroom_id are required")
        
        success = db.remove_student_enrollment(student_id, classroom_id)
        if not success:
            raise HTTPException(status_code=404, detail="Enrollment not found")
        
        return {"message": "Successfully left classroom"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/enroll/{student_id}/{classroom_id}")
async def remove_student_enrollment(student_id: str, classroom_id: str):
    """Remove a student from a classroom"""
    try:
        success = db.remove_student_enrollment(student_id, classroom_id)
        if not success:
            raise HTTPException(status_code=404, detail="Enrollment not found")
        return {"message": "Student removed from classroom successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/classroom-assignments")
async def create_classroom_assignment(assignment: AssignmentCreate):
    """Create a new assignment for a specific classroom"""
    try:
        assignment_id = db.create_assignment(
            classroom_id=assignment.classroom_id,
            title=assignment.title,
            description=assignment.description,
            instructions=assignment.instructions,
            level=assignment.level,
            duration=assignment.duration,
            due_date=assignment.due_date,
            prompt=assignment.prompt,
            vocab=assignment.vocab,
            min_vocab_words=assignment.min_vocab_words
        )
        assignment_data = db.get_assignment_by_id(assignment_id)
        return {"assignment": assignment_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/classrooms/{classroom_id}/assignments")
async def get_classroom_assignments(classroom_id: str):
    """Get all assignments for a classroom"""
    try:
        assignments = db.get_classroom_assignments(classroom_id)
        return {"assignments": assignments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/students/{student_id}/assignments")
async def get_student_assignments(student_id: str):
    """Get all assignments available to a student"""
    try:
        assignments = db.get_student_assignments(student_id)
        return {"assignments": assignments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/teachers/{teacher_id}/assignments")
async def get_teacher_assignments(teacher_id: str):
    """Get all assignments for a teacher across all classrooms"""
    try:
        # Get all classrooms for this teacher
        classrooms = db.get_teacher_classrooms(teacher_id)
        all_assignments = []
        
        # Get assignments for each classroom
        for classroom in classrooms:
            classroom_assignments = db.get_classroom_assignments(classroom['id'])
            # Add classroom info to each assignment
            for assignment in classroom_assignments:
                assignment['classroom_name'] = classroom['name']
                assignment['classroom_id'] = classroom['id']
            all_assignments.extend(classroom_assignments)
        
        # Sort by creation date (newest first)
        all_assignments.sort(key=lambda x: x['created_at'], reverse=True)
        
        return {"assignments": all_assignments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/assignments/{assignment_id}")
async def get_assignment(assignment_id: str):
    """Get assignment by ID"""
    try:
        assignment = db.get_assignment_by_id(assignment_id)
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        return assignment
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/assignments/{assignment_id}")
async def update_assignment(assignment_id: str, assignment: AssignmentUpdate):
    """Update an existing assignment"""
    try:
        success = db.update_assignment(
            assignment_id=assignment_id,
            title=assignment.title,
            description=assignment.description,
            instructions=assignment.instructions,
            level=assignment.level,
            duration=assignment.duration,
            due_date=assignment.due_date,
            prompt=assignment.prompt,
            vocab=assignment.vocab,
            min_vocab_words=assignment.min_vocab_words
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Assignment not found")
            
        return {"message": "Assignment updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/assignments/{assignment_id}")
async def delete_assignment(assignment_id: str):
    """Delete an assignment and all related student data (soft delete)"""
    try:
        # Soft delete the assignment and all related data
        with sqlite3.connect("vocafow.db") as conn:
            cursor = conn.cursor()
            
            # Soft delete the assignment
            cursor.execute("UPDATE assignments SET is_active = FALSE WHERE id = ?", (assignment_id,))
            
            # Soft delete all assignment sessions for this assignment
            cursor.execute("""
                UPDATE assignment_sessions 
                SET is_active = FALSE 
                WHERE assignment_id = ?
            """, (assignment_id,))
            
            # Note: conversation_logs don't have is_active column, but they're linked to sessions
            # The sessions are soft deleted, so logs won't appear in student views
            
            conn.commit()
        
        return {"message": "Assignment and related student data deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/classrooms/{classroom_id}/analytics")
async def get_classroom_analytics(classroom_id: str):
    """Get analytics for a classroom"""
    try:
        analytics = db.get_classroom_analytics(classroom_id)
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/{level}")
async def websocket_endpoint(websocket: WebSocket, level: str = "intermediate"):
    await websocket.accept()
    connection_id = id(websocket)  # Unique ID for this connection
    print(f"WebSocket connection {connection_id} established with level: {level}")
    
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY not set")
        await websocket.send_text("Error: OPENAI_API_KEY not set")
        return
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # TTS function using ElevenLabs for best Spanish voices
        async def generate_speech(text: str, level: str = "intermediate") -> bytes:
            print(f"Generating speech for text: '{text[:50]}...' with level: {level}")
            print(f"TTS_SERVICE: {TTS_SERVICE}, ELEVENLABS_API_KEY present: {bool(ELEVENLABS_API_KEY)}")
            
            # Prioritize ElevenLabs when API key is available for best Spanish voices
            if ELEVENLABS_API_KEY:
                try:
                    # Different voices for each level
                    voice_map = {
                        "beginner": "21m00Tcm4TlvDq8ikWAM",  # Rachel - clear, friendly female voice
                        "intermediate": "29vD33N1CtxCmqQRPOHJ",  # Spanish male voice
                        "advanced": "AZnzlk1XvdvUeBnXmlld"   # Drew - natural male voice
                    }
                    
                    voice_id = voice_map.get(level, "29vD33N1CtxCmqQRPOHJ")
                    print(f"Using ElevenLabs voice: {voice_id}")
                    
                    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                    headers = {
                        "Accept": "audio/mpeg",
                        "Content-Type": "application/json",
                        "xi-api-key": ELEVENLABS_API_KEY
                    }
                    data = {
                        "text": text,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {
                            "stability": 0.75,
                            "similarity_boost": 0.75,
                            "style": 0.0,
                            "use_speaker_boost": True
                        }
                    }
                    
                    response = requests.post(url, json=data, headers=headers)
                    if response.status_code == 200:
                        print("ElevenLabs TTS successful")
                        return response.content
                    else:
                        print(f"ElevenLabs error: {response.status_code} - {response.text}")
                except Exception as e:
                    print(f"ElevenLabs TTS failed: {e}")
            
            # Fallback to OpenAI (but will have Spanish issues)
            print("Falling back to OpenAI TTS with shimmer voice")
            speech_response = client.audio.speech.create(
                model="tts-1",
                voice="shimmer",
                input=text,
                speed=1.1
            )
            print("OpenAI TTS successful")
            return speech_response.content
        
        # Define level-specific prompts and icebreakers
        level_configs = {
            "beginner": {
                "system_prompt": "Eres un amigo español amigable para estudiantes de secundaria. Habla de forma natural sobre temas apropiados para menores de edad. Usa vocabulario simple y presente indicativo. Mantén las frases cortas y naturales. Sé breve y amigable. NO saludes repetidamente ni des lecciones. REGLAS DE CONTENIDO ESTRICTAS: NUNCA, BAJO NINGUNA CIRCUNSTANCIA, menciones alcohol, vino, cerveza, bebidas alcoholicas, drogas, temas sexuales, violencia, o cualquier contenido inapropiado. Si un estudiante pregunta sobre bebidas alcoholicas, responde 'Lo siento, solo puedo sugerir bebidas sin alcohol como agua, jugos o refrescos'. Si un estudiante pregunta sobre temas inapropiados, redirige educativamente a temas apropiados. Solo sugiere bebidas sin alcohol (agua, jugos, refrescos).",
                "icebreakers": [
                    "¡Hola! ¿Qué tal tu día?",
                    "¿Has hecho algo divertido últimamente?",
                    "¿Qué te gusta hacer en tu tiempo libre?",
                    "¿Tienes alguna mascota? Me encantan los animales.",
                    "¿Cuál es tu comida favorita? A mí me gusta la pizza.",
                    "¿Qué música escuchas estos días?",
                    "¿Has visto alguna película buena recientemente?",
                    "¿Prefieres el verano o el invierno?",
                    "¿Qué bebida te gusta? Yo soy de agua.",
                    "¿Practicas algún deporte?",
                    "¿Dónde te gustaría viajar?",
                    "¿Tienes hermanos? A veces discuto con los míños.",
                    "¿Cuál es tu color favorito? El mío es azul.",
                    "Qué tal el clima donde vives?",
                    "¿Qué haces normalmente los fines de semana?"
                ]
            },
            "intermediate": {
                "system_prompt": "Eres un amigo español conversacional para estudiantes de secundaria. Habla sobre temas apropiados para menores de edad de forma espontánea. Usa presente, pretérito y futuro simple. Mantén una conversación fluida y amigable. Usa lenguaje informal pero educado (tú/tú). Sé breve y natural. NO saludos repetidos ni correcciones. REGLAS DE CONTENIDO ESTRICTAS: NUNCA, BAJO NINGUNA CIRCUNSTANCIA, menciones alcohol, vino, cerveza, bebidas alcoholicas, drogas, temas sexuales, violencia, o cualquier contenido inapropiado. Si un estudiante pregunta sobre bebidas alcoholicas, responde 'Lo siento, solo puedo sugerir bebidas sin alcohol como agua, jugos, refrescos, té o café'. Si un estudiante pregunta sobre temas inapropiados, redirige educativamente a temas apropiados. Solo sugiere bebidas sin alcohol (jugos, refrescos, té, agua).",
                "icebreakers": [
                    "¡Hola! ¿Cómo estás hoy?",
                    "¿Qué tal tu día hasta ahora?",
                    "¿Qué te gustaría hacer hoy?",
                    "¿Has practicado español antes?",
                    "¿Qué tiempo hace donde estás?",
                    "¿Qué has visto en Netflix últimamente?",
                    "¿Cuál es tu canción favorita ahora?",
                    "¿Has visto alguna película buena recientemente?",
                    "¿Qué planes tienes para el fin de semana?",
                    "¿Qué opinas sobre las nuevas series de streaming?",
                    "¿Has escuchado música buena últimamente?",
                    "¿Qué tipo de videos ves en internet?",
                    "¿Cuál es tu meme favorito este mes?",
                    "¿Has viajado a algún lugar interesante?",
                    "¿Qué libro estás leyendo?",
                    "¿Cuál es tu videojuego favorito?",
                    "¿Qué piensas sobre los estrenos recientes?",
                    "¿Has probado algún restaurante nuevo?",
                    "¿Qué celebridad sigues en redes sociales?"
                ]
            },
            "advanced": {
                "system_prompt": "Eres un profesional nativo de un país hispanohablante con experiencia en atención al cliente. Habla de forma sofisticada y natural, usando un vocabulario rico y variado. Usa 'usted' para el contexto formal de hotel/restaurant, pero hazlo de manera fluida y natural, no rígida. Incorpora expresiones idiomáticas, modismos cultos, y frases más elaboradas. Usa todos los tiempos verbales incluyendo subjuntivo y condicional de forma espontánea. Mantén un tono profesional pero cálido y auténtico, como lo haría un profesional bien educado en España, México o Argentina. Usa conectores complejos y frases bien estructuradas. REGLAS DE CONTENIDO ESTRICTAS: NUNCA, BAJO NINGUNA CIRCUNSTANCIA, menciones alcohol, vino, cerveza, bebidas alcoholicas, drogas, temas sexuales, violencia, o cualquier contenido inapropiado para menores de edad. Si un estudiante pregunta sobre bebidas alcoholicas, responde con elegancia 'Le sugiero opciones sin alcohol como té infusiones o agua mineral'. Si un estudiante pregunta sobre temas inapropiados, redirige con diplomacia y naturalidad.",
                "icebreakers": [
                    "¡Buenas tardes! Encantado de ayudarle con su registro.",
                    "¡Hola! Bienvenido a nuestro establecimiento. ¿En qué puedo asistirle hoy?",
                    "¡Muy buenos días! ¿Cómo puedo servirle en su visita?",
                    "¡Hola! Qué gusto verle por aquí. ¿Necesita alguna asistencia?",
                    "¡Buenas! ¿Qué tal su día? Espero poder ayudarle con lo que necesite.",
                    "¡Hola! Bienvenido. ¿En qué le puedo ser útil hoy?",
                    "¡Muy buenas! ¿Qué le trae por nuestro establecimiento?",
                    "¡Hola! Qué placer atenderle. ¿Hay algo específico en lo que pueda ayudarle?",
                    "¡Buenas tardes! ¿Cómo está? Espero que su estancia sea excelente.",
                    "¡Hola! Bienvenido. ¿En qué puedo hacer su experiencia más agradable?",
                    "¡Muy buenos días! ¿Listo para comenzar su registro? Estoy a su disposición.",
                    "¡Hola! Qué bueno tenerle con nosotros. ¿Necesita algo para empezar?",
                    "¡Buenas! ¿Cómo puedo facilitar su estancia con nosotros?",
                    "¡Hola! Encantado de atenderle. ¿Qué necesita exactamente?",
                    "¡Muy buenas! ¿Listo para su check-in? Estoy aquí para ayudarle.",
                    "¡Hola! Bienvenido. ¿Hay algo que pueda hacer por usted hoy?",
                    "¡Buenas tardes! ¿Cómo puedo hacer su registro más eficiente?",
                    "¡Hola! Qué gusto atenderle. ¿Necesita ayuda con algo específico?",
                    "¡Muy buenas! ¿En qué puedo asistirle para que su visita sea perfecta?",
                    "¡Hola! Bienvenido. ¿Listo para comenzar? Estoy a su completa disposición."
                ]
            }
        }
        
        # Get config for selected level, default to intermediate
        config = level_configs.get(level, level_configs["intermediate"])
        print(f"Using {level} level configuration")
        
        # Check if this is an assignment session
        is_assignment = False
        assignment_prompt = None
        assignment_context = None
        
        import random
        icebreaker = random.choice(config["icebreakers"])
        
        # Wait for assignment setup message (with timeout)
        assignment_data = None
        try:
            # Wait for setup message with a short timeout
            setup_data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            setup_message = json.loads(setup_data)
            if setup_message.get("type") == "assignment_setup":
                assignment_data = setup_message.get("assignment")
                is_assignment = True
                print(f"Received assignment setup: {assignment_data.get('title', 'Unknown')}")
                
                # Extract assignment level for voice selection
                assignment_level = assignment_data.get("level", level)
                print(f"Assignment level: {assignment_level}, WebSocket level: {level}")
                
                # Use assignment level for voice selection
                level = assignment_level
                
                # Use custom prompt if provided, otherwise create contextual prompt
                if assignment_data.get("prompt"):
                    # Give the bot only what it needs: custom prompt + vocabulary + level guidance
                    level_guidance = level_configs.get(level, {}).get("system_prompt", "")
                    
                    # Get vocabulary list for the bot to incorporate
                    vocab_list = assignment_data.get("vocab", [])
                    vocab_instruction = ""
                    if vocab_list:
                        vocab_instruction = f"\n\nVocabulary to incorporate: {', '.join(vocab_list)}. Try to use these words naturally in the conversation."
                    
                    # Create bot prompt with only bot-relevant information
                    assignment_prompt = f"""{assignment_data['prompt']}{vocab_instruction}

Level Guidance: {level_guidance}"""
                    
                    print(f"Using bot-focused prompt: custom prompt + vocabulary + level guidance")
                    print(f"Bot prompt preview: {assignment_prompt[:300]}...")
                else:
                    # Create contextual prompt based on assignment
                    vocab_list = assignment_data.get("vocab", [])
                    vocab_instruction = ""
                    if vocab_list:
                        vocab_instruction = f" Intenta incorporar naturalmente estas palabras de vocabulario: {', '.join(vocab_list)}."
                    
                    assignment_prompt = f"Eres un ayudante de español para una tarea de secundaria. Contexto: {assignment_data.get('description', '')}. Instrucciones: {assignment_data.get('instructions', '')}.{vocab_instruction} Mantén la conversación enfocada en este contexto. Sé amigable y natural. Usa el nivel de español apropiado para {level}. IMPORTANTE: Solo responde a los mensajes del estudiante. No inventes respuestas ni continúes la conversación por tu cuenta. Espera siempre a que el estudiante hable primero. REGLAS DE CONTENIDO ESTRICTAS: NUNCA, BAJO NINGUNA CIRCUNSTANCIA, menciones alcohol, vino, cerveza, bebidas alcoholicas, drogas, temas sexuales, violencia, o cualquier contenido inapropiado para menores de edad. Si un estudiante pregunta sobre bebidas alcoholicas, responde 'Lo siento, solo puedo sugerir bebidas sin alcohol como agua, jugos, refrescos, té o café'. Si un estudiante pregunta sobre temas inapropiados, redirige educativamente a temas apropiados. Mantén toda conversación 100% apropiada para un entorno educativo de secundaria."
                    print(f"Using generated contextual prompt")
                
                # Create contextual icebreaker based on assignment
                if assignment_data.get("prompt"):
                    # Generate contextual opening based on teacher's prompt
                    try:
                        # Get level guidance for AI generation
                        level_guidance = level_configs.get(level, {}).get("system_prompt", "")
                        
                        # Translate teacher's prompt to Spanish if needed
                        teacher_prompt = assignment_data['prompt']
                        # Check if prompt is likely in English (simple heuristic)
                        if any(word in teacher_prompt.lower() for word in ['the ', 'you are', ' and ', ' is ', ' to ']):
                            try:
                                translation_response = client.chat.completions.create(
                                    model="gpt-3.5-turbo",
                                    messages=[
                                        {"role": "system", "content": "Translate the following text to Spanish. Only return the translation, no extra text."},
                                        {"role": "user", "content": teacher_prompt}
                                    ],
                                    max_tokens=200,
                                    temperature=0.3
                                )
                                spanish_prompt = translation_response.choices[0].message.content.strip()
                                print(f"Translated teacher prompt: {teacher_prompt} -> {spanish_prompt}")
                            except Exception as e:
                                print(f"Error translating prompt: {e}")
                                spanish_prompt = teacher_prompt  # Fallback to original
                        else:
                            spanish_prompt = teacher_prompt
                        
                        # Use OpenAI to generate an appropriate opening line
                        opening_prompt = f"""Based on this scenario and level guidance, generate a natural Spanish opening line that the AI should say to start the conversation:

Scenario: {spanish_prompt}

Level Guidance: {level_guidance}

Requirements:
- Generate ONLY the opening line (no extra text)
- Make it natural and appropriate for the scenario
- Follow the level guidance above for vocabulary, formality, and style
- Keep it concise and conversational
- Do not include any explanations or greetings like "Here is an opening line:"
- Just provide the exact Spanish text the AI should say

Opening line:"""

                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "user", "content": opening_prompt}
                            ],
                            max_tokens=50,
                            temperature=0.7
                        )
                        
                        generated_opening = response.choices[0].message.content.strip()
                        icebreaker = generated_opening
                        print(f"Generated contextual opening: {icebreaker}")
                        
                    except Exception as e:
                        print(f"Error generating opening: {e}")
                        # Fallback to generic opening
                        icebreaker = "¡Hola! Estoy listo para comenzar."
                    
                elif assignment_data.get("description"):
                    # Generate opening based on description
                    try:
                        opening_prompt = f"""Based on this assignment description, generate a natural Spanish opening line:

Description: {assignment_data.get('description', '')}
Instructions: {assignment_data.get('instructions', '')}

Requirements:
- Generate ONLY the opening line
- Make it natural and appropriate for {level} level Spanish
- Keep it concise and conversational

Opening line:"""

                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "user", "content": opening_prompt}
                            ],
                            max_tokens=50,
                            temperature=0.7
                        )
                        
                        generated_opening = response.choices[0].message.content.strip()
                        icebreaker = generated_opening
                        print(f"Generated description-based opening: {icebreaker}")
                        
                    except Exception as e:
                        print(f"Error generating opening: {e}")
                        icebreaker = "¡Hola! Estoy listo para ayudarte."
                else:
                    icebreaker = random.choice(config["icebreakers"])
                
                print(f"Using assignment icebreaker: {icebreaker}")
            else:
                # Not an assignment setup, treat as practice mode
                print("No assignment setup received, using practice mode")
                is_assignment = False
                
        except asyncio.TimeoutError:
            # No message received within timeout, treat as practice mode
            print("Timeout waiting for assignment setup, using practice mode")
            is_assignment = False
        except Exception as e:
            print(f"Error receiving assignment setup: {e}")
            # Continue with default behavior (practice mode)
            is_assignment = False
        
        # Generate speech for icebreaker
        try:
            audio_bytes = await generate_speech(icebreaker, level)
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            
            # Send icebreaker with audio
            await websocket.send_text(json.dumps({
                "type": "voice_response",
                "text": icebreaker,
                "audio": audio_base64,
                "transcription": None
            }))
        except Exception as e:
            print(f"Error generating icebreaker audio: {e}")
            try:
                # Fallback to text only
                await websocket.send_text(f"bot:{icebreaker}")
            except Exception as e2:
                print(f"Error sending fallback message: {e2}")
                return
        
        # Maintain conversation history with level-specific system prompt
        system_prompt = assignment_prompt if assignment_prompt else config["system_prompt"]
        conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "assistant", "content": icebreaker}
        ]
        
        # Handle messages
        while True:
            try:
                # Wait for user message
                data = await websocket.receive_text()
                print(f"Connection {connection_id} received message: {data}")
                
                # Parse JSON message
                try:
                    message_data = json.loads(data)
                except json.JSONDecodeError:
                    # Handle legacy text format
                    if data.startswith("user:"):
                        message_data = {"type": "text", "content": data[5:]}
                    else:
                        continue
                
                # Validate this is still the active connection
                if websocket.client_state.name != "CONNECTED":
                    print(f"Connection {connection_id} no longer active, stopping")
                    break
                
                if message_data.get("type") == "text":
                    user_message = message_data.get("content", "")
                    print(f"Processing user message: '{user_message}'")
                    print(f"Current history length: {len(conversation_history)}")
                    
                    # Only add user message to history, not bot responses yet
                    conversation_history.append({"role": "user", "content": user_message})
                    
                    # Get response from OpenAI with level-specific parameters
                    # Advanced level needs more tokens for complex responses
                    if level == "advanced":
                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=conversation_history,
                            max_tokens=250,  # More tokens for advanced discussions
                            temperature=0.7,  # Slightly lower for more coherent long responses
                            presence_penalty=0.4,  # Lower to avoid repetition in long texts
                            frequency_penalty=0.2
                        )
                    else:
                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=conversation_history,
                            max_tokens=120,
                            temperature=0.8,
                            presence_penalty=0.6,
                            frequency_penalty=0.3
                        )
                    
                    bot_response = response.choices[0].message.content
                    print(f"Generated bot response: '{bot_response}'")
                    
                    # Content filtering - check for prohibited content
                    prohibited_words = ['vino', 'cerveza', 'cervezas', 'alcohol', 'alcohólicas', 'alcoholicas', 'bebidas alcoholicas', 'bebidas alcohólicas']
                    response_lower = bot_response.lower()
                    
                    for word in prohibited_words:
                        if word in response_lower:
                            print(f"PROHIBITED CONTENT DETECTED: {word}")
                            bot_response = "Lo siento, solo puedo sugerir bebidas sin alcohol como agua, jugos, refrescos, té o café. ¿Le gustaría alguna de esas opciones?"
                            break
                    
                    # Add bot response to history
                    conversation_history.append({"role": "assistant", "content": bot_response})
                    
                    # Keep history manageable (last 10 exchanges)
                    if len(conversation_history) > 21:  # system + 10 pairs
                        conversation_history = [conversation_history[0]] + conversation_history[-20:]
                    
                    await websocket.send_text(f"bot:{bot_response}")
                    
                elif message_data.get("type") == "voice":
                    # Handle voice input - speech to text
                    audio_data = message_data.get("audio", "")
                    
                    try:
                        # Transcribe audio using OpenAI Whisper
                        transcription = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=("audio.webm", base64.b64decode(audio_data), "audio/webm")
                        )
                        
                        user_message = transcription.text
                        print(f"Transcribed: {user_message}")
                        
                        # Add transcribed message to history
                        conversation_history.append({"role": "user", "content": user_message})
                        
                        # Get response from OpenAI with level-specific parameters
                        # Advanced level needs more tokens for complex responses
                        if level == "advanced":
                            response = client.chat.completions.create(
                                model="gpt-3.5-turbo",
                                messages=conversation_history,
                                max_tokens=250,  # More tokens for advanced discussions
                                temperature=0.7,  # Slightly lower for more coherent long responses
                                presence_penalty=0.4,  # Lower to avoid repetition in long texts
                                frequency_penalty=0.2
                            )
                        else:
                            response = client.chat.completions.create(
                                model="gpt-3.5-turbo",
                                messages=conversation_history,
                                max_tokens=120,
                                temperature=0.8,
                                presence_penalty=0.6,
                                frequency_penalty=0.3
                            )
                        
                        bot_response = response.choices[0].message.content
                        print(f"Sending response: {bot_response}")
                        
                        # Content filtering - check for prohibited content
                        prohibited_words = ['vino', 'cerveza', 'cervezas', 'alcohol', 'alcohólicas', 'alcoholicas', 'bebidas alcoholicas', 'bebidas alcohólicas']
                        response_lower = bot_response.lower()
                        
                        for word in prohibited_words:
                            if word in response_lower:
                                print(f"PROHIBITED CONTENT DETECTED: {word}")
                                bot_response = "Lo siento, solo puedo sugerir bebidas sin alcohol como agua, jugos, refrescos, té o café. ¿Le gustaría alguna de esas opciones?"
                                break
                        
                        # Add bot response to history
                        conversation_history.append({"role": "assistant", "content": bot_response})
                        
                        # Keep history manageable
                        if len(conversation_history) > 21:
                            conversation_history = [conversation_history[0]] + conversation_history[-20:]
                        
                        # Generate speech from response using the new TTS function
                        audio_bytes = await generate_speech(bot_response, level)
                        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                        
                        # Send both text and audio
                        await websocket.send_text(json.dumps({
                            "type": "voice_response",
                            "text": bot_response,
                            "audio": audio_base64,
                            "transcription": user_message
                        }))
                        
                    except Exception as e:
                        print(f"Voice processing error: {e}")
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "content": f"Error procesando voz: {str(e)}"
                        }))
                    
            except WebSocketDisconnect:
                print("Client disconnected")  # Debug log
                break
                
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                print(error_msg)  # Debug log
                try:
                    await websocket.send_text(f"bot:Lo siento, ha ocurrido un error: {str(e)}")
                except Exception as e2:
                    print(f"Error sending error message: {e2}")
                    break
                break
                
    except Exception as e:
        await websocket.send_text(f"Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
