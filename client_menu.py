import os
import sys
import subprocess
import pygame

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if load_dotenv is not None:
    load_dotenv(os.path.join(BASE_DIR, ".env"))

ROLES = ["rtp", "nsh", "br", "dispatcher"]
ROLE_LABELS = {
    "rtp": "РТП",
    "nsh": "НШ",
    "br": "БР",
    "dispatcher": "Диспетчер",
}


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


def run_menu():
    default_ip = os.getenv("SERVER_IP", "127.0.0.1")
    default_port = os.getenv("SERVER_PORT", "5555")
    default_password = os.getenv("SERVER_PASSWORD", "my_super_password")
    default_role = os.getenv("PLAYER_ROLE", "rtp").lower()

    pygame.init()
    menu_w, menu_h = 760, 470
    screen = pygame.display.set_mode((menu_w, menu_h))
    pygame.display.set_caption("Песочница пожара - Настройки клиента")
    clock = pygame.time.Clock()
    title_font = get_ui_font(36, bold=True)
    font = get_ui_font(24)
    hint_font = get_ui_font(18)

    fields = [
        {"label": "IP сервера", "value": str(default_ip), "secret": False},
        {"label": "Порт сервера", "value": str(default_port), "secret": False},
        {"label": "Пароль", "value": str(default_password), "secret": True},
    ]
    role_index = ROLES.index(default_role) if default_role in ROLES else 0
    active = 0
    error = ""

    while True:
        start_rect = pygame.Rect(130, 390, 220, 56)
        quit_rect = pygame.Rect(410, 390, 220, 56)
        input_rects = [pygame.Rect(270, 108 + i * 68, 360, 48) for i in range(len(fields))]

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if start_rect.collidepoint(event.pos):
                    try:
                        port = int(fields[1]["value"])
                        if not (1 <= port <= 65535):
                            raise ValueError
                        pygame.quit()
                        return {
                            "SERVER_IP": fields[0]["value"],
                            "SERVER_PORT": str(port),
                            "SERVER_PASSWORD": fields[2]["value"],
                            "PLAYER_ROLE": ROLES[role_index],
                        }
                    except ValueError:
                        error = "Порт должен быть числом от 1 до 65535"
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
                elif event.key == pygame.K_LEFT:
                    role_index = (role_index - 1) % len(ROLES)
                elif event.key == pygame.K_RIGHT:
                    role_index = (role_index + 1) % len(ROLES)
                elif event.key == pygame.K_1:
                    role_index = 0
                elif event.key == pygame.K_2:
                    role_index = 1
                elif event.key == pygame.K_3:
                    role_index = 2
                elif event.key == pygame.K_4:
                    role_index = 3
                elif event.key == pygame.K_RETURN:
                    try:
                        port = int(fields[1]["value"])
                        if not (1 <= port <= 65535):
                            raise ValueError
                        pygame.quit()
                        return {
                            "SERVER_IP": fields[0]["value"],
                            "SERVER_PORT": str(port),
                            "SERVER_PASSWORD": fields[2]["value"],
                            "PLAYER_ROLE": ROLES[role_index],
                        }
                    except ValueError:
                        error = "Порт должен быть числом от 1 до 65535"
                elif event.key == pygame.K_BACKSPACE:
                    fields[active]["value"] = fields[active]["value"][:-1]
                else:
                    if event.unicode.isprintable() and len(fields[active]["value"]) < 64:
                        fields[active]["value"] += event.unicode

        screen.fill((18, 24, 38))
        screen.blit(title_font.render("Меню клиента", True, (240, 244, 255)), (250, 28))
        screen.blit(hint_font.render("TAB - следующее поле, ENTER - старт", True, (170, 188, 220)), (205, 72))

        for i, field in enumerate(fields):
            y = 108 + i * 68
            screen.blit(font.render(field["label"], True, (220, 225, 236)), (95, y + 10))
            color = (95, 160, 255) if i == active else (78, 90, 120)
            pygame.draw.rect(screen, color, input_rects[i], width=2, border_radius=7)
            shown = "*" * len(field["value"]) if field["secret"] else field["value"]
            screen.blit(font.render(shown, True, (245, 245, 245)), (input_rects[i].x + 10, input_rects[i].y + 10))

        role_rect = pygame.Rect(270, 312, 360, 48)
        pygame.draw.rect(screen, (78, 90, 120), role_rect, width=2, border_radius=7)
        screen.blit(font.render("Роль", True, (220, 225, 236)), (95, 322))
        screen.blit(font.render(ROLE_LABELS[ROLES[role_index]], True, (245, 245, 245)), (role_rect.x + 10, role_rect.y + 10))
        screen.blit(hint_font.render("LEFT/RIGHT или 1-4: РТП/НШ/БР/Диспетчер", True, (170, 188, 220)), (165, 365))

        pygame.draw.rect(screen, (40, 160, 80), start_rect, border_radius=8)
        pygame.draw.rect(screen, (170, 60, 60), quit_rect, border_radius=8)
        screen.blit(font.render("Старт", True, (255, 255, 255)), (208, 405))
        screen.blit(font.render("Выход", True, (255, 255, 255)), (490, 405))

        if error:
            screen.blit(hint_font.render(error, True, (255, 120, 120)), (180, 340))

        pygame.display.flip()
        clock.tick(60)


def main():
    config = run_menu()
    if config is None:
        return

    env = os.environ.copy()
    env.update(config)
    subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "client.py")], env=env)


if __name__ == "__main__":
    main()