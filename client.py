import pygame
import sys
import socket
import threading
import json
import struct
import random
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# ================= НАСТРОЙКИ СЕТИ =================
# os.getenv берет значение из .env. Вторым аргументом указано значение по умолчанию (на случай, если .env нет или там пусто)
SERVER_IP = os.getenv('SERVER_IP', '127.0.0.1')
SERVER_PORT = int(os.getenv('SERVER_PORT', 5555)) # Порт обязательно нужно конвертировать в число (int)
SERVER_PASSWORD = os.getenv('SERVER_PASSWORD', 'my_super_password')

# ================= НАСТРОЙКИ ИГРЫ =================
CELL = 16
WIDTH = 960
HEIGHT = 704
COLS = WIDTH // CELL
ROWS = HEIGHT // CELL
FPS = 30

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption(f"Песочница пожара [{SERVER_IP}]")
clock = pygame.time.Clock()
font = pygame.font.SysFont("consolas", 20)
bigfont = pygame.font.SysFont("consolas", 32)

try:
    fire_texture = pygame.image.load("fire.png").convert_alpha()
except FileNotFoundError:
    print("❌ Файл fire.png не найден!")
    sys.exit()

server_grid = [[[0, 0, "empty"] for _ in range(COLS)] for _ in range(ROWS)]
edit_mode = True
running_sim = False

TOOLS =["grass", "tree", "lake", "house", "wall", "floor", "ignite"]
tool_names = {
    "grass": "Трава 🌿(1)", "tree": "Дерево 🌲(2)", "lake": "Озеро 💧(3)",
    "house": "Дом 🏠(4)", "wall": "Стена(5)", "floor": "Пол(6)", "ignite": "Очаг 🔥(7)"
}
current_tool = "grass"

RESET_RECT = pygame.Rect(WIDTH - 160, 15, 140, 40)

# ================= СЕТЕВОЕ ВЗАИМОДЕЙСТВИЕ =================
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    print(f"🔄 Подключение к {SERVER_IP}:{SERVER_PORT}...")
    client.connect((SERVER_IP, SERVER_PORT))
    print("✅ Подключено к серверу! Авторизация...")
    
    # СРАЗУ ПОСЛЕ ПОДКЛЮЧЕНИЯ ОТПРАВЛЯЕМ ПАРОЛЬ
    auth_data = {'type': 'AUTH', 'password': SERVER_PASSWORD}
    msg = json.dumps(auth_data).encode('utf-8')
    client.sendall(struct.pack('>I', len(msg)) + msg)
    
except Exception as e:
    print(f"❌ Не удалось подключиться к серверу: {e}")
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
            
            if msglen > 1000000:
                print("Слишком большой пакет от сервера. Отключаемся.")
                break

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
        print("\n❌ Связь с сервером потеряна (Или неверный пароль)!")

threading.Thread(target=receive_thread, daemon=True).start()

# ================= ОТРИСОВКА =================
def draw_textured_cell(screen, rect, fuel, intensity, ctype, gx, gy):
    x, y = rect.x, rect.y
    size = CELL

    if ctype == "tree":
        pygame.draw.rect(screen, (28, 75, 28), rect)
        colors =[(55, 165, 45), (75, 195, 65), (95, 225, 85), (45, 145, 35)]
        seed = (gx * 17 + gy * 31) % 100
        for i in range(9):
            ox = (seed + i * 11) % (size - 4) + 2
            oy = (seed + i * 17) % (size - 4) + 2
            pygame.draw.circle(screen, colors[(seed + i) % 4], (x + ox, y + oy), 4)

    elif ctype == "grass":
        pygame.draw.rect(screen, (38, 135, 48), rect)
        for i in range(5):
            ox = (gx * 3 + i) % (size - 3) + 1
            pygame.draw.line(screen, (65, 190, 75), (x + ox, y + size), (x + ox + 1, y + 3), 2)

    elif ctype == "water":
        pygame.draw.rect(screen, (18, 95, 185), rect)
        for i in range(4):
            ox = (gy * 7 + i * 5) % size
            pygame.draw.line(screen, (40, 165, 255), (x + ox, y + 4 + i*3), (x + ox + 7, y + 4 + i*3), 1)

    else:
        if fuel > 170: pygame.draw.rect(screen, (92, 52, 32), rect)
        elif fuel > 70: pygame.draw.rect(screen, (158, 112, 52), rect)
        elif fuel > 20: pygame.draw.rect(screen, (42, 148, 52), rect)
        else: pygame.draw.rect(screen, (30, 25, 20), rect)

def draw_grid():
    for y in range(ROWS):
        for x in range(COLS):
            fuel, intensity, ctype = server_grid[y][x]
            rect = pygame.Rect(x * CELL, y * CELL, CELL, CELL)

            if intensity > 0:
                scaled = pygame.transform.scale(fire_texture, (CELL, CELL))
                offset_x = random.randint(-2, 2)
                offset_y = -random.randint(0, 3)
                screen.blit(scaled, (rect.x + offset_x, rect.y + offset_y))
            else:
                draw_textured_cell(screen, rect, fuel, intensity, ctype, x, y)

def draw_ui():
    pygame.draw.rect(screen, (18, 18, 28), (0, HEIGHT - 90, WIDTH, 90))
    for i, tool in enumerate(TOOLS):
        col = (255, 70, 70) if tool == current_tool else (65, 65, 90)
        pygame.draw.rect(screen, col, (15 + i * 128, HEIGHT - 72, 120, 55))
        txt = font.render(tool_names[tool], True, (255, 255, 255))
        screen.blit(txt, (25 + i * 128, HEIGHT - 60))

    mode = "РЕДАКТИРОВАНИЕ — SPACE запустить" if edit_mode else "СИМУЛЯЦИЯ — SPACE пауза"
    color = (255, 240, 100) if edit_mode else (255, 60, 60)
    screen.blit(bigfont.render(mode, True, color), (20, 12))

    mouse_pos = pygame.mouse.get_pos()
    if RESET_RECT.collidepoint(mouse_pos):
        pygame.draw.rect(screen, (255, 80, 80), RESET_RECT, border_radius=6)
    else:
        pygame.draw.rect(screen, (200, 50, 50), RESET_RECT, border_radius=6)
    
    reset_txt = font.render("ОЧИСТИТЬ", True, (255, 255, 255))
    screen.blit(reset_txt, (RESET_RECT.x + 25, RESET_RECT.y + 10))

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
            if event.key == pygame.K_7: current_tool = "ignite"

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if RESET_RECT.collidepoint(event.pos):
                    send_to_server({'type': 'R'})

    if edit_mode and pygame.mouse.get_pressed()[0]:
        mx, my = pygame.mouse.get_pos()
        if not RESET_RECT.collidepoint((mx, my)):
            gx, gy = mx // CELL, my // CELL
            if gy < ROWS - 6:
                send_to_server({'type': 'CLICK', 'x': gx, 'y': gy, 'tool': current_tool})

    screen.fill((12, 22, 45))
    draw_grid()
    draw_ui()
    pygame.display.flip()
    clock.tick(FPS)

client.close()
pygame.quit()