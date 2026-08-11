"""오버레이의 마우스 조작을 **진짜 이벤트 경로로** 잰다.

핸들러를 손으로 부르는 검사로는 못 잡는 것이 있어서 따로 둔다. 실제로 그랬다 —
캔버스와 Toplevel 양쪽에 바인딩해 두면 캔버스에서 난 이벤트가 Toplevel 바인딩으로
**전파되어 핸들러가 두 번** 돈다. 좌클릭 전환은 두 번 토글되어 제자리로 돌아오고,
우클릭은 메뉴가 두 개 뜬다. 핸들러를 한 번씩 부르는 검사는 이걸 통과시킨다.

창은 conftest의 withdraw된 세션 루트 아래 만들고 끝나면 지운다.
"""

from datetime import datetime, timedelta, timezone

import pytest

from claude_usage_overlay import overlay as ovmod
from claude_usage_overlay.config import Config
from claude_usage_overlay.models import HudState, Status, UsageSnapshot

@pytest.fixture
def hud(root, monkeypatch):
    """살아 있는 오버레이 하나. config.json에는 쓰지 않는다.

    **시각을 고정하지 않는다.** 그리기가 datetime.now()를 보므로 고정 NOW로
    스냅샷을 만들면 리셋 시각이 한참 지난 것이 되어 `0:00`이 그려진다. 30초를
    얹어 두면 테스트가 도는 동안 `5:20`이 유지된다.
    """
    monkeypatch.setattr(ovmod, "save_config", lambda cfg, path=None: None)
    now = datetime.now(timezone.utc)
    overlay = ovmod.Overlay(root, Config())
    overlay.update(
        HudState(
            Status.OK,
            UsageSnapshot(
                62.0, now + timedelta(hours=5, minutes=20, seconds=30), None, now
            ),
            "",
        )
    )
    overlay._redraw()
    root.update()
    yield overlay
    overlay._win.destroy()


def _click(overlay, x=30, y=30):
    overlay._canvas.event_generate("<Button-1>", x=x, y=y)
    overlay._canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
    overlay._win.update()


def test_one_click_toggles_once(hud):
    """**핸들러가 두 번 돌면 토글이 상쇄되어 아무 일도 안 일어난다.**

    화면에서는 "클릭해도 남은 시간이 안 나온다"로 보인다.
    """
    assert hud._show_time is False
    _click(hud)
    assert hud._show_time is True
    _click(hud)
    assert hud._show_time is False


def test_the_click_actually_changes_what_is_drawn(hud):
    """상태 변수만 보면 그리기가 안 따라오는 경우를 놓친다."""
    def drawn():
        c = hud._canvas
        return [c.itemcget(i, "text") for i in c.find_all() if c.type(i) == "text"]

    assert drawn() == ["62"]
    _click(hud)
    assert drawn() == ["5:20"]


def test_a_right_click_opens_exactly_one_menu(hud, monkeypatch):
    """두 번 열리면 메뉴가 겹쳐 뜨고 하나를 닫아도 다른 하나가 남는다."""
    opened = []
    monkeypatch.setattr(hud, "_show_menu", lambda x, y: opened.append((x, y)))
    hud._canvas.event_generate("<Button-3>", x=20, y=20)
    hud._win.update()
    assert len(opened) == 1


def test_a_drag_does_not_toggle(hud):
    """3px 판정. 끌고 나서 뗀 것은 클릭이 아니다."""
    canvas = hud._canvas
    canvas.event_generate("<Button-1>", x=30, y=30)
    canvas.event_generate("<B1-Motion>", x=50, y=30)
    canvas.event_generate("<ButtonRelease-1>", x=50, y=30)
    hud._win.update()
    assert hud._show_time is False


def test_the_overlay_stops_climbing_while_its_own_menu_is_open(hud, monkeypatch):
    """**항상 위 재주장이 자기 메뉴를 덮는다.**

    메뉴는 방금 누른 자리, 곧 오버레이 위에 뜨므로 반드시 겹친다. 재주장을 안
    쉬면 1초 안에 메뉴가 오버레이 뒤로 사라진다 (실측으로 그랬다).
    """
    from claude_usage_overlay import menu_popup

    climbed = []
    monkeypatch.setattr(ovmod, "keep_on_top", lambda hwnd: climbed.append(hwnd))

    hud._keep_on_top()
    assert len(climbed) == 1, "평소에는 올라가야 한다"

    monkeypatch.setattr(menu_popup, "is_open", lambda: True)
    hud._keep_on_top()
    assert len(climbed) == 1, "메뉴가 떠 있는 동안은 쉰다"


def test_a_hidden_overlay_does_not_climb(hud, monkeypatch):
    """숨은 창의 z-순서를 만지면 잠깐 나타나 보일 수 있다."""
    climbed = []
    monkeypatch.setattr(ovmod, "keep_on_top", lambda hwnd: climbed.append(hwnd))
    hud._visible = False
    hud._keep_on_top()
    assert climbed == []


def test_entering_and_leaving_flips_hover_once(hud):
    """호버가 두 번 뒤집히면 자세히 모드의 ⚙·✕가 깜빡인다."""
    hud._canvas.event_generate("<Enter>", x=30, y=30)
    hud._win.update()
    assert hud._hover is True
    hud._canvas.event_generate("<Leave>", x=30, y=30)
    hud._win.update()
    assert hud._hover is False
