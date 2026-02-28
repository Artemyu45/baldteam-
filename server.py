import socket
import threading
import json
import struct
import time
import random

# ================= НАСТРОЙКИ СЕРВЕРА =================
HOST = '0.0.0.0'
PORT = 5555
MAX_PLAYERS = 5
SERVER_PASSWORD = "my_super_password" # <--- УСТАНОВИ СВОЙ ПАРОЛЬ ЗДЕСЬ

COLS = 60
ROWS = 44
UPDATE_EVERY = 7

# ================= ЛОГИКА ИГРЫ =================
class Cell:
    def __init__(self):
        self.fuel = 0
        self.intensity = 0
        self.type = "empty"

grid = [[Cell() for _ in range(COLS)] for _ in range(ROWS)]
edit_mode = True
running_sim = False
frame = 0

def place_stamp(x, y, tool):
    if tool == "grass":
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = x + dx, y + dy
                if 0 <= nx < COLS and 0 <= ny < ROWS:
                    grid[ny][nx].fuel = random.randint(28, 55)
                    grid[ny][nx].type = "grass"
    elif tool == "tree":
        for dy in range(9):
            nx, ny = x, y + dy
            if 0 <= ny < ROWS:
                grid[ny][nx].fuel = 115
                grid[ny][nx].type = "tree"
        for layer in range(6):
            r = 7 - layer
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if abs(dx) + abs(dy) <= r and random.random() < 0.88:
                        nx, ny = x + dx, y - layer * 2 - 6 + dy
                        if 0 <= nx < COLS and 0 <= ny < ROWS:
                            grid[ny][nx].fuel = random.randint(72, 115)
                            grid[ny][nx].type = "tree"
    elif tool == "lake":
        size = 9
        for dy in range(-size, size + 1):
            for dx in range(-size, size + 1):
                if dx*dx + dy*dy <= size*size + random.randint(-4, 4):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < COLS and 0 <= ny < ROWS:
                        grid[ny][nx].fuel = 0
                        grid[ny][nx].intensity = 0
                        grid[ny][nx].type = "water"
    elif tool == "house":
        for dy in range(-6, 7):
            for dx in range(-9, 10):
                nx, ny = x + dx, y + dy
                if 0 <= nx < COLS and 0 <= ny < ROWS:
                    if abs(dy) in (6, -6) or abs(dx) in (9, -9):
                        grid[ny][nx].fuel = random.randint(200, 250)
                        grid[ny][nx].type = "wall"
                    else:
                        grid[ny][nx].fuel = random.randint(100, 150)
                        grid[ny][nx].type = "floor"
    elif tool == "wall":
        grid[y][x].fuel = 230
        grid[y][x].type = "wall"
    elif tool == "floor":
        grid[y][x].fuel = 130
        grid[y][x].type = "floor"
    elif tool == "ignite":
        grid[y][x].intensity = random.randint(40, 60)

def update_fire():
    for y in range(ROWS - 2, 4, -1):
        for x in range(1, COLS - 1):
            c = grid[y][x]
            if c.type == "water":
                c.intensity = 0
                continue
            if c.intensity > 0:
                c.intensity = max(0, c.intensity - 1)
                c.fuel = max(0, c.fuel - 1)
                if c.intensity > 16:
                    for dx, dy in [(0,-1),(-1,-1),(1,-1),(-1,0),(1,0),(0,1)]:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < COLS and 0 <= ny < ROWS:
                            n = grid[ny][nx]
                            if n.type != "water" and n.fuel > 22 and n.intensity == 0:
                                chance = 0.26 if n.type in ("tree", "wall") else 0.10
                                if random.random() < chance:
                                    n.intensity = random.randint(20, 38)
    for y in range(ROWS):
        for x in range(COLS):
            if grid[y][x].fuel <= 8:
                grid[y][x].intensity = 0

# ================= СЕТЬ =================
clients = []
grid_lock = threading.Lock()

def send_msg(sock, data):
    msg = json.dumps(data).encode('utf-8')
    sock.sendall(struct.pack('>I', len(msg)) + msg)

def client_thread(conn, addr):
    global edit_mode, running_sim, grid
    print(f"[?] Попытка входа от: {addr}. Ожидание пароля...")
    
    try:
        # Даем клиенту ровно 5 секунд, чтобы прислать пароль, иначе отключаем (защита от зависаний)
        conn.settimeout(5.0) 
        
        raw_msglen = conn.recv(4)
        if not raw_msglen: return
        msglen = struct.unpack('>I', raw_msglen)[0]
        
        if msglen > 1000: # Пароль не может весить больше 1 КБ
            print(f"[!] Атака! Пакет слишком большой {addr}")
            return
            
        data = b''
        while len(data) < msglen:
            packet = conn.recv(msglen - len(data))
            if not packet: return
            data += packet
            
        auth_cmd = json.loads(data.decode('utf-8'))
        
        # ПРОВЕРКА ПАРОЛЯ
        if auth_cmd.get('type') != 'AUTH' or auth_cmd.get('password') != SERVER_PASSWORD:
            print(f"[-] Неверный пароль от {addr}. Отключаем.")
            return # Выходим, код идет в блок finally и закрывает соединение
            
        print(f"[+] Игрок {addr} ввел верный пароль и вошел в игру!")
        
        # Снимаем таймер (во время игры можно ничего не присылать)
        conn.settimeout(None)
        
        # Только теперь добавляем в список активных игроков
        clients.append(conn)
        
        # ОСНОВНОЙ ЦИКЛ ОБРАБОТКИ ИГРЫ
        while True:
            raw_msglen = conn.recv(4)
            if not raw_msglen: break
            msglen = struct.unpack('>I', raw_msglen)[0]
            
            if msglen > 10000:
                print(f"[!] Атака! Слишком большой пакет от {addr}")
                break

            data = b''
            while len(data) < msglen:
                packet = conn.recv(msglen - len(data))
                if not packet: break
                data += packet
            
            cmd = json.loads(data.decode('utf-8'))
            
            with grid_lock:
                if cmd['type'] == 'CLICK':
                    place_stamp(cmd['x'], cmd['y'], cmd['tool'])
                elif cmd['type'] == 'SPACE':
                    if edit_mode:
                        edit_mode = False
                        running_sim = True
                    else:
                        running_sim = not running_sim
                elif cmd['type'] == 'R':
                    grid = [[Cell() for _ in range(COLS)] for _ in range(ROWS)]
                    edit_mode = True
                    running_sim = False
                    
    except socket.timeout:
        print(f"[-] {addr} не прислал пароль вовремя. Отключен.")
    except Exception as e:
        pass # Обычное отключение игрока
    finally:
        if conn in clients:
            clients.remove(conn)
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
            state = {
                'grid': net_grid,
                'edit_mode': edit_mode,
                'running_sim': running_sim
            }
        
        for c in clients[:]:
            try:
                send_msg(c, state)
            except:
                pass
                
        time.sleep(1/30)

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((HOST, PORT))
server.listen(MAX_PLAYERS)
print(f"[*] Сервер запущен. Ожидание игроков (Макс {MAX_PLAYERS})...")
print(f"[*] ТЕКУЩИЙ ПАРОЛЬ СЕРВЕРА: {SERVER_PASSWORD}")

threading.Thread(target=game_loop, daemon=True).start()

while True:
    conn, addr = server.accept()
    if len(clients) >= MAX_PLAYERS:
        conn.close()
    else:
        # Теперь мы НЕ добавляем в список клиентов сразу, а передаем в поток для проверки пароля
        threading.Thread(target=client_thread, args=(conn, addr), daemon=True).start()