from claude_usage_overlay import theme


def test_below_warn_is_green():
    assert theme.color_for(0) == theme.GREEN
    assert theme.color_for(69.9) == theme.GREEN


def test_warn_band_is_yellow():
    assert theme.color_for(70) == theme.YELLOW
    assert theme.color_for(89.9) == theme.YELLOW


def test_danger_band_is_red():
    assert theme.color_for(90) == theme.RED
    assert theme.color_for(100) == theme.RED


def test_custom_thresholds_are_honored():
    assert theme.color_for(55, warn=50, danger=80) == theme.YELLOW
    assert theme.color_for(85, warn=50, danger=80) == theme.RED
