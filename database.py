import sqlite3
import os
from datetime import datetime

DB_PATH = 'transcriber.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Jobs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            filename TEXT,
            custom_name TEXT,
            status TEXT,
            progress INTEGER DEFAULT 0,
            message TEXT,
            result_text TEXT,
            download_url TEXT,
            language TEXT,
            initial_prompt TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Jobs table columns check (Migration)
    columns = [row[1] for row in cursor.execute('PRAGMA table_info(jobs)').fetchall()]
    if 'language' not in columns:
        cursor.execute('ALTER TABLE jobs ADD COLUMN language TEXT')
    if 'initial_prompt' not in columns:
        cursor.execute('ALTER TABLE jobs ADD COLUMN initial_prompt TEXT')

    conn.commit()
    conn.close()

def create_job(job_id, filename, custom_name, language=None, initial_prompt=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO jobs (id, filename, custom_name, status, message, language, initial_prompt) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (job_id, filename, custom_name, 'queued', 'Queued...', language, initial_prompt)
    )
    conn.commit()
    conn.close()

def update_job(job_id, status=None, progress=None, message=None, result_text=None, download_url=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if status:
        updates.append('status = ?')
        params.append(status)
    if progress is not None:
        updates.append('progress = ?')
        params.append(progress)
    if message:
        updates.append('message = ?')
        params.append(message)
    if result_text:
        updates.append('result_text = ?')
        params.append(result_text)
    if download_url:
        updates.append('download_url = ?')
        params.append(download_url)
    
    if updates:
        updates.append('updated_at = CURRENT_TIMESTAMP')
        query = f'UPDATE jobs SET {", ".join(updates)} WHERE id = ?'
        params.append(job_id)
        cursor.execute(query, params)
        conn.commit()
    
    conn.close()

def get_job(job_id):
    conn = get_db_connection()
    job = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    return dict(job) if job else None

def get_recent_jobs(limit=10):
    conn = get_db_connection()
    jobs = conn.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
    conn.close()
    return [dict(job) for job in jobs]

if __name__ == '__main__':
    init_db()
    print("Database initialized.")
