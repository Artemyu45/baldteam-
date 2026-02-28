import pygame
import sys
import socket
import threading
import json
import struct
import random
import os
import base64
from radio_core import record, get_audio_stream

# ================= НАСТРОЙКИ =================
SERVER_IP = '127.0.0.1'
SERVER_PORT = 5555
SERVER_PASSWORD = 'my_super_password'
CELL = 16
GRID_WIDTH, PANEL_WIDTH = 960, 200
WIDTH, HEIGHT = GRID_WIDTH + PANEL_WIDTH, 704
COLS, ROWS = GRID_WIDTH // CELL, HEIGHT // CELL
FPS = 30

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Fire Sandbox + Radio")
clock = pygame.time.Clock()
font = pygame.font.SysFont("consolas", 18)

# Состояние
server_grid = [[[0, 0, "empty"] for _ in range(COLS)] for _ in range(ROWS)]
edit_mode, running_sim, is_talking = True, False, False
current_tool = "grass"
TOOLS = ["grass", "tree", "lake", "house", "wall", "floor", "stone", "ignite"]

# Сеть
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((SERVER_IP, SERVER_PORT))


def send(data):
    msg = json.dumps(data).encode('utf-8')
    client.sendall(struct.pack('>I', len(msg)) + msg)


send({'type': 'AUTH', 'password': SERVER_PASSWORD})


def audio_thread():
    stream = get_audio_stream()
    while True:
        if is_talking:
            raw_data = record(stream, 1024)
            if raw_data:
                send({'type': 'VOICE', 'data': base64.b64encode(raw_data).decode('utf-8')})
        else:
            pygame.time.wait(20)


threading.Thread(target=audio_thread, daemon=True).start()


def recv_thread():
    global server_grid, edit_mode, running_sim
    while True:
        try:
            raw = client.recv(4)
            if not raw: break
            length = struct.unpack('>I', raw)[0]
            data = b''
            while len(data) < length: data += client.recv(length - len(data))
            msg = json.loads(data.decode('utf-8'))
            server_grid, edit_mode, running_sim = msg['grid'], msg['edit_mode'], msg['running_sim']
        except:
            break


threading.Thread(target=recv_thread, daemon=True).start()


def draw():
    for y in range(ROWS):
        for x in range(COLS):
            fuel, intensity, ctype = server_grid[y][x]
            rect = pygame.Rect(x * CELL, y * CELL, CELL, CELL)
            if intensity > 5:
                color = (255, random.randint(50, 150), 0)
            elif ctype == "grass":
                color = (30, 120, 30)
            elif ctype == "trunk":
                color = (80, 50, 20)
            elif ctype == "foliage":
                color = (20, 80, 20)
            elif ctype == "water":
                color = (0, 100, 200)
            else:
                color = (20, 20, 25)
            pygame.draw.rect(screen, color, rect)

    # UI
    pygame.draw.rect(screen, (40, 40, 50), (GRID_WIDTH, 0, PANEL_WIDTH, HEIGHT))
    txt = "РАЦИЯ: ВКЛ" if is_talking else "РАЦИЯ: ВЫКЛ (F)"
    col = (0, 255, 0) if is_talking else (200, 200, 200)
    screen.blit(font.render(txt, True, col), (GRID_WIDTH + 10, 20))
    screen.blit(font.render(f"Инструмент: {current_tool}", True, (255, 255, 255)), (GRID_WIDTH + 10, 60))


# Цикл
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT: sys.exit()
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_f: is_talking = True
            if event.key == pygame.K_SPACE: send({'type': 'SPACE'})
            if event.key == pygame.K_1: current_tool = "grass"
            if event.key == pygame.K_2: current_tool = "tree"
            if event.key == pygame.K_8: current_tool = "ignite"
        if event.type == pygame.KEYUP:
            if event.key == pygame.K_f: is_talking = False

    if edit_mode and pygame.mouse.get_pressed()[0]:
        mx, my = pygame.mouse.get_pos()
        if mx < GRID_WIDTH: send({'type': 'CLICK', 'x': mx // CELL, 'y': my // CELL, 'tool': current_tool})

    screen.fill((0, 0, 0))
    draw()
    pygame.display.flip()
    clock.tick(FPS)