"""PyInstaller 진입 스크립트.

`claude_usage_overlay/__main__.py`를 직접 엔트리로 주면 안 된다. PyInstaller는
그것을 패키지가 아니라 단독 스크립트로 실행하므로 `from .config import ...`
같은 상대 import가 전부 깨진다. 패키지를 정식으로 import하는 껍데기를 둔다.
"""

from claude_usage_overlay.__main__ import main

if __name__ == "__main__":
    main()
