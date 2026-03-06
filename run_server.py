import os
import shutil
import threading
import time
import uuid
import json
from flask import Flask, render_template, request, jsonify, send_from_directory
import whisper
import torch
import ffmpeg
from werkzeug.utils import secure_filename
import database
import socket
import platform
import subprocess
import ctypes

# --- CHANGE 1: Point to 'templates' (plural) to match your folder ---
app = Flask(__name__, static_folder='static', template_folder='templates')

app.config['UPLOAD_FOLDER'] = 'temp_audio'
app.config['OUTPUT_FOLDER'] = 'transcriptions'

# --- CHANGE 2: Linux compatible backup path (Windows 'G:' drive won't work here) ---
# This will create a folder in your home directory for backups
app.config['DRIVE_FOLDER'] = os.path.expanduser("~/transcriptions_backup")

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
os.makedirs(app.config['DRIVE_FOLDER'], exist_ok=True)

# Initialize Database
database.init_db()

# Global jobs dict (sync with DB)
jobs = {}

print("Loading model...")
device = "cuda" if torch.cuda.is_available() else "cpu"

# --- CHANGE 3: Load the 'small' model from your local 'Model' folder ---
# download_root="./Model" tells Whisper to look in your folder first.
# We force "small" because "medium/large" will crash your 2GB GPU.
try:
    model = whisper.load_model("small", device=device, download_root="./Model")
    print(f"Model loaded on {device}")
except Exception as e:
    print(f"Error loading model from ./Model: {e}")
    print("Attempting to download/load default small model...")
    model = whisper.load_model("small", device=device)

@app.route('/')
def index():
    return render_template('index.html')

def transcribe_worker(job_id, file_path, custom_name=None, trim_start=None, trim_end=None, delete_original=True, model_name="small", language=None, initial_prompt=None):
    """Background worker with cancellation checks."""
    try:
        if jobs[job_id]['status'] == 'cancelled': return

        database.update_job(job_id, status='processing', progress=10, message="Preprocessing Audio...")
        jobs[job_id]['message'] = "Preprocessing Audio..."
        jobs[job_id]['progress'] = 10

        file_to_process = file_path
        
        # 1. Trim if necessary
        if trim_start is not None and trim_end is not None:
            if jobs[job_id]['status'] == 'cancelled': return
            
            database.update_job(job_id, progress=20, message=f"Trimming audio ({trim_start}s to {trim_end}s)...")
            jobs[job_id]['message'] = f"Trimming audio ({trim_start}s to {trim_end}s)..."
            jobs[job_id]['progress'] = 20
            
            try:
                base, ext = os.path.splitext(file_path)
                trimmed_path = f"{base}_trimmed_{uuid.uuid4().hex}{ext}"
                
                (
                    ffmpeg
                    .input(file_path)
                    .audio
                    .filter('atrim', start=float(trim_start), end=float(trim_end))
                    .output(trimmed_path)
                    .run(overwrite_output=True, quiet=True)
                )
                file_to_process = trimmed_path
            except Exception as e:
                print(f"Trim error: {e}")

        if jobs[job_id]['status'] == 'cancelled':
            if file_to_process != file_path and os.path.exists(file_to_process):
                os.remove(file_to_process)
            return

        # 2. Transcribe
        database.update_job(job_id, progress=40, message="Transcribing (this may take a moment)...")
        jobs[job_id]['message'] = "Transcribing (this may take a moment)..."
        jobs[job_id]['progress'] = 40
        
        # Robustness params
        language = jobs[job_id].get('language') or None
        initial_prompt = jobs[job_id].get('initial_prompt') or None

        # transcribe with params
        result = model.transcribe(
            file_to_process, 
            fp16=(device=="cuda"),
            language=language,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False # Prevents weird repeating loops
        )
        transcript = result["text"]
        
        if jobs[job_id]['status'] == 'cancelled':
            if file_to_process != file_path and os.path.exists(file_to_process):
                os.remove(file_to_process)
            return

        database.update_job(job_id, progress=90, message="Saving files...")
        jobs[job_id]['progress'] = 90
        jobs[job_id]['message'] = "Saving files..."

        # 3. Save Files
        original_name = os.path.basename(file_path)
        if custom_name and custom_name.strip():
            safe_name = secure_filename(custom_name.strip())
            if not safe_name: safe_name = "transcription"
            txt_filename = f"{safe_name}.txt"
        else:
            txt_filename = f"{os.path.splitext(original_name)[0]}.txt"

        local_path = os.path.join(app.config['OUTPUT_FOLDER'], txt_filename)
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(transcript)

        # Copy to Backup Folder
        if os.path.exists(app.config['DRIVE_FOLDER']):
            try:
                drive_path = os.path.join(app.config['DRIVE_FOLDER'], txt_filename)
                shutil.copy2(local_path, drive_path)
            except Exception as e:
                print(f"Backup failed: {e}")

        # Cleanup
        if delete_original and os.path.exists(file_path):
            os.remove(file_path)
        if file_to_process != file_path and os.path.exists(file_to_process):
            os.remove(file_to_process)

        download_url = f"/download_transcription/{txt_filename}"
        database.update_job(job_id, status='completed', progress=100, result_text=transcript, download_url=download_url)
        
        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['progress'] = 100
        jobs[job_id]['result'] = {
            'transcript': transcript,
            'download_url': download_url
        }

    except Exception as e:
        if jobs[job_id]['status'] != 'cancelled':
            database.update_job(job_id, status='failed', message=str(e))
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['message'] = str(e)
            print(f"Job {job_id} failed: {e}")

    except Exception as e:
        if jobs[job_id]['status'] != 'cancelled':
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['message'] = str(e)
            print(f"Job {job_id} failed: {e}")

@app.route('/start_upload_job', methods=['POST'])
def start_upload_job():
    if 'audio_file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['audio_file']
    custom_name = request.form.get('custom_filename')
    start_time = request.form.get('startTime')
    end_time = request.form.get('endTime')
    language = request.form.get('language')
    initial_prompt = request.form.get('initial_prompt')

    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    job_id = uuid.uuid4().hex
    jobs[job_id] = {
        'status': 'queued', 
        'progress': 0, 
        'message': 'Queued...',
        'language': language,
        'initial_prompt': initial_prompt
    }
    database.create_job(job_id, file.filename, custom_name, language=language, initial_prompt=initial_prompt)

    thread = threading.Thread(
        target=transcribe_worker, 
        kwargs={
            'job_id': job_id,
            'file_path': save_path,
            'custom_name': custom_name,
            'trim_start': start_time,
            'trim_end': end_time,
            'delete_original': True,
            'language': language,
            'initial_prompt': initial_prompt
        }
    )
    thread.start()

    return jsonify({'job_id': job_id})

@app.route('/start_mic_job', methods=['POST'])
def start_mic_job():
    if 'audio_blob' not in request.files:
        return jsonify({'error': 'No audio data'}), 400

    audio_blob = request.files['audio_blob']
    filename = f"mic_{uuid.uuid4().hex}.webm"
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    audio_blob.save(save_path)

    job_id = uuid.uuid4().hex
    custom_name = request.form.get('custom_name') or "Microphone Recording"
    jobs[job_id] = {'status': 'queued', 'progress': 0, 'message': 'Queued...'}
    database.create_job(job_id, filename, custom_name)
    
    thread = threading.Thread(
        target=transcribe_worker, 
        kwargs={
            'job_id': job_id,
            'file_path': save_path,
            'custom_name': custom_name,
            'delete_original': True
        }
    )
    thread.start()

    return jsonify({'job_id': job_id})

@app.route('/cancel_job/<job_id>', methods=['POST'])
def cancel_job(job_id):
    if job_id in jobs:
        jobs[job_id]['status'] = 'cancelled'
        database.update_job(job_id, status='cancelled')
        return jsonify({'status': 'cancelled'})
    return jsonify({'error': 'Job not found'}), 404

@app.route('/history')
def get_history():
    recent_jobs = database.get_recent_jobs(20)
    return jsonify(recent_jobs)

@app.route('/job_status/<job_id>')
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

def format_timestamp(seconds):
    td = time.gmtime(seconds)
    return time.strftime("%H:%M:%S,000", td)

def generate_srt(text):
    # This is a simplified SRT generator as Whisper 'small' 
    # doesn't provide word-level timestamps by default in this setup
    # but we can structure the text into blocks.
    lines = text.split('. ')
    srt_content = ""
    for i, line in enumerate(lines):
        if not line.strip(): continue
        start = i * 5
        end = (i + 1) * 5
        srt_content += f"{i+1}\n{format_timestamp(start)} --> {format_timestamp(end)}\n{line.strip()}\n\n"
    return srt_content

@app.route('/download_export/<job_id>/<format>')
def download_export(job_id, format):
    job = database.get_job(job_id)
    if not job or not job['result_text']:
        return "Not found", 404
    
    content = job['result_text']
    filename = f"{job['custom_name'] or 'transcription'}.{format}"
    
    if format == 'srt':
        content = generate_srt(content)
    elif format == 'json':
        content = json.dumps({"text": content, "job_id": job_id}, indent=2)
    
    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/download_transcription/<filename>')
def download_transcription(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)

def expose_port(port):
    """Automatically adds a Windows Firewall rule to allow incoming traffic on this port."""
    if platform.system() == "Windows":
        rule_name = f"Flask Port {port}"
        check_cmd = ['netsh', 'advfirewall', 'firewall', 'show', 'rule', f'name={rule_name}']
        result = subprocess.run(check_cmd, capture_output=True)
        if result.returncode != 0:
            print(f"[*] Firewall rule '{rule_name}' not found. Prompting for Admin access to add it...")
            args = f"advfirewall firewall add rule name=\"{rule_name}\" dir=in action=allow protocol=TCP localport={port}"
            try:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", "netsh", args, None, 0)
                print("[*] Firewall rule added.")
            except Exception as e:
                print(f"[!] Failed to add firewall rule: {e}")

if __name__ == '__main__':
    port = 5000
    expose_port(port)
    
    use_https = False
    ssl_args = {}
    if os.path.exists('cert.pem') and os.path.exists('key.pem'):
        use_https = True
        ssl_args = {'ssl_context': ('cert.pem', 'key.pem')}
    else:
        try:
            import OpenSSL
            use_https = True
            ssl_args = {'ssl_context': 'adhoc'}
        except ImportError:
            pass

    protocol = "https" if use_https else "http"

    print("\n" + "="*50)
    print("Transcriber App is Available On:")
    print("="*50)
    print(f"   Local: {protocol}://127.0.0.1:{port}")
    try:
        hostname = socket.gethostname()
        ips = socket.gethostbyname_ex(hostname)[2]
        for ip in ips:
            if ip != "127.0.0.1":
                print(f"   Network: {protocol}://{ip}:{port}")
    except Exception as e:
        pass
    print("="*50 + "\n")

    if not use_https:
        print("[!] Warning: Running on HTTP. Microphone access may be blocked on non-localhost IPs.")
        print("[!] To enable HTTPS, run: pip install pyopenssl cryptography")

    # Host 0.0.0.0 is critical for network/Tailscale access
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=port, **ssl_args)