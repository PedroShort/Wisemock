"""Window geometry helpers shared by the web and fallback Qt windows."""
import sys

from PyQt5.QtWidgets import QApplication


def _available_geometry(window):
    """Return the usable screen geometry for ``window``.

    Qt reports this in logical pixels, so it already accounts for Windows
    display scaling and macOS Retina scaling.
    """
    app = QApplication.instance()
    screen = None
    if window is not None and hasattr(window, "screen"):
        try:
            screen = window.screen()
        except Exception:
            screen = None
    if screen is None and app is not None:
        try:
            screen = app.primaryScreen()
        except Exception:
            screen = None
    if screen is not None:
        return screen.availableGeometry()
    desktop = QApplication.desktop()
    return desktop.availableGeometry(window) if window is not None else desktop.availableGeometry()


def fit_window_to_screen(window, preferred_size, minimum_size=(700, 520),
                         screen_fraction=0.88, edge_margin=48):
    """Resize and center ``window`` within the current screen's work area."""
    available = _available_geometry(window)
    avail_w = max(1, available.width())
    avail_h = max(1, available.height())

    max_w = min(int(avail_w * screen_fraction), max(1, avail_w - edge_margin))
    max_h = min(int(avail_h * screen_fraction), max(1, avail_h - edge_margin))
    max_w = max(min(320, avail_w), min(avail_w, max_w))
    max_h = max(min(360, avail_h), min(avail_h, max_h))

    min_w = min(int(minimum_size[0]), max_w)
    min_h = min(int(minimum_size[1]), max_h)
    width = max(min(int(preferred_size[0]), max_w), min_w)
    height = max(min(int(preferred_size[1]), max_h), min_h)

    window.setMinimumSize(min_w, min_h)
    window.resize(width, height)
    left = available.x() + (avail_w - width) // 2
    top = available.y() + (avail_h - height) // 2
    window.move(left, top)


def web_zoom_for_screen(window):
    """Return a WebEngine zoom factor that neutralizes Windows DPI inflation."""
    if not sys.platform.startswith("win"):
        return 1.0

    app = QApplication.instance()
    screen = None
    if window is not None and hasattr(window, "screen"):
        try:
            screen = window.screen()
        except Exception:
            screen = None
    if screen is None and app is not None:
        screen = app.primaryScreen()
    if screen is None:
        return 1.0

    scale_candidates = [1.0]
    try:
        scale_candidates.append(float(screen.devicePixelRatio()))
    except Exception:
        pass
    try:
        scale_candidates.append(float(screen.logicalDotsPerInch()) / 96.0)
    except Exception:
        pass

    scale = max(scale_candidates)
    if scale <= 1.05:
        return 1.0
    return max(0.5, min(1.0, 1.0 / scale))
