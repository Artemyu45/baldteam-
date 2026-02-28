import socket
import threading
import json
import struct
import time
import random
import os

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

# ================= РЕАЛИСТИЧНЫЕ ПАРАМЕТРЫ =================
WIND = (1, -3)
WIND_STRENGTH = 2.15

FUEL_PROPERTIES = {
    "grass":    {"ign_temp": 42, "burn_rate": 3.8, "heat_gen": 58,  "spread_mult": 1.85},
    "trunk":    {"ign_temp": 65, "burn_rate": 0.72, "heat_gen": 52, "spread_mult": 1.45},
    "foliage":  {"ign_temp": 38, "burn_rate": 4.2, "heat_gen": 138, "spread_mult": 0.8},
    "wall":     {"ign_temp": 72, "burn_rate": 0.95,"heat_gen": 78, "spread_mult": 0.7},
    "floor":    {"ign_temp": 48, "burn_rate": 2.2, "heat_gen": 70, "spread_mult": 1.4},
    "stone":    {"ign_temp": 9999,"burn_rate": 0,   "heat_gen": 0,   "spread_mult": 0},
    "water":    {"ign_temp": 9999,"burn_rate": 0,   "heat_gen": 0,   "spread_mult": 0},
    "concrete": {"ign_temp": 9999, "burn_rate": 0,   "heat_gen": 0,   "spread_mult": 0},
    "hydrant":  {"ign_temp": 140,   "burn_rate": 0.4, "heat_gen": 35,  "spread_mult": 0.3},
    "wood_floor":{"ign_temp": 45,   "burn_rate": 2.8, "heat_gen": 75,  "spread_mult": 1.6},
    "firecar_root": {"ign_temp": 9999, "burn_rate": 0, "heat_gen": 0, "spread_mult": 0},
    "firecar_part": {"ign_temp": 9999, "burn_rate": 0, "heat_gen": 0, "spread_mult": 0},
    "road_turn_root":     {"ign_temp": 9999, "burn_rate": 0, "heat_gen": 0, "spread_mult": 0},
    "road_turn_part":     {"ign_temp": 9999, "burn_rate": 0, "heat_gen": 0, "spread_mult": 0},
}

def place_stamp(x, y, tool):
    if not (0 <= x < COLS and 0 <= y < ROWS): return

    if tool == "tree":
        # СТВОЛ
        trunk_height = 12
        for dy in range(trunk_height):
            ny = y + dy
            if ny >= ROWS: break
            c = grid[ny][x]
            c.type = "trunk"
            c.fuel = random.randint(175, 235)
            c.moisture = random.uniform(9, 19)
            c.heat = 0.0
            c.state = "unburned"
            c.intensity = 0

        # КРОНА
        crown_base = y + trunk_height - 6
        for layer in range(8):
            radius = 7 - layer // 2
            for dy in range(-radius - 1, radius + 2):
                for dx in range(-radius - 1, radius + 2):
                    if abs(dx) + abs(dy) > radius + random.random() * 1.8: continue
                    nx, ny = x + dx, crown_base - layer + dy
                    if not (0 <= nx < COLS and 0 <= ny < ROWS): continue
                    c = grid[ny][nx]
                    if c.type == "trunk": continue
                    c.type = "foliage"
                    c.fuel = random.randint(68, 118)
                    c.moisture = random.uniform(28, 48)
                    c.heat = 0.0
                    c.state = "unburned"
                    c.intensity = 0

    elif tool == "grass":
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = x + dx, y + dy
                if 0 <= nx < COLS and 0 <= ny < ROWS:
                    c = grid[ny][nx]
                    c.type = "grass"
                    c.fuel = random.randint(28, 55)
                    c.moisture = random.uniform(18, 35)
                    c.heat = 0
                    c.state = "unburned"

    elif tool == "lake":
        size = 9
        for dy in range(-size, size + 1):
            for dx in range(-size, size + 1):
                if dx*dx + dy*dy <= size*size + random.randint(-5, 5):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < COLS and 0 <= ny < ROWS:
                        c = grid[ny][nx]
                        c.type = "water"
                        c.fuel = 0
                        c.intensity = 0
                        c.moisture = 100
                        c.state = "burned"

    elif tool == "house":
        for dy in range(-6, 7):
            for dx in range(-9, 10):
                nx, ny = x + dx, y + dy
                if 0 <= nx < COLS and 0 <= ny < ROWS:
                    c = grid[ny][nx]
                    if abs(dy) in (6, -6) or abs(dx) in (9, -9):
                        c.type = "wall"
                        c.fuel = random.randint(200, 255)
                    else:
                        c.type = "floor"
                        c.fuel = random.randint(100, 155)
                    c.moisture = 12
                    c.heat = 0
                    c.state = "unburned"

    elif tool == "wall":
        c = grid[y][x]
        c.type = "wall"
        c.fuel = 230
        c.moisture = 10
        c.state = "unburned"

    elif tool == "floor":
        c = grid[y][x]
        c.type = "floor"
        c.fuel = 130
        c.moisture = 15
        c.state = "unburned"

    elif tool == "stone":
        c = grid[y][x]
        c.type = "stone"
        c.fuel = 0
        c.moisture = 0
        c.state = "burned"

    elif tool == "ignite":
        c = grid[y][x]
        c.intensity = random.randint(45, 72)
        c.heat = 92.0
        c.state = "burning"
        c.moisture = 4.0
    elif tool == "concrete":
        c = grid[y][x]
        c.type = "concrete"
        c.fuel = 0
        c.moisture = 0
        c.state = "burned"

    elif tool == "hydrant":
        c = grid[y][x]
        c.type = "hydrant"
        c.fuel = random.randint(8, 25)
        c.moisture = 5
        c.state = "unburned"

    elif tool == "wood_floor":
        c = grid[y][x]
        c.type = "floor"          # можно сделать отдельный тип, если хочешь
        c.fuel = random.randint(140, 190)
        c.moisture = 12
        c.state = "unburned"
    elif tool == "road_straight":
        # Размер 64x64 = 4x4 клетки
        w, h = 4, 4
        if x + w <= COLS and y + h <= ROWS:
            for dy in range(h):
                for dx in range(w):
                    c = grid[y + dy][x + dx]
                    if dx == 0 and dy == 0:
                        c.type = "road_straight_root" # Тут будет рисоваться текстура
                    else:
                        c.type = "road_straight_part" # Это просто физическое тело дороги
                    c.fuel = 0
                    c.moisture = 0
                    c.intensity = 0
                    c.state = "burned"

    elif tool == "road_turn":
        # Размер 80x80 = 5x5 клеток
        w, h = 5, 5
        if x + w <= COLS and y + h <= ROWS:
            for dy in range(h):
                for dx in range(w):
                    c = grid[y + dy][x + dx]
                    if dx == 0 and dy == 0:
                        c.type = "road_turn_root"
                    else:
                        c.type = "road_turn_part"
                    c.fuel = 0
                    c.moisture = 0
                    c.intensity = 0
                    c.state = "burned"
    elif tool == "firecar":
        # Машина 64x128 пикселей = 4x8 клеток
        if x + 3 < COLS and y + 7 < ROWS: # Проверка, чтобы не выйти за края карты
            for dy in range(8):
                for dx in range(4):
                    c = grid[y + dy][x + dx]
                    if dx == 0 and dy == 0:
                        c.type = "firecar_root" # Главная клетка, где будет текстура
                    else:
                        c.type = "firecar_part" # Остальной корпус (коллизия)
                    c.fuel = 0
                    c.moisture = 0
                    c.intensity = 0
                    c.state = "burned" # Не горит

def update_fire():
    if not running_sim: return

    heat_map = [[0.0 for _ in range(COLS)] for _ in range(ROWS)]

    # 1. Генерация тепла + ветер + вертикальный bias
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
                    if not (0 <= nx < COLS and 0 <= ny < ROWS): continue

                    dist = max(1.0, (abs(dx) + abs(dy)) ** 0.72)
                    heat = heat_out / dist
                    wind_bias = (dx * WIND[0] + dy * WIND[1]) * WIND_STRENGTH * 0.65
                    vertical_bias = 3.2 if dy < 0 else 0.55

                    heat_map[ny][nx] += heat + wind_bias * vertical_bias

            c.fuel = max(0, c.fuel - props["burn_rate"] * (c.intensity / 42))
            c.intensity = max(0, c.intensity - 1.45)

    # 2. Зажигание с 3D-правилом для кроны
    for y in range(ROWS):
        for x in range(COLS):
            c = grid[y][x]
            if c.type == "water":
                c.heat = 0
                continue

            c.heat = c.heat * 0.67 + heat_map[y][x]

            if c.state in ("unburned", "smoldering") and c.fuel > 16:
                props = FUEL_PROPERTIES.get(c.type, FUEL_PROPERTIES["grass"])
                ign_temp = props["ign_temp"]

                if c.type == "foliage":
                    burning_trunk_near = False
                    for check_y in range(y + 1, min(ROWS, y + 7)):
                        for check_x in range(max(0, x-2), min(COLS, x+3)):
                            if grid[check_y][check_x].type == "trunk" and grid[check_y][check_x].intensity > 15:
                                burning_trunk_near = True
                                break
                        if burning_trunk_near: break
                    if not burning_trunk_near:
                        ign_temp *= 2.85

                final_ign_temp = ign_temp * (1 + c.moisture / 130)

                if c.heat > final_ign_temp:
                    c.intensity = random.randint(33, 59)
                    c.state = "burning"
                    c.moisture = max(0, c.moisture - 24)

    # 3. Затухание
    for y in range(ROWS):
        for x in range(COLS):
            c = grid[y][x]
            if c.fuel <= 8:
                c.intensity = 0
                if c.state != "burned":
                    c.state = "smoldering" if c.fuel > 3 else "burned"
                c.heat *= 0.52

# ================= СЕТЬ =================
clients = []
client_roles = {}
grid_lock = threading.Lock()
ALLOWED_ROLES = {"rtp", "nsh", "br", "dispatcher"}
ROLE_LABELS = {
    "rtp": "РТП",
    "nsh": "НШ",
    "br": "БР",
    "dispatcher": "Диспетчер",
}


def recv_exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data

def send_msg(sock, data):
    try:
        msg = json.dumps(data).encode('utf-8')
        sock.sendall(struct.pack('>I', len(msg)) + msg)
    except:
        pass

def client_thread(conn, addr):
    global edit_mode, running_sim, grid, WIND, WIND_STRENGTH
    print(f"[?] Попытка входа от: {addr}. Ожидание авторизации...")

    try:
        conn.settimeout(5.0)
        raw_msglen = recv_exact(conn, 4)
        if not raw_msglen:
            print(f"[-] {addr} не прислал данные авторизации")
            return
        msglen = struct.unpack('>I', raw_msglen)[0]
        if msglen <= 0 or msglen > 4096:
            print(f"[-] Некорректный пакет авторизации от {addr}: {msglen}")
            return

        data = recv_exact(conn, msglen)
        if not data:
            print(f"[-] Неполный пакет авторизации от {addr}")
            return

        auth_cmd = json.loads(data.decode('utf-8'))
        role = str(auth_cmd.get('role', '')).lower()

        if auth_cmd.get('type') != 'AUTH' or auth_cmd.get('password') != SERVER_PASSWORD:
            send_msg(conn, {'type': 'AUTH_FAIL', 'reason': 'Неверный пароль'})
            print(f"[-] Неверный пароль от {addr}. Отключаем.")
            return

        if role not in ALLOWED_ROLES:
            send_msg(conn, {'type': 'AUTH_FAIL', 'reason': 'Недопустимая роль'})
            print(f"[-] Недопустимая роль от {addr}: {role!r}. Отключаем.")
            return

        send_msg(conn, {'type': 'AUTH_OK', 'role': role})
        conn.settimeout(None)

        clients.append(conn)
        client_roles[conn] = role
        print(f"[+] Игрок {addr} вошел в игру. Роль: {ROLE_LABELS.get(role, role)}")
        
        while True:
            raw_msglen = recv_exact(conn, 4)
            if not raw_msglen:
                break
            msglen = struct.unpack('>I', raw_msglen)[0]
            if msglen <= 0 or msglen > 5000000:  
                print(f"[-] Пакет слишком большой от {addr}: {msglen} байт")
                break
            data = recv_exact(conn, msglen)
            if not data:
                break
            cmd = json.loads(data.decode('utf-8'))

            with grid_lock:
                cmd_type = cmd.get('type')
                if cmd_type == 'CLICK':
                    place_stamp(cmd['x'], cmd['y'], cmd['tool'])
                elif cmd_type == 'FILL_BASE':
                    tool = cmd['tool']
                    for yy in range(ROWS):
                        for xx in range(COLS):
                            c = grid[yy][xx]
                            if c.type in ("empty", "grass", "floor", "stone"):
                                if tool == "empty":
                                    c.type = "empty"
                                    c.fuel = 0
                                elif tool == "grass":
                                    c.type = "grass"
                                    c.fuel = random.randint(28, 55)
                                elif tool == "floor":
                                    c.type = "floor"
                                    c.fuel = 130
                                elif tool == "stone":
                                    c.type = "stone"
                                    c.fuel = 0
                                c.intensity = 0
                                c.heat = 0
                                c.moisture = 25 if tool == "grass" else 15
                                c.state = "unburned"
                elif cmd_type == 'SPACE':
                    if edit_mode:
                        edit_mode = False
                        running_sim = True
                    else:
                        running_sim = not running_sim
                elif cmd_type == 'R':
                    grid = [[Cell() for _ in range(COLS)] for _ in range(ROWS)]
                    edit_mode = True
                    running_sim = False
                elif cmd_type == 'LOAD_MAP':
                    received_grid = cmd.get('grid')
                    # Проверяем, что карта пришла и её размеры совпадают с сервером
                    if received_grid and len(received_grid) == ROWS and all(len(row) == COLS for row in received_grid):
                        for yy in range(ROWS):
                            for xx in range(COLS):
                                # Клиент присылает ячейку в виде списка: [fuel, intensity, type]
                                cell_data = received_grid[yy][xx]
                                c = grid[yy][xx]
                                
                                c.fuel = cell_data[0]
                                c.intensity = cell_data[1]
                                c.type = cell_data[2]
                                
                                # Сбрасываем симуляционные параметры ячейки по умолчанию
                                c.heat = 0.0
                                if c.type in ("water", "stone", "concrete"):
                                    c.moisture = 100 if c.type == "water" else 0
                                    c.state = "burned"
                                else:
                                    c.moisture = 15.0 # Безопасное среднее значение влажности
                                    # Если при загрузке ячейка уже горит, ставим правильный статус
                                    c.state = "burning" if c.intensity > 0 else "unburned"
                                    
                        edit_mode = True
                        running_sim = False
                        print(f"Карта успешно загружена от клиента {addr}")
            # =======================================================

    except socket.timeout:
        print(f"[-] {addr} не прошел авторизацию вовремя. Отключен.")
    except Exception as e:
        print(f"[!] Ошибка клиента {addr}: {e}")
    finally:
        if conn in clients:
            clients.remove(conn)
        if conn in client_roles:
            del client_roles[conn]
        conn.close()
        print(f"[-] Игрок отключен: {addr}")

def game_loop():
    global frame
    while True:
        with grid_lock:
            if running_sim and frame % UPDATE_EVERY == 0:
                update_fire()
            frame += 1

            net_grid = [[[c.fuel, c.intensity, c.type] for c in row] for row in grid]
            state = {'grid': net_grid, 'edit_mode': edit_mode, 'running_sim': running_sim}

        for c in clients[:]:
            send_msg(c, state)

        time.sleep(1/33)

# ================= ЗАПУСК =================
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(MAX_PLAYERS)

print(f"Сервер запущен на {HOST}:{PORT} | Пароль: {SERVER_PASSWORD}")

threading.Thread(target=game_loop, daemon=True).start()
while True:
    conn, addr = server.accept()
    if len(clients) >= MAX_PLAYERS:
        conn.close()
    else:
        # Теперь мы НЕ добавляем в список клиентов сразу, а передаем в поток для проверки пароля
        threading.Thread(target=client_thread, args=(conn, addr), daemon=True).start()