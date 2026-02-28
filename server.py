import socket
import threading
import json
import struct
import time
import random
import base64
from radio_core import get_audio_stream, play

# ================= НАСТРОЙКИ СЕРВЕРА =================
HOST = '0.0.0.0'
PORT = 5555
MAX_PLAYERS = 8
SERVER_PASSWORD = "my_super_password"

COLS = 60
ROWS = 44
UPDATE_EVERY = 6

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
clients = []
grid_lock = threading.Lock()

# Инициализация звука (Сервер только СЛУШАЕТ)
try:
    sdstream = get_audio_stream()
    print("✅ Аудио-выход инициализирован")
except Exception as e:
    sdstream = None
    print(f"⚠️ Звуковое устройство не найдено: {e}")

FUEL_PROPERTIES = {
    "grass":    {"ign_temp": 42, "burn_rate": 3.8, "heat_gen": 58,  "spread_mult": 1.85},
    "trunk":    {"ign_temp": 65, "burn_rate": 0.72, "heat_gen": 52, "spread_mult": 1.45},
    "foliage":  {"ign_temp": 38, "burn_rate": 4.2, "heat_gen": 138, "spread_mult": 0.8},
    "wall":     {"ign_temp": 72, "burn_rate": 0.95,"heat_gen": 78, "spread_mult": 0.7},
    "floor":    {"ign_temp": 48, "burn_rate": 2.2, "heat_gen": 70, "spread_mult": 1.4},
    "stone":    {"ign_temp": 9999,"burn_rate": 0,   "heat_gen": 0,   "spread_mult": 0},
    "water":    {"ign_temp": 9999,"burn_rate": 0,   "heat_gen": 0,   "spread_mult": 0},
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
    elif tool == "grass":
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = x + dx, y + dy
                if 0 <= nx < COLS and 0 <= ny < ROWS:
                    grid[ny][nx].type, grid[ny][nx].fuel = "grass", random.randint(28, 55)
    elif tool == "lake":
        for dy in range(-9, 10):
            for dx in range(-9, 10):
                if dx*dx + dy*dy <= 81:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < COLS and 0 <= ny < ROWS:
                        grid[ny][nx].type, grid[ny][nx].fuel, grid[ny][nx].state = "water", 0, "burned"
    elif tool == "ignite":
        grid[y][x].intensity, grid[y][x].state, grid[y][x].heat = 60, "burning", 90.0

def update_fire():
    heat_map = [[0.0 for _ in range(COLS)] for _ in range(ROWS)]
    for y in range(ROWS):
        for x in range(COLS):
            c = grid[y][x]
            if c.intensity > 5:
                props = FUEL_PROPERTIES.get(c.type, FUEL_PROPERTIES["grass"])
                heat_out = props["heat_gen"] * (c.intensity / 50)
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < COLS and 0 <= ny < ROWS:
                            heat_map[ny][nx] += heat_out / (abs(dx)+abs(dy)+1)
                c.fuel -= props["burn_rate"]
                c.intensity -= 0.5
    for y in range(ROWS):
        for x in range(COLS):
            c = grid[y][x]
            c.heat = c.heat * 0.5 + heat_map[y][x]
            if c.state == "unburned" and c.fuel > 0:
                props = FUEL_PROPERTIES.get(c.type, FUEL_PROPERTIES["grass"])
                if c.heat > props["ign_temp"]:
                    c.state, c.intensity = "burning", 40

def client_thread(conn, addr):
    global edit_mode, running_sim, grid
    try:
        raw_msglen = conn.recv(4)
        if not raw_msglen: return
        msglen = struct.unpack('>I', raw_msglen)[0]
        auth = json.loads(conn.recv(msglen).decode('utf-8'))
        if auth.get('password') != SERVER_PASSWORD: return
        clients.append(conn)
        while True:
            raw_msglen = conn.recv(4)
            if not raw_msglen: break
            msglen = struct.unpack('>I', raw_msglen)[0]
            data = b''
            while len(data) < msglen:
                data += conn.recv(msglen - len(data))
            cmd = json.loads(data.decode('utf-8'))
            with grid_lock:
                if cmd['type'] == 'VOICE' and sdstream:
                    play(sdstream, base64.b64decode(cmd['data']))
                elif cmd['type'] == 'CLICK': place_stamp(cmd['x'], cmd['y'], cmd['tool'])
                elif cmd['type'] == 'SPACE':
                    if edit_mode: edit_mode = False; running_sim = True
                    else: running_sim = not running_sim
                elif cmd['type'] == 'R':
                    grid = [[Cell() for _ in range(COLS)] for _ in range(ROWS)]
                    edit_mode, running_sim = True, False
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
            state = json.dumps({'grid': net_grid, 'edit_mode': edit_mode, 'running_sim': running_sim}).encode('utf-8')
            msg = struct.pack('>I', len(state)) + state
        for c in clients[:]:
            try: c.sendall(msg)
            except: clients.remove(c)
        time.sleep(1/30)

threading.Thread(target=game_loop, daemon=True).start()
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((HOST, PORT)); server.listen(MAX_PLAYERS)
print(f"🚀 Сервер на {PORT}")
while True:
    conn, addr = server.accept()
    threading.Thread(target=client_thread, args=(conn, addr), daemon=True).start()