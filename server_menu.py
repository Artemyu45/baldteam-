import json
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
from collections import deque

import pygame

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if load_dotenv is not None:
    load_dotenv(os.path.join(BASE_DIR, ".env"))

ROLE_KEYS = ["РТП", "НШ", "БР", "Диспетчер"]


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


def recv_exact(sock, size, stop_event=None, max_wait_sec=4.0):
    data = b""
    started = time.time()
    while len(data) < size:
        if stop_event is not None and stop_event.is_set():
            return None
        try:
            chunk = sock.recv(size - len(data))
        except socket.timeout:
            if time.time() - started >= max_wait_sec:
                return None
            continue
        if not chunk:
            return None
        data += chunk
    return data


def run_menu():
    default_host = os.getenv("SERVER_HOST", "0.0.0.0")
    default_port = os.getenv("SERVER_PORT", "5555")
    default_max_players = os.getenv("MAX_PLAYERS", "5")
    default_password = os.getenv("SERVER_PASSWORD", "my_super_password")

    pygame.init()
    menu_w, menu_h = 800, 470
    screen = pygame.display.set_mode((menu_w, menu_h))
    pygame.display.set_caption("Песочница пожара - Настройки сервера")
    clock = pygame.time.Clock()
    title_font = get_ui_font(36, bold=True)
    font = get_ui_font(24)
    hint_font = get_ui_font(18)

    fields = [
        {"label": "Host", "value": str(default_host), "secret": False},
        {"label": "Port", "value": str(default_port), "secret": False},
        {"label": "Макс. игроков", "value": str(default_max_players), "secret": False},
        {"label": "Пароль", "value": str(default_password), "secret": True},
    ]
    active = 0
    error = ""

    while True:
        start_rect = pygame.Rect(145, 382, 230, 58)
        quit_rect = pygame.Rect(425, 382, 230, 58)
        input_rects = [pygame.Rect(310, 105 + i * 68, 400, 44) for i in range(len(fields))]

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if start_rect.collidepoint(event.pos):
                    try:
                        new_port = int(fields[1]["value"])
                        new_max_players = int(fields[2]["value"])
                        if not (1 <= new_port <= 65535):
                            raise ValueError
                        if new_max_players < 1:
                            raise ValueError
                        return {
                            "SERVER_HOST": fields[0]["value"],
                            "SERVER_PORT": str(new_port),
                            "MAX_PLAYERS": str(new_max_players),
                            "SERVER_PASSWORD": fields[3]["value"],
                        }
                    except ValueError:
                        error = "Port: 1-65535, Макс. игроков: >= 1"
                elif quit_rect.collidepoint(event.pos):
                    pygame.quit()
                    return None
                else:
                    for i, rect in enumerate(input_rects):
                        if rect.collidepoint(event.pos):
                            active = i
                            break
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    active = (active + 1) % len(fields)
                elif event.key == pygame.K_RETURN:
                    try:
                        new_port = int(fields[1]["value"])
                        new_max_players = int(fields[2]["value"])
                        if not (1 <= new_port <= 65535):
                            raise ValueError
                        if new_max_players < 1:
                            raise ValueError
                        return {
                            "SERVER_HOST": fields[0]["value"],
                            "SERVER_PORT": str(new_port),
                            "MAX_PLAYERS": str(new_max_players),
                            "SERVER_PASSWORD": fields[3]["value"],
                        }
                    except ValueError:
                        error = "Port: 1-65535, Макс. игроков: >= 1"
                elif event.key == pygame.K_BACKSPACE:
                    fields[active]["value"] = fields[active]["value"][:-1]
                else:
                    if event.unicode.isprintable() and len(fields[active]["value"]) < 64:
                        fields[active]["value"] += event.unicode

        screen.fill((22, 27, 40))
        screen.blit(title_font.render("Меню сервера", True, (244, 246, 255)), (258, 26))
        screen.blit(hint_font.render("TAB - следующее поле, ENTER - запуск", True, (170, 188, 220)), (244, 72))

        for i, field in enumerate(fields):
            y = 105 + i * 68
            screen.blit(font.render(field["label"], True, (220, 225, 236)), (95, y + 8))
            color = (95, 160, 255) if i == active else (78, 90, 120)
            pygame.draw.rect(screen, color, input_rects[i], width=2, border_radius=7)
            shown = "*" * len(field["value"]) if field["secret"] else field["value"]
            screen.blit(font.render(shown, True, (245, 245, 245)), (input_rects[i].x + 10, input_rects[i].y + 9))

        pygame.draw.rect(screen, (40, 160, 80), start_rect, border_radius=8)
        pygame.draw.rect(screen, (170, 60, 60), quit_rect, border_radius=8)
        screen.blit(font.render("Запустить", True, (255, 255, 255)), (198, 399))
        screen.blit(font.render("Выход", True, (255, 255, 255)), (505, 399))

        if error:
            screen.blit(hint_font.render(error, True, (255, 120, 120)), (240, 352))

        pygame.display.flip()
        clock.tick(60)


def start_server_process(config):
    env = os.environ.copy()
    env.update(config)
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, "server.py")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def log_reader_loop(process, state, stop_event):
    connect_re = re.compile(r"\[\+\] Игрок (.+) вошел в игру\. Роль: (.+)")
    disconnect_re = re.compile(r"\[-\] Игрок отключен: (.+)")

    for line in process.stdout:
        if stop_event.is_set():
            return

        text = line.rstrip("\n")
        if not text:
            continue
            
        # Выводим лог сервера прямо в консоль
        print(text)

        with state["lock"]:
            m = connect_re.search(text)
            if m:
                addr = m.group(1).strip()
                role = m.group(2).strip()
                if addr == state.get("observer_addr"):
                    continue
                state["players"][addr] = role
                continue

            m = disconnect_re.search(text)
            if m:
                addr = m.group(1).strip()
                if addr == state.get("observer_addr"):
                    continue
                if addr in state["players"]:
                    del state["players"][addr]


def observer_loop(config, state, stop_event):
    host = config["SERVER_HOST"]
    if host in ("0.0.0.0", "::", ""):
        host = "127.0.0.1"
    port = int(config["SERVER_PORT"])
    password = config["SERVER_PASSWORD"]

    while not stop_event.is_set():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(2.0)
            sock.connect((host, port))

            auth_data = {"type": "AUTH", "password": password, "role": "dispatcher"}
            payload = json.dumps(auth_data).encode("utf-8")
            sock.sendall(struct.pack(">I", len(payload)) + payload)

            raw_len = recv_exact(sock, 4, stop_event=stop_event)
            if not raw_len:
                raise RuntimeError("Нет ответа авторизации")
            msg_len = struct.unpack(">I", raw_len)[0]
            auth_reply = recv_exact(sock, msg_len, stop_event=stop_event)
            if not auth_reply:
                raise RuntimeError("Неполный ответ авторизации")
            auth_obj = json.loads(auth_reply.decode("utf-8"))
            if auth_obj.get("type") != "AUTH_OK":
                raise RuntimeError(auth_obj.get("reason", "AUTH_FAIL"))

            with state["lock"]:
                state["observer_connected"] = True
                state["observer_error"] = ""
                state["observer_addr"] = str(sock.getsockname())
                state["players"].pop(state["observer_addr"], None)

            sock.settimeout(0.5)
            while not stop_event.is_set():
                raw_len = recv_exact(sock, 4, stop_event=stop_event, max_wait_sec=3.0)
                if not raw_len:
                    break
                msg_len = struct.unpack(">I", raw_len)[0]
                if msg_len > 1_500_000:
                    break
                raw_state = recv_exact(sock, msg_len, stop_event=stop_event, max_wait_sec=3.0)
                if not raw_state:
                    break
                msg = json.loads(raw_state.decode("utf-8"))
                if "grid" in msg:
                    with state["lock"]:
                        state["grid"] = msg["grid"]
                        state["last_grid_update"] = time.time()

        except Exception as exc:
            with state["lock"]:
                state["observer_connected"] = False
                state["observer_error"] = str(exc)
                state["observer_addr"] = None
        finally:
            try:
                sock.close()
            except Exception:
                pass

        if not stop_event.is_set():
            time.sleep(1.0)


def cell_color(cell):
    fuel, intensity, ctype = cell
    if intensity > 0:
        if intensity > 30:
            return (255, 120, 20)
        return (255, 180, 50)
    if ctype == "water":
        return (25, 100, 200)
    if ctype == "tree":
        return (30, 120, 40)
    if ctype == "grass":
        return (50, 165, 70)
    if ctype == "wall":
        return (120, 90, 70)
    if ctype == "floor":
        return (145, 120, 80)
    if fuel > 0:
        return (70, 90, 70)
    return (25, 25, 25)


def draw_minimap(surface, grid):
    if not grid:
        surface.fill((20, 20, 20))
        return

    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    if rows == 0 or cols == 0:
        surface.fill((20, 20, 20))
        return

    cw = max(1, surface.get_width() // cols)
    ch = max(1, surface.get_height() // rows)
    surface.fill((15, 15, 15))
    for y in range(rows):
        for x in range(cols):
            pygame.draw.rect(surface, cell_color(grid[y][x]), (x * cw, y * ch, cw, ch))


def role_counts(players):
    counts = {key: 0 for key in ROLE_KEYS}
    for role in players.values():
        if role in counts:
            counts[role] += 1
    return counts


def dashboard_loop(config, process):
    pygame.init()
    screen = pygame.display.set_mode((1200, 760))
    pygame.display.set_caption("Сервер - Панель мониторинга")
    clock = pygame.time.Clock()

    title_font = get_ui_font(34, bold=True)
    font = get_ui_font(22)
    small_font = get_ui_font(18)

    state = {
        "lock": threading.Lock(),
        "grid": None,
        "players": {},
        "observer_connected": False,
        "observer_error": "",
        "observer_addr": None,
        "last_grid_update": 0.0,
    }
    stop_event = threading.Event()

    threading.Thread(target=log_reader_loop, args=(process, state, stop_event), daemon=True).start()
    threading.Thread(target=observer_loop, args=(config, state, stop_event), daemon=True).start()

    stop_rect = pygame.Rect(920, 38, 220, 56)
    map_surface = pygame.Surface((420, 308))

    running = True
    while running:
        server_alive = process.poll() is None

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if stop_rect.collidepoint(event.pos):
                    if server_alive:
                        try:
                            process.terminate()
                        except Exception:
                            pass
                    else:
                        running = False

        with state["lock"]:
            grid = state["grid"]
            players = dict(state["players"])
            observer_connected = state["observer_connected"]
            observer_error = state["observer_error"]
            last_grid_update = state["last_grid_update"]

        draw_minimap(map_surface, grid)
        counts = role_counts(players)

        screen.fill((16, 22, 34))
        screen.blit(title_font.render("Админ-панель сервера", True, (240, 245, 255)), (34, 34))
        pygame.draw.rect(screen, (185, 62, 62), stop_rect, border_radius=10)
        button_text = "Остановить сервер" if server_alive else "Закрыть панель"
        screen.blit(font.render(button_text, True, (255, 255, 255)), (934, 54))

        status = "Работает" if server_alive else "Остановлен"
        status_col = (90, 220, 120) if server_alive else (240, 110, 110)
        screen.blit(font.render(f"Статус: {status}", True, status_col), (40, 92))
        screen.blit(small_font.render(f"Host: {config['SERVER_HOST']}:{config['SERVER_PORT']}", True, (185, 200, 225)), (40, 124))
        screen.blit(small_font.render(f"Лимит игроков: {config['MAX_PLAYERS']}", True, (185, 200, 225)), (40, 146))

        obs_status = "OK" if observer_connected else "OFF"
        obs_col = (120, 220, 140) if observer_connected else (240, 130, 130)
        screen.blit(small_font.render(f"Канал карты: {obs_status}", True, obs_col), (40, 170))
        if observer_error:
            screen.blit(small_font.render(f"Ошибка канала: {observer_error[:80]}", True, (240, 130, 130)), (40, 192))
        if last_grid_update > 0:
            dt = time.time() - last_grid_update
            lag_col = (120, 220, 140) if dt < 1.0 else (255, 190, 120)
            screen.blit(small_font.render(f"Обновление карты: {dt:.1f}с назад", True, lag_col), (40, 214))

        map_rect = pygame.Rect(40, 230, 420, 308)
        pygame.draw.rect(screen, (70, 85, 112), map_rect, width=2, border_radius=8)
        screen.blit(map_surface, (map_rect.x, map_rect.y))
        screen.blit(small_font.render("Мини-карта (real-time)", True, (200, 214, 236)), (40, 548))

        panel_x = 500
        screen.blit(font.render(f"Подключено: {len(players)}", True, (240, 245, 255)), (panel_x, 230))
        screen.blit(small_font.render(
            f"РТП: {counts['РТП']} | НШ: {counts['НШ']} | БР: {counts['БР']} | Диспетчер: {counts['Диспетчер']}",
            True,
            (188, 206, 230),
        ), (panel_x, 264))

        screen.blit(font.render("Игроки", True, (240, 245, 255)), (panel_x, 304))
        y = 338
        if players:
            for addr, role in list(players.items())[:12]:
                line = f"{role}: {addr}"
                screen.blit(small_font.render(line, True, (205, 217, 235)), (panel_x, y))
                y += 24
        else:
            screen.blit(small_font.render("Нет подключений", True, (170, 182, 205)), (panel_x, y))

        pygame.display.flip()
        clock.tick(30)

    # Завершающий блок, который вы скинули
    stop_event.set()
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
    pygame.quit()


def main():
    config = run_menu()
    if config is None:
        return
    process = start_server_process(config)
    dashboard_loop(config, process)


if __name__ == "__main__":
    main()