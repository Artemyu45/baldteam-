import pygame
import sys
import socket
import threading
import json
import struct
import random
import os
from dotenv import load_dotenv



BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

SERVER_IP = os.getenv('SERVER_IP', '127.0.0.1')
SERVER_PORT = int(os.getenv('SERVER_PORT', 5555))
SERVER_PASSWORD = os.getenv('SERVER_PASSWORD', 'my_super_password')
PLAYER_ROLE = os.getenv('PLAYER_ROLE', 'rtp').lower()
ROLES = ["rtp", "nsh", "br", "dispatcher"]
ROLE_LABELS = {
    "rtp": "РТП",
    "nsh": "НШ",
    "br": "БР",
    "dispatcher": "Диспетчер",
}
if PLAYER_ROLE not in ROLES:
    PLAYER_ROLE = "rtp"


def get_ui_font(size, bold=False):
    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return pygame.font.Font(path, size)
            except Exception:
                pass

    for name in ["arial", "helvetica", "dejavusans", "noto sans", "liberationsans", "segoeui"]:
        matched = pygame.font.match_font(name, bold=bold)
        if matched:
            return pygame.font.Font(matched, size)
    return pygame.font.SysFont(None, size, bold=bold)


# ================= НАСТРОЙКИ ИГРЫ =================
CELL = 16
GRID_WIDTH = 960
PANEL_WIDTH = 200
WIDTH = GRID_WIDTH + PANEL_WIDTH
HEIGHT = 704
COLS = GRID_WIDTH // CELL
ROWS = HEIGHT // CELL
FPS = 30

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))

pygame.display.set_caption(f"Песочница пожара [{SERVER_IP}] [{ROLE_LABELS.get(PLAYER_ROLE, PLAYER_ROLE)}]")
clock = pygame.time.Clock()
font = get_ui_font(20)
bigfont = get_ui_font(32)

try:
    fire_texture = pygame.image.load(os.path.join(BASE_DIR, "fire.png")).convert_alpha()
except FileNotFoundError:
    print("❌ Файл fire.png не найден!")
    sys.exit()

server_grid = [[[0, 0, "empty"] for _ in range(COLS)] for _ in range(ROWS)]
edit_mode = True
running_sim = False

TOOLS = ["grass", "tree", "lake", "house", "wall", "floor", "stone", "ignite"]
tool_names = {
    "grass": "Трава(1)", "tree": "Дерево(2)", "lake": "Озеро(3)",
    "house": "Дом(4)", "wall": "Стена(5)", "floor": "Пол(6)", 
    "stone": "Камень(7)", "ignite": "Очаг(8)"}


current_tool = "grass"

# === Панель базового пола ===
BASE_OPTIONS = [
    {"id": "empty", "name": "Пусто ⬛", "color": (50, 50, 50)},
    {"id": "grass", "name": "Трава 🌿", "color": (38, 135, 48)},
    {"id": "floor", "name": "Дер.Пол 🪵", "color": (158, 112, 52)},
    {"id": "stone", "name": "Камень 🪨", "color": (100, 100, 105)}
]
base_buttons = []
start_y = 100
for i, opt in enumerate(BASE_OPTIONS):
    rect = pygame.Rect(GRID_WIDTH + 15, start_y + i * 55, PANEL_WIDTH - 30, 45)
    base_buttons.append({"rect": rect, "opt": opt})

RESET_RECT = pygame.Rect(GRID_WIDTH + 15, HEIGHT - 70, PANEL_WIDTH - 30, 45)

# ================= СЕТЕВОЕ ВЗАИМОДЕЙСТВИЕ =================
def recv_exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data


client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    print(f"🔄 Подключение к {SERVER_IP}:{SERVER_PORT}...")
    client.connect((SERVER_IP, SERVER_PORT))
    print("✅ Подключено к серверу!")

    auth_data = {'type': 'AUTH', 'password': SERVER_PASSWORD, 'role': PLAYER_ROLE}
    msg = json.dumps(auth_data).encode('utf-8')
    client.sendall(struct.pack('>I', len(msg)) + msg)

    client.settimeout(5.0)
    raw_msglen = recv_exact(client, 4)
    if not raw_msglen:
        raise RuntimeError("Сервер не прислал ответ авторизации")
    msglen = struct.unpack('>I', raw_msglen)[0]
    payload = recv_exact(client, msglen)
    if not payload:
        raise RuntimeError("Сервер прислал неполный ответ авторизации")
    auth_reply = json.loads(payload.decode("utf-8"))
    if auth_reply.get("type") != "AUTH_OK":
        raise RuntimeError(auth_reply.get("reason", "Ошибка авторизации"))
    client.settimeout(None)
    print(f"✅ Авторизация успешна. Роль: {ROLE_LABELS.get(PLAYER_ROLE, PLAYER_ROLE)}")
    
except Exception as e:
    print(f"❌ Не удалось подключиться к серверу: {e}")
    try:
        client.close()
    except Exception:
        pass
    sys.exit()

def send_to_server(data):
    try:
        msg = json.dumps(data).encode('utf-8')
        client.sendall(struct.pack('>I', len(msg)) + msg)
    except:
        pass

def receive_thread():
    global server_grid, edit_mode, running_sim
    try:
        while True:
            raw_msglen = client.recv(4)
            if not raw_msglen: break
            msglen = struct.unpack('>I', raw_msglen)[0]
            if msglen > 1000000: break

            data = b''
            while len(data) < msglen:
                packet = client.recv(msglen - len(data))
                if not packet: break
                data += packet
            
            state = json.loads(data.decode('utf-8'))
            server_grid = state['grid']
            edit_mode = state['edit_mode']
            running_sim = state['running_sim']
    except Exception as e:
        print("\n❌ Связь с сервером потеряна!")

threading.Thread(target=receive_thread, daemon=True).start()

# ================= ОТРИСОВКА =================
def draw_textured_cell(screen, rect, fuel, intensity, ctype, gx, gy):
    x, y = rect.x, rect.y
    size = CELL

    if intensity > 0:
        scaled = pygame.transform.scale(fire_texture, (CELL, CELL))
        offset_x = random.randint(-3, 3)
        offset_y = -random.randint(0, 5)
        screen.blit(scaled, (rect.x + offset_x, rect.y + offset_y))
        return

    # === 3D-ДЕРЕВО ===
    if ctype == "trunk":
        pygame.draw.rect(screen, (94, 54, 32), rect)
        for i in range(7):
            ox = (gx * 7 + i * 5) % size
            oy = (gy * 13 + i * 3) % size
            pygame.draw.line(screen, (68, 38, 22), 
                           (x + ox, y + oy), (x + ox + 3, y + oy + 2), 2)

    elif ctype == "foliage":
        pygame.draw.rect(screen, (18, 75, 35), rect)
        colors = [(45, 165, 55), (65, 195, 75), (35, 145, 45), (55, 175, 65)]
        seed = (gx * 17 + gy * 23) % 100
        for i in range(14):
            r = 4 if i < 8 else 3
            ox = (seed + i * 11) % (size - r*2) + r
            oy = (seed + i * 19) % (size - r*2) + r
            col = colors[(seed + i) % 4]
            pygame.draw.circle(screen, col, (x + ox, y + oy), r)

    elif ctype == "grass":
        pygame.draw.rect(screen, (38, 135, 48), rect)
        for i in range(6):
            ox = (gx * 3 + i) % (size - 3) + 1
            pygame.draw.line(screen, (65, 190, 75), (x + ox, y + size - 2), 
                           (x + ox + 1, y + 4), 2)

    elif ctype == "water":
        pygame.draw.rect(screen, (18, 95, 185), rect)
        for i in range(5):
            ox = (gy * 7 + i * 5) % size
            pygame.draw.line(screen, (40, 165, 255), (x + ox, y + 4 + i*3), 
                           (x + ox + 8, y + 4 + i*3), 1)

    elif ctype == "stone":
        pygame.draw.rect(screen, (100, 100, 105), rect)
        for i in range(4):
            ox = (gx * 5 + i * 7) % CELL
            oy = (gy * 3 + i * 11) % CELL
            pygame.draw.rect(screen, (70, 70, 75), (x + ox, y + oy, 3, 3))

    else:  # floor, wall, empty и т.д.
        if fuel > 170: color = (92, 52, 32)
        elif fuel > 70: color = (158, 112, 52)
        elif fuel > 20: color = (42, 148, 52)
        else: color = (30, 25, 20)
        pygame.draw.rect(screen, color, rect)

def draw_grid():
    for y in range(ROWS):
        for x in range(COLS):
            fuel, intensity, ctype = server_grid[y][x]
            rect = pygame.Rect(x * CELL, y * CELL, CELL, CELL)
            draw_textured_cell(screen, rect, fuel, intensity, ctype, x, y)

def draw_ui():
    pygame.draw.rect(screen, (18, 18, 28), (0, HEIGHT - 90, GRID_WIDTH, 90))
    for i, tool in enumerate(TOOLS):
        col = (255, 70, 70) if tool == current_tool else (65, 65, 90)
        rect = pygame.Rect(10 + i * 118, HEIGHT - 72, 110, 55)
        pygame.draw.rect(screen, col, rect, border_radius=5)
        txt = font.render(tool_names[tool], True, (255, 255, 255))
        screen.blit(txt, txt.get_rect(center=rect.center))

    mode = "РЕДАКТИРОВАНИЕ — SPACE запустить" if edit_mode else "СИМУЛЯЦИЯ — SPACE пауза"
    color = (255, 240, 100) if edit_mode else (255, 60, 60)
    screen.blit(bigfont.render(mode, True, color), (20, 12))

    pygame.draw.rect(screen, (25, 25, 35), (GRID_WIDTH, 0, PANEL_WIDTH, HEIGHT))
    pygame.draw.line(screen, (50, 50, 60), (GRID_WIDTH, 0), (GRID_WIDTH, HEIGHT), 2)
    
    title = font.render("Базовый пол:", True, (220, 220, 220))
    screen.blit(title, (GRID_WIDTH + 15, 60))

    mouse_pos = pygame.mouse.get_pos()
    for btn in base_buttons:
        rect = btn["rect"]
        opt = btn["opt"]
        color = opt["color"]
        if rect.collidepoint(mouse_pos):
            color = (min(255, color[0]+35), min(255, color[1]+35), min(255, color[2]+35))
        pygame.draw.rect(screen, color, rect, border_radius=5)
        pygame.draw.rect(screen, (200, 200, 200), rect, 1, border_radius=5)
        txt = font.render(opt["name"], True, (255, 255, 255))
        screen.blit(txt, txt.get_rect(center=rect.center))

    if RESET_RECT.collidepoint(mouse_pos):
        pygame.draw.rect(screen, (255, 80, 80), RESET_RECT, border_radius=6)
    else:
        pygame.draw.rect(screen, (200, 50, 50), RESET_RECT, border_radius=6)
    reset_txt = font.render("ОЧИСТИТЬ ВСЕ", True, (255, 255, 255))
    screen.blit(reset_txt, reset_txt.get_rect(center=RESET_RECT.center))

# ================= ГЛАВНЫЙ ЦИКЛ =================
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE: send_to_server({'type': 'SPACE'})
            if event.key == pygame.K_r: send_to_server({'type': 'R'})
            if event.key == pygame.K_1: current_tool = "grass"
            if event.key == pygame.K_2: current_tool = "tree"
            if event.key == pygame.K_3: current_tool = "lake"
            if event.key == pygame.K_4: current_tool = "house"
            if event.key == pygame.K_5: current_tool = "wall"
            if event.key == pygame.K_6: current_tool = "floor"
            if event.key == pygame.K_7: current_tool = "stone"
            if event.key == pygame.K_8: current_tool = "ignite"

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if RESET_RECT.collidepoint(event.pos):
                send_to_server({'type': 'R'})
            else:
                for btn in base_buttons:
                    if btn["rect"].collidepoint(event.pos):
                        send_to_server({'type': 'FILL_BASE', 'tool': btn["opt"]["id"]})

    if edit_mode and pygame.mouse.get_pressed()[0]:
        mx, my = pygame.mouse.get_pos()
        if mx < GRID_WIDTH and my < HEIGHT - 90:
            gx, gy = mx // CELL, my // CELL
            if 0 <= gx < COLS and 0 <= gy < ROWS:
                send_to_server({'type': 'CLICK', 'x': gx, 'y': gy, 'tool': current_tool})

    screen.fill((12, 22, 45))
    draw_grid()
    draw_ui()
    pygame.display.flip()
    clock.tick(FPS)

client.close()
pygame.quit()