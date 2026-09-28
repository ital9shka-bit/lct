"""Generate C4 container diagrams for the handoff and the About dialog."""

from math import atan2, cos, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "architecture"
OUT.mkdir(parents=True, exist_ok=True)
REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
BG, INK, MUTED = "#F8FAFD", "#17283F", "#536782"
BLUE, TEAL, AMBER, EDGE = "#2A5FCE", "#138472", "#A56D27", "#8DA4C4"


class Canvas:
    def __init__(self, width, height):
        self.image = Image.new("RGB", (width, height), BG)
        self.draw = ImageDraw.Draw(self.image)
        self.width = width

    def font(self, size, bold=False):
        return ImageFont.truetype(BOLD if bold else REGULAR, size)

    def text(self, x, y, value, size=22, color=INK, bold=False):
        self.draw.text((x, y), value, font=self.font(size, bold), fill=color)

    def box(self, xy, fill="#FFFFFF", outline="#CAD7E8", radius=17, width=2):
        self.draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

    def arrow(self, *points):
        self.draw.line(points, fill=EDGE, width=4, joint="curve")
        x1, y1 = points[-2]
        x2, y2 = points[-1]
        angle = atan2(y2-y1, x2-x1)
        self.draw.polygon([
            (x2, y2),
            (x2-16*cos(angle-.5), y2-16*sin(angle-.5)),
            (x2-16*cos(angle+.5), y2-16*sin(angle+.5)),
        ], fill=EDGE)

    def label(self, x, y, value):
        font = self.font(18, True)
        width = self.draw.textbbox((0, 0), value, font=font)[2]
        self.box((x-9, y-5, x+width+9, y+31), "#FFFFFF", "#FFFFFF", 8)
        self.text(x, y, value, 18, MUTED, True)

    def card(self, xy, kind, name, tech, lines, color=BLUE):
        x1, y1, x2, y2 = xy
        self.box((x1+5, y1+7, x2+5, y2+7), "#E9EFF7", "#E9EFF7")
        self.box(xy)
        self.box((x1, y1, x1+9, y2), color, color, 4)
        tint = {BLUE: "#EBF2FF", TEAL: "#E7F6F2", AMBER: "#FFF3E4"}[color]
        pill_width = min(20 + len(kind)*11, x2-x1-48)
        self.box((x1+24, y1+19, x1+24+pill_width, y1+51), tint, tint, 8)
        self.text(x1+34, y1+24, kind, 17, color, True)
        self.text(x1+25, y1+61, name, 30, INK, True)
        self.text(x1+25, y1+105, tech, 20, MUTED)
        for n, line in enumerate(lines):
            self.text(x1+25, y1+144+n*27, line, 19, "#3F526D")

    def header(self, title, subtitle, state):
        self.text(68, 48, "C4  /  CONTAINER VIEW", 19, BLUE, True)
        self.text(68, 91, title, 48, INK, True)
        self.text(70, 158, subtitle, 23, MUTED)
        self.box((self.width-294, 66, self.width-70, 127), "#E8F0FC", "#E8F0FC", 14)
        self.text(self.width-260, 80, state, 29, BLUE, True)

    def boundary(self, xy):
        self.box(xy, "#F0F5FC", "#A8BEDD", 24, 3)
        x1, y1, _, _ = xy
        self.box((x1+22, y1-19, x1+435, y1+21), "#F0F5FC", "#F0F5FC", 9)
        self.text(x1+36, y1-13, "СИСТЕМА  ·  СТРОЙКОНТРОЛЬ", 22, BLUE, True)

    def legend(self, y, note):
        self.text(70, y, "ОБОЗНАЧЕНИЯ", 18, MUTED, True)
        x = 270
        for color, label in [(BLUE, "Человек / приложение"), (TEAL, "Данные"), (AMBER, "Сетевой сервис")]:
            self.box((x, y+4, x+22, y+26), color, color, 5)
            self.text(x+34, y, label, 18, MUTED)
            x += 365
        self.text(70, y+51, note, 18, MUTED)


def as_is():
    c = Canvas(2400, 1390)
    c.header("СтройКонтроль · действующая архитектура", "Контейнеры системы и их сетевые связи · 28 сентября 2026", "AS IS")
    c.boundary((430, 250, 1760, 1195))
    c.text(1850, 268, "СЕТЕВЫЕ СЕРВИСЫ", 22, MUTED, True)
    for points in [
        [(355, 608), (500, 608)], [(810, 608), (900, 608)], [(1210, 608), (1300, 608)],
        [(1440, 715), (1440, 800), (930, 800), (930, 885)],
        [(1535, 715), (1535, 885)],
        [(1660, 550), (1788, 550), (1788, 490), (1850, 490)],
        [(1660, 650), (1790, 650), (1790, 897), (1850, 897)],
    ]:
        c.arrow(*points)
    c.card((70, 500, 355, 715), "ЧЕЛОВЕК", "Пользователь", "Веб-браузер", ["Открывает контроль дня", "и исходные кадры"])
    c.card((500, 500, 810, 715), "КОНТЕЙНЕР", "Веб-клиент", "React · Vite", ["Интерфейс и запросы", "к серверному API"])
    c.card((900, 500, 1210, 715), "КОНТЕЙНЕР", "Веб-вход", "Caddy · Nginx", ["TLS, статика и", "обратное прокси"])
    c.card((1300, 500, 1660, 715), "КОНТЕЙНЕР", "API и правила", "FastAPI · Python", ["Анализ, статусы,", "история и осмотры"])
    c.card((760, 885, 1100, 1100), "ДАННЫЕ", "PostgreSQL", "PostgreSQL 17", ["План, проверки, ответы AI", "и дневные оценки"], TEAL)
    c.card((1240, 885, 1580, 1100), "ДАННЫЕ", "Фото и файлы", "Внешнее S3-хранилище", ["Оригиналы кадров", "и вложения осмотров"], TEAL)
    c.card((1850, 385, 2320, 595), "СЕТЕВОЙ СЕРВИС", "GateLLM", "HTTPS · API", ["Живой анализ фото и", "сравнение техники"], AMBER)
    c.card((1850, 792, 2320, 1002), "СЕТЕВОЙ СЕРВИС", "Rusender", "HTTPS · API", ["Приветственное письмо", "после регистрации"], AMBER)
    for args in [(371,565,"работает"),(817,565,"HTTPS"),(1217,565,"HTTP"),(1115,760,"SQL"),(1546,803,"S3 API"),(1668,467,"HTTPS · JSON"),(1650,842,"HTTPS · email")]:
        c.label(*args)
    c.legend(1270, "GateLLM принадлежит владельцу проекта; схема показывает его как отдельный сетевой сервис.")
    c.image.save(OUT / "architecture-as-is.png", optimize=True)
    c.image.save(ROOT / "prototype/public/assets/architecture-as-is.png", optimize=True)


def to_be():
    c = Canvas(2600, 1480)
    c.header("СтройКонтроль · целевая архитектура", "Предлагаемые контейнеры и интеграции · после демонстрационного этапа", "TO BE")
    c.boundary((430, 245, 1830, 1295))
    c.text(1950, 252, "ПРОВАЙДЕРЫ", 22, MUTED, True)
    for points in [
        [(355,510),(500,510)], [(810,510),(900,510)], [(1210,510),(1300,510)],
        [(355,1074),(398,1074),(398,750),(1050,750),(1050,620)],
        [(1430,620),(1430,820),(660,820),(660,970)],
        [(1530,620),(1530,865),(1090,865),(1090,970)],
        [(1390,1074),(1250,1074)],
        [(1740,1009),(1872,1009),(1872,385),(1950,385)],
        [(1740,1045),(1892,1045),(1892,625),(1950,625)],
        [(1740,1090),(1912,1090),(1912,865),(1950,865)],
        [(1740,1130),(1932,1130),(1932,1105),(1950,1105)],
    ]:
        c.arrow(*points)
    c.card((70,400,355,620), "ЧЕЛОВЕК", "Участник", "Веб-браузер", ["Владелец, инженер", "или наблюдатель"])
    c.card((500,400,810,620), "КОНТЕЙНЕР", "Веб-клиент", "React · Vite", ["Права в интерфейсе", "и восстановление доступа"])
    c.card((900,400,1210,620), "КОНТЕЙНЕР", "Веб-вход", "Caddy · Nginx", ["TLS и маршрутизация", "к API и статике"])
    c.card((1300,400,1710,620), "КОНТЕЙНЕР", "API и роли", "FastAPI · Python", ["Права по объекту, план,", "осмотры, сброс пароля"])
    c.card((70,965,355,1185), "СЕТЕВОЙ КЛИЕНТ", "Edge-агент", "RTSP → HTTPS", ["Приём кадров камер", "с проверкой источника"], AMBER)
    c.card((500,970,820,1185), "ДАННЫЕ", "Фото и файлы", "S3-совместимое хранилище", ["Кадры, вложения,", "резервное копирование"], TEAL)
    c.card((930,970,1250,1185), "ДАННЫЕ", "PostgreSQL", "PostgreSQL · job queue", ["Версии, аудит и очередь", "фоновых заданий"], TEAL)
    c.card((1390,970,1740,1185), "КОНТЕЙНЕР", "Фоновый worker", "Python · provider adapters", ["Анализ, сравнения", "и уведомления"])
    c.card((1950,290,2490,480), "СЕТЕВОЙ СЕРВИС", "GateLLM", "HTTPS · текущий провайдер", ["Визуальный AI-анализ"], AMBER)
    c.card((1950,530,2490,720), "СЕТЕВОЙ СЕРВИС", "Yandex AI Studio", "HTTPS · кандидат", ["После проверки фото + JSON"], AMBER)
    c.card((1950,770,2490,960), "СЕТЕВОЙ СЕРВИС", "Rusender", "HTTPS · email", ["Письма и сброс пароля"], AMBER)
    c.card((1950,1010,2490,1200), "СЕТЕВОЙ СЕРВИС", "SMS-провайдер", "HTTPS · кандидат", ["Оповещения по правилам"], AMBER)
    for args in [(373,467,"работает"),(818,467,"HTTPS"),(1218,467,"HTTP"),(596,708,"HTTPS · кадры"),(843,783,"S3 API"),(1210,829,"SQL · задания"),(1260,1025,"SQL · claim"),(1750,342,"HTTPS · AI"),(1750,582,"HTTPS · AI"),(1750,822,"HTTPS · email"),(1750,1062,"HTTPS · SMS")]:
        c.label(*args)
    c.legend(1360, "TO BE — предложение. Выбор модели, SMS и edge-приём требуют отдельной реализации и испытаний.")
    c.image.save(OUT / "architecture-to-be.png", optimize=True)


if __name__ == "__main__":
    as_is()
    to_be()
