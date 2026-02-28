import os
import sys
import socket
import threading
import json
import struct
import random
import base64
import pygame
import tkinter as tk
from tkinter import filedialog
from radio_core import get_audio_stream, record

# ================= НАСТРОЙКИ =================
SERVER_IP = '127.0.0.1'
SERVER_PORT = 5555
SERVER_PASSWORD = 'my_super_password'
CELL = 16
GRID_WIDTH, PANEL_WIDTH = 960, 250
WIDTH, HEIGHT = GRID_WIDTH + PANEL_WIDTH, 704
COLS, ROWS = GRID_WIDTH // CELL, HEIGHT // CELL
FPS = 30

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Fire Sandbox + Radio")
clock = pygame.time.Clock()
font = pygame.font.SysFont("arial", 18)
is_talking = False

# ================= СЕТЬ =================
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((SERVER_IP, SERVER_PORT))


def send_to_server(data):
    try:
        msg = json.dumps(data).encode('utf-8')
        client.sendall(struct.pack('>I', len(msg)) + msg)
    except:
        pass


send_to_server({'type': 'AUTH', 'password': SERVER_PASSWORD, 'role': 'rtp'})


# ================= ПОТОК РАДИО =================
def audio_thread():
    global is_talking
    try:
        stream = get_audio_stream()
        while True:
            if is_talking:
                data = record(stream, 1024)
                if data:
                    encoded = base64.b64encode(data).decode('utf-8')
                    send_to_server({'type': 'VOICE', 'data': encoded})
            else:
                pygame.time.wait(20)
    except Exception as e:
        print(f"Аудио ошибка: {e}")


threading.Thread(target=audio_thread, daemon=True).start()

# ================= ОСНОВНАЯ ЛОГИКА =================
server_grid = [[[0, 0, "empty"] for _ in range(COLS)] for _ in range(ROWS)]
edit_mode, running_sim = True, False
current_tool = "grass"


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


def draw_ui():
    pygame.draw.rect(screen, (30, 30, 40), (GRID_WIDTH, 0, PANEL_WIDTH, HEIGHT))
    # Индикатор рации
    color = (255, 50, 50) if is_talking else (100, 100, 100)
    pygame.draw.circle(screen, color, (GRID_WIDTH + 20, 30), 8)
    txt = "РАЦИЯ: В ЭФИРЕ (F)" if is_talking else "РАЦИЯ: ГОТОВ (F)"
    screen.blit(font.render(txt, True, (255, 255, 255)), (GRID_WIDTH + 40, 20))
    screen.blit(font.render(f"Инструмент: {current_tool}", True, (200, 200, 200)), (GRID_WIDTH + 20, 60))


while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT: sys.exit()
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_f: is_talking = True
            if event.key == pygame.K_SPACE: send_to_server({'type': 'SPACE'})
            if event.key == pygame.K_r: send_to_server({'type': 'R'})
            if event.key == pygame.K_1: current_tool = "grass"
            if event.key == pygame.K_2: current_tool = "tree"
            if event.key == pygame.K_8: current_tool = "ignite"
        if event.type == pygame.KEYUP:
            if event.key == pygame.K_f: is_talking = False

    if edit_mode and pygame.mouse.get_pressed()[0]:
        mx, my = pygame.mouse.get_pos()
        if mx < GRID_WIDTH:
            send_to_server({'type': 'CLICK', 'x': mx // CELL, 'y': my // CELL, 'tool': current_tool})

    screen.fill((0, 0, 0))
    for y in range(ROWS):
        for x in range(COLS):
            fuel, intensity, ctype = server_grid[y][x]
            if intensity > 8:
                color = (255, 100, 0)
            elif ctype == "grass":
                color = (34, 139, 34)
            elif ctype == "trunk":
                color = (101, 67, 33)
            elif ctype == "foliage":
                color = (0, 100, 0)
            elif ctype == "water":
                color = (0, 105, 148)
            else:
                color = (20, 20, 20)
            pygame.draw.rect(screen, color, (x * CELL, y * CELL, CELL, CELL))

    draw_ui()
    pygame.display.flip()
    clock.tick(FPS)