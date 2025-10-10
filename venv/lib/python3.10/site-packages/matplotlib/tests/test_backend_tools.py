import pytest

from matplotlib.backend_tools import ToolHelpBase


@pytest.mark.parametrize('rc_shortcut,expected', [
    ('home', 'Home'),
    ('backspace', 'Backspace'),
    ('f1', 'F1'),
    ('ctrl+a', 'Ctrl+A'),
    ('ctrl+A', 'Ctrl+Shift+A'),
    ('a', 'a'),
    ('A', 'A'),
    ('ctrl+shift+f1', 'Ctrl+Shift+F1'),
    ('1', '1'),
    ('cmd+p', 'Cmd+P'),
    ('cmd+1', 'Cmd+1'),
])
def test_format_shortcut(rc_shortcut, expected):
    assert ToolHelpBase.format_shortcut(rc_shortcut) == expected
