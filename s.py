import os, spotipy, requests, threading, subprocess, asyncio
from flask import Flask, send_file, make_response, request
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

IS_RENDER = os.getenv("RENDER") == "true"
BASE_DIR = os.path.abspath(os.path.dirname(__file__)) if '__file__' in globals() else os.getcwd()
path_downloads = os.path.join(BASE_DIR, 'Downloads_playlists/')

# Spotify credentials
CLIENT_ID = '382cbaacee964b1f9bafdf14ab86f549'
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = 'https://www.google.com/?hl=es'
SCOPE = 'playlist-read-private playlist-read-collaborative'
REFRESH_TOKEN = os.getenv('REFRESH_TOKEN')

auth_manager = SpotifyOAuth(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, scope=SCOPE)
token_info = auth_manager.refresh_access_token(REFRESH_TOKEN)
access_token = token_info['access_token']
sp = spotipy.Spotify(auth=access_token)


async def upload_file(file_path):
    app = Flask(__name__)
    port = 5000
    result = {
        'public_url': None, 'download_event': asyncio.Event(), 'shutdown_event': asyncio.Event()
    }

    @app.route('/download')
    def download_file():
        response = make_response(send_file(file_path, as_attachment=True))
        response.headers["ngrok-skip-browser-warning"] = "true"
        return response

    def run_server():
        app.run(port=port, host="0.0.0.0")

    async def start_ngrok():
        if IS_RENDER:
            result['public_url'] = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:5000")
            print(result['public_url'])
        else:
            ngrok_process = subprocess.Popen(["ngrok", "http", str(port)],
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE)
            await asyncio.sleep(2)
            try:
                tunnels = requests.get("http://localhost:4040/api/tunnels").json()
                result['public_url'] = tunnels["tunnels"][0]["public_url"]
            except Exception as e:
                print("ngrok error:", e)
                return

        print(f"🔗 URL: {result['public_url']}/download")
        await asyncio.wait_for(result['shutdown_event'].wait(), timeout=7200)

    flask_thread = threading.Thread(target=run_server, daemon=True)
    flask_thread.start()

    await start_ngrok()
    os.remove(file_path)
    return


async def set_up():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(BASE_DIR, "s.py")
    await upload_file(file_path)

asyncio.run(set_up())
