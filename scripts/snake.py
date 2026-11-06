#!/usr/bin/env python3
"""Gera uma cobrinha animada (SVG) para o perfil do GitHub.

Ela percorre o quadro de contribuições, come as "maçãs" (dias com
contribuição), cresce a cada maçã e vai encolhendo de novo depois.
Usa só a biblioteca padrão do Python.
"""
import argparse
import datetime as dt
import os
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

# ---- comportamento ---------------------------------------------------------
STEP_SECONDS = 0.09     # tempo de cada passo
BASE_LEN = 3            # tamanho da cobrinha sem comer nada
GROW_PER_APPLE = 5      # quanto cada maçã faz ela crescer
DECAY_STEPS = 3         # a cada quantos passos ela perde 1 segmento
MAX_GROW = 12           # limite de crescimento


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


def build_path(grid):
    """Caminho em zigue-zague. A última coluna sempre desce, então o caminho
    nunca dá salto, mesmo com a última semana incompleta."""
    last = max(w for w, _ in grid)
    path = []
    for w in range(last + 1):
        rows = range(7) if (last - w) % 2 == 0 else range(6, -1, -1)
        path.extend((w, r) for r in rows if (w, r) in grid)
    return path


def compute_timeline(path, grid):
    n = len(path)
    apples = [k for k, cell in enumerate(path) if grid[cell] > 0]
    total = n + BASE_LEN + MAX_GROW + GROW_PER_APPLE * DECAY_STEPS + 3
    lengths = []
    cur = BASE_LEN
    for i in range(total):
        bonus = sum(max(0, GROW_PER_APPLE - (i - k) // DECAY_STEPS) for k in apples if k <= i)
        target = BASE_LEN + min(MAX_GROW, bonus)
        if target > cur:
            cur += 1      # cresce 1 por passo: a cauda fica parada e a cabeça avança
        elif target < cur:
            cur -= 1      # encolhe 1 por passo
        lengths.append(cur)
    return apples, lengths, total


def seg_position(path, i, j):
    n = len(path)
    return path[min(max(i - j, 0), n - 1)]


def render_svg(grid, path, apples, lengths, total):
    weeks = max(w for w, _ in grid) + 1
    width = weeks * PITCH + 2 * MARGIN
    height = 7 * PITCH + 2 * MARGIN
    duration = total * STEP_SECONDS
    max_len = max(lengths)
    apple_step = {path[k]: k for k in apples}

    css = [
        f".s{{animation-duration:{duration:.2f}s;animation-iteration-count:infinite;"
        "animation-timing-function:linear}}"
    ]
    for level, color in enumerate(DOT_COLORS):
        css.append(f".c{level}{{fill:{color}}}")

    def px(cell):
        return MARGIN + cell[0] * PITCH, MARGIN + cell[1] * PITCH

    # animação de cada segmento da cobrinha
    for j in range(max_len):
        frames = []
        for i in range(total):
            x, y = px(seg_position(path, i, j))
            visible = j < lengths[i] and i < total - 1
            opacity = max(0.4, 1 - 0.045 * j) if visible else 0
            pct = 100 * i / (total - 1)
            frames.append(f"{pct:.3f}%{{transform:translate({x}px,{y}px);opacity:{opacity:.2f}}}")
        css.append(f"@keyframes k{j}{{{''.join(frames)}}}")
        css.append(f".s{j}{{animation-name:k{j}}}")

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f"<style>{''.join(css)}</style>",
        f'<rect width="{width}" height="{height}" rx="8" fill="{BACKGROUND}"/>',
    ]

    # quadradinhos; os que viram maçã somem quando a cobrinha chega neles
    eaten_css = []
    for cell, level in sorted(grid.items()):
        x, y = px(cell)
        cls = f"c{level}"
        if cell in apple_step:
            k = apple_step[cell]
            pct = 100 * k / (total - 1)
            idx = f"{cell[0]}_{cell[1]}"
            eaten_css.append(
                f"@keyframes e{idx}{{0%{{fill:{DOT_COLORS[level]}}}"
                f"{pct:.3f}%{{fill:{DOT_COLORS[0]}}}100%{{fill:{DOT_COLORS[0]}}}}}"
                f".e{idx}{{animation:e{idx} {duration:.2f}s steps(1,end) infinite}}"
            )
            cls += f" e{idx}"
        parts.append(f'<rect class="{cls}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2"/>')

    parts.insert(2, f"<style>{''.join(eaten_css)}</style>")

    # cobrinha por cima: cauda primeiro, cabeça por último
    for j in reversed(range(max_len)):
        fill = HEAD_COLOR if j == 0 else SNAKE_COLOR
        parts.append(
            f'<rect class="s s{j}" width="{CELL}" height="{CELL}" rx="3" fill="{fill}" opacity="0"/>'
        )

    parts.append("</svg>")
    return "".join(parts)


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
    path = build_path(grid)
    apples, lengths, total = compute_timeline(path, grid)
    svg = render_svg(grid, path, apples, lengths, total)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"{len(cells)} dias, {len(apples)} maçãs, {total} passos, {len(svg) / 1024:.0f} KB -> {args.out}")


if __name__ == "__main__":
    main()
