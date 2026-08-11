"""첫 실행 판정과 안내창.

**첫 실행인지는 기동할 때 한 번만 판정해 불리언으로 들고 다닌다.** 5장의 자동
IsPromoted도 "config.json이 없으면"을 조건으로 삼는데, 그쪽은 아이콘이 뜨기를
기다렸다가 별도 스레드에서 늦게 실행된다. 둘이 각자 파일을 확인하면 안내창이
먼저 저장해 버려서 자동 시도가 영영 돌지 않는다. 그래서 판정은 __main__이 한 번만
하고 이 모듈은 그 결과를 받는다.

**안내창을 띄우는 즉시 config.json을 기본값으로 저장한다.** 그러지 않으면 사용자가
아무 설정도 건드리지 않는 한 매 실행마다 뜬다.

도식은 도형으로 그린다. 스크린샷 파일을 끼워 넣으면 exe가 커지고 배율도 안 따라간다.
"""

import tkinter as tk
from pathlib import Path

from . import theme
from .config import Config, config_path, save_config
from .winmetrics import dark_title_bar, dpi_scale

TITLE = "Claude 사용량 — 처음 실행"

HEADING = "트레이 아이콘을 작업 표시줄에 꺼내 두면 편합니다"
BODY = (
    "사용량은 작업 표시줄 오른쪽 트레이 아이콘에 늘 보입니다.\n"
    "숨은 아이콘 안에 들어가 있으면 ∧를 눌러 꺼낼 수 있습니다."
)

LAST_LINE_WIN11 = "지금 안 하셔도 됩니다. 다음 로그온부터는 저절로 나옵니다."
LAST_LINE_WIN10 = (
    "설정 > 작업 표시줄 > 작업 표시줄에 표시할 아이콘 선택에서 켜도 됩니다."
)

BASE_WIDTH = 380
PAD = 18
FONT_PX = 13
HEADING_PX = 15
HINT_PX = 11
DIAGRAM_H = 96


def is_first_run(path: Path | None = None) -> bool:
    """config.json이 없으면 첫 실행이다.

    깨진 파일도 "한 번 켠 적이 있다"는 증거로 본다. 내용을 읽어 판정하면 오타 하나에
    안내창이 매 실행마다 뜬다.
    """
    return not (path or config_path()).exists()


def last_line(supported: bool) -> str:
    """마지막 줄만 OS로 갈린다.

    Win11에서는 첫 실행에 IsPromoted=1을 써두므로 "다음 로그온부터 저절로 나온다"가
    참이다. Win10에서는 우리가 써둘 값이 없으므로 그 약속을 할 수 없다.

    **스펙 14장의 미해결 항목이 여기에 걸려 있다.** IsPromoted가 다음 로그온에
    실제로 반영되는지 확인되지 않았고, 안 되면 이 문구가 거짓이 된다.
    """
    return LAST_LINE_WIN11 if supported else LAST_LINE_WIN10


def show_intro(root: tk.Tk, config: Config, supported: bool) -> None:
    """안내창을 띄우고 config.json을 저장한다.

    **띄우는 즉시 저장한다.** 그러지 않으면 사용자가 아무 설정도 건드리지 않는 한
    매 실행마다 뜬다.

    새 Config()가 아니라 **살아 있는 것**을 저장한다. 안내창이 뜨기 전에 오버레이가
    이미 저장한 값(예: ✕를 눌러 숨긴 상태)이 있으면 그것을 덮으면 안 된다.
    """
    save_config(config)

    s = dpi_scale()
    win = tk.Toplevel(root)
    win.title(TITLE)
    win.resizable(False, False)
    win.configure(bg=theme.BG)
    win.bind("<Escape>", lambda _e: win.destroy())

    body = tk.Frame(win, bg=theme.BG)
    body.pack(fill="both", expand=True, padx=round(PAD * s), pady=round(PAD * s))

    def label(text: str, px: int, color: str) -> None:
        tk.Label(
            body, text=text, bg=theme.BG, fg=color, justify="left", anchor="w",
            font=("Pretendard", -round(px * s)),
        ).pack(fill="x", pady=(0, round(6 * s)))

    label(HEADING, HEADING_PX, theme.TEXT_LIGHT)
    _draw_diagram(body, s)
    label(BODY, FONT_PX, theme.TEXT_LIGHT)
    label(last_line(supported), HINT_PX, theme.TEXT_DIM)

    tk.Button(
        body, text="알겠습니다", command=win.destroy,
        font=("Pretendard", -round(FONT_PX * s)),
        bg=theme.RING_TRACK, fg=theme.TEXT_LIGHT,
        activebackground=theme.GREY, activeforeground=theme.TEXT_LIGHT,
        relief="flat", borderwidth=0, padx=round(14 * s), pady=round(4 * s),
    ).pack(anchor="e")

    win.update_idletasks()
    win.geometry(f"{round(BASE_WIDTH * s)}x{win.winfo_reqheight()}")
    try:
        dark_title_bar(int(win.wm_frame(), 16))
    except (tk.TclError, ValueError):
        pass


def _draw_diagram(parent: tk.Misc, s: float) -> None:
    """작업 표시줄과 숨은 아이콘 팝업, 그리고 끄는 방향.

    도형만 쓴다. 그려지는 것은 이렇다 —

        ┌──────────┐          ← 숨은 아이콘 팝업 (아이콘 셋)
        └────┬─────┘
        ═════╧═══[∧][icon]═   ← 작업 표시줄. ∧ 오른쪽이 트레이다
              └──→ 화살표가 팝업에서 표시줄 쪽을 가리킨다
    """
    w = round((BASE_WIDTH - PAD * 2) * s)
    h = round(DIAGRAM_H * s)
    canvas = tk.Canvas(parent, width=w, height=h, bg=theme.BG, highlightthickness=0)
    canvas.pack(fill="x", pady=(0, round(10 * s)))

    bar_h = round(22 * s)
    bar_y = h - bar_h
    canvas.create_rectangle(0, bar_y, w, h, fill=theme.RING_TRACK, outline="")

    # ∧와 그 오른쪽의 트레이 아이콘 둘.
    chevron_x = w - round(96 * s)
    mid = bar_y + bar_h / 2
    tip = round(4 * s)
    canvas.create_line(
        chevron_x - tip, mid + tip / 2, chevron_x, mid - tip / 2,
        chevron_x + tip, mid + tip / 2,
        fill=theme.TEXT_LIGHT, width=max(1, round(1.5 * s)),
        capstyle="round", joinstyle="round",
    )
    icon = round(12 * s)
    for index, color in enumerate((theme.GREY, theme.FILL_GREEN)):
        x = chevron_x + round((22 + index * 20) * s)
        canvas.create_rectangle(
            x, mid - icon / 2, x + icon, mid + icon / 2, fill=color, outline=""
        )

    # 숨은 아이콘 팝업. ∧ 위에 뜬다.
    pop_w, pop_h = round(84 * s), round(34 * s)
    pop_x = chevron_x - pop_w // 2
    pop_y = bar_y - pop_h - round(16 * s)
    canvas.create_rectangle(
        pop_x, pop_y, pop_x + pop_w, pop_y + pop_h,
        fill=theme.BG, outline=theme.TEXT_DIM,
    )
    for index in range(3):
        x = pop_x + round((12 + index * 22) * s)
        y = pop_y + pop_h / 2
        color = theme.FILL_GREEN if index == 1 else theme.GREY
        canvas.create_rectangle(
            x, y - icon / 2, x + icon, y + icon / 2, fill=color, outline=""
        )

    # 팝업의 아이콘에서 표시줄 트레이로 향하는 화살표. 끄는 방향이 이 그림의 요점이다.
    start = (pop_x + round(26 * s) + icon / 2, pop_y + pop_h)
    end = (chevron_x + round(46 * s), mid - icon / 2 - round(3 * s))
    canvas.create_line(
        *start, start[0], end[1] - round(10 * s), *end,
        fill=theme.GREEN, width=max(1, round(1.5 * s)),
        arrow="last", arrowshape=(round(8 * s), round(10 * s), round(4 * s)),
        smooth=True,
    )
