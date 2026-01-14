import os
import json
import base64
import sqlite3
import requests
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI
import google.genai as genai
import asyncio
from dotenv import load_dotenv
from datetime import datetime
import uuid
from pydantic import BaseModel
from typing import List, Optional
import google.genai as genai_client

# Import database models
from database import db

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/gemini", StaticFiles(directory="gemini-live-language-lab/dist", html=True), name="gemini")
templates = Jinja2Templates(directory="templates")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NARAKEET_API_KEY = os.getenv("NARAKEET_API_KEY")  # Optional: for best Spanish voices
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")  # Optional: for better Spanish voices
TTS_SERVICE = os.getenv("TTS_SERVICE", "openai")  # Options: "openai", "elevenlabs", "narakeet"

# Initialize Google AI for LearnLM
if GOOGLE_API_KEY:
    import google.genai as genai
    # Create client for new API
    client = genai.Client(api_key=GOOGLE_API_KEY)
    # Store client for use in functions
    learnlm_client = client
    print("LearnLM client initialized with Gemini 2.5 Pro")
else:
    learnlm_client = None
    print("Warning: GOOGLE_API_KEY not set - LearnLM features disabled")

# Debug environment variables
print(f"=== AI Configuration ===")
print(f"OPENAI_API_KEY present: {bool(OPENAI_API_KEY)}")
print(f"GOOGLE_API_KEY present: {bool(GOOGLE_API_KEY)}")
print(f"ELEVENLABS_API_KEY present: {bool(ELEVENLABS_API_KEY)}")
print(f"TTS_SERVICE: {TTS_SERVICE}")
print(f"LearnLM available: {bool(learnlm_client)}")
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

@app.get("/language-lab", response_class=HTMLResponse)
async def language_lab(request: Request):
    """Serve the Gemini Live Language Lab"""
    return RedirectResponse(url="/gemini/")

# Pydantic models for API requests
class TeacherCreate(BaseModel):
    name: str
    email: str

class ClassroomCreate(BaseModel):
    name: str
    description: str = ""
    grade_level: str = ""
    subject: str = ""
    spanish_level: str = ""
    is_advanced: bool = False

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
    level_standard: str = 'ACTFL'  # ACTFL, CEFR, etc.
    duration: int
    due_date: Optional[str] = None
    prompt: Optional[str] = None
    vocab: Optional[List[str]] = None
    min_vocab_words: int = 0
    # Avatar and learning features
    avatar_role: Optional[str] = None  # doctor, waiter, travel agent, etc.
    student_objective: Optional[str] = None  # what student should accomplish
    avatar_characteristics: Optional[List[str]] = None  # patient, encouraging, etc.
    voice_speed: float = 1.0  # speech rate multiplier
    speak_slowly: bool = False  # hablar lento y claro
    theme: Optional[str] = None  # conversation context and vocabulary focus

class AssignmentUpdate(BaseModel):
    title: str
    description: str
    instructions: str
    level: str
    level_standard: str = 'ACTFL'  # ACTFL, CEFR, etc.
    duration: int
    due_date: Optional[str] = None
    prompt: Optional[str] = None
    vocab: Optional[List[str]] = None
    min_vocab_words: int = 0
    # Avatar and learning features
    avatar_role: Optional[str] = None  # doctor, waiter, travel agent, etc.
    student_objective: Optional[str] = None  # what student should accomplish
    avatar_characteristics: Optional[List[str]] = None  # patient, encouraging, etc.
    voice_speed: float = 1.0  # speech rate multiplier
    speak_slowly: bool = False  # hablar lento y claro
    theme: Optional[str] = None  # conversation context and vocabulary focus

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
async def create_classroom(classroom: ClassroomCreate, teacher_id: str):
    """Create a new classroom"""
    try:
        classroom_id = db.create_classroom(
            teacher_id=teacher_id,
            name=classroom.name,
            description=classroom.description,
            grade_level=classroom.grade_level,
            subject=classroom.subject,
            spanish_level=classroom.spanish_level,
            is_advanced=classroom.is_advanced
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
            level_standard=assignment.level_standard,
            duration=assignment.duration,
            due_date=assignment.due_date,
            prompt=assignment.prompt,
            vocab=assignment.vocab,
            min_vocab_words=assignment.min_vocab_words,
            avatar_role=assignment.avatar_role,
            student_objective=assignment.student_objective,
            avatar_characteristics=assignment.avatar_characteristics,
            voice_speed=assignment.voice_speed,
            speak_slowly=assignment.speak_slowly,
            theme=getattr(assignment, 'theme', None)  # Add theme field
        )
        
        # Get the assignment data without the JOIN to avoid classroom dependency issues
        with sqlite3.connect(db.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM assignments WHERE id = ? AND is_active = TRUE
            """, (assignment_id,))
            row = cursor.fetchone()
            if row:
                assignment_data = dict(row)
                if assignment_data['vocab']:
                    assignment_data['vocab'] = json.loads(assignment_data['vocab'])
                # Add classroom info if possible
                try:
                    classroom = db.get_classroom_by_id(assignment_data['classroom_id'])
                    if classroom:
                        assignment_data['classroom_name'] = classroom['name']
                except:
                    pass  # Continue without classroom info
                return {"assignment": assignment_data}
            else:
                return {"assignment": None}
        
        return {"assignment": None}
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
            cursor.execute("UPDATE assignments SET is_active = 0 WHERE id = ?", (assignment_id,))
            
            # Soft delete all assignment sessions for this assignment
            cursor.execute("""
                UPDATE assignment_sessions 
                SET is_active = 0 
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

# Helper function to get AI response (LearnLM or OpenAI fallback)
async def get_ai_response(conversation_history: list, level: str = "intermediate", assignment_data: dict = None) -> str:
    """Get response from LearnLM or fallback to OpenAI"""
    try:
        # Try LearnLM first if available
        if learnlm_client:
            print("Using LearnLM for educational conversation")
            
            # Convert conversation format for LearnLM
            formatted_history = []
            for msg in conversation_history:
                if msg["role"] == "user":
                    formatted_history.append(f"Student: {msg['content']}")
                elif msg["role"] == "assistant":
                    formatted_history.append(f"Tutor: {msg['content']}")
            
            # Create level-specific prompt
            level_guidance = {
                "beginner": "Use simple vocabulary, short sentences, and speak slowly. Be very encouraging and patient.",
                "intermediate": "Use moderate vocabulary and grammar. Provide gentle corrections and scaffold support.",
                "advanced": "Use complex vocabulary and nuanced expressions. Challenge with sophisticated grammar and cultural context."
            }
            
            # Use assignment context if available, otherwise use generic prompt
            if assignment_data:
                system_prompt_template = build_parts_prompt(assignment_data, level)
                # Replace the placeholder with actual conversation history
                system_prompt = system_prompt_template.replace("{conversation_history}", " ".join(formatted_history))
            else:
                system_prompt = f"""You are a Spanish conversation partner.

PARTS FRAMEWORK:
- P: Persona - Friendly, encouraging conversation partner
- A: Act - Help students practice Spanish through natural conversation
- R: Recipient - {level} level student
- T: Theme - Everyday conversations and personal interests
- S: Structure - Natural flow with appropriate vocabulary and grammar

{level_guidance.get(level, "")}

Current conversation:
{' '.join(formatted_history)}

Respond naturally in Spanish. Keep it conversational and appropriate for {level} level. No English translations.

Response:"""
            
            response = learnlm_client.models.generate_content(
                model='models/gemini-2.5-flash-native-audio-latest',
                contents=system_prompt
            )
            bot_response = response.text
            print(f"LearnLM response: '{bot_response}'")
            return bot_response
            
    except Exception as e:
        print(f"LearnLM failed: {e}")
    
    # Fallback to OpenAI
    print("Falling back to OpenAI")
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        if level == "advanced":
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=conversation_history,
                max_tokens=250,
                temperature=0.7,
                presence_penalty=0.4,
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
        
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI fallback also failed: {e}")
        return "Lo siento, estoy teniendo problemas técnicos. ¿Puedes repetir eso?"

async def get_scaffolding_response(spanish_text: str, level: str = "intermediate") -> str:
    """Generate scaffolding with English translations for review section only"""
    try:
        if learnlm_client:
            print("Generating scaffolding for review section")
            
            level_guidance = {
                "beginner": "Provide simple English translations and basic explanations.",
                "intermediate": "Provide English translations and grammar explanations.",
                "advanced": "Provide nuanced English translations and cultural context."
            }
            
            scaffolding_prompt = f"""You are a Spanish language tutor providing educational scaffolding.

For the given Spanish text, provide helpful scaffolding by:
1. Identifying 3-5 key vocabulary words to highlight
2. For each highlighted word, provide: <span class="vocab-highlight">spanish_word</span><span class="tooltip">english_translation</span>
3. Add brief grammar explanations after the text
4. Add cultural context when relevant

Format:
Spanish text with individual word highlights, followed by grammar explanations.

Example:
Me gusta la <span class="vocab-highlight">lechuga</span><span class="tooltip">lettuce</span> y los <span class="vocab-highlight">tomates</span><span class="tooltip">tomatoes</span> porque son <span class="vocab-highlight">saludables</span><span class="tooltip">healthy</span>.

Grammar note: "Me gusta" is used to express likes/dislikes.

Cultural note: Fresh vegetables are important in Spanish cuisine.

Spanish text: {spanish_text}

Level: {level}
{level_guidance.get(level, "")}

Enhanced text:"""
            
            try:
                response = learnlm_client.models.generate_content(
                    model='models/gemini-2.5-flash-native-audio-latest',
                    contents=scaffolding_prompt
                )
                scaffolding_response = response.text.strip()
                # Remove any surrounding quotes (handle various quote types)
                if (scaffolding_response.startswith('"') and scaffolding_response.endswith('"')) or \
                   (scaffolding_response.startswith('"') and scaffolding_response.endswith('"')):
                    scaffolding_response = scaffolding_response[1:-1]
                # Also remove any leading/trailing quotes that might be left
                scaffolding_response = scaffolding_response.strip('"').strip('"')
                print(f"Scaffolding response: '{scaffolding_response}'")
                return scaffolding_response
            except Exception as gemini_error:
                print(f"Gemini scaffolding failed: {gemini_error}")
                # Fallback to OpenAI
                pass
            
        # OpenAI fallback for scaffolding
        print("Falling back to OpenAI for scaffolding")
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        level_guidance = {
            "beginner": "Provide simple English translations and basic explanations.",
            "intermediate": "Provide English translations and grammar explanations.",
            "advanced": "Provide nuanced English translations and cultural context."
        }
        
        scaffolding_prompt = f"""You are a Spanish language tutor providing educational scaffolding.

For the given Spanish text, provide helpful scaffolding by:
1. Identifying 3-5 key vocabulary words to highlight
2. For each highlighted word, provide: <span class="vocab-highlight">spanish_word</span><span class="tooltip">english_translation</span>
3. Add brief grammar explanations after the text
4. Add cultural context when relevant

Format:
Spanish text with individual word highlights, followed by grammar explanations.

Example:
Me gusta la <span class="vocab-highlight">lechuga</span><span class="tooltip">lettuce</span> y los <span class="vocab-highlight">tomates</span><span class="tooltip">tomatoes</span> porque son <span class="vocab-highlight">saludables</span><span class="tooltip">healthy</span>.

Grammar note: "Me gusta" is used to express likes/dislikes.

Cultural note: Fresh vegetables are important in Spanish cuisine.

Spanish text: {spanish_text}

Level: {level}
{level_guidance.get(level, "")}

Enhanced text:"""
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": scaffolding_prompt},
                {"role": "user", "content": "Generate the enhanced text:"}
            ],
            max_tokens=200,
            temperature=0.7
        )
        
        scaffolding_response = response.choices[0].message.content.strip()
        # Remove any surrounding quotes (handle various quote types)
        if (scaffolding_response.startswith('"') and scaffolding_response.endswith('"')) or \
           (scaffolding_response.startswith('"') and scaffolding_response.endswith('"')):
            scaffolding_response = scaffolding_response[1:-1]
        # Also remove any leading/trailing quotes that might be left
        scaffolding_response = scaffolding_response.strip('"').strip('"')
        print(f"OpenAI scaffolding response: '{scaffolding_response}'")
        return scaffolding_response
            
    except Exception as e:
        print(f"Scaffolding generation failed: {e}")
        return spanish_text  # Fallback to original text

@app.post("/api/save-session")
async def save_session(request: dict):
    """Save a completed session to database"""
    try:
        session_data = request
        
        # Create session record using existing method
        session_id = db.create_assignment_session(
            assignment_id=session_data.get("assignmentId", ""),
            student_id=session_data.get("studentName", ""),
            start_time=session_data.get("startTime"),
            end_time=session_data.get("endTime"),
            completed=session_data.get("completed", False),
            message_count=session_data.get("messageCount", 0),
            voice_used=session_data.get("voiceUsed", False),
            transcript_used=session_data.get("transcriptUsed", False)
        )
        
        # Insert conversation logs directly
        with sqlite3.connect("vocafow.db") as conn:
            cursor = conn.cursor()
            for msg in session_data.get("conversation", []):
                log_id = str(uuid.uuid4())
                # Map sender to message_type
                message_type = "user" if msg.get("sender") == "user" else "bot"
                
                cursor.execute("""
                    INSERT INTO conversation_logs 
                    (id, session_id, message_type, content, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    log_id,
                    session_id,
                    message_type,
                    msg.get("content", ""),
                    msg.get("timestamp")
                ))
            conn.commit()
        
        return {"success": True, "session_id": session_id}
        
    except Exception as e:
        print(f"Error saving session: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/generate-scaffolding")
async def generate_scaffolding(request: dict):
    """Generate scaffolding for review section"""
    try:
        text = request.get("text", "")
        level = request.get("level", "intermediate")
        
        if not text:
            return {"error": "No text provided"}
        
        scaffolding = await get_scaffolding_response(text, level)
        return {"scaffolding": scaffolding}
        
    except Exception as e:
        print(f"Error generating scaffolding: {e}")
        return {"error": str(e), "scaffolding": text}

# Helper function to build PARTS framework prompt
def build_parts_prompt(assignment_data: dict, level: str) -> str:
    """Build a structured PARTS framework prompt for Spanish conversation"""
    
    # Extract PARTS elements from assignment data
    persona = assignment_data.get('avatar_role', 'friendly conversation partner')
    characteristics = assignment_data.get('avatar_characteristics', [])
    student_objective = assignment_data.get('student_objective', 'practice Spanish conversation')
    recipient_level = assignment_data.get('level', level)
    theme = assignment_data.get('theme', assignment_data.get('title', 'Spanish conversation'))
    instructions = assignment_data.get('instructions', '')
    vocab_list = assignment_data.get('vocab', [])
    
    # Build Persona section
    persona_traits = f" who is {', '.join(characteristics)}" if characteristics else ""
    persona_section = f"P: Persona - You are a {persona}{persona_traits}"
    
    # Build Act section  
    act_section = f"A: Act - Guide the student to {student_objective}. {instructions}"
    
    # Build Recipient section
    recipient_section = f"R: Recipient - {recipient_level} level Spanish student"
    
    # Build Theme section
    theme_section = f"T: Theme - {theme}"
    if vocab_list:
        theme_section += f". Key vocabulary: {', '.join(vocab_list)}"
    
    # Build Structure section
    structure_section = f"S: Structure - Natural conversation flow with appropriate vocabulary and grammar for {recipient_level} level"
    
    # Combine PARTS into a concise, conversation-focused prompt
    parts_prompt = f"""You are a Spanish language tutor using the PARTS framework.

{persona_section}
{act_section}
{recipient_section}
{theme_section}
{structure_section}

CONVERSATION GUIDELINES:
- Maintain natural, authentic conversation flow
- Use vocabulary and grammar appropriate for {recipient_level} level
- Provide gentle guidance and encouragement
- No English translations or explanations
- Focus on communication practice

Current conversation:
{{conversation_history}}

Respond naturally in Spanish as the {persona}. Keep it conversational and engaging.

Response:"""
    
    return parts_prompt

@app.websocket("/ws/{level}")
async def websocket_endpoint(websocket: WebSocket, level: str = "intermediate"):
    await websocket.accept()
    connection_id = id(websocket)  # Unique ID for this connection
    print(f"WebSocket connection {connection_id} established with level: {level}")
    
    # Initialize assignment data at connection level
    assignment_data = None
    
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY not set")
        await websocket.send_text("Error: OPENAI_API_KEY not set")
        return
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # TTS function using ElevenLabs for best Spanish voices with voice speed control
        async def generate_speech(text: str, level: str = "intermediate", voice_speed: float = 1.0, speak_slowly: bool = False) -> bytes:
            print(f"Generating speech for text: '{text[:50]}...' with level: {level}, speed: {voice_speed}, speak_slowly: {speak_slowly}")
            print(f"TTS_SERVICE: {TTS_SERVICE}, ELEVENLABS_API_KEY present: {bool(ELEVENLABS_API_KEY)}")
            
            # Adjust speed based on speak_slowly parameter
            adjusted_speed = voice_speed * 0.8 if speak_slowly else voice_speed
            
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
                    print(f"Using ElevenLabs voice: {voice_id} with speed: {adjusted_speed}")
                    
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
                            "use_speaker_boost": True,
                            "rate": adjusted_speed  # Control speech rate
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
                speed=adjusted_speed
            )
            print("OpenAI TTS successful")
            return speech_response.content
        
        # Define level-specific prompts and icebreakers with ACTFL/CEFR standards
        level_configs = {
            # ACTFL Standards
            "novice_low": {
                "standard": "ACTFL",
                "system_prompt": "Eres un tutor amigable de español para principiantes. Usa palabras y frases muy simples, presente indicativo, vocabulario básico. Habla lentamente y repite si es necesario. Enfócate en comunicación survival.",
                "icebreakers": ["Hola", "¿Cómo estás?", "Me llamo...", "¿Cómo te llamas?"]
            },
            "novice_mid": {
                "standard": "ACTFL",
                "system_prompt": "Eres un tutor amigable de español. Usa frases cortas y simples, presente indicativo, vocabulario cotidiano. Haz preguntas básicas y da respuestas directas.",
                "icebreakers": ["¡Hola! ¿Qué tal?", "¿Cómo estás hoy?", "¿De dónde eres?", "¿Qué te gusta hacer?"]
            },
            "novice_high": {
                "standard": "ACTFL",
                "system_prompt": "Eres un conversacional español amigable. Usa frases simples, presente y algún pretérito, vocabulario familiar. Mantén conversaciones breves sobre temas conocidos.",
                "icebreakers": ["¡Hola! ¿Cómo estás?", "¿Qué tal tu día?", "¿Qué has hecho hoy?", "¿Tienes hobbies?"]
            },
            "intermediate_low": {
                "standard": "ACTFL",
                "system_prompt": "Eres un conversacional español natural. Usa presente, pretérito, futuro simple. Habla sobre temas personales, rutinas, experiencias. Sé espontáneo pero claro.",
                "icebreakers": ["¡Hola! ¿Qué tal tu día?", "¿Qué te gustaría hacer hoy?", "¿Has practicado español antes?", "¿Qué tiempo hace donde estás?"]
            },
            "intermediate_mid": {
                "standard": "ACTFL",
                "system_prompt": "Eres un conversacional español fluido. Usa varios tiempos verbales, vocabulario amplio. Habla sobre opiniones, experiencias, planes futuros. Sé natural y expresivo.",
                "icebreakers": ["¡Hola! ¿Cómo estás?", "¿Qué tal todo por aquí?", "¿Qué planes tienes para hoy?", "¿Algo interesante últimamente?"]
            },
            "intermediate_high": {
                "standard": "ACTFL",
                "system_prompt": "Eres un conversacional español avanzado. Usa todos los tiempos, vocabulario rico, expresiones idiomáticas simples. Habla sobre temas abstractos, opiniones, narrativas.",
                "icebreakers": ["¡Hola! ¿Qué tal?", "¿Cómo va todo?", "¿Qué te cuenta la vida?", "¿Algo nuevo o interesante?"]
            },
            "advanced": {
                "standard": "ACTFL",
                "system_prompt": "Eres un conversacional español nativo. Usa lenguaje complejo, subjuntivo, condicional, vocabulario extenso, expresiones idiomáticas. Habla sobre cualquier tema con naturalidad y matices.",
                "icebreakers": ["¡Hola! ¿Qué tal todo?", "¿Cómo vamos?", "¿Qué novedades tienes?", "¿Cómo te encuentras hoy?"]
            },
            # CEFR Standards
            "a1": {
                "standard": "CEFR",
                "system_prompt": "Eres un tutor de español básico. Presente simple, vocabulario elemental, frases muy cortas. Enfócate en presentaciones, información personal, entorno inmediato.",
                "icebreakers": ["Hola", "Me llamo...", "¿Cómo te llamas?", "¿De dónde eres?"]
            },
            "a2": {
                "standard": "CEFR",
                "system_prompt": "Eres un conversacional español elemental. Frases simples, rutinas, descripciones básicas. Habla sobre familia, trabajo, tiempo libre, viajes locales.",
                "icebreakers": ["¡Hola! ¿Qué tal?", "¿Cómo estás?", "¿Qué haces?", "¿Dónde vives?"]
            },
            "b1": {
                "standard": "CEFR",
                "system_prompt": "Eres un conversacional español intermedio. Experiencias, sueños, opiniones. Conecta ideas, explica razones. Habla sobre temas familiares y personales con algo de fluidez.",
                "icebreakers": ["¡Hola! ¿Cómo estás?", "¿Qué tal tu semana?", "¿Qué te gusta hacer?", "¿Has viajado mucho?"]
            },
            "b2": {
                "standard": "CEFR",
                "system_prompt": "Eres un conversacional español avanzado. Argumentos, discusiones abstractas, matices. Habla con fluidez y espontaneidad sobre temas complejos.",
                "icebreakers": ["¡Hola! ¿Qué tal?", "¿Cómo va todo?", "¿Qué opinas sobre...?", "¿Algo interesante últimamente?"]
            },
            "c1": {
                "standard": "CEFR",
                "system_prompt": "Eres un conversacional español experto. Lenguaje flexible, efectivo, social/profesional. Usa estructuras complejas, vocabulario preciso, expresiones idiomáticas.",
                "icebreakers": ["¡Hola! ¿Qué tal?", "¿Cómo te encuentras?", "¿Qué te parece la situación actual?", "¿Alguna reflexión interesante?"]
            },
            "c2": {
                "standard": "CEFR",
                "system_prompt": "Eres un conversacional español nativo-culto. Comprende todo, distingue matices finos. Habla con precisión, fluidez, naturalidad sobre cualquier tema.",
                "icebreakers": ["¡Hola! ¿Qué tal?", "¿Cómo vamos?", "¿Qué te parece...?", "¿Algún pensamiento profundo hoy?"]
            },
            # Legacy backward compatibility
            "beginner": {
                "standard": "ACTFL",
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
            }
        }
        
        # Get config for selected level, default to intermediate_mid
        print(f"DEBUG: Looking for level '{level}' in level_configs")
        print(f"DEBUG: Available levels: {list(level_configs.keys())}")
        
        if level in level_configs:
            config = level_configs[level]
            print(f"DEBUG: Found config for level '{level}'")
        else:
            config = level_configs["intermediate_mid"]
            print(f"DEBUG: Level '{level}' not found, using intermediate_mid as fallback")
        print(f"Using {level} level configuration")
        
        # Check if this is an assignment session
        is_assignment = False
        assignment_prompt = None
        assignment_context = None
        
        import random
        icebreaker = random.choice(config["icebreakers"])
        
        # Wait for assignment setup message (with timeout)
        try:
            # Wait for setup message with a short timeout
            setup_data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            setup_message = json.loads(setup_data)
            if setup_message.get("type") == "assignment_setup":
                assignment_data = setup_message.get("assignment")
                print(f"Received assignment setup: {assignment_data.get('title', 'Unknown')}")
                
                # Extract assignment level for voice selection
                assignment_level = assignment_data.get("level", level)
                print(f"Assignment level: {assignment_level}, WebSocket level: {level}")
                
                # Use assignment level for voice selection
                level = assignment_level
                
                # Always use PARTS framework prompt from teacher's input
                assignment_prompt = build_parts_prompt(assignment_data, level)
                print(f"Using PARTS framework prompt")
                
                # Generate contextual icebreaker using Gemini 3 with PARTS prompt, fallback to OpenAI
                try:
                    # Use the assignment's persona and objective to generate opening
                    icebreaker_prompt = f"""Based on this assignment setup, generate a natural Spanish opening line that starts the conversation:

Assignment Details:
- Persona: {assignment_data.get('avatar_role', 'conversation partner')}
- Student Objective: {assignment_data.get('student_objective', 'practice Spanish')}
- Context: {assignment_data.get('description', '')}
- Instructions: {assignment_data.get('instructions', '')}

Requirements:
- Generate ONLY the opening line (no extra text)
- Make it natural and appropriate for the scenario
- Match the {level} proficiency level
- Keep it concise and conversational
- Stay in character as the persona
- Just provide the exact Spanish text to start the conversation

Opening line:"""

                    if learnlm_client:
                        response = learnlm_client.models.generate_content(
                            model='models/gemini-2.5-flash-native-audio-latest',
                            contents=icebreaker_prompt
                        )
                        icebreaker = response.text.strip()
                        print(f"Generated icebreaker with Gemini Flash: {icebreaker}")
                    else:
                        # Use OpenAI with same PARTS framework
                        client = OpenAI(api_key=OPENAI_API_KEY)
                        response = client.chat.completions.create(
                            model="gpt-4",
                            messages=[
                                {"role": "system", "content": icebreaker_prompt},
                                {"role": "user", "content": "Generate the opening line:"}
                            ],
                            max_tokens=50,
                            temperature=0.7
                        )
                        icebreaker = response.choices[0].message.content.strip()
                        print(f"Generated icebreaker with OpenAI: {icebreaker}")
                        
                except Exception as e:
                    print(f"Error generating icebreaker with Gemini: {e}")
                    # Fallback to OpenAI with same PARTS framework
                    try:
                        client = OpenAI(api_key=OPENAI_API_KEY)
                        response = client.chat.completions.create(
                            model="gpt-4",
                            messages=[
                                {"role": "system", "content": icebreaker_prompt},
                                {"role": "user", "content": "Generate the opening line:"}
                            ],
                            max_tokens=50,
                            temperature=0.7
                        )
                        icebreaker = response.choices[0].message.content.strip()
                        print(f"Generated icebreaker with OpenAI fallback: {icebreaker}")
                    except Exception as openai_error:
                        print(f"OpenAI fallback also failed: {openai_error}")
                        # Final fallback to default icebreaker
                        import random
                        icebreaker = random.choice(config["icebreakers"])
                        print(f"Using fallback icebreaker: {icebreaker}")
                
                # Continue with assignment mode
                is_assignment = True
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
                    
                    # Get response from LearnLM (with OpenAI fallback)
                    bot_response = await get_ai_response(conversation_history, level, assignment_data)
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
                    print(f"DEBUG: Sent bot message: {bot_response[:100]}...")  # Debug log
                    
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
                        
                        # Get response from LearnLM (with OpenAI fallback)
                        bot_response = await get_ai_response(conversation_history, level, assignment_data)
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
