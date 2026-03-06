# AI Transcriber App

A powerful, premium-looking local transcription application powered by OpenAI's Whisper model. It features a modern, responsive web interface, local background persistence with SQLite, and fully supports HTTPS for network and Tailscale access.

## Key Features

- **Premium Interface:** Modern glassmorphism design with a seamless dark/light mode toggle and micro-animations.
- **Live Microphone Support:** Record audio directly from your browser, securely over HTTPS.
- **Robust Transcription:** Powered by Whisper with parameter tuning (language selection, initial contextual prompts) to significantly reduce hallucinations and improve accuracy.
- **Multiple Export Formats:** Instant downloads for plain text (TXT), JSON, and SRT subtitle files.
- **Local Persistence:** All history is automatically saved to a local SQLite database (`transcriber.db`) so you can resume sessions or download past exports anytime.
- **Network Ready:** Automatically opens the necessary Windows firewall rule and binds to all interfaces, making it immediately accessible from your Tailscale VPN, local Wi-Fi, and localhost.

## Installation

1. Clone the repository:
```bash
git clone https://github.com/Big-whiz/scribe-local.git
cd transcriber_app
```

2. Create a virtual environment (optional but recommended):
```bash
python -m venv venv
venv\Scripts\activate
```

3. Install the required Python dependencies:
```bash
pip install -r requirements.txt
```

4. Install FFmpeg
Make sure you have [FFmpeg](https://ffmpeg.org/) installed on your system and added to your system PATH. This is required for Whisper to process audio files.

## Running the App

To start the server, simply run:
```bash
python run_server.py
```

Upon launching:
- A local database (`transcriber.db`) will automatically be created in the application directory.
- A secure self-signed SSL certificate (`cert.pem`, `key.pem`) will be generated at runtime.
- You may be prompted by Windows UAC to allow Python to automatically open **Port 5000** in your network firewall.
- Watch the console output for the specific URL to use on your local machine or Tailscale VPN.

## Security Notice

When you access the app via HTTPS on your local network or Tailscale, your browser will warn you that the connection is "Not Private" or "Unsafe". This is completely expected because the server is using a self-signed certificate rather than a domain-verified one. You can safely click **Advanced** -> **Proceed to [IP] (unsafe)** to use the app and record from your microphone safely.
