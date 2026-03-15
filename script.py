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
        r = requests.post(f"http://{ip}/post", json={"Command": "Device/GetDeviceTime"}, timeout=0.2)
        if r.status_code == 200: results.append(ip)
    except: pass

def find_pixoo():
    if PIXOO_IP:
        return PIXOO_IP
    my_ip = get_my_ip()
    prefix = ".".join(my_ip.split(".")[:-1])
    print(f"Suche Pixoo in {prefix}.x...")
    threads, found = [], []
    for i in range(1, 255):
        t = threading.Thread(target=check_ip, args=(prefix, i, found))
        threads.append(t); t.start()
    for t in threads: t.join()
    return found[0] if found else None

def perform_login():
    try:
        print("Hole CSRF-Token...")
        response = session.get(f"{BASE_URL}/login", timeout=5)
        token_match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
        if not token_match: return False

        csrf_token = token_match.group(1)
        login_data = {"csrf_token": csrf_token, "username": USER, "password": PASSWORD}
        res = session.post(f"{BASE_URL}/login", data=login_data, timeout=5)
        return res.status_code == 200 or "dashboard" in res.url
    except: return False

def get_downloader_data():
    try:
        response = session.get(f"{BASE_URL}/api/queue", timeout=5)
        if response.status_code == 401:
            if perform_login():
                response = session.get(f"{BASE_URL}/api/queue", timeout=5)
            else: return None
        return response.json() if response.status_code == 200 else None
    except: return None

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

        # Prozent aus ffmpeg_progress
        percent = float(data.get('ffmpeg_progress', {}).get('percent', 0.0))

        # UI ZEICHNEN (Jetzt alles auf x=2 für Linksbündigkeit)
        pixoo.draw_text(display_title, (2, 2), (255, 180, 0))         # Titel (Gelb/Orange)
        pixoo.draw_text(ep_code, (2, 14), (0, 255, 255))              # SxxExxx (Cyan)
        pixoo.draw_text(f"Ep {prog_info}", (2, 26), (150, 150, 150))  # 4/10 (Grau)
        pixoo.draw_text(f"{int(percent)}%", (2, 38), (255, 255, 255)) # Prozent (Weiß) - Jetzt links!

        # Ladebalken ganz unten
        bar_width = int((percent / 100) * 59)
        if bar_width < 2: bar_width = 2
        for y in range(54, 57):
            pixoo.draw_line((2, y), (2 + bar_width, y), (0, 255, 100))

        print(f"Update: {title} {ep_code} ({int(percent)}%)")
    else:
        pixoo.draw_text("IDLE", (2, 25), (100, 100, 100))

    pixoo.push()

# --- MAIN ---
if __name__ == "__main__":
    pixoo_ip = find_pixoo()
    if not pixoo_ip:
        print("Kein Pixoo gefunden!"); exit()

    print(f"Verbunden mit Pixoo: {pixoo_ip}")
    pixoo = Pixoo(pixoo_ip)

    while True:
        data = get_downloader_data()
        update_display(pixoo, data)
        time.sleep(UPDATE_INTERVAL)
