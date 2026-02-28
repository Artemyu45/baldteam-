import os
import sys
import socket
import threading
import json
import struct
import random
import io

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

import pygame
import tkinter as tk
from tkinter import filedialog

# ================= НАСТРОЙКИ ПРИЛОЖЕНИЯ =================
if sys.platform == "win32" and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if load_dotenv:
    load_dotenv(os.path.join(BASE_DIR, ".env"))
MAPS_DIR = os.path.join(BASE_DIR, "maps")
os.makedirs(MAPS_DIR, exist_ok=True)

# ================= СЕТЕВЫЕ НАСТРОЙКИ КЛИЕНТА =================
SERVER_IP = os.getenv('SERVER_IP', '127.0.0.1')
SERVER_PORT = int(os.getenv('SERVER_PORT', 5555))
SERVER_PASSWORD = os.getenv('SERVER_PASSWORD', 'my_super_password')
PLAYER_ROLE = os.getenv('PLAYER_ROLE', 'rtp').lower()

ROLES = ["rtp", "nsh", "br", "dispatcher"]
ROLE_LABELS = {
    "rtp": "РТП", "nsh": "НШ", "br": "БР", "dispatcher": "Диспетчер"
}

def get_ui_font(size, bold=False):
    font_paths = [
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try: return pygame.font.Font(path, size)
            except Exception: pass
    try: return pygame.font.SysFont("arial", size, bold=bold)
    except Exception: return pygame.font.Font(None, size)

# ================= НАСТРОЙКИ PYGAME =================
CELL = 16
GRID_WIDTH = 960
PANEL_WIDTH = 250
WIDTH = GRID_WIDTH + PANEL_WIDTH
HEIGHT = 704
COLS = GRID_WIDTH // CELL
ROWS = HEIGHT // CELL
FPS = 30

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption(f"Песочница пожара [{SERVER_IP}] [{ROLE_LABELS.get(PLAYER_ROLE, PLAYER_ROLE)}]")
clock = pygame.time.Clock()
font = get_ui_font(19)
bigfont = get_ui_font(32)
small_font = get_ui_font(16)

# ================= ТЕКСТУРЫ =================
TEXTURE_DIR = os.path.join(BASE_DIR, "textures")
TEXTURES = {}

for file in os.listdir(TEXTURE_DIR):
    if file.lower().endswith(".png"):
        key = file.lower().replace(".png", "")
        path = os.path.join(TEXTURE_DIR, file)
        try:
            img = pygame.image.load(path).convert_alpha()
            TEXTURES[key] = img
            print(f"✓ loaded texture: {key}")
        except Exception as e:
            print(f"✗ error loading {file}: {e}")

if "fire" not in TEXTURES and os.path.exists(os.path.join(BASE_DIR, "fire.png")):
    try:
        TEXTURES["fire"] = pygame.image.load(os.path.join(BASE_DIR, "fire.png")).convert_alpha()
        print("✓ loaded fire.png from root")
    except:
        pass

def load_textures():
    global TEXTURES, fire_texture
    os.makedirs(TEXTURE_DIR, exist_ok=True)
    TEXTURES = {}
    print(f"🌲 Загрузка текстур из: {TEXTURE_DIR}")

    fire_path = os.path.join(BASE_DIR, "fire.png")
    try:
        fire_texture = pygame.image.load(fire_path).convert_alpha()
        print("   ✓ fire.png загружен")
    except Exception:
        print("   ⚠ fire.png не найден! Создаем заглушку.")
        fire_texture = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
        fire_texture.fill((255, 100, 0, 180))

    for filename in os.listdir(TEXTURE_DIR):
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue
        key = os.path.splitext(filename)[0].lower()
        path = os.path.join(TEXTURE_DIR, filename)
        try:
            img = pygame.image.load(path).convert_alpha()
            if key in ("firecar",):
                TEXTURES["firecar"] = pygame.transform.scale(img, (64, 128))
            elif key in ("road", "road_straight"):
                TEXTURES["road"] = pygame.transform.scale(img, (CELL*4, CELL*4))
            elif key in ("road_right", "road_turn"):
                TEXTURES["road_right"] = pygame.transform.scale(img, (CELL*5, CELL*5))
            elif key == "grass":
                TEXTURES["grass"] = pygame.transform.scale(img, (CELL, CELL))
            else:
                TEXTURES[key] = pygame.transform.scale(img, (CELL, CELL))
            print(f"   ✓ {filename} → {key}")
        except Exception as e:
            print(f"   ✗ {filename}: {e}")
    print(f"✅ Загружено текстур: {len(TEXTURES)}")

load_textures()

# ================= ИНСТРУМЕНТЫ =================
TOOLS = [
    "grass", "tree", "lake", "house", "wall", "floor",
    "wood_floor", "stone", "concrete", "hydrant",
    "road", "road_right",
    "firecar", "ignite"
]

tool_names = {
    "grass": "Трава", "tree": "Дерево", "lake": "Озеро", "house": "Дом",
    "wall": "Стена", "floor": "Пол", "wood_floor": "Дер. пол",
    "stone": "Камень", "concrete": "Бетон", "hydrant": "Гидрант",
    "firecar": "АЦ (Машина)", "ignite": "Очаг",
    "road": "Дорога (Прямая)",
    "road_right": "Дорога (Поворот)"
}

current_tool = "grass"

# ================= КАТЕГОРИИ =================
SECTION_BTN_H = 36
SECTION_BTN_W = PANEL_WIDTH - 30
SECTION_GAP = 8
DROPDOWN_ITEM_H = 30
DROPDOWN_ITEM_GAP = 6
DROPDOWN_TOP_PAD = 8    # отступ сверху от кнопки секции до первого элемента
DROPDOWN_BOTTOM_PAD = 4 # отступ снизу после последнего элемента

SECTION_KEYS = ["cars", "objects", "floor"]

CATEGORIES = {
    "cars": ["firecar"],
    "objects": ["hydrant", "house", "wall", "lake", "tree", "ignite"],
    "floor": ["grass", "floor", "wood_floor", "stone", "concrete"]
}
SECTION_LABELS = {"cars": "Машины", "objects": "Объекты", "floor": "Пол"}

dropdown_open_section = None
last_dropdown_buttons = []
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# Динамически вычисляемые rect-ы для секций и нижних кнопок
# Хранятся между кадрами, чтобы обработчик событий мог их использовать
last_section_buttons = []   # [{"key": ..., "rect": Rect}, ...]
last_save_rect = None
last_load_rect = None
last_reset_rect = None
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<


def calc_dropdown_height(section_key):
    """Высота выпадающего списка для данной секции (включая отступы)."""
    n = len(CATEGORIES[section_key])
    return DROPDOWN_TOP_PAD + n * DROPDOWN_ITEM_H + (n - 1) * DROPDOWN_ITEM_GAP + DROPDOWN_BOTTOM_PAD


# ================= СЕТЬ =================
def recv_exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk: return None
        data += chunk
    return data

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    print(f"🔄 Подключение к {SERVER_IP}:{SERVER_PORT}...")
    client.connect((SERVER_IP, SERVER_PORT))
    auth_data = {'type': 'AUTH', 'password': SERVER_PASSWORD, 'role': PLAYER_ROLE}
    msg = json.dumps(auth_data).encode('utf-8')
    client.sendall(struct.pack('>I', len(msg)) + msg)

    client.settimeout(5.0)
    raw_msglen = recv_exact(client, 4)
    msglen = struct.unpack('>I', raw_msglen)[0]
    payload = recv_exact(client, msglen)
    auth_reply = json.loads(payload.decode("utf-8"))
    if auth_reply.get("type") != "AUTH_OK":
        raise RuntimeError(auth_reply.get("reason", "Ошибка авторизации"))
    client.settimeout(None)
    print(f"✅ Авторизация успешна. Роль: {ROLE_LABELS.get(PLAYER_ROLE, PLAYER_ROLE)}")
except Exception as e:
    print(f"❌ Ошибка подключения: {e}")
    pygame.quit()
    sys.exit()

def send_to_server(data):
    try:
        msg = json.dumps(data).encode('utf-8')
        client.sendall(struct.pack('>I', len(msg)) + msg)
    except Exception: pass

def receive_thread():
    global server_grid, edit_mode, running_sim
    while True:
        try:
            raw = recv_exact(client, 4)
            if not raw: break
            msglen = struct.unpack('>I', raw)[0]
            data = recv_exact(client, msglen)
            if not data: break
            state = json.loads(data.decode('utf-8'))
            server_grid = state['grid']
            edit_mode = state['edit_mode']
            running_sim = state['running_sim']
        except Exception:
            print("❌ Связь с сервером потеряна")
            os._exit(1)

server_grid = [[[0, 0, "empty"] for _ in range(COLS)] for _ in range(ROWS)]
edit_mode = True
running_sim = False
threading.Thread(target=receive_thread, daemon=True).start()

# ================= СОХРАНЕНИЕ / ЗАГРУЗКА =================
def fit_grid(grid, src_rows, src_cols):
    new_grid = [[[0, 0, "empty"] for _ in range(COLS)] for _ in range(ROWS)]
    for y in range(min(src_rows, ROWS)):
        for x in range(min(src_cols, COLS)):
            try: new_grid[y][x] = grid[y][x]
            except (IndexError, KeyError): pass
    return new_grid

def save_map():
    try:
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON карты", "*.json"), ("Все файлы", "*.*")],
            initialdir=MAPS_DIR, title="Сохранить карту"
        )
        root.destroy()
    except Exception as e:
        print(f"❌ Ошибка диалога сохранения: {e}"); return
    if not filepath: return
    try:
        map_data = {"version": 1, "cols": COLS, "rows": ROWS, "grid": server_grid}
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(map_data, f, ensure_ascii=False)
        print(f"💾 Карта сохранена: {os.path.basename(filepath)}")
    except Exception as e:
        print(f"❌ Ошибка сохранения файла: {e}")

def load_map():
    try:
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        filepath = filedialog.askopenfilename(
            filetypes=[("JSON карты", "*.json"), ("Все файлы", "*.*")],
            initialdir=MAPS_DIR, title="Загрузить карту"
        )
        root.destroy()
    except Exception as e:
        print(f"❌ Ошибка диалога загрузки: {e}"); return
    if not filepath: return
    try:
        with open(filepath, 'r', encoding='utf-8') as f: map_data = json.load(f)
        if isinstance(map_data, dict) and "grid" in map_data:
            grid = map_data["grid"]
            src_cols, src_rows = map_data.get("cols", COLS), map_data.get("rows", ROWS)
            if src_cols != COLS or src_rows != ROWS:
                print(f"⚠️  Размер карты ({src_cols}×{src_rows}) отличается, подгоняю под {COLS}×{ROWS}")
                grid = fit_grid(grid, src_rows, src_cols)
        elif isinstance(map_data, list): grid = map_data
        else: print("❌ Неизвестный формат файла"); return
        send_to_server({'type': 'LOAD_MAP', 'grid': grid})
        print(f"📂 Карта {os.path.basename(filepath)} отправлена на сервер")
    except Exception as e:
        print(f"❌ Ошибка загрузки файла: {e}")

# ================= ОТРИСОВКА =================
def draw_textured_cell(surface, rect, fuel, intensity, ctype, gx, gy):
    x, y = rect.x, rect.y

    if ctype == "firecar_root":
        if "firecar" in TEXTURES:
            surface.blit(TEXTURES["firecar"], (x, y))
        else:
            pygame.draw.rect(surface, (200, 30, 30), (x, y, 64, 128))
        return
    elif ctype == "firecar_part":
        return

    if ctype == "road_straight_root":
        if "road" in TEXTURES:
            surface.blit(TEXTURES["road"], (x, y))
        else:
            pygame.draw.rect(surface, (60, 60, 65), (x, y, CELL*4, CELL*4))
        return
    elif ctype == "road_straight_part":
        return

    if ctype == "road_turn_root":
        if "road_right" in TEXTURES:
            surface.blit(TEXTURES["road_right"], (x, y))
        else:
            pygame.draw.rect(surface, (60, 60, 65), (x, y, CELL*5, CELL*5))
        return
    elif ctype == "road_turn_part":
        return

    if intensity > 8:
        scaled = pygame.transform.scale(fire_texture, (CELL, CELL))
        offset_x = random.randint(-3, 3)
        offset_y = -random.randint(0, 5) - intensity // 10
        surface.blit(scaled, (x + offset_x, y + offset_y))
        return

    texture_key = ctype
    if texture_key.endswith("_root"):
        texture_key = texture_key.replace("_root", "")
    if texture_key.endswith("_part"):
        return

    if texture_key in ("road_straight", "road"):
        texture_key = "road"
    elif texture_key in ("road_turn", "road_right"):
        texture_key = "road_right"
    elif texture_key == "floor" and "wood_floor" in TEXTURES:
        texture_key = "wood_floor"
    elif texture_key == "lake" and "water" in TEXTURES:
        texture_key = "water"

    if texture_key in TEXTURES:
        surface.blit(TEXTURES[texture_key], rect)
        return

    if texture_key in ("trunk",):
        color = (94, 54, 32)
    elif texture_key in ("foliage",):
        color = (18, 75, 35)
    elif texture_key in ("grass",):
        color = (38, 135, 48)
    elif texture_key in ("water", "lake"):
        color = (18, 95, 185)
    elif texture_key == "stone":
        color = (100, 100, 105)
    elif texture_key == "concrete":
        color = (85, 85, 95)
    elif texture_key == "hydrant":
        color = (180, 20, 20)
    elif texture_key in ("wall", "floor", "wood_floor") and fuel > 20:
        color = (158, 112, 52)
    elif texture_key in ("road", "road_right"):
        color = (60, 60, 65)
    else:
        color = (30, 25, 20)

    pygame.draw.rect(surface, color, rect)

def draw_grid():
    for y in range(ROWS):
        for x in range(COLS):
            fuel, intensity, ctype = server_grid[y][x]
            rect = pygame.Rect(x * CELL, y * CELL, CELL, CELL)
            draw_textured_cell(screen, rect, fuel, intensity, ctype, x, y)


# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# НОВАЯ draw_ui — динамический расчёт позиций
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
def draw_ui():
    global last_dropdown_buttons, last_section_buttons
    global last_save_rect, last_load_rect, last_reset_rect

    last_dropdown_buttons = []
    last_section_buttons = []

    pygame.draw.rect(screen, (25, 25, 35), (GRID_WIDTH, 0, PANEL_WIDTH, HEIGHT))
    pygame.draw.line(screen, (50, 50, 60), (GRID_WIDTH, 0), (GRID_WIDTH, HEIGHT), 3)

    mouse_pos = pygame.mouse.get_pos()

    # --- Динамический расчёт Y для каждой секции ---
    cur_y = 18  # начальная Y

    for idx, key in enumerate(SECTION_KEYS):
        # Рисуем кнопку секции
        rect = pygame.Rect(GRID_WIDTH + 15, cur_y, SECTION_BTN_W, SECTION_BTN_H)
        last_section_buttons.append({"key": key, "rect": rect})

        active = (dropdown_open_section == key)
        hover = rect.collidepoint(mouse_pos)
        color = (70, 100, 170) if active else (75, 85, 120) if hover else (65, 75, 110)
        border = (255, 215, 80) if active else (150, 160, 190) if hover else (130, 140, 170)
        pygame.draw.rect(screen, color, rect, border_radius=8)
        pygame.draw.rect(screen, border, rect, width=3 if active or hover else 1, border_radius=8)

        # Стрелочка ▼ / ▲
        arrow = "▲" if active else "▼"
        arrow_surf = small_font.render(arrow, True, (255, 255, 255))
        screen.blit(arrow_surf, (rect.right - 24, rect.y + 8))

        txt = small_font.render(SECTION_LABELS[key], True, (255, 255, 255))
        screen.blit(txt, (rect.x + 12, rect.y + 8))

        cur_y += SECTION_BTN_H  # сдвигаемся вниз на высоту кнопки

        # Если эта секция раскрыта — рисуем dropdown и сдвигаем cur_y
        if dropdown_open_section == key:
            items = CATEGORIES[key]
            cur_y += DROPDOWN_TOP_PAD

            for i, item in enumerate(items):
                item_rect = pygame.Rect(GRID_WIDTH + 20, cur_y,
                                        PANEL_WIDTH - 40, DROPDOWN_ITEM_H)
                item_hover = item_rect.collidepoint(mouse_pos)
                # Подсветка выбранного инструмента
                is_selected = (current_tool == item)
                if is_selected:
                    bg_color = (110, 130, 180)
                elif item_hover:
                    bg_color = (95, 95, 140)
                else:
                    bg_color = (75, 80, 110)

                pygame.draw.rect(screen, bg_color, item_rect, border_radius=6)
                border_c = (255, 215, 80) if is_selected else \
                           (200, 200, 200) if item_hover else (150, 150, 170)
                pygame.draw.rect(screen, border_c, item_rect, 1, border_radius=6)

                tx = item_rect.x + 8
                if item in TEXTURES:
                    thumb = pygame.transform.scale(TEXTURES[item], (24, 24))
                    screen.blit(thumb, (item_rect.x + 6, item_rect.y + 3))
                    tx += 30
                screen.blit(small_font.render(tool_names.get(item, item), True, (255, 255, 255)),
                            (tx, item_rect.y + 6))

                last_dropdown_buttons.append({"rect": item_rect, "tool": item,
                                              "section": key})

                cur_y += DROPDOWN_ITEM_H + DROPDOWN_ITEM_GAP

            # убираем лишний GAP после последнего элемента, добавляем BOTTOM_PAD
            cur_y -= DROPDOWN_ITEM_GAP
            cur_y += DROPDOWN_BOTTOM_PAD

        # отступ перед следующей секцией
        cur_y += SECTION_GAP

    # --- Кнопки сохранения / загрузки / сброса ---
    # Добавляем отступ перед нижними кнопками
    cur_y += 16
    half_w = (PANEL_WIDTH - 30) // 2

    last_save_rect = pygame.Rect(GRID_WIDTH + 15, cur_y, half_w, 36)
    last_load_rect = pygame.Rect(GRID_WIDTH + 15 + half_w + 10, cur_y, half_w, 36)

    hover_s = last_save_rect.collidepoint(mouse_pos)
    pygame.draw.rect(screen, (50, 160, 80) if hover_s else (40, 120, 60),
                     last_save_rect, border_radius=8)
    st = small_font.render("Сохранить", True, (255, 255, 255))
    screen.blit(st, st.get_rect(center=last_save_rect.center))

    hover_l = last_load_rect.collidepoint(mouse_pos)
    pygame.draw.rect(screen, (50, 100, 180) if hover_l else (35, 75, 140),
                     last_load_rect, border_radius=8)
    lt = small_font.render("Загрузить", True, (255, 255, 255))
    screen.blit(lt, lt.get_rect(center=last_load_rect.center))

    cur_y += 44
    last_reset_rect = pygame.Rect(GRID_WIDTH + 15, cur_y, PANEL_WIDTH - 30, 38)

    hover_r = last_reset_rect.collidepoint(mouse_pos)
    pygame.draw.rect(screen, (255, 70, 70) if hover_r else (190, 50, 50),
                     last_reset_rect, border_radius=9)
    rt = small_font.render("ОЧИСТИТЬ ВСЁ", True, (255, 255, 255))
    screen.blit(rt, rt.get_rect(center=last_reset_rect.center))

    # Подсказка внизу
    hint = small_font.render("SPACE — старт/пауза • R — сброс", True, (170, 180, 200))
    screen.blit(hint, (20, HEIGHT - 26))


# ================= ГЛАВНЫЙ ЦИКЛ =================
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            if mods & pygame.KMOD_CTRL:
                if event.key == pygame.K_s: save_map()
                elif event.key == pygame.K_l: load_map()
            else:
                if event.key == pygame.K_SPACE: send_to_server({'type': 'SPACE'})
                if event.key == pygame.K_r: send_to_server({'type': 'R'})
                key_map = {
                    pygame.K_1: "grass", pygame.K_2: "tree", pygame.K_3: "lake",
                    pygame.K_4: "house", pygame.K_5: "wall", pygame.K_6: "floor",
                    pygame.K_7: "wood_floor", pygame.K_8: "stone", pygame.K_9: "hydrant",
                    pygame.K_c: "concrete", pygame.K_m: "firecar",
                    pygame.K_MINUS: "ignite", pygame.K_KP_MINUS: "ignite",
                    pygame.K_q: "road",
                    pygame.K_e: "road_right"
                }
                if event.key in key_map: current_tool = key_map[event.key]

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if mx > GRID_WIDTH:  # клик по UI панели
                handled = False

                # --- Клик по кнопкам секций ---
                for sb in last_section_buttons:
                    if sb['rect'].collidepoint(event.pos):
                        key = sb['key']
                        if dropdown_open_section == key:
                            dropdown_open_section = None
                        else:
                            dropdown_open_section = key
                        handled = True
                        break
                if handled:
                    continue

                # --- Клик по элементам выпадающего списка ---
                for db in last_dropdown_buttons:
                    if db['rect'].collidepoint(event.pos):
                        picked = db['tool']
                        current_tool = picked
                        section = db.get('section', '')
                        if section == 'floor':
                            send_to_server({'type': 'FILL_BASE', 'tool': picked})
                        else:
                            send_to_server({'type': 'SELECT_TOOL', 'tool': picked})
                        handled = True
                        break
                if handled:
                    continue

                # --- Кнопки сохранения / загрузки / сброса ---
                if last_save_rect and last_save_rect.collidepoint(event.pos):
                    save_map(); continue
                if last_load_rect and last_load_rect.collidepoint(event.pos):
                    load_map(); continue
                if last_reset_rect and last_reset_rect.collidepoint(event.pos):
                    send_to_server({'type': 'R'}); continue

    if edit_mode and pygame.mouse.get_pressed()[0]:
        mx, my = pygame.mouse.get_pos()
        if mx < GRID_WIDTH:
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
sys.exit()