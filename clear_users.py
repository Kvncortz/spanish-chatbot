#!/usr/bin/env python3
"""
Script to clear all users from the database
"""

import sqlite3
import os

def clear_all_users():
    """Clear all users from the database"""
    db_path = "vocafow.db"
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Get counts before deletion
            cursor.execute("SELECT COUNT(*) FROM teachers")
            teacher_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM students")
            student_count = cursor.fetchone()[0]
            
            print(f"Found {teacher_count} teachers and {student_count} students")
            
            # Clear all users (this will cascade delete classrooms, assignments, etc.)
            cursor.execute("DELETE FROM teachers")
            cursor.execute("DELETE FROM students")
            
            # Reset auto-increment counters (if the table exists)
            try:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('teachers', 'students')")
            except sqlite3.OperationalError:
                # sqlite_sequence table doesn't exist, which is fine
                pass
            
            conn.commit()
            
            print("✅ All users deleted successfully!")
            print("📚 All associated classrooms, assignments, and sessions have also been removed.")
            
    except Exception as e:
        print(f"❌ Error clearing users: {e}")

if __name__ == "__main__":
    print("🗑️  Clearing all users from the database...")
    confirm = input("⚠️  This will delete ALL users and their data. Are you sure? (yes/no): ")
    
    if confirm.lower() == 'yes':
        clear_all_users()
    else:
        print("❌ Operation cancelled.")
