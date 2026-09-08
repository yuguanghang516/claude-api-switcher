"""Isolated visual review: Ctrl+1..5 pages, Ctrl+L/D light/dark."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.gui import MainWindow
from app.theme import theme

class Preview(MainWindow):
    def _detect_gcli2api(self):
        pass
    def _detect_claude_environment(self):
        pass

with tempfile.TemporaryDirectory(prefix='switcher-ui-review-') as state:
    app = Preview(str(Path(state) / 'data'), str(Path(state) / 'logs'))
    app.root.title('Claude API Switcher — UI REVIEW')
    if '--light' in sys.argv:
        theme.apply_mode('light')
    if '--small' in sys.argv:
        app.root.geometry('1100x720')
    for page in ('switcher', 'gcli', 'gateway', 'usage', 'settings'):
        if '--' + page in sys.argv:
            app._switch_tab(page)
    for index, page in enumerate(('switcher', 'gcli', 'gateway', 'usage', 'settings'), 1):
        app.root.bind(f'<Control-Key-{index}>', lambda event, page=page: app._switch_tab(page))
    app.root.bind('<Control-l>', lambda event: theme.apply_mode('light'))
    app.root.bind('<Control-d>', lambda event: theme.apply_mode('dark'))
    app.root.bind('<Control-m>', lambda event: app.root.geometry('1100x720'))
    app.root.bind('<Control-b>', lambda event: app.root.geometry('1240x860'))
    app.run()
