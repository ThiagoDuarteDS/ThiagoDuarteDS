#!/usr/bin/env python3
"""Gera uma cobrinha animada (SVG) para o perfil do GitHub.

A cobrinha entra pela esquerda e vai atrás da maçã mais próxima pelo menor
caminho. As maçãs são os dias com contribuição, e algumas maçãs extras
aparecem pelo quadro durante a animação. A cada maçã ela cresce e depois
vai encolhendo de novo. Usa só a biblioteca padrão do Python.
"""
import argparse
import collections
import datetime as dt
import os
import random
import re
import sys
import urllib.request

# ---- aparência -------------------------------------------------------------
CELL = 12
PITCH = 14
MARGIN = 12
BACKGROUND = "#0d1117"
DOT_COLORS = ["#161b22", "#0b3d5c", "#0f6a9a", "#00a8e8", "#00e5ff"]
SNAKE_COLOR = "#00e5ff"
HEAD_COLOR = "#e0fbff"
APPLE_COLOR = "#ff4d6d"

# ---- comportamento ---------------------------------------------------------
STEP_SECONDS = 0.11     # tempo de cada passo
BASE_LEN = 3            # tamanho da cobrinha sem comer nada
GROW_PER_APPLE = 4      # quanto cada maçã faz ela crescer
DECAY_STEPS = 4         # a cada quantos passos ela perde 1 segmento
MAX_GROW = 12           # limite de crescimento
BONUS_APPLES = 6        # maçãs extras que aparecem durante a animação
SPAWN_EVERY = 22        # a cada quantos passos pode aparecer uma maçã extra
MAX_STEPS = 3000

NEIGHBORS = ((1, 0), (0, 1), (0, -1), (-1, 0))


def fetch_html(user):
    url = f"https://github.com/users/{user}/contributions"
    req = urllib.request.Request(url, headers={"User-Agent": "snake-generator"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_cells(html):
    """Lê o HTML do quadro e devolve {data: nível de 0 a 4}."""
    cells = {}
    for tag in re.findall(r"<td\b[^>]*>", html):
        date = re.search(r'data-date="(\d{4}-\d{2}-\d{2})"', tag)
        level = re.search(r'data-level="(\d)"', tag)
        if date and level:
            cells[dt.date.fromisoformat(date.group(1))] = int(level.group(1))
    return cells


def build_grid(cells):
    """Converte datas em (coluna = semana, linha = dia da semana, domingo = 0)."""
    first = min(cells)
    offset = (first.weekday() + 1) % 7
    grid = {}
    for day, level in cells.items():
        idx = (day - first).days + offset
        grid[(idx // 7, idx % 7)] = level
    return grid


def bfs(start, goals, blocked, grid):
    """Menor caminho de start até a meta mais próxima (sem incluir start)."""
    prev = {start: None}
    queue = collections.deque([start])
    while queue:
        cur = queue.popleft()
        if cur != start and cur in goals:
            path = []
            while cur != start:
                path.append(cur)
                cur = prev[cur]
            return path[::-1]
        for dx, dy in NEIGHBORS:
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in grid and nxt not in blocked and nxt not in prev:
                prev[nxt] = cur
                queue.append(nxt)
    return None


def simulate(grid):
    """Roda o "jogo": devolve o caminho da cabeça, o tamanho em cada passo,
    o passo em que cada maçã foi comida e as maçãs extras."""
    rng = random.Random(f"{len(grid)}:{sum(grid.values())}")
    weeks = max(w for w, _ in grid) + 1
    row0 = min((r for w, r in grid if w == 0), key=lambda r: abs(r - 3))

    apples = {c for c, lvl in grid.items() if lvl > 0}
    eaten = {}                 # maçã de contribuição -> passo em que foi comida
    bonus = []                 # maçãs extras: {"cell", "spawn", "eat"}
    live_bonus = set()
    eat_steps = []

    trail = [(-1, row0), (0, row0)]     # entra pela esquerda
    lengths = [BASE_LEN]
    state = {"len": BASE_LEN}

    def arrive(i):
        head = trail[i]
        if head in apples and head not in eaten:
            eaten[head] = i
            eat_steps.append(i)
        elif head in live_bonus:
            live_bonus.discard(head)
            for b in bonus:
                if b["cell"] == head and b["eat"] is None:
                    b["eat"] = i
            eat_steps.append(i)
        growth = sum(max(0, GROW_PER_APPLE - (i - k) // DECAY_STEPS) for k in eat_steps)
        target = BASE_LEN + min(MAX_GROW, growth)
        state["len"] += (target > state["len"]) - (target < state["len"])   # 1 por passo
        lengths.append(state["len"])

    def occupied(i):
        return {trail[i - j] for j in range(1, lengths[i]) if i - j >= 0}

    arrive(1)
    i = 1
    spawned = 0
    while i < MAX_STEPS:
        head = trail[i]
        body = occupied(i)
        apples_left = apples - set(eaten)

        if spawned < BONUS_APPLES and i % SPAWN_EVERY == 0 and (apples_left or i < SPAWN_EVERY * BONUS_APPLES):
            options = [
                c for c, lvl in sorted(grid.items())
                if lvl == 0 and c not in body and c != head and c not in live_bonus
                and 4 <= abs(c[0] - head[0]) + abs(c[1] - head[1]) <= 20
            ]
            if options:
                cell = rng.choice(options)
                live_bonus.add(cell)
                bonus.append({"cell": cell, "spawn": i, "eat": None})
                spawned += 1

        goals = apples_left | live_bonus
        if not goals and spawned >= BONUS_APPLES:
            break
        if not goals:
            break
        path = bfs(head, goals, body, grid) or bfs(head, goals, set(), grid)
        if not path:
            break
        trail.append(path[0])
        i += 1
        arrive(i)

    # saída: vai até a última coluna e sai do quadro pela direita
    head = trail[i]
    last_col = {c for c in grid if c[0] == weeks - 1}
    if head[0] != weeks - 1:
        path = bfs(head, last_col, occupied(i), grid) or bfs(head, last_col, set(), grid) or []
        for cell in path:
            trail.append(cell)
            i += 1
            arrive(i)
    row = trail[i][1]
    for t in range(BASE_LEN + MAX_GROW + 3):
        trail.append((weeks + t, row))
        i += 1
        arrive(i)

    for b in bonus:
        if b["eat"] is None:
            b["eat"] = len(trail) - 1
    return trail, lengths, eaten, bonus


def render_svg(grid, trail, lengths, eaten, bonus):
    weeks = max(w for w, _ in grid) + 1
    width = weeks * PITCH + 2 * MARGIN
    height = 7 * PITCH + 2 * MARGIN
    total = len(trail)
    duration = total * STEP_SECONDS
    max_len = max(lengths)

    def pct(step):
        return 100 * step / (total - 1)

    def px(cell):
        return MARGIN + cell[0] * PITCH, MARGIN + cell[1] * PITCH

    def seg_cell(i, j):
        idx = i - j
        if idx < 0:
            return (trail[0][0] + idx, trail[0][1])   # ainda fora do quadro, à esquerda
        return trail[min(idx, total - 1)]

    css = [
        f".s{{animation-duration:{duration:.2f}s;animation-iteration-count:infinite;"
        "animation-timing-function:linear}}"
    ]
    for level, color in enumerate(DOT_COLORS):
        css.append(f".c{level}{{fill:{color}}}")

    for j in range(max_len):
        frames = []
        for i in range(total):
            x, y = px(seg_cell(i, j))
            visible = j < lengths[i] and i < total - 1
            opacity = max(0.4, 1 - 0.045 * j) if visible else 0
            frames.append(f"{pct(i):.3f}%{{transform:translate({x}px,{y}px);opacity:{opacity:.2f}}}")
        css.append(f"@keyframes k{j}{{{''.join(frames)}}}.s{j}{{animation-name:k{j}}}")

    dots = []
    for cell, level in sorted(grid.items()):
        x, y = px(cell)
        cls = f"c{level}"
        if cell in eaten:
            name = f"e{cell[0]}_{cell[1]}"
            css.append(
                f"@keyframes {name}{{0%{{fill:{DOT_COLORS[level]}}}"
                f"{pct(eaten[cell]):.3f}%{{fill:{DOT_COLORS[0]}}}100%{{fill:{DOT_COLORS[0]}}}}}"
                f".{name}{{animation:{name} {duration:.2f}s steps(1,end) infinite}}"
            )
            cls += f" {name}"
        dots.append(f'<rect class="{cls}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2"/>')

    extras = []
    for n, b in enumerate(bonus):
        x, y = px(b["cell"])
        css.append(
            f"@keyframes b{n}{{0%{{opacity:0}}{pct(b['spawn']):.3f}%{{opacity:1}}"
            f"{pct(b['eat']):.3f}%{{opacity:0}}100%{{opacity:0}}}}"
            f".b{n}{{animation:b{n} {duration:.2f}s steps(1,end) infinite}}"
        )
        extras.append(
            f'<circle class="b{n}" cx="{x + CELL / 2}" cy="{y + CELL / 2}" r="{CELL * 0.42:.1f}" '
            f'fill="{APPLE_COLOR}" opacity="0"/>'
        )

    snake = []
    for j in reversed(range(max_len)):          # cauda primeiro, cabeça por cima
        fill = HEAD_COLOR if j == 0 else SNAKE_COLOR
        snake.append(f'<rect class="s s{j}" width="{CELL}" height="{CELL}" rx="3" fill="{fill}" opacity="0"/>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><style>{"".join(css)}</style>'
        f'<rect width="{width}" height="{height}" rx="8" fill="{BACKGROUND}"/>'
        + "".join(dots) + "".join(extras) + "".join(snake) + "</svg>"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default=os.environ.get("GITHUB_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER"))
    parser.add_argument("--out", default="dist/github-snake.svg")
    parser.add_argument("--html", help="usar um HTML salvo em vez de buscar no GitHub (para testes)")
    args = parser.parse_args()

    if args.html:
        with open(args.html, encoding="utf-8") as f:
            html = f.read()
    else:
        if not args.user:
            sys.exit("Informe --user ou defina GITHUB_USER.")
        html = fetch_html(args.user)

    cells = parse_cells(html)
    if not cells:
        sys.exit("Não consegui ler o quadro de contribuições (o formato da página pode ter mudado).")

    grid = build_grid(cells)
    trail, lengths, eaten, bonus = simulate(grid)
    svg = render_svg(grid, trail, lengths, eaten, bonus)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"{len(cells)} dias, {len(eaten)} maçãs de contribuição, {len(bonus)} extras, "
          f"{len(trail)} passos, {len(svg) / 1024:.0f} KB -> {args.out}")


if __name__ == "__main__":
    main()
