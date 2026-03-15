import requests
import time
import re
import socket
import threading
import os
import sys
from unittest.mock import MagicMock

# Mock tkinter and ImageTk to prevent ImportError in headless environment
try:
    import tkinter
except ImportError:
    mock_tk = MagicMock()
    sys.modules["tkinter"] = mock_tk
    sys.modules["_tkinter"] = mock_tk

try:
    from PIL import ImageTk
except ImportError:
    sys.modules["PIL.ImageTk"] = MagicMock()

from pixoo import Pixoo

# Robustness hack for Pixoo library
def pixoo_post(url, payload, timeout=2):
    import requests
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        if response.status_code == 200:
            try:
                data = response.json()
                # Check for the specific error structure reported by the user
                if 'errors' in data:
                    return {"error_code": -1, "details": data}
                return data
            except Exception:
                return {"error_code": 0}
        return {"error_code": -1, "status": response.status_code}
    except Exception as e:
        raise e

def robust_get_all_device_configurations(self):
    try:
        return pixoo_post(self._Pixoo__url, {'Command': 'Channel/GetAllConf'})
    except Exception:
        return {"error_code": 0}

def robust_load_counter(self):
    try:
        data = pixoo_post(self._Pixoo__url, {'Command': 'Draw/GetHttpGifId'})
        if data.get('error_code') == 0 and 'PicId' in data:
            self._Pixoo__counter = int(data['PicId'])
            return
    except Exception:
        pass
    self._Pixoo__counter = 1

def robust_send_buffer(self):
    import base64
    self._Pixoo__counter = self._Pixoo__counter + 1
    if self.refresh_connection_automatically and self._Pixoo__counter >= self._Pixoo__refresh_counter_limit:
        self._Pixoo__reset_counter()
        self._Pixoo__counter = 1

    if self.simulated:
        self._Pixoo__simulator.display(self._Pixoo__buffer, self._Pixoo__counter)
        self._Pixoo__buffers_send = self._Pixoo__buffers_send + 1
        return

    try:
        if self._Pixoo__buffers_send == 0:
            print(f"Sende ersten Buffer an {self._Pixoo__url}...", flush=True)
        payload = {
            'Command': 'Draw/SendHttpGif',
            'PicNum': 1,
            'PicWidth': self.size,
            'PicOffset': 0,
            'PicID': self._Pixoo__counter,
            'PicSpeed': 1000,
            'PicData': str(base64.b64encode(bytearray(self._Pixoo__buffer)).decode())
        }
        res_json = pixoo_post(self._Pixoo__url, payload)
        if res_json.get("error_code") != 0:
            print(f"Pixoo Error: {res_json}", flush=True)
        self._Pixoo__buffers_send = self._Pixoo__buffers_send + 1
    except Exception as e:
        print(f"Pixoo Push Fehler: {e}", flush=True)

def robust_reset_counter(self):
    if self.simulated: return
    try:
        res = pixoo_post(self._Pixoo__url, {'Command': 'Draw/ResetHttpGifId'})
        if res.get("error_code") != 0:
            print(f"Pixoo Reset Error: {res}", flush=True)
    except Exception as e:
        print(f"Pixoo Reset Fehler: {e}", flush=True)

def robust_set_channel(self, channel):
    if self.simulated: return
    try:
        pixoo_post(self._Pixoo__url, {
            'Command': 'Channel/SetIndex',
            'SelectIndex': int(channel)
        })
    except Exception as e:
        print(f"Pixoo SetChannel Fehler: {e}", flush=True)

def robust_set_brightness(self, brightness):
    if self.simulated: return
    try:
        from pixoo.utilities import clamp
        brightness = clamp(brightness, 0, 100)
        pixoo_post(self._Pixoo__url, {
            'Command': 'Channel/SetBrightness',
            'Brightness': brightness
        })
    except Exception as e:
        print(f"Pixoo SetBrightness Fehler: {e}", flush=True)

Pixoo.get_all_device_configurations = robust_get_all_device_configurations
Pixoo._Pixoo__load_counter = robust_load_counter
Pixoo._Pixoo__send_buffer = robust_send_buffer
Pixoo._Pixoo__reset_counter = robust_reset_counter
Pixoo.set_channel = robust_set_channel
Pixoo.set_brightness = robust_set_brightness

# --- KONFIGURATION ---
BASE_URL = os.getenv("BASE_URL")
USER = os.getenv("USER")
PASSWORD = os.getenv("PASSWORD")
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", 3))
PIXOO_IP = os.getenv("PIXOO_IP")

session = requests.Session()

# --- HILFSFUNKTIONEN ---
def get_my_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip

def check_ip(ip_prefix, i, results):
    ip = f"{ip_prefix}.{i}"
    try:
        r = requests.post(f"http://{ip}/post", json={"Command": "Device/GetDeviceTime"}, timeout=0.5)
        if r.status_code == 200:
            data = r.json()
            # Validiere, dass es wirklich ein Pixoo ist (typischerweise error_code 0)
            if 'error_code' in data:
                results.append(ip)
    except: pass

def find_pixoo():
    if PIXOO_IP:
        return PIXOO_IP
    my_ip = get_my_ip()
    prefix = ".".join(my_ip.split(".")[:-1])
    print(f"Suche Pixoo in {prefix}.x...", flush=True)
    threads, found = [], []
    for i in range(1, 255):
        t = threading.Thread(target=check_ip, args=(prefix, i, found))
        threads.append(t); t.start()
    for t in threads: t.join()
    return found[0] if found else None

def perform_login():
    try:
        print("Hole CSRF-Token...", flush=True)
        response = session.get(f"{BASE_URL}/login", timeout=5)
        token_match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
        if not token_match: return False

        csrf_token = token_match.group(1)
        login_data = {"csrf_token": csrf_token, "username": USER, "password": PASSWORD}
        res = session.post(f"{BASE_URL}/login", data=login_data, timeout=5)
        return res.status_code == 200 or "dashboard" in res.url
    except Exception as e:
        print(f"Login fehlgeschlagen: {e}", flush=True)
        return False

def get_downloader_data():
    try:
        response = session.get(f"{BASE_URL}/api/queue", timeout=5)
        if response.status_code == 401:
            if perform_login():
                response = session.get(f"{BASE_URL}/api/queue", timeout=5)
            else: return None
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        print(f"Fehler beim Abrufen der Downloader-Daten: {e}", flush=True)
        return None

# --- NEU: EXTRAHIERT SxxExx AUS DER URL ---
def format_episode_string(active_item):
    url = active_item.get('current_url', '')
    # Suche nach staffel-X und episode-X
    s_match = re.search(r'staffel-(\d+)', url)
    e_match = re.search(r'episode-(\d+)', url)

    if s_match and e_match:
        s = s_match.group(1).zfill(2)
        e = e_match.group(1).zfill(3)
        return f"S{s}E{e}"

    # Fallback, falls URL leer ist (nimmt die Zahlen aus dem JSON)
    curr_ep = str(active_item.get('current_episode', 0)).zfill(3)
    return f"Episode {curr_ep}"

def update_display(pixoo, data):
    pixoo.fill((0, 0, 0))

    if not data or 'items' not in data:
        pixoo.draw_text("Warte...", (2, 25), (100, 100, 100))
        pixoo.push(); return

    active_item = next((item for item in data['items'] if item['status'] == "running"), None)

    if active_item:
        title = active_item.get('title', 'Download')
        display_title = (title[:12] + '..') if len(title) > 12 else title

        # SxxExx Info generieren
        ep_code = format_episode_string(active_item)
        # Fortschritt (z.B. "4/10")
        prog_info = f"{active_item.get('current_episode')}/{active_item.get('total_episodes')}"

        # Prozent und Bandbreite aus ffmpeg_progress
        ffmpeg_data = data.get('ffmpeg_progress', {})
        percent = float(ffmpeg_data.get('percent', 0.0))
        bandwidth = ffmpeg_data.get('bandwidth', '0.0 MB/s')

        # UI ZEICHNEN
        pixoo.draw_text(display_title, (2, 2), (255, 180, 0))         # Titel (Gelb/Orange)
        pixoo.draw_text(ep_code, (2, 14), (0, 255, 255))              # SxxExxx (Cyan)
        pixoo.draw_text(f"Ep {prog_info}", (2, 26), (150, 150, 150))  # 4/10 (Grau)

        # Prozent und Bandbreite (ca. 5px über dem Balken bei y=54)
        # Wir nutzen y=42 (54 - 5 gap - ~7 font height)
        pixoo.draw_text(f"{int(percent)}%", (2, 42), (255, 255, 255))

        # Bandbreite rechtsbündig (geschätzt: 4px pro Zeichen + 1px Abstand)
        bw_x = 62 - (len(bandwidth) * 4)
        pixoo.draw_text(bandwidth, (bw_x, 42), (255, 255, 255))

        # Ladebalken ganz unten (y=54 bis 56)
        # Hintergrund für den Balken (Dunkelgrau)
        for y in range(54, 57):
            pixoo.draw_line((2, y), (61, y), (40, 40, 40))

        # Aktueller Fortschritt (Grün)
        bar_width = int((percent / 100) * 59)
        if bar_width > 0:
            for y in range(54, 57):
                pixoo.draw_line((2, y), (2 + bar_width, y), (0, 255, 100))

        print(f"Update: {title} {ep_code} ({int(percent)}%) - {bandwidth}", flush=True)
    else:
        pixoo.draw_text("IDLE", (2, 25), (100, 100, 100))

    pixoo.push()

# --- MAIN ---
if __name__ == "__main__":
    print("Starte Skript...", flush=True)
    pixoo_ip = find_pixoo()
    if not pixoo_ip:
        print("Kein Pixoo gefunden!", flush=True); exit()

    print(f"Verbunden mit Pixoo: {pixoo_ip}", flush=True)
    pixoo = Pixoo(pixoo_ip)

    # Sicherstellen, dass wir auf dem richtigen Kanal sind und Counter zurücksetzen
    print("Initialisiere Pixoo...", flush=True)
    pixoo.set_channel(3)
    pixoo._Pixoo__reset_counter()

    while True:
        data = get_downloader_data()
        update_display(pixoo, data)
        time.sleep(UPDATE_INTERVAL)
