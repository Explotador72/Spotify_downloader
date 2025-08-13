import os
import sys
import asyncio
import logging
import time
import webbrowser
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional
import zipfile
import subprocess
import glob
import shutil
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from yt_dlp import YoutubeDL
from dotenv import load_dotenv

# Configuración
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constantes
BASE_DIR = Path(__file__).parent if '__file__' in globals() else Path.cwd()
DOWNLOADS_DIR = BASE_DIR / 'Downloads_playlists'
MAX_WORKERS = 15  # Aumentado de 10 a 15
YTDL_TIMEOUT = 20  # Reducido de 30 a 20
SERVER_PORT = 8080

# Spotify configuración
SPOTIFY_CONFIG = {
    'client_id': '382cbaacee964b1f9bafdf14ab86f549',
    'client_secret': os.getenv('CLIENT_SECRET'),
    'redirect_uri': 'https://www.google.com/?hl=es',
    'scope': 'playlist-read-private playlist-read-collaborative',
    'refresh_token': os.getenv('REFRESH_TOKEN')
}

class SystemSetup:
    """Clase para configurar dependencias del sistema"""
    
class SystemSetup:
    """Clase para configurar dependencias del sistema"""
    
    @staticmethod
    def refresh_environment_path():
        """Refresca las variables de entorno PATH sin reiniciar"""
        try:
            import winreg
            
            # Leer PATH del sistema
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as key:
                system_path = winreg.QueryValueEx(key, "PATH")[0]
            
            # Leer PATH del usuario
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                    user_path = winreg.QueryValueEx(key, "PATH")[0]
            except FileNotFoundError:
                user_path = ""
            
            # Combinar y actualizar PATH actual
            new_path = f"{user_path};{system_path}" if user_path else system_path
            os.environ['PATH'] = new_path
            
            logger.info("🔄 Variables de entorno actualizadas")
            return True
            
        except Exception as e:
            logger.debug(f"Error refrescando PATH: {e}")
            return False
    
    @staticmethod
    def verify_ffmpeg_with_retry(max_retries=3, delay=2) -> bool:
        """Verifica FFmpeg con reintentos y refresco de PATH"""
        for attempt in range(max_retries):
            try:
                result = subprocess.run(['ffmpeg', '-version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=10)
                if result.returncode == 0:
                    logger.info(f"✅ FFmpeg verificado (intento {attempt + 1})")
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            if attempt < max_retries - 1:
                logger.info(f"🔄 Refrescando PATH... (intento {attempt + 1})")
                SystemSetup.refresh_environment_path()
                time.sleep(delay)
        
        return False
    
    @staticmethod
    def check_and_install_ffmpeg() -> bool:
        """Verifica e instala FFmpeg si no está disponible"""
        logger.info("🔍 Verificando FFmpeg...")
        
        # Verificación inicial
        if SystemSetup.verify_ffmpeg_with_retry(max_retries=1):
            logger.info("✅ FFmpeg ya está instalado")
            return True
        
        logger.warning("⚠️ FFmpeg no encontrado. Intentando instalar...")
        
        # Intentar instalar con diferentes métodos
        install_methods = [
            # Winget - con flags para aceptar automáticamente
            (['winget', 'install', 'FFmpeg', '--accept-source-agreements', '--accept-package-agreements', '--silent'], "Winget"),
            # Scoop
            (['scoop', 'install', 'ffmpeg'], "Scoop"),
            # Chocolatey
            (['choco', 'install', 'ffmpeg', '-y'], "Chocolatey"),
        ]
        
        for command, method in install_methods:
            try:
                logger.info(f"📦 Intentando instalar con {method}...")
                result = subprocess.run(command, 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=300)
                
                if result.returncode == 0:
                    logger.info(f"✅ Instalación completada con {method}")
                    
                    # Verificar instalación con reintentos y refresco de PATH
                    logger.info("🔍 Verificando instalación...")
                    if SystemSetup.verify_ffmpeg_with_retry():
                        logger.info(f"✅ FFmpeg instalado y verificado exitosamente con {method}")
                        return True
                    else:
                        logger.warning(f"⚠️ {method} reportó éxito pero FFmpeg no es accesible")
                        continue
                        
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.debug(f"Falló instalación con {method}: {e}")
                continue
        
        # Instrucciones manuales si todo falla
        logger.error("""
❌ No se pudo instalar FFmpeg automáticamente.
📝 Instala manualmente:

1. Chocolatey: choco install ffmpeg -y
2. Winget: winget install FFmpeg --accept-source-agreements --accept-package-agreements --silent
3. Manual: https://ffmpeg.org/download.html

⚠️ El programa continuará pero la normalización de audio estará deshabilitada.
Reinicia la terminal después de la instalación manual.
        """)
        return False
    
    @staticmethod
    def update_ytdlp() -> bool:
        """Actualiza yt-dlp a la última versión"""
        logger.info("🔄 Verificando actualizaciones de yt-dlp...")
        
        try:
            # Intentar actualizar con pip primero
            result = subprocess.run([
                sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'
            ], capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0:
                logger.info("✅ yt-dlp actualizado exitosamente con pip")
                return True
            else:
                logger.debug(f"Falló actualización con pip: {result.stderr}")
                
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"Error actualizando con pip: {e}")
        
        # Intentar con yt-dlp -U si pip falla
        try:
            result = subprocess.run(['yt-dlp', '-U'], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=120)
            
            if result.returncode == 0:
                logger.info("✅ yt-dlp actualizado exitosamente")
                return True
            else:
                logger.debug(f"Falló yt-dlp -U: {result.stderr}")
                
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug(f"Error con yt-dlp -U: {e}")
        
        logger.warning("⚠️ No se pudo actualizar yt-dlp, continuando con versión actual")
        return False

class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Servidor HTTP personalizado para servir archivos"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOWNLOADS_DIR), **kwargs)
    
    def log_message(self, format, *args):
        """Silencia logs del servidor"""
        pass
    
    def end_headers(self):
        """Añade headers para descarga"""
        self.send_header('Content-Disposition', 'attachment')
        super().end_headers()

class FileServer:
    """Servidor web simple para servir archivos"""
    
    def __init__(self, port: int = SERVER_PORT):
        self.port = port
        self.server = None
        self.thread = None
    
    def start(self):
        """Inicia el servidor en un hilo separado"""
        try:
            self.server = HTTPServer(('localhost', self.port), CustomHTTPRequestHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logger.info(f"Servidor iniciado en http://localhost:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Error iniciando servidor: {e}")
            return False
    
    def stop(self):
        """Detiene el servidor"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("Servidor detenido")

class SpotifyDownloader:
    def __init__(self):
        logger.info("🚀 Iniciando Spotify Downloader...")
        
        # Configurar dependencias del sistema
        self._setup_system()
        
        # Inicializar Spotify
        self.sp = self._init_spotify()
        DOWNLOADS_DIR.mkdir(exist_ok=True)
        
        logger.info("✅ Spotify Downloader listo")
    
    def _setup_system(self):
        """Configura las dependencias del sistema"""
        # Actualizar yt-dlp
        SystemSetup.update_ytdlp()
        
        # Verificar/instalar FFmpeg
        self.ffmpeg_available = SystemSetup.check_and_install_ffmpeg()
        
        if not self.ffmpeg_available:
            logger.warning("🔇 Normalización de audio deshabilitada (FFmpeg no disponible)")
            os.environ['NORMALIZE_AUDIO'] = 'false'
    
    def _init_spotify(self) -> spotipy.Spotify:
        """Inicializa cliente de Spotify"""
        auth_manager = SpotifyOAuth(**{k: v for k, v in SPOTIFY_CONFIG.items() if k != 'refresh_token'})
        token_info = auth_manager.refresh_access_token(SPOTIFY_CONFIG['refresh_token'])
        return spotipy.Spotify(auth=token_info['access_token'])
    
    @staticmethod
    def normalize_filename(text: str) -> str:
        """Normaliza nombres de archivo"""
        return text.translate(str.maketrans('\\/.:*?"<>|', '__________')).strip()
    
    def _get_youtube_url(self, track_name: str, artist_name: str, duration: int) -> Optional[str]:
        """Busca la mejor coincidencia en YouTube"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'socket_timeout': 15,  # Reducido de 30 a 15
            'retries': 1  # Solo 1 reintento
        }
        
        try:
            with YoutubeDL(ydl_opts) as ydl:
                # Búsqueda más específica y rápida
                query = f"{track_name} {artist_name}"[:60]  # Limitar longitud
                results = ydl.extract_info(f"ytsearch2:{query}", download=False)  # Solo 2 en lugar de 3
                entries = results.get('entries', [])
                
                if not entries:
                    return None
                
                # Tomar el primer resultado si no hay duración, sino el mejor match
                if not duration or duration == 0:
                    return entries[0].get('url')
                
                best_match = min(entries, key=lambda x: abs(x.get('duration', 0) - duration))
                return best_match.get('url')
        except Exception as e:
            logger.error(f"Error buscando {track_name}: {e}")
            return None
    
    def _download_track(self, url: str, output_path: Path, final_filename: str) -> Optional[Path]:
        """Descarga y procesa una pista"""
        temp_filename = f"temp_{hash(url) % 10000}"
        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",  # Preferir m4a es más rápido
            "outtmpl": str(output_path / f"{temp_filename}.%(ext)s"),
            "ignoreerrors": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",  # Reducido de 320 a 192 para velocidad
            }],
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': YTDL_TIMEOUT,
            'retries': 1,  # Solo 1 reintento en lugar de los por defecto
        }
        
        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Buscar el archivo descargado y renombrarlo
            downloaded_files = list(output_path.glob(f"{temp_filename}*.mp3"))
            if downloaded_files:
                temp_file = downloaded_files[0]
                final_path = output_path / f"{final_filename}.mp3"
                
                # Reducido el tiempo de espera
                time.sleep(0.5)
                
                # Solo 2 intentos en lugar de 3
                for attempt in range(2):
                    try:
                        temp_file.rename(final_path)
                        return final_path
                    except OSError:
                        time.sleep(1)
                        continue
                
            return None
        except Exception as e:
            logger.error(f"Error descargando {url}: {e}")
            return None
    
    def _normalize_audio(self, file_path: Path) -> bool:
        """Normaliza audio usando FFmpeg - OPCIONAL para velocidad"""
        # Verificar si FFmpeg está disponible
        if not hasattr(self, 'ffmpeg_available') or not self.ffmpeg_available:
            logger.debug(f"FFmpeg no disponible, saltando normalización: {file_path.name}")
            return True
            
        # Hacer normalización opcional para mayor velocidad
        normalize_enabled = os.getenv('NORMALIZE_AUDIO', 'true').lower() == 'true'
        
        if not normalize_enabled:
            logger.debug(f"Normalización saltada para velocidad: {file_path.name}")
            return True
            
        if not file_path.exists():
            return False
            
        try:
            temp_path = file_path.with_name(f"norm_{file_path.name}")
            # Comando más simple y rápido
            cmd = [
                "ffmpeg", "-loglevel", "quiet", "-y", "-i", str(file_path),
                "-ar", "44100", "-b:a", "192k", str(temp_path)  # Sin loudnorm para velocidad
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=60)  # Reducido timeout
            
            if result.returncode == 0 and temp_path.exists():
                time.sleep(1)  # Reducido
                
                for attempt in range(3):  # Reducido de 5 a 3
                    try:
                        file_path.unlink()
                        temp_path.rename(file_path)
                        logger.debug(f"Audio normalizado: {file_path.name}")
                        return True
                    except OSError as e:
                        if attempt < 2:
                            time.sleep(1)  # Reducido
                            continue
                        else:
                            logger.error(f"No se pudo reemplazar archivo: {e}")
                            if temp_path.exists():
                                temp_path.unlink()
                            return False
            else:
                if temp_path.exists():
                    temp_path.unlink()
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout normalizando {file_path.name}")
            return False
        except Exception as e:
            logger.error(f"Error normalizando {file_path}: {e}")
            return False
    
    def _process_track(self, track: Dict, playlist_path: Path) -> None:
        """Procesa una pista individual"""
        track_name = self.normalize_filename(track["name"])
        artists = ", ".join([a["name"] for a in track["artists"]])
        artist_name = self.normalize_filename(artists)
        final_filename = f"{artist_name} - {track_name}"
        filename_pattern = f"*{track_name}*.mp3"
        
        # Verificar si ya existe
        if list(playlist_path.glob(filename_pattern)):
            logger.debug(f"Ya existe: {track_name}")  # Cambiado a debug para menos spam
            return
        
        # Buscar en YouTube
        duration = track['duration_ms'] // 1000
        youtube_url = self._get_youtube_url(track_name, artist_name, duration)
        
        if not youtube_url:
            logger.warning(f"No encontrado: {track_name} - {artist_name}")
            return
        
        logger.info(f"⬇️ {track_name} - {artist_name}")  # Mensaje más corto
        
        # Descargar
        downloaded_file = self._download_track(youtube_url, playlist_path, final_filename)
        
        if downloaded_file and downloaded_file.exists():
            # Normalizar audio solo si está habilitado
            success = self._normalize_audio(downloaded_file)
            if success:
                logger.debug(f"✅ Completado: {track_name}")
        else:
            logger.error(f"❌ Falló: {track_name} - {artist_name}")
    
    def _get_all_tracks(self, playlist_id: str) -> List[Dict]:
        """Obtiene todas las pistas de una playlist"""
        tracks = []
        offset = 0
        limit = 100
        
        while True:
            results = self.sp.playlist_items(playlist_id, limit=limit, offset=offset)
            tracks.extend([item['track'] for item in results['items'] if item['track']])
            
            if not results['next']:
                break
            offset += limit
        
        return tracks
    
    def _create_zip(self, playlist_path: Path, zip_path: Path) -> None:
        """Crea archivo ZIP con las pistas descargadas"""
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in playlist_path.glob("*.mp3"):
                    zipf.write(file_path, file_path.name)
            
            shutil.rmtree(playlist_path)
            logger.info(f"ZIP creado: {zip_path}")
        except Exception as e:
            logger.error(f"Error creando ZIP: {e}")
    
    async def download_playlist(self, playlist_url: str) -> Optional[Path]:
        """Descarga una playlist completa"""
        try:
            playlist_id = playlist_url.split("/")[-1].split("?")[0]
            playlist = self.sp.playlist(playlist_id)
            playlist_name = self.normalize_filename(playlist['name'])
            
            playlist_path = DOWNLOADS_DIR / playlist_name
            playlist_path.mkdir(exist_ok=True)
            
            logger.info(f"Procesando playlist: {playlist_name}")
            
            tracks = self._get_all_tracks(playlist_id)
            logger.info(f"Total de pistas: {len(tracks)}")
            
            # Descargar en paralelo
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = [
                    executor.submit(self._process_track, track, playlist_path)
                    for track in tracks
                ]
                
                # Esperar a que terminen todas
                for future in futures:
                    future.result()
            
            # Crear ZIP
            zip_path = DOWNLOADS_DIR / f"{playlist_name}.zip"
            self._create_zip(playlist_path, zip_path)
            
            return zip_path
            
        except Exception as e:
            logger.error(f"Error procesando playlist: {e}")
            return None

async def main():
    """Función principal"""
    downloader = SpotifyDownloader()
    server = FileServer()
    
    url = input('URL de la playlist de Spotify: ').strip()
    if not url:
        logger.error("URL requerida")
        return
    
    logger.info("Iniciando descarga...")
    zip_file = await downloader.download_playlist(url)
    
    if zip_file:
        logger.info(f"Descarga completada: {zip_file}")
        
        # Iniciar servidor
        if server.start():
            file_url = f"http://localhost:{SERVER_PORT}/zip"
            logger.info(f"✅ Archivo disponible en: {file_url}")
            
            try:
                print(f"\n📁 Servidor activo en: http://localhost:{SERVER_PORT}")
                print(f"🔗 Descarga directa: {file_url}")
                print("📝 Presiona Ctrl+C para detener el servidor y salir\n")
                
                # Mantener servidor activo
                while True:
                    await asyncio.sleep(1)
                    
            except KeyboardInterrupt:
                logger.info("\nDeteniendo servidor...")
                server.stop()
                logger.info("¡Adiós!")
        else:
            logger.error("No se pudo iniciar el servidor web")
            logger.info(f"Archivo guardado localmente: {zip_file}")
    else:
        logger.error("Error en la descarga")

if __name__ == "__main__":
    asyncio.run(main())