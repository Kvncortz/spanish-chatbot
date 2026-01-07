import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
import uuid
import hashlib

class DatabaseManager:
    def __init__(self, db_path: str = "vocafow.db"):
        self.db_path = db_path
        self.init_database()
    
    def hash_password(self, password: str) -> str:
        """Hash a password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash"""
        return self.hash_password(password) == password_hash
    
    def init_database(self):
        """Initialize the database with all required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Teachers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS teachers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    school TEXT,
                    title TEXT,
                    bio TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Add teacher profile columns if they don't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE teachers ADD COLUMN school TEXT")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
            
            try:
                cursor.execute("ALTER TABLE teachers ADD COLUMN title TEXT")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
            
            try:
                cursor.execute("ALTER TABLE teachers ADD COLUMN bio TEXT")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
            
            try:
                cursor.execute("ALTER TABLE teachers ADD COLUMN password_hash TEXT")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
            
            # Classrooms table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS classrooms (
                    id TEXT PRIMARY KEY,
                    teacher_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    grade_level TEXT,
                    subject TEXT,
                    spanish_level TEXT,
                    is_advanced BOOLEAN DEFAULT FALSE,
                    join_code TEXT UNIQUE NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (teacher_id) REFERENCES teachers (id)
                )
            """)
            
            # Add spanish_level column if it doesn't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE classrooms ADD COLUMN spanish_level TEXT")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
            
            # Add is_advanced column if it doesn't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE classrooms ADD COLUMN is_advanced BOOLEAN DEFAULT FALSE")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
            
            # Add due_date column to assignments table if it doesn't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE assignments ADD COLUMN due_date TIMESTAMP")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
            
            # Add is_active column to assignment_sessions table if it doesn't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE assignment_sessions ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
            
            # Students table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    password_hash TEXT NOT NULL,
                    grade_level TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Add password_hash column to students table if it doesn't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE students ADD COLUMN password_hash TEXT")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
            
            # Add is_active column to students table if it doesn't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE students ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
            
            # Enrollments table (many-to-many relationship between students and classrooms)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS enrollments (
                    id TEXT PRIMARY KEY,
                    student_id TEXT NOT NULL,
                    classroom_id TEXT NOT NULL,
                    enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (student_id) REFERENCES students (id),
                    FOREIGN KEY (classroom_id) REFERENCES classrooms (id),
                    UNIQUE(student_id, classroom_id)
                )
            """)
            
            # Assignments table (updated to include classroom_id)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS assignments (
                    id TEXT PRIMARY KEY,
                    classroom_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    instructions TEXT,
                    level TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    due_date TIMESTAMP,
                    prompt TEXT,
                    vocab TEXT,  -- JSON array of vocabulary words
                    min_vocab_words INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (classroom_id) REFERENCES classrooms (id)
                )
            """)
            
            # Add min_vocab_words column if it doesn't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE assignments ADD COLUMN min_vocab_words INTEGER DEFAULT 0")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    # Column already exists, which is fine
                    pass
                else:
                    raise e
            
            # Add attempt_number column to assignment_sessions if it doesn't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE assignment_sessions ADD COLUMN attempt_number INTEGER DEFAULT 1")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    # Column already exists, which is fine
                    pass
                else:
                    raise e
            
            # Assignment sessions table (tracks individual student attempts)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS assignment_sessions (
                    id TEXT PRIMARY KEY,
                    assignment_id TEXT NOT NULL,
                    student_id TEXT NOT NULL,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    completed BOOLEAN DEFAULT FALSE,
                    message_count INTEGER DEFAULT 0,
                    voice_used BOOLEAN DEFAULT FALSE,
                    transcript_used BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    submitted_for_grading BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (assignment_id) REFERENCES assignments (id),
                    FOREIGN KEY (student_id) REFERENCES students (id)
                )
            """)
            
            # Add submitted_for_grading column if it doesn't exist (for existing databases)
            cursor.execute("PRAGMA table_info(assignment_sessions)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'submitted_for_grading' not in columns:
                cursor.execute("ALTER TABLE assignment_sessions ADD COLUMN submitted_for_grading BOOLEAN DEFAULT FALSE")
            
            # Conversation logs table (detailed conversation data)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_logs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message_type TEXT NOT NULL,  -- 'user' or 'bot'
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES assignment_sessions (id)
                )
            """)
            
            # Add created_at column to conversation_logs table if it doesn't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE conversation_logs ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
            
            conn.commit()
    
    # Teacher operations
    def create_teacher(self, name: str, email: str, password: str, school: str = None, title: str = None) -> str:
        """Create a new teacher"""
        teacher_id = str(uuid.uuid4())
        password_hash = self.hash_password(password)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO teachers (id, name, email, password_hash, school, title) VALUES (?, ?, ?, ?, ?, ?)",
                (teacher_id, name, email, password_hash, school, title)
            )
            conn.commit()
        return teacher_id
    
    def get_teacher_by_id(self, teacher_id: str) -> Optional[Dict]:
        """Get teacher by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM teachers WHERE id = ?", (teacher_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_teacher_by_email(self, email: str) -> Optional[Dict]:
        """Get teacher by email"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM teachers WHERE email = ?", (email,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def authenticate_teacher(self, email: str, password: str) -> Optional[Dict]:
        """Authenticate teacher with email and password"""
        teacher = self.get_teacher_by_email(email)
        if teacher and self.verify_password(password, teacher['password_hash']):
            # Don't return password hash
            teacher_copy = teacher.copy()
            del teacher_copy['password_hash']
            return teacher_copy
        return None
    
    def update_teacher(self, teacher_id: str, name: str = None, email: str = None, 
                      school: str = None, title: str = None, bio: str = None) -> bool:
        """Update teacher profile"""
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if email is not None:
            updates.append("email = ?")
            params.append(email)
        if school is not None:
            updates.append("school = ?")
            params.append(school)
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if bio is not None:
            updates.append("bio = ?")
            params.append(bio)
        
        if not updates:
            return False
        
        params.append(teacher_id)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE teachers SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
            return cursor.rowcount > 0
    
    # Classroom operations
    def create_classroom(self, teacher_id: str, name: str, description: str = "", 
                        grade_level: str = "", subject: str = "", spanish_level: str = "", 
                        is_advanced: bool = False) -> str:
        """Create a new classroom"""
        classroom_id = str(uuid.uuid4())
        join_code = self._generate_join_code()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO classrooms (id, teacher_id, name, description, grade_level, subject, spanish_level, is_advanced, join_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (classroom_id, teacher_id, name, description, grade_level, subject, spanish_level, is_advanced, join_code))
            conn.commit()
        return classroom_id
    
    def _generate_join_code(self) -> str:
        """Generate a unique 6-character join code"""
        import random
        import string
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not self.get_classroom_by_join_code(code):
                return code
    
    def get_classroom_by_id(self, classroom_id: str) -> Optional[Dict]:
        """Get classroom by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, t.name as teacher_name 
                FROM classrooms c
                JOIN teachers t ON c.teacher_id = t.id
                WHERE c.id = ?
            """, (classroom_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_classroom_by_join_code(self, join_code: str) -> Optional[Dict]:
        """Get classroom by join code"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, t.name as teacher_name 
                FROM classrooms c
                JOIN teachers t ON c.teacher_id = t.id
                WHERE c.join_code = ? AND c.is_active = TRUE
            """, (join_code,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_teacher_classrooms(self, teacher_id: str) -> List[Dict]:
        """Get all classrooms for a teacher"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, 
                       COUNT(e.id) as student_count,
                       COUNT(a.id) as assignment_count
                FROM classrooms c
                LEFT JOIN enrollments e ON c.id = e.classroom_id AND e.is_active = TRUE
                LEFT JOIN assignments a ON c.id = a.classroom_id AND a.is_active = TRUE
                WHERE c.teacher_id = ? AND c.is_active = TRUE
                GROUP BY c.id
                ORDER BY c.created_at DESC
            """, (teacher_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_classroom(self, classroom_id: str, name: str = None, description: str = None,
                        grade_level: str = None, subject: str = None) -> bool:
        """Update classroom details"""
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if grade_level is not None:
            updates.append("grade_level = ?")
            params.append(grade_level)
        if subject is not None:
            updates.append("subject = ?")
            params.append(subject)
        
        if not updates:
            return False
        
        params.append(classroom_id)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE classrooms SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_classroom(self, classroom_id: str) -> bool:
        """Soft delete a classroom"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE classrooms SET is_active = FALSE WHERE id = ?", (classroom_id,))
            cursor.execute("UPDATE enrollments SET is_active = FALSE WHERE classroom_id = ?", (classroom_id,))
            cursor.execute("UPDATE assignments SET is_active = FALSE WHERE classroom_id = ?", (classroom_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    # Student operations
    def create_student(self, name: str, email: str, password: str, grade_level: str = None) -> str:
        """Create a new student"""
        student_id = str(uuid.uuid4())
        password_hash = self.hash_password(password)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO students (id, name, email, password_hash, grade_level) VALUES (?, ?, ?, ?, ?)",
                (student_id, name, email, password_hash, grade_level)
            )
            conn.commit()
        return student_id
    
    def get_assignment_by_id(self, assignment_id: str) -> Optional[Dict]:
        """Get assignment by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,))
            row = cursor.fetchone()
            if row:
                assignment = dict(row)
                if assignment['vocab']:
                    assignment['vocab'] = json.loads(assignment['vocab'])
                return assignment
            return None
    
    def get_all_assignments(self) -> List[Dict]:
        """Get all assignments"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM assignments WHERE is_active = TRUE ORDER BY created_at DESC")
            results = []
            for row in cursor.fetchall():
                assignment = dict(row)
                if assignment['vocab']:
                    assignment['vocab'] = json.loads(assignment['vocab'])
                results.append(assignment)
            return results
    
    def get_student_by_email(self, email: str) -> Optional[Dict]:
        """Get student by email"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students WHERE email = ?", (email,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def authenticate_student(self, email: str, password: str) -> Optional[Dict]:
        """Authenticate student with email and password"""
        student = self.get_student_by_email(email)
        if student and self.verify_password(password, student['password_hash']):
            # Don't return password hash
            student_copy = student.copy()
            del student_copy['password_hash']
            return student_copy
        return None
    
    # Enrollment operations
    def enroll_student(self, student_id: str, classroom_id: str) -> str:
        """Enroll a student in a classroom"""
        enrollment_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO enrollments (id, student_id, classroom_id)
                VALUES (?, ?, ?)
            """, (enrollment_id, student_id, classroom_id))
            conn.commit()
        return enrollment_id
    
    def get_classroom_students(self, classroom_id: str) -> List[Dict]:
        """Get all students enrolled in a classroom"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.*, e.enrolled_at
                FROM students s
                JOIN enrollments e ON s.id = e.student_id
                WHERE e.classroom_id = ? AND e.is_active = TRUE
                ORDER BY s.name
            """, (classroom_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_student_classrooms(self, student_id: str) -> List[Dict]:
        """Get all classrooms a student is enrolled in"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, t.name as teacher_name, e.enrolled_at
                FROM classrooms c
                JOIN teachers t ON c.teacher_id = t.id
                JOIN enrollments e ON c.id = e.classroom_id
                WHERE e.student_id = ? AND e.is_active = TRUE AND c.is_active = TRUE
                ORDER BY e.enrolled_at DESC
            """, (student_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def remove_student_enrollment(self, student_id: str, classroom_id: str) -> bool:
        """Remove a student from a classroom"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE enrollments SET is_active = FALSE 
                WHERE student_id = ? AND classroom_id = ?
            """, (student_id, classroom_id))
            conn.commit()
            return cursor.rowcount > 0
    
    # Assignment operations
    def create_assignment(self, classroom_id: str, title: str, description: str, 
                         instructions: str, level: str, duration: int, 
                         due_date: str = None, prompt: str = None, vocab: List[str] = None, min_vocab_words: int = 0) -> str:
        """Create a new assignment"""
        assignment_id = str(uuid.uuid4())
        vocab_json = json.dumps(vocab) if vocab else None
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO assignments (id, classroom_id, title, description, instructions, 
                                       level, duration, due_date, prompt, vocab, min_vocab_words)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (assignment_id, classroom_id, title, description, instructions, 
                  level, duration, due_date, prompt, vocab_json, min_vocab_words))
            conn.commit()
        return assignment_id
    
    def update_assignment(self, assignment_id: str, title: str, description: str, 
                         instructions: str, level: str, duration: int, 
                         due_date: str = None, prompt: str = None, vocab: List[str] = None, min_vocab_words: int = None) -> bool:
        """Update an existing assignment"""
        vocab_json = json.dumps(vocab) if vocab else None
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE assignments 
                SET title = ?, description = ?, instructions = ?, 
                    level = ?, duration = ?, due_date = ?, prompt = ?, vocab = ?, min_vocab_words = ?
                WHERE id = ?
            """, (title, description, instructions, level, duration, due_date, prompt, vocab_json, min_vocab_words, assignment_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_classroom_assignments(self, classroom_id: str) -> List[Dict]:
        """Get all assignments for a classroom"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.*, 
                       COUNT(s.id) as session_count,
                       COUNT(CASE WHEN s.completed = TRUE THEN 1 END) as completion_count
                FROM assignments a
                LEFT JOIN assignment_sessions s ON a.id = s.assignment_id
                WHERE a.classroom_id = ? AND a.is_active = TRUE
                GROUP BY a.id
                ORDER BY a.created_at DESC
            """, (classroom_id,))
            results = []
            for row in cursor.fetchall():
                assignment = dict(row)
                if assignment['vocab']:
                    assignment['vocab'] = json.loads(assignment['vocab'])
                results.append(assignment)
            return results
    
    def get_assignment_by_id(self, assignment_id: str) -> Optional[Dict]:
        """Get assignment by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.*, c.name as classroom_name, c.teacher_id
                FROM assignments a
                JOIN classrooms c ON a.classroom_id = c.id
                WHERE a.id = ? AND a.is_active = TRUE
            """, (assignment_id,))
            row = cursor.fetchone()
            if row:
                assignment = dict(row)
                if assignment['vocab']:
                    assignment['vocab'] = json.loads(assignment['vocab'])
                return assignment
            return None
    
    def get_student_assignments(self, student_id: str) -> List[Dict]:
        """Get all assignments available to a student"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.*, c.name as classroom_name,
                       s.completed, s.id as session_id, s.start_time, s.end_time,
                       s.created_at as session_created_at
                FROM assignments a
                JOIN classrooms c ON a.classroom_id = c.id
                JOIN enrollments e ON c.id = e.classroom_id
                LEFT JOIN assignment_sessions s ON a.id = s.assignment_id AND s.student_id = ? AND s.is_active = TRUE
                WHERE e.student_id = ? AND e.is_active = TRUE 
                  AND c.is_active = TRUE AND a.is_active = TRUE
                ORDER BY a.created_at DESC, s.created_at DESC
            """, (student_id, student_id))
            results = []
            seen_assignments = set()
            for row in cursor.fetchall():
                assignment = dict(row)
                assignment_id = assignment['id']
                
                # Only process each assignment once
                if assignment_id in seen_assignments:
                    continue
                
                seen_assignments.add(assignment_id)
                
                # If there's no session, mark as not completed
                if not assignment['session_id']:
                    assignment['completed'] = False
                else:
                    # Only mark as completed if the session is actually completed
                    assignment['completed'] = bool(assignment['completed'])
                
                if assignment['vocab']:
                    assignment['vocab'] = json.loads(assignment['vocab'])
                results.append(assignment)
            return results
    
    # Session and analytics operations
    def create_assignment_session(self, assignment_id: str, student_id: str, 
                                start_time: str = None, end_time: str = None,
                                completed: bool = False, message_count: int = 0,
                                voice_used: bool = False, transcript_used: bool = False) -> str:
        """Create a new assignment session with full details"""
        session_id = str(uuid.uuid4())
        
        # Calculate attempt number for this student/assignment
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as attempt_count 
                FROM assignment_sessions 
                WHERE assignment_id = ? AND student_id = ? AND is_active = TRUE
            """, (assignment_id, student_id))
            attempt_count = cursor.fetchone()[0]
            attempt_number = attempt_count + 1
            
            cursor.execute("""
                INSERT INTO assignment_sessions 
                (id, assignment_id, student_id, start_time, end_time, 
                 completed, message_count, voice_used, transcript_used, created_at, attempt_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, assignment_id, student_id, start_time or datetime.now().isoformat(),
                  end_time, completed, message_count, voice_used, transcript_used,
                  datetime.now().isoformat(), attempt_number))
            conn.commit()
        
        return session_id
    
    def update_session(self, session_id: str, end_time: datetime = None, 
                      completed: bool = None, message_count: int = None,
                      voice_used: bool = None, transcript_used: bool = None) -> bool:
        """Update assignment session"""
        updates = []
        params = []
        
        if end_time is not None:
            updates.append("end_time = ?")
            params.append(end_time)
        if completed is not None:
            updates.append("completed = ?")
            params.append(completed)
        if message_count is not None:
            updates.append("message_count = ?")
            params.append(message_count)
        if voice_used is not None:
            updates.append("voice_used = ?")
            params.append(voice_used)
        if transcript_used is not None:
            updates.append("transcript_used = ?")
            params.append(transcript_used)
        
        if not updates:
            return False
        
        params.append(session_id)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE assignment_sessions SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
            return cursor.rowcount > 0
    
    def log_conversation_message(self, session_id: str, message_type: str, content: str, timestamp: str = None) -> str:
        """Log a conversation message"""
        log_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO conversation_logs (id, session_id, message_type, content, timestamp, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (log_id, session_id, message_type, content, timestamp or datetime.now().isoformat(), datetime.now().isoformat()))
            conn.commit()
        return log_id
    
    def get_classroom_analytics(self, classroom_id: str) -> Dict:
        """Get analytics for a classroom"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Basic stats
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT e.student_id) as total_students,
                    COUNT(DISTINCT a.id) as total_assignments,
                    COUNT(DISTINCT s.id) as total_sessions,
                    COUNT(CASE WHEN s.completed = TRUE THEN 1 END) as completed_sessions
                FROM classrooms c
                LEFT JOIN enrollments e ON c.id = e.classroom_id AND e.is_active = TRUE
                LEFT JOIN assignments a ON c.id = a.classroom_id AND a.is_active = TRUE
                LEFT JOIN assignment_sessions s ON a.id = s.assignment_id
                WHERE c.id = ?
            """, (classroom_id,))
            stats = cursor.fetchone()
            
            # Voice usage
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN s.voice_used = TRUE THEN 1 END) as voice_sessions,
                    COUNT(s.id) as total_sessions_with_voice
                FROM assignment_sessions s
                JOIN assignments a ON s.assignment_id = a.id
                WHERE a.classroom_id = ?
            """, (classroom_id,))
            voice_stats = cursor.fetchone()
            
            # Average completion time
            cursor.execute("""
                SELECT AVG(CASE 
                    WHEN s.completed = TRUE AND s.end_time IS NOT NULL 
                    THEN (julianday(s.end_time) - julianday(s.start_time)) * 24 * 60 
                    ELSE NULL END) as avg_completion_minutes
                FROM assignment_sessions s
                JOIN assignments a ON s.assignment_id = a.id
                WHERE a.classroom_id = ? AND s.completed = TRUE
            """, (classroom_id,))
            time_stats = cursor.fetchone()
            
            return {
                'total_students': stats[0] or 0,
                'total_assignments': stats[1] or 0,
                'total_sessions': stats[2] or 0,
                'completed_sessions': stats[3] or 0,
                'completion_rate': (stats[3] / stats[2] * 100) if stats[2] > 0 else 0,
                'voice_usage_rate': (voice_stats[0] / voice_stats[1] * 100) if voice_stats[1] > 0 else 0,
                'avg_completion_minutes': round(time_stats[0] or 0, 1)
            }
    
    def get_student_sessions(self, student_id: str, classroom_id: str = None) -> List[Dict]:
        """Get all sessions for a student, optionally filtered by classroom"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if classroom_id:
                cursor.execute("""
                    SELECT s.*, a.title as assignment_title, a.level,
                           c.name as classroom_name
                    FROM assignment_sessions s
                    JOIN assignments a ON s.assignment_id = a.id
                    JOIN classrooms c ON a.classroom_id = c.id
                    WHERE s.student_id = ? AND a.classroom_id = ? 
                      AND s.is_active = TRUE AND a.is_active = TRUE AND c.is_active = TRUE
                    ORDER BY s.submitted_for_grading DESC, s.created_at DESC, s.attempt_number DESC
                """, (student_id, classroom_id))
            else:
                cursor.execute("""
                    SELECT s.*, a.title as assignment_title, a.level,
                           c.name as classroom_name
                    FROM assignment_sessions s
                    JOIN assignments a ON s.assignment_id = a.id
                    JOIN classrooms c ON a.classroom_id = c.id
                    WHERE s.student_id = ? 
                      AND s.is_active = TRUE AND a.is_active = TRUE AND c.is_active = TRUE
                    ORDER BY s.submitted_for_grading DESC, s.created_at DESC, s.attempt_number DESC
                """, (student_id,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_students(self) -> List[Dict]:
        """Get all students"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students WHERE is_active = TRUE ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_conversation_logs_by_session(self, session_id: str) -> List[Dict]:
        """Get all conversation logs for a session"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM conversation_logs 
                WHERE session_id = ? 
                ORDER BY created_at ASC
            """, (session_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def submit_session_for_grading(self, session_id: str) -> bool:
        """Submit a session for grading (unsubmits other sessions for same assignment/student)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                # First, get the session details to find other sessions for same assignment/student
                cursor.execute("""
                    SELECT assignment_id, student_id FROM assignment_sessions 
                    WHERE id = ?
                """, (session_id,))
                session = cursor.fetchone()
                
                if not session:
                    return False
                
                assignment_id, student_id = session
                
                # Unsubmit all other sessions for this assignment/student
                cursor.execute("""
                    UPDATE assignment_sessions 
                    SET submitted_for_grading = FALSE 
                    WHERE assignment_id = ? AND student_id = ? AND id != ?
                """, (assignment_id, student_id, session_id))
                
                # Submit this session
                cursor.execute("""
                    UPDATE assignment_sessions 
                    SET submitted_for_grading = TRUE 
                    WHERE id = ?
                """, (session_id,))
                
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                print(f"Error submitting session for grading: {e}")
                return False
    
    def get_submitted_session(self, assignment_id: str, student_id: str) -> Optional[Dict]:
        """Get the session submitted for grading for a specific assignment/student"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM assignment_sessions 
                WHERE assignment_id = ? AND student_id = ? AND submitted_for_grading = TRUE
                ORDER BY created_at DESC
                LIMIT 1
            """, (assignment_id, student_id))
            
            result = cursor.fetchone()
            return dict(result) if result else None

# Global database instance
db = DatabaseManager()
