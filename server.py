import socket
import threading
import json
import struct
import time
import random
import os
import base64
from radio_core import get_audio_stream, play

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# ================= НАСТРОЙКИ СЕРВЕРА =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if load_dotenv is not None:
    load_dotenv(os.path.join(BASE_DIR, ".env"))

HOST = os.getenv("SERVER_HOST", "127.0.0.1")
PORT = int(os.getenv("SERVER_PORT", "5555"))
MAX_PLAYERS = int(os.getenv("MAX_PLAYERS", "5"))
SERVER_PASSWORD = os.getenv("SERVER_PASSWORD", "my_super_password")

COLS = 60
ROWS = 44
UPDATE_EVERY = 6

# ================= ИНИЦИАЛИЗАЦИЯ АУДИО =================
try:
    sd_stream = get_audio_stream()
    print("✅ Аудиосистема сервера запущена (Воспроизведение)")
except Exception as e:
    sd_stream = None
    print(f"⚠️ Аудио не поддерживается на сервере: {e}")


# ================= ЛОГИКА ИГРЫ =================
class Cell:
    def __init__(self):
        self.fuel = 0
        self.intensity = 0
        self.type = "empty"
        self.heat = 0.0
        self.moisture = 22.0
        self.state = "unburned"


grid = [[Cell() for _ in range(COLS)] for _ in range(ROWS)]
edit_mode = True
running_sim = False
frame = 0

WIND = (1, -3)
WIND_STRENGTH = 2.15

FUEL_PROPERTIES = {
    "grass": {"ign_temp": 42, "burn_rate": 3.8, "heat_gen": 58, "spread_mult": 1.85},
    "trunk": {"ign_temp": 65, "burn_rate": 0.72, "heat_gen": 52, "spread_mult": 1.45},
    "foliage": {"ign_temp": 38, "burn_rate": 4.2, "heat_gen": 138, "spread_mult": 0.8},
    "wall": {"ign_temp": 72, "burn_rate": 0.95, "heat_gen": 78, "spread_mult": 0.7},
    "floor": {"ign_temp": 48, "burn_rate": 2.2, "heat_gen": 70, "spread_mult": 1.4},
    "stone": {"ign_temp": 9999, "burn_rate": 0, "heat_gen": 0, "spread_mult": 0},
    "water": {"ign_temp": 9999, "burn_rate": 0, "heat_gen": 0, "spread_mult": 0},
    "concrete": {"ign_temp": 9999, "burn_rate": 0, "heat_gen": 0, "spread_mult": 0},
    "hydrant": {"ign_temp": 140, "burn_rate": 0.4, "heat_gen": 35, "spread_mult": 0.3},
    "wood_floor": {"ign_temp": 45, "burn_rate": 2.8, "heat_gen": 75, "spread_mult": 1.6},
    "firecar_root": {"ign_temp": 9999, "burn_rate": 0, "heat_gen": 0, "spread_mult": 0},
    "firecar_part": {"ign_temp": 9999, "burn_rate": 0, "heat_gen": 0, "spread_mult": 0},
    "road_turn_root": {"ign_temp": 9999, "burn_rate": 0, "heat_gen": 0, "spread_mult": 0},
    "road_turn_part": {"ign_temp": 9999, "burn_rate": 0, "heat_gen": 0, "spread_mult": 0},
}


def place_stamp(x, y, tool):
    if not (0 <= x < COLS and 0 <= y < ROWS): return
    if tool == "tree":
        trunk_height = 12
        for dy in range(trunk_height):
            ny = y + dy
            if ny >= ROWS: break
            c = grid[ny][x]
            c.type, c.fuel, c.moisture = "trunk", random.randint(175, 235), random.uniform(9, 19)
            c.heat, c.state, c.intensity = 0.0, "unburned", 0
        crown_base = y + trunk_height - 6
        for layer in range(8):
            radius = 7 - layer // 2
            for dy in range(-radius - 1, radius + 2):
                for dx in range(-radius - 1, radius + 2):
                    if abs(dx) + abs(dy) > radius + random.random() * 1.8: continue
                    nx, ny = x + dx, crown_base - layer + dy
                    if 0 <= nx < COLS and 0 <= ny < ROWS and grid[ny][nx].type != "trunk":
                        c = grid[ny][nx]
                        c.type, c.fuel, c.moisture = "foliage", random.randint(68, 118), random.uniform(28, 48)
                        c.heat, c.state, c.intensity = 0.0, "unburned", 0
    elif tool == "grass":
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = x + dx, y + dy
                if 0 <= nx < COLS and 0 <= ny < ROWS:
                    c = grid[ny][nx]
                    c.type, c.fuel, c.moisture = "grass", random.randint(28, 55), random.uniform(18, 35)
                    c.heat, c.state = 0, "unburned"
    elif tool == "lake":
        size = 9
        for dy in range(-size, size + 1):
            for dx in range(-size, size + 1):
                if dx * dx + dy * dy <= size * size + random.randint(-5, 5):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < COLS and 0 <= ny < ROWS:
                        c = grid[ny][nx]
                        c.type, c.fuel, c.intensity, c.moisture, c.state = "water", 0, 0, 100, "burned"
    elif tool == "house":
        for dy in range(-6, 7):
            for dx in range(-9, 10):
                nx, ny = x + dx, y + dy
                if 0 <= nx < COLS and 0 <= ny < ROWS:
                    c = grid[ny][nx]
                    if abs(dy) in (6, -6) or abs(dx) in (9, -9):
                        c.type, c.fuel = "wall", random.randint(200, 255)
                    else:
                        c.type, c.fuel = "floor", random.randint(100, 155)
                    c.moisture, c.heat, c.state = 12, 0, "unburned"
    elif tool == "ignite":
        c = grid[y][x]
        c.intensity, c.heat, c.state, c.moisture = random.randint(45, 72), 92.0, "burning", 4.0
    # Остальные инструменты (wall, stone, firecar и т.д.) по аналогии...
    elif tool == "stone":
        c = grid[y][x]
        c.type, c.fuel, c.state = "stone", 0, "burned"


def update_fire():
    if not running_sim: return
    heat_map = [[0.0 for _ in range(COLS)] for _ in range(ROWS)]
    for y in range(ROWS):
        for x in range(COLS):
            c = grid[y][x]
            if c.intensity <= 8: continue
            props = FUEL_PROPERTIES.get(c.type, FUEL_PROPERTIES["grass"])
            heat_out = props["heat_gen"] * (c.intensity / 55)
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    if dx == 0 and dy == 0: continue
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < COLS and 0 <= ny < ROWS:
                        dist = max(1.0, (abs(dx) + abs(dy)) ** 0.72)
                        wind_bias = (dx * WIND[0] + dy * WIND[1]) * WIND_STRENGTH * 0.65
                        vertical_bias = 3.2 if dy < 0 else 0.55
                        heat_map[ny][nx] += (heat_out / dist) + wind_bias * vertical_bias
            c.fuel = max(0, c.fuel - props["burn_rate"] * (c.intensity / 42))
            c.intensity = max(0, c.intensity - 1.45)
    for y in range(ROWS):
        for x in range(COLS):
            c = grid[y][x]
            if c.type == "water": c.heat = 0; continue
            c.heat = c.heat * 0.67 + heat_map[y][x]
            if c.state in ("unburned", "smoldering") and c.fuel > 16:
                props = FUEL_PROPERTIES.get(c.type, FUEL_PROPERTIES["grass"])
                final_ign_temp = props["ign_temp"] * (1 + c.moisture / 130)
                if c.heat > final_ign_temp:
                    c.intensity, c.state, c.moisture = random.randint(33, 59), "burning", max(0, c.moisture - 24)


# ================= СЕТЬ =================
clients = []
grid_lock = threading.Lock()


def recv_exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk: return None
        data += chunk
    return data


def send_msg(sock, data):
    try:
        msg = json.dumps(data).encode('utf-8')
        sock.sendall(struct.pack('>I', len(msg)) + msg)
    except:
        pass


def client_thread(conn, addr):
    global edit_mode, running_sim, grid
    try:
        conn.settimeout(5.0)
        raw_msglen = recv_exact(conn, 4)
        if not raw_msglen: return
        msglen = struct.unpack('>I', raw_msglen)[0]
        data = recv_exact(conn, msglen)
        auth_cmd = json.loads(data.decode('utf-8'))
        if auth_cmd.get('type') != 'AUTH' or auth_cmd.get('password') != SERVER_PASSWORD:
            send_msg(conn, {'type': 'AUTH_FAIL'});
            return
        send_msg(conn, {'type': 'AUTH_OK'})
        conn.settimeout(None)
        clients.append(conn)

        while True:
            raw_msglen = recv_exact(conn, 4)
            if not raw_msglen: break
            msglen = struct.unpack('>I', raw_msglen)[0]
            data = recv_exact(conn, msglen)
            cmd = json.loads(data.decode('utf-8'))

            if cmd.get('type') == 'VOICE' and sd_stream:
                audio_bytes = base64.b64decode(cmd['data'])
                play(sd_stream, audio_bytes)
                continue

            with grid_lock:
                ctype = cmd.get('type')
                if ctype == 'CLICK':
                    place_stamp(cmd['x'], cmd['y'], cmd['tool'])
                elif ctype == 'SPACE':
                    if edit_mode:
                        edit_mode, running_sim = False, True
                    else:
                        running_sim = not running_sim
                elif ctype == 'R':
                    grid = [[Cell() for _ in range(COLS)] for _ in range(ROWS)]
                    edit_mode, running_sim = True, False
                elif ctype == 'LOAD_MAP':
                    # Логика загрузки карты из твоего файла...
                    pass
    except:
        pass
    finally:
        if conn in clients: clients.remove(conn)
        conn.close()


def game_loop():
    global frame
    while True:
        with grid_lock:
            if running_sim and frame % UPDATE_EVERY == 0: update_fire()
            frame += 1
            net_grid = [[[c.fuel, c.intensity, c.type] for c in row] for row in grid]
            state = {'grid': net_grid, 'edit_mode': edit_mode, 'running_sim': running_sim}
        for c in clients[:]: send_msg(c, state)
        time.sleep(1 / 33)


server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT));
server.listen(MAX_PLAYERS)
threading.Thread(target=game_loop, daemon=True).start()
print(f"Сервер запущен на {PORT}")
while True:
    conn, addr = server.accept()
    threading.Thread(target=client_thread, args=(conn, addr), daemon=True).start()