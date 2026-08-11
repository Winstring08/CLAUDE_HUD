"""테스트가 함께 쓰는 Tk 루트.

**모듈마다 tk.Tk()를 만들면 안 된다.** 이 환경에서는 첫 인스턴스를 destroy()한 뒤
같은 프로세스에서 두 번째를 만들면 Tcl이 자기 라이브러리를 못 읽고 죽는다
(실측: `couldn't read file ".../tcl/tk8.6/ttk/ttk.tcl": no such file or directory`
— 파일은 멀쩡히 있다). 순수 tkinter만으로 재현되므로 이 프로젝트 코드와는 무관하다.

파일 하나가 Tk를 쓸 때는 드러나지 않다가, 두 번째 파일이 Tk를 쓰기 시작하는
순간 뒤에 오는 쪽이 통째로 ERROR가 된다. 파일별로 돌리면 멀쩡하고 전체로 돌리면
깨지므로 원인을 찾기 어렵다.

그래서 루트는 **세션에 하나**다. withdraw해 두므로 창은 여전히 뜨지 않는다.
"""

import tkinter as tk

import pytest


@pytest.fixture(scope="session")
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()
