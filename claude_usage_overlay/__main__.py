"""진입점.

스레드 배치:
  메인 스레드   tkinter (오버레이·설정창) + 1초마다 상태 펌프
  폴러 스레드   5분마다 API 조회
  트레이 스레드 pystray 이벤트 루프
  (첫 실행에 한 번) 아이콘 고정 스레드

tkinter 창 조작은 메인 스레드에서만 한다. 폴러는 잠금으로 보호된 state()만
노출하고, 트레이 메뉴는 Overlay가 after()로 넘겨준 것만 창에 반영시킨다.
"""

import threading
import tkinter as tk

from . import first_run, font_install, tray_promote
from .config import load_config
from .credentials import CredentialStore
from .overlay import Overlay
from .poller import Poller
from .tray import Tray
from .winmetrics import enable_dpi_awareness

PUMP_INTERVAL_MS = 1000


def main() -> None:
    # Tk()보다 먼저 불러야 한다. 이걸 빠뜨리면 Windows가 창을 비트맵 확대하고
    # 그 위에 Overlay가 dpi_scale()을 또 곱해 배율의 제곱만큼 커진다.
    enable_dpi_awareness()

    # 번들 Pretendard를 이 프로세스에 올린다. 이것도 Tk()보다 먼저다 —
    # Tk는 시작할 때 글꼴 목록을 읽으므로, 나중에 올리면 이번 실행에서는 못 쓴다.
    font_install.activate()

    # **첫 실행인지는 여기서 한 번만 판정한다.** 안내창이 config.json을 저장하고
    # 아이콘 고정 스레드는 아이콘이 뜬 뒤에야 도는데, 둘이 각자 파일을 확인하면
    # 안내창이 먼저 저장해 버려 자동 시도가 영영 돌지 않는다.
    first = first_run.is_first_run()

    config = load_config()

    poller = Poller(store=CredentialStore(), config=config)
    poller.start()

    root = tk.Tk()
    root.withdraw()  # 보이지 않는 루트. 실제 창은 Overlay가 만드는 Toplevel이다

    overlay = Overlay(root, config)
    tray = Tray(poller, overlay, config)

    threading.Thread(target=tray.run, daemon=True).start()

    if first:
        first_run.show_intro(root, config, supported=tray_promote.is_supported())
        # **첫 실행 1회만 자동으로 써둔다.** 이후로는 건드리지 않는다 — 나중에
        # 직접 숨긴 사람과 싸우지 않기 위해서다.
        #
        # 별도 스레드인 이유는 항목이 아이콘이 한 번 뜬 뒤에야 생기기 때문이다.
        # 여기서 기다리면 mainloop가 시작되지 않아 창이 아예 안 뜬다.
        threading.Thread(target=tray_promote.promote_when_ready, daemon=True).start()

    def pump() -> None:
        try:
            state = poller.state()
            overlay.update(state)
            tray.refresh_icon()
        finally:
            # 재예약을 finally에 둔다. 이 줄에 도달하지 못하면 다음 after가
            # 안 걸리고 상태 갱신이 **영구히** 멈춘다 — 오버레이는 자기 _tick으로
            # 계속 그리므로 화면은 살아 있는 채 값만 얼어붙고, pythonw에는
            # 콘솔이 없어 아무도 원인을 못 본다.
            root.after(PUMP_INTERVAL_MS, pump)

    root.after(PUMP_INTERVAL_MS, pump)
    root.mainloop()


if __name__ == "__main__":
    main()
