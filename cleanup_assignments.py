#!/usr/bin/env python3
"""
Script to clean up inactive assignments that are still in the database
"""

import sqlite3
import os

def cleanup_inactive_assignments():
    """Hard delete assignments that are marked as inactive or don't belong to any classroom"""
    db_path = "vocafow.db"
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # First, let's see all assignments
            cursor.execute("""
                SELECT a.id, a.title, a.is_active, c.name as classroom_name, c.id as classroom_id
                FROM assignments a
                LEFT JOIN classrooms c ON a.classroom_id = c.id
                ORDER BY a.created_at DESC
            """)
            all_assignments = cursor.fetchall()
            
            print(f"Found {len(all_assignments)} total assignments:")
            for i, (id, title, is_active, classroom_name, classroom_id) in enumerate(all_assignments, 1):
                status = "ACTIVE" if is_active == 1 else "INACTIVE"
                classroom = classroom_name or "NO CLASSROOM"
                print(f"  {i}. {title} - {status} - Classroom: {classroom}")
            
            # Find assignments to delete (inactive ones or ones with no classroom)
            to_delete = []
            for id, title, is_active, classroom_name, classroom_id in all_assignments:
                if is_active == 0 or not classroom_id or not classroom_name:
                    to_delete.append((id, title, is_active, classroom_name or "None"))
            
            if not to_delete:
                print("\n✅ No inactive or orphaned assignments found!")
                return
            
            print(f"\n🗑️  Found {len(to_delete)} assignments to delete:")
            for i, (id, title, is_active, classroom) in enumerate(to_delete, 1):
                reason = "INACTIVE" if is_active == 0 else "NO CLASSROOM"
                print(f"  {i}. {title} - {reason}")
            
            confirm = input(f"\n⚠️  Delete these {len(to_delete)} assignments permanently? (yes/no): ")
            
            if confirm.lower() == 'yes':
                # Hard delete the assignments and all related data
                for assignment_id, title, _, _ in to_delete:
                    print(f"Deleting: {title}")
                    
                    # Delete assignment sessions
                    cursor.execute("DELETE FROM assignment_sessions WHERE assignment_id = ?", (assignment_id,))
                    
                    # Delete the assignment
                    cursor.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
                
                conn.commit()
                print(f"\n✅ Successfully deleted {len(to_delete)} assignments!")
                print("📚 All related sessions have also been removed.")
                
                # Show remaining assignments
                cursor.execute("SELECT COUNT(*) FROM assignments")
                remaining = cursor.fetchone()[0]
                print(f"📊 Remaining assignments: {remaining}")
                
            else:
                print("❌ Operation cancelled.")
                
    except Exception as e:
        print(f"❌ Error cleaning up assignments: {e}")

if __name__ == "__main__":
    print("🧹 Cleaning up inactive assignments...")
    cleanup_inactive_assignments()
