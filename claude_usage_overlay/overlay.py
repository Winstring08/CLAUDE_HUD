"""tkinter 오버레이 창.

1초마다 다시 그리지만 네트워크는 부르지 않는다. 카운트다운은
resets_at에서 로컬로 계산한다. 화면은 매초 살아 움직이고 API는 5분에 한 번만.

**모드가 둘이다.**

    기본     66 × 66. 링 하나에 숫자 하나. 평소에 덜 거슬리게
    자세히   190 × 62. 링 + 카운트다운 + 갱신 문구 두 줄 (예전 모습 그대로)

모든 픽셀 치수는 기준값 × DPI 배율이다. 배율 150% PC에서도 같은 크기로 보인다.
글꼴만 규칙이 다르다 — fonts_for()의 주석을 보라.
"""

import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime, timezone

from PIL import ImageTk

from . import font_install, text_center, theme
from .icon_render import LOADING_TEXT as RING_LOADING
from .ring_render import render_ring
from .config import Config, save_config
from .formatting import (
    LOADING_TEXT,
    RATE_LIMITED_TEXT,
    format_age,
    format_countdown,
)
from .models import HudState, Status
from .winmetrics import dpi_scale, round_window_corners, work_area

# 폭 190은 눈대중이 아니라 역산이다. 화면에 나갈 수 있는 모든 문구를 재서
# 가장 긴 것이 카운트다운 "10시간 14분 후 리셋"이고, **Pretendard가 없는 PC의
# 폴백 글꼴(Segoe UI) 기준으로 181px**이다. 거기에 여유를 뒀다.
#
# 글꼴이 무엇이냐로 폭이 달라진다는 점이 중요하다 — 같은 문구가 Pretendard로는
# 169px, Segoe UI로는 181px이다. 한글 글리프가 없는 Segoe UI에서는 Tk가 고른
# 다른 글꼴이 한글을 그리고 그쪽이 더 넓기 때문이다. 창은 **넓은 쪽**에 맞춘다.
#
# 한때 240px이었다. 드물게 뜨는 안내 문구가 길었기 때문이다 —
# "Claude Code를 한 번 실행하세요"가 228px, "호출 한도 — 잠시 후 재시도"가
# 202px을 요구했다. 그 둘 때문에 **평소 화면 오른쪽 71px이 늘 비어 있었다.**
# 문구를 짧게 다듬어(formatting.py) 창을 내용에 맞췄다.
#
# create_text에는 width 옵션이 없어 넘치면 경고 없이 잘린다.
# tests/test_overlay_layout.py가 이 여유를 지킨다.
BASE_WIDTH, BASE_HEIGHT = 190, 62
BASE_RING_BOX = (12, 12, 54, 54)   # x0, y0, x1, y1
BASE_RING_WIDTH = 5
BASE_TEXT_X = 66
BASE_LINE1_Y, BASE_LINE2_Y = 24, 40
BASE_RIGHT_MARGIN = 10
MARGIN = 24
ALPHA = 0.82

# 기본 모드 — 정사각형. 링 하나에 숫자 하나.
#
# 바깥 지름 50px에 여백 8px, 두께 5px이므로 안쪽 지름이 40px이다. 자세히 모드의
# 링(안쪽 32px)보다 크므로 시작 글꼴도 그만큼 크다.
SMALL_SIZE = 66
SMALL_RING_BOX = (8, 8, 58, 58)
SMALL_RING_WIDTH = 5

# 글꼴 크기는 픽셀이다. 음수로 넘긴다 (Tk 규약: 음수 = 픽셀, 양수 = 포인트).
#
# **문구마다 시작 크기를 따로 고른다.** 같은 크기로 `100`과 `5:20`을 둘 다 담으려면
# 15px인데(실측), 그러면 평소 보는 숫자가 작아진다.
SMALL_FONT_PCT_PX = 18
SMALL_FONT_TIME_PX = 15

# 자세히 모드의 링은 안쪽이 32px뿐이다. 꽉 채우면 숫자가 링 선에 닿아 답답해 보인다.
BASE_FONT_PCT_PX = 16
PCT_INNER_MARGIN = 4   # 링 선과 글자 사이에 남기는 여백
BASE_FONT_LINE1_PX = 12
BASE_FONT_LINE2_PX = 11

MIN_RING_FONT_PX = 8   # 이 아래로는 줄이지 않는다. 넘치는 편이 낫다

# 갱신 지연 임계에 더하는 여유. 분 반올림 경계에서 깜빡이지 않게 한다.
GAP_PADDING_SECONDS = 60

# 앞에서부터 **설치돼 있는 것**을 쓴다. Segoe UI는 한글 글리프가 없어
# 한글만 Tk가 고른 다른 글꼴로 그려지므로, 한글까지 한 글꼴로 덮는
# Pretendard를 앞에 둔다. Pretendard가 없으면 예전 그대로 Segoe UI다.
#
# 맑은 고딕을 사이에 두지 않는다. 한글 로케일에서 families()가 "맑은 고딕"
# 이라는 한글 이름으로 내놓아 "Malgun Gothic"으로는 잡히지도 않고, 잡히면
# 잡히는 대로 Pretendard를 안 깐 사람의 화면이 멋대로 바뀐다.
FONT_CANDIDATES = ("Pretendard Variable", "Pretendard", "Segoe UI")
FALLBACK_FAMILY = "Segoe UI"

# 값이 낡은 상태. 아이콘과 같은 기준을 쓴다.
DIM_STATUSES = frozenset({Status.STALE, Status.RATE_LIMITED})


def is_refresh_gap(fetched_at: datetime, now: datetime, poll_seconds: int) -> bool:
    """갱신이 한 주기를 통째로 건너뛰었는지.

    참이면 링 채움과 숫자를 지우고 흐린 `!` 하나만 그린다. 낡은 숫자는 없느니만
    못하고, 숫자를 못 믿으면 링도 못 믿는다.

    **한 번의 실패로 지우면 안 된다.** poller._handle_unauthorized()의 401 경합은
    백오프 없이 다음 틱에 저절로 낫는데, poll_seconds + 60을 기준으로 삼으면 그
    회복을 기다리는 동안(기본 5분 주기에서 4분) 내내 숫자가 사라진다. 두 번
    연속 실패해야, 즉 한 주기를 통째로 건너뛰어야 지운다. 세 번이면 그건 경합이
    아니라 인증 문제라 poller가 Status.RELOGIN으로 넘겨 또렷한 `!`가 된다.
    """
    return (now - fetched_at).total_seconds() > poll_seconds * 2 + GAP_PADDING_SECONDS


def ring_symbol(state: HudState, now: datetime, poll_seconds: int) -> tuple[str, str] | None:
    """링 안에 숫자 대신 기호를 그려야 하면 (기호, 색), 아니면 None.

    어휘는 icon_render의 것을 그대로 쓴다. `!`가 두 뜻을 갖지만 밝기로 갈린다 —
    **기다리면 낫는 것은 흐리게, 사용자가 조치해야 하는 것은 또렷하게.**
    """
    if state.status is Status.RELOGIN:
        return "!", theme.RED
    if state.status is Status.SCHEMA_ERROR:
        return "?", theme.TEXT_LIGHT
    if state.snapshot is None:
        # 첫 조회 전이거나 한 번도 성공하지 못했다. 여기서 `?`를 쓰면 프로그램을
        # 켤 때마다 몇 초 동안 "데이터 형식이 바뀜" 기호가 뜬다.
        return RING_LOADING, theme.TEXT_DIM
    if state.status in DIM_STATUSES and is_refresh_gap(
        state.snapshot.fetched_at, now, poll_seconds
    ):
        return "!", theme.TEXT_DIM_RING
    return None


def ring_inner_box(
    ring_box: tuple[int, int, int, int], ring_width: int, scale: float
) -> tuple[int, int, int, int]:
    """링 안쪽 원이 차지하는 상자. 글자를 중앙에 놓는 기준이다."""
    x0, y0, x1, y1 = (round(v * scale) for v in ring_box)
    rw = max(3, round(ring_width * scale))
    return (x0 + rw, y0 + rw, x1 - rw, y1 - rw)


def ring_text_limit(
    ring_box: tuple[int, int, int, int], ring_width: int, scale: float
) -> int:
    """링 안에 글자가 들어가야 하는 폭.

    계산을 함수로 빼는 이유는 테스트가 코드와 **같은 산수**를 써야 하기 때문이다 —
    round(32 × 배율)로 어림하면 125%에서 1px 어긋나 통과해야 할 것이 떨어지거나
    반대가 된다.
    """
    x0, _y0, x1, _y1 = ring_inner_box(ring_box, ring_width, scale)
    return (x1 - x0) - 2 * round(PCT_INNER_MARGIN * scale)


def resized_position(
    x: int,
    y: int,
    old_size: tuple[int, int],
    new_size: tuple[int, int],
    area: tuple[int, int, int, int],
) -> tuple[int, int]:
    """창 크기가 바뀔 때의 새 좌표. **오른쪽 아래 모서리를 고정한다.**

    기본 위치가 작업 영역 오른쪽 아래이므로 그래야 제자리에 남는다.

    **옮겨둔 자리에서는 작업 영역 안으로 되민다.** 창은 드래그로 어디든 갈 수
    있고, 왼쪽 끝에 붙여둔 상태에서 자세히로 바꾸면 오른쪽 아래를 고정한 채
    왼쪽으로 124px 자라 화면 밖으로 나간다.

    예전에 16d1eba가 폭 변경에 대해 같은 보정을 넣은 적이 있으나, 위치 저장
    기능을 통째로 되돌린 62a2fa4가 함께 지웠다. 새로 만드는 부분이다.
    """
    old_w, old_h = old_size
    new_w, new_h = new_size
    left, top, right, bottom = area
    nx = max(left, min(x + old_w - new_w, right - new_w))
    ny = max(top, min(y + old_h - new_h, bottom - new_h))
    return nx, ny


def pick_font_family(root: tk.Misc, candidates=FONT_CANDIDATES) -> str:
    """후보 중 **실제로 설치된** 첫 글꼴 이름. 없으면 FALLBACK_FAMILY.

    이 확인을 건너뛰고 이름만 적으면 안 된다. Tk는 없는 글꼴을 조용히
    기본 글꼴로 바꿔 그리므로 화면은 그럴듯한데, 창 폭을 역산한 근거
    (tests/test_overlay_layout.py)는 엉뚱한 글꼴을 잰 값이 된다. 글꼴이
    바뀌면 글자 폭도 바뀌고, 넘치는 문구는 create_text가 말없이 잘라낸다.
    """
    installed = {name.lower() for name in tkfont.families(root=root)}
    for name in candidates:
        if name.lower() in installed:
            return name
    return FALLBACK_FAMILY


def fonts_for(scale: float, family: str = FALLBACK_FAMILY) -> dict[str, tuple]:
    """글꼴 크기를 **픽셀**로 만든다. Tk에서 음수 = 픽셀, 양수 = 포인트다.

    포인트로 주면 안 된다. enable_dpi_awareness()를 켜는 순간 Tk의
    `tk scaling`이 실제 DPI를 따라가고, 포인트→픽셀 환산이 이미 배율을
    반영한다. 거기에 dpi_scale()을 또 곱하면 확대가 두 번 걸린다 —
    144 DPI에서 10pt는 28px인데 round(10 × 1.5) = 15pt를 주면 41px이 되어
    기대값 26px의 약 1.6배가 된다. 캔버스 치수는 픽셀이라 곱셈이 맞으므로
    창은 제 크기인데 글자만 넘쳐 잘린다.

    픽셀 크기는 tk scaling에 흔들리지 않는다(실측: scaling 1.333과 2.0에서
    -13px 모두 linespace 17px). 그래서 여기서만 배율을 곱하면 되고,
    캔버스 치수와 정확히 같은 비율로 커진다.
    """
    return {
        "line1": (family, -round(BASE_FONT_LINE1_PX * scale)),
        "line2": (family, -round(BASE_FONT_LINE2_PX * scale)),
    }


class Overlay:
    def __init__(self, root: tk.Tk, config: Config) -> None:
        self._config = config
        self._scale = dpi_scale()

        s = self._scale
        self._w = round(BASE_WIDTH * s)
        self._h = round(BASE_HEIGHT * s)
        self._ring = tuple(round(v * s) for v in BASE_RING_BOX)
        self._ring_width = max(3, round(BASE_RING_WIDTH * s))
        self._text_x = round(BASE_TEXT_X * s)
        self._line1_y = round(BASE_LINE1_Y * s)
        self._line2_y = round(BASE_LINE2_Y * s)
        self._family = pick_font_family(root)
        fonts = fonts_for(s, self._family)
        # 링 안 숫자는 여기서 정하지 않는다. 자릿수를 봐야 하므로 _pct_font()가 맡는다.
        self._font_line1 = fonts["line1"]
        self._font_line2 = fonts["line2"]

        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)          # 테두리 제거
        self._win.attributes("-topmost", True)    # 항상 위
        self._win.attributes("-alpha", ALPHA)     # 반투명
        self._win.configure(bg=theme.BG)

        x, y = self._initial_position()
        self._win.geometry(f"{self._w}x{self._h}+{x}+{y}")

        self._canvas = tk.Canvas(
            self._win, width=self._w, height=self._h, bg=theme.BG, highlightthickness=0
        )
        self._canvas.pack()
        self._round_corners()

        # 드래그로 옮길 수 있지만 놓은 자리를 저장하지는 않는다.
        # 그래서 <ButtonRelease-1>에 걸 일이 없다.
        self._drag = {"x": 0, "y": 0}
        for widget in (self._win, self._canvas):
            widget.bind("<Button-1>", self._on_press)
            widget.bind("<B1-Motion>", self._on_drag)

        # 링 그림 캐시. PhotoImage는 참조가 끊기면 화면에서 사라진다.
        self._ring_key: tuple | None = None
        self._ring_photo: ImageTk.PhotoImage | None = None

        # 링 안 숫자 글꼴 캐시. 자릿수마다 크기가 다르므로 자릿수를 키로 쓴다.
        self._ring_inner = (self._ring[2] - self._ring[0]) - 2 * self._ring_width
        self._pct_fonts: dict[int, tkfont.Font] = {}

        self._state = HudState(Status.STALE, None, LOADING_TEXT)
        self._visible = config.overlay_visible
        if not self._visible:
            self._win.withdraw()
        self._tick()

    # --- 공개 인터페이스 -------------------------------------------------
    #
    # show/hide/is_visible은 **트레이 메뉴에서 불린다 — 즉 pystray 스레드다.**
    # tkinter 창 조작은 메인 스레드 몫이므로 여기서 직접 하지 않고 after()로
    # 넘긴다. 표시 여부도 Tk에 묻지 않고 우리가 들고 있는다.

    def update(self, state: HudState) -> None:
        self._state = state

    def show(self) -> None:
        self._set_visible(True)

    def hide(self) -> None:
        self._set_visible(False)

    def is_visible(self) -> bool:
        """Tk에 묻지 않는다. 트레이 메뉴 문구를 그릴 때마다 불리는 함수라
        pystray 스레드에서 Tk를 건드리게 된다."""
        return self._visible

    def _set_visible(self, visible: bool) -> None:
        """after()는 콜백을 tkinter 이벤트 큐에 넣을 뿐이고,
        실제 withdraw/deiconify는 메인 스레드의 mainloop가 실행한다."""
        self._visible = visible
        self._config.overlay_visible = visible
        save_config(self._config)
        self._win.after(0, self._win.deiconify if visible else self._win.withdraw)

    # --- 모양 ------------------------------------------------------------

    def _round_corners(self) -> None:
        """무테두리 창의 직각 모서리를 둥글게 다듬는다.

        HWND는 창이 한 번 배치된 뒤에야 유효하므로 update_idletasks가 먼저다.
        실패하면 각진 창일 뿐이니 조용히 넘어간다.
        """
        try:
            self._win.update_idletasks()
            hwnd = int(self._win.wm_frame(), 16)
        except (tk.TclError, ValueError):
            return
        round_window_corners(hwnd)

    # --- 위치 ------------------------------------------------------------

    def _initial_position(self) -> tuple[int, int]:
        """언제나 화면 오른쪽 **아래**. 옮겨둔 자리를 기억하지 않는다.

        오른쪽 위는 창의 닫기 단추와 브라우저 탭이 몰려 있어 사용자가 자주
        건드리는 자리다. 항상 위에 떠 있는 창을 거기 두면 클릭을 가로챈다.
        오른쪽 아래는 트레이 아이콘과도 가까워 눈이 오가기 쉽다.

        화면 크기가 아니라 **작업 영역**을 기준으로 잡는다. 화면 크기에는
        작업 표시줄이 포함돼 있어서, 그걸로 아래쪽에 붙이면 표시줄 뒤로 숨는다.

        드래그는 그 세션 동안만 유지된다. 늘 같은 자리에서 시작하는 편이
        어디를 봐야 할지 헷갈리지 않고, 저장된 좌표가 지금 없는 모니터를
        가리켜 창을 못 찾는 사고도 애초에 생기지 않는다.
        """
        _left, _top, right, bottom = work_area()
        return right - self._w - MARGIN, bottom - self._h - MARGIN

    # --- 드래그 이동 ------------------------------------------------------

    def _on_press(self, event) -> None:
        self._drag["x"] = event.x_root - self._win.winfo_x()
        self._drag["y"] = event.y_root - self._win.winfo_y()

    def _on_drag(self, event) -> None:
        self._win.geometry(
            f"+{event.x_root - self._drag['x']}+{event.y_root - self._drag['y']}"
        )

    # --- 그리기 ----------------------------------------------------------

    def _tick(self) -> None:
        self._redraw()
        self._win.after(1000, self._tick)

    def _redraw(self) -> None:
        c = self._canvas
        c.delete("all")
        state = self._state
        now = datetime.now(timezone.utc)

        if state.status is Status.RELOGIN:
            # 문구는 credentials가 정한다. "제목 — 할 일" 형태를 두 줄로 나눈다.
            head, _, tail = state.detail.partition(" — ")
            self._draw_ring(0, theme.GREY)
            self._draw_text(head or "재로그인 필요", theme.RED, tail, theme.TEXT_DIM)
            return

        if state.snapshot is None:
            # 첫 조회 전(STALE)과 SCHEMA_ERROR가 모두 여기로 온다. 문구는
            # 만든 쪽이 정하므로 오버레이는 기호를 고를 필요가 없다 —
            # 트레이 아이콘만 "…"와 "?"를 구분한다.
            self._draw_ring(0, theme.GREY)
            self._draw_text(state.detail or LOADING_TEXT, theme.TEXT_DIM, "", theme.TEXT_DIM)
            return

        snap = state.snapshot
        pct = snap.five_hour_pct
        color = theme.color_for(pct, self._config.warn_pct, self._config.danger_pct)
        dim = state.status in DIM_STATUSES

        self._draw_ring(pct, theme.RING_DIM if dim else color)
        # 링 안에는 숫자만. % 기호는 링 자체가 이미 비율을 말하고 있어 군더더기다.
        number = str(int(round(pct)))
        c.create_text(
            (self._ring[0] + self._ring[2]) / 2,
            (self._ring[1] + self._ring[3]) / 2,
            text=number,
            fill=theme.TEXT_DIM_RING if dim else theme.TEXT_LIGHT,
            font=self._pct_font(number),
        )

        # resets_at이 None이면 "—"가 온다. 링과 숫자는 그대로 그린다.
        line1 = format_countdown(snap.resets_at, now)
        if state.status is Status.STALE:
            line2, line2_color = state.detail, theme.YELLOW
        elif state.status is Status.RATE_LIMITED:
            line2, line2_color = RATE_LIMITED_TEXT, theme.YELLOW
        else:
            line2, line2_color = format_age(snap.fetched_at, now), theme.TEXT_DIM

        self._draw_text(
            line1, theme.TEXT_DIM_RING if dim else theme.TEXT_LIGHT, line2, line2_color
        )

    def _pct_font(self, text: str) -> tkfont.Font:
        """링 안에 들어가는 가장 큰 글꼴.

        평소에는 두 자리라 큼직하게 들어가고, 100%가 되는 순간에만 한 단계
        작아진다. 자릿수로 캐시하는 이유는 숫자 글리프 폭이 서로 같아서
        `62`와 `87`이 같은 크기를 쓰기 때문이다.
        """
        digits = len(text)
        cached = self._pct_fonts.get(digits)
        if cached is not None:
            return cached

        limit = self._ring_inner - round(PCT_INNER_MARGIN * self._scale) * 2
        px = round(BASE_FONT_PCT_PX * self._scale)
        font = tkfont.Font(root=self._win, family=self._family, size=-px, weight="bold")
        while px > 8 and font.measure(text) > limit:
            px -= 1
            font = tkfont.Font(
                root=self._win, family=self._family, size=-px, weight="bold"
            )

        self._pct_fonts[digits] = font
        return font

    def _draw_ring(self, pct: float, color: str) -> None:
        """링은 캔버스가 아니라 PIL이 그린다.

        create_arc에는 안티앨리어싱이 없어 곡선이 픽셀 계단으로 드러난다.
        ring_render는 크게 그려 축소하므로 경계가 매끈하다.

        그림은 (크기, 정수 %, 색)이 바뀔 때만 다시 만든다. _redraw는 1초마다
        도는데 사용률은 5분에 한 번만 움직이므로 대부분 캐시가 그대로 쓰인다.
        PhotoImage는 참조를 놓으면 가비지 컬렉션되어 화면에서 사라지므로
        self에 붙들고 있어야 한다.
        """
        x0, y0, x1, y1 = self._ring
        key = (x1 - x0, int(round(pct)), color)
        if key != self._ring_key:
            self._ring_photo = ImageTk.PhotoImage(
                render_ring(
                    x1 - x0, pct, color, bg=theme.BG, width=self._ring_width
                )
            )
            self._ring_key = key
        self._canvas.create_image(x0, y0, image=self._ring_photo, anchor="nw")

    def _draw_text(self, line1: str, color1: str, line2: str, color2: str) -> None:
        self._canvas.create_text(
            self._text_x, self._line1_y, text=line1, anchor="w",
            fill=color1, font=self._font_line1,
        )
        if line2:
            self._canvas.create_text(
                self._text_x, self._line2_y, text=line2, anchor="w",
                fill=color2, font=self._font_line2,
            )
