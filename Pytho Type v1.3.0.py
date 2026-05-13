import sys
import os
import termios
import subprocess
import shlex
import time
import curses
import json
import re
from datetime import datetime


# ---------- app settings ----------

APP_NAME = "Pytho Type"
APP_SUBTITLE = "A python typing game without pygame"
APP_AUTHOR = "Plusone & ChatGPT"

DEFAULT_TEXT = (
    "By precisely shaping the leading edge of ultrafast high-power laser pulses, "
    "bright 'harmonic' radiation has been generated with great efficiency from plasma "
    "oscillating at almost the speed of light. This long-sought regime removes a key "
    "barrier to the production of extremely intense electromagnetic fields for "
    "applications such as compact particle acceleration, attosecond science and "
    "strong-field physics."
)

DATA_DIR = os.path.expanduser("~/.pytho_type")
TEXTS_PATH = os.path.join(DATA_DIR, "saved_texts.json")
RECORDS_PATH = os.path.join(DATA_DIR, "records.json")
FONT_SIZE_PATH = os.path.join(DATA_DIR, "font_size.txt")

DEFAULT_FONT_SIZE = 20
MIN_FONT_SIZE = 12
MAX_FONT_SIZE = 40
FONT_SIZE_STEP = 2

MAX_GAME_WIDTH = 82
MIN_GAME_WIDTH = 42


# ---------- setup ----------

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


ensure_data_dir()


# ---------- font size ----------

def load_font_size():
    try:
        with open(FONT_SIZE_PATH, "r", encoding="utf-8") as f:
            size = int(f.read().strip())
        return max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))
    except Exception:
        return DEFAULT_FONT_SIZE


def save_font_size(size):
    ensure_data_dir()
    with open(FONT_SIZE_PATH, "w", encoding="utf-8") as f:
        f.write(str(size))


def apply_terminal_font_size(size):
    size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, int(size)))

    script = f'''
    tell application "Terminal"
        activate
        try
            set font size of current settings of selected tab of front window to {size}
        end try
    end tell
    '''

    subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    save_font_size(size)


# ---------- auto relaunch in dedicated Terminal window ----------

def relaunch_in_terminal_if_needed():
    try:
        fd = sys.stdin.fileno()
        termios.tcgetattr(fd)
        return
    except Exception:
        pass

    script_path = os.path.abspath(__file__)
    command = f"python3 {shlex.quote(script_path)}"
    font_size = load_font_size()

    # Important:
    # 1. Create a dedicated Terminal tab/window for Pytho Type.
    # 2. Try to fullscreen first.
    # 3. Apply font size after fullscreen.
    applescript = f'''
    tell application "Terminal"
        activate
        set gameTab to do script {command!r}
        delay 0.8

        try
            set custom title of gameTab to "Pytho Type"
        end try
    end tell

    delay 0.5

    tell application "System Events"
        tell process "Terminal"
            set frontmost to true

            try
                perform action "AXRaise" of window "Pytho Type"
            end try

            delay 0.2
            keystroke "f" using {{control down, command down}}
        end tell
    end tell

    delay 0.8

    tell application "Terminal"
        try
            set font size of current settings of selected tab of front window to {font_size}
        end try
    end tell
    '''

    subprocess.run(["osascript", "-e", applescript])
    sys.exit()


relaunch_in_terminal_if_needed()


# ---------- json storage ----------

def load_json(path, default):
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def save_json(path, data):
    ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_text_library():
    return load_json(TEXTS_PATH, {})


def save_text_library(data):
    save_json(TEXTS_PATH, data)


def load_records():
    return load_json(RECORDS_PATH, [])


def save_records(records):
    save_json(RECORDS_PATH, records)


# ---------- text cleaning / file reading ----------

def normalize_text(text):
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = " ".join(text.split())
    return text.strip()


def clean_rtf_artifacts(text):
    bad_patterns = [
        r"Helvetica;\s*;;\s*\*;;\s*irnatural\s*tightenfactor0",
        r"Helvetica;",
        r"irnatural\s*tightenfactor0",
        r"tightenfactor0",
        r"\*;;",
        r";;",
    ]

    for pattern in bad_patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    return normalize_text(text)


def strip_rtf_fallback(rtf):
    rtf = re.sub(r"{\\fonttbl.*?}", " ", rtf, flags=re.DOTALL)

    rtf = re.sub(
        r"\\u(-?\d+)\??",
        lambda m: chr(int(m.group(1))) if int(m.group(1)) >= 0 else " ",
        rtf
    )

    rtf = re.sub(r"\\'[0-9a-fA-F]{2}", " ", rtf)
    rtf = re.sub(r"\\par[d]?", " ", rtf)
    rtf = re.sub(r"\\line", " ", rtf)
    rtf = re.sub(r"\\tab", " ", rtf)
    rtf = re.sub(r"\\[a-zA-Z]+\d* ?", " ", rtf)
    rtf = rtf.replace("{", " ").replace("}", " ").replace("\\", " ")

    return clean_rtf_artifacts(rtf)


def read_text_file(path):
    path = os.path.expanduser(path).strip().strip("'").strip('"')
    lower_path = path.lower()

    if lower_path.endswith(".rtf"):
        result = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", path],
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and result.stdout.strip():
            return clean_rtf_artifacts(result.stdout)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    if raw.lstrip().startswith("{\\rtf"):
        result = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", path],
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and result.stdout.strip():
            return clean_rtf_artifacts(result.stdout)

        return strip_rtf_fallback(raw)

    return normalize_text(raw)


def choose_file_with_finder():
    script = '''
    set chosenFile to choose file with prompt "Choose a .txt or .rtf file for Pytho Type"
    POSIX path of chosenFile
    '''

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return None

    path = result.stdout.strip()
    return path if path else None


# ---------- curses helpers ----------

def init_colors():
    curses.start_color()
    curses.use_default_colors()

    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(4, curses.COLOR_WHITE, -1)
    curses.init_pair(5, curses.COLOR_CYAN, -1)
    curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_RED)
    curses.init_pair(7, curses.COLOR_YELLOW, -1)


def dynamic_width(stdscr):
    _, w = stdscr.getmaxyx()
    return max(MIN_GAME_WIDTH, min(MAX_GAME_WIDTH, w - 8))


def center_x(stdscr, content_width=None):
    _, w = stdscr.getmaxyx()
    if content_width is None:
        content_width = dynamic_width(stdscr)
    return max((w - content_width) // 2, 0)


def center_y(stdscr, block_height):
    h, _ = stdscr.getmaxyx()
    return max((h - block_height) // 2, 1)


def refresh_terminal_layout(stdscr):
    try:
        curses.update_lines_cols()
        curses.resize_term(0, 0)
        stdscr.clear()
        stdscr.refresh()
    except Exception:
        try:
            stdscr.clear()
            stdscr.refresh()
        except Exception:
            pass


def safe_addstr(stdscr, y, x, text, attr=0):
    h, w = stdscr.getmaxyx()

    if y < 0 or y >= h:
        return

    if x < 0 or x >= w:
        return

    max_len = max(w - x - 1, 0)

    if max_len <= 0:
        return

    try:
        stdscr.addstr(y, x, text[:max_len], attr)
    except curses.error:
        pass


def wait_key(stdscr):
    stdscr.refresh()
    return stdscr.getch()


def get_string(stdscr, y, x, max_len=2000):
    curses.echo()
    curses.curs_set(1)
    stdscr.refresh()

    try:
        value = stdscr.getstr(y, x, max_len).decode("utf-8")
    except Exception:
        value = ""

    curses.noecho()
    curses.curs_set(0)
    return value


def message_screen(stdscr, title, message):
    stdscr.clear()

    width = dynamic_width(stdscr)
    x = center_x(stdscr, width)
    y = center_y(stdscr, 7)

    safe_addstr(stdscr, y, x, title, curses.A_BOLD | curses.color_pair(5))
    y += 2
    safe_addstr(stdscr, y, x, message)
    y += 2
    safe_addstr(stdscr, y, x, "Press Enter, Esc, or any key to continue.")
    wait_key(stdscr)


def wrap_text(text, width):
    lines = []
    start = 0

    while start < len(text):
        end = min(start + width, len(text))

        if end < len(text):
            space = text.rfind(" ", start, end)
            if space > start:
                end = space + 1

        lines.append((start, end))
        start = end

    return lines


def draw_title(stdscr, y, x, subtitle=None):
    safe_addstr(stdscr, y, x, APP_NAME, curses.A_BOLD | curses.color_pair(5))
    if subtitle:
        safe_addstr(stdscr, y + 1, x, subtitle, curses.color_pair(4))


def confirm_screen(stdscr, question):
    stdscr.clear()

    width = dynamic_width(stdscr)
    x = center_x(stdscr, width)
    y = center_y(stdscr, 6)

    safe_addstr(stdscr, y, x, "Confirm", curses.A_BOLD | curses.color_pair(7))
    y += 2
    safe_addstr(stdscr, y, x, question)
    y += 2
    safe_addstr(stdscr, y, x, "Press Y to confirm. Enter/Esc/other key = cancel.")
    stdscr.refresh()

    ch = stdscr.getch()
    return ch in (ord("y"), ord("Y"))


# ---------- home / settings ----------

def home_screen(stdscr):
    while True:
        stdscr.clear()

        width = dynamic_width(stdscr)
        x = center_x(stdscr, width)
        y = center_y(stdscr, 14)

        draw_title(stdscr, y, x, APP_SUBTITLE)
        y += 2
        safe_addstr(stdscr, y, x, f"by {APP_AUTHOR}", curses.color_pair(7))
        y += 3

        menu = [
            "P - start practice",
            "T - choose text",
            "R - records",
            "S - settings",
            "Q - quit",
        ]

        for item in menu:
            safe_addstr(stdscr, y, x, item)
            y += 1

        y += 2
        safe_addstr(stdscr, y, x, "Press P, T, R, S, or Q.")
        stdscr.refresh()

        ch = stdscr.getch()

        if ch in (ord("p"), ord("P")):
            return "practice"

        if ch in (ord("t"), ord("T")):
            return "choose_text"

        if ch in (ord("r"), ord("R")):
            return "records"

        if ch in (ord("s"), ord("S")):
            return "settings"

        if ch in (ord("q"), ord("Q")):
            return "quit"


def settings_screen(stdscr):
    while True:
        stdscr.clear()

        width = dynamic_width(stdscr)
        x = center_x(stdscr, width)
        y = center_y(stdscr, 13)

        draw_title(stdscr, y, x, "Settings")
        y += 3

        menu = [
            "F - font size",
            "D - delete saved texts",
            "R - delete typing records",
            "A - delete all app data",
            "Enter / Esc - back",
        ]

        for item in menu:
            safe_addstr(stdscr, y, x, item)
            y += 1

        stdscr.refresh()

        ch = stdscr.getch()

        if ch in (10, 13, 27):
            return

        if ch in (ord("f"), ord("F")):
            font_settings_screen(stdscr)

        elif ch in (ord("d"), ord("D")):
            delete_saved_texts_screen(stdscr)

        elif ch in (ord("r"), ord("R")):
            delete_records_screen(stdscr)

        elif ch in (ord("a"), ord("A")):
            delete_all_app_data_screen(stdscr)


def delete_all_app_data_screen(stdscr):
    if confirm_screen(stdscr, "Delete saved texts, records, and font settings?"):
        for path in (TEXTS_PATH, RECORDS_PATH, FONT_SIZE_PATH):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

        message_screen(stdscr, "Deleted", "All app data has been deleted.")


def font_settings_screen(stdscr):
    while True:
        current_size = load_font_size()

        stdscr.clear()

        width = dynamic_width(stdscr)
        x = center_x(stdscr, width)
        y = center_y(stdscr, 10)

        safe_addstr(stdscr, y, x, "Font size settings", curses.A_BOLD | curses.color_pair(5))
        y += 2

        safe_addstr(stdscr, y, x, f"Current font size: {current_size}")
        y += 2

        safe_addstr(stdscr, y, x, "+ - increase font size")
        y += 1
        safe_addstr(stdscr, y, x, "- - decrease font size")
        y += 1
        safe_addstr(stdscr, y, x, "R - reset to default size")
        y += 1
        safe_addstr(stdscr, y, x, "Enter / Esc - back")
        y += 2

        safe_addstr(stdscr, y, x, "Press +, -, R, Enter, or Esc.")
        stdscr.refresh()

        ch = stdscr.getch()

        if ch in (10, 13, 27):
            return

        if ch in (ord("+"), ord("=")):
            apply_terminal_font_size(min(MAX_FONT_SIZE, current_size + FONT_SIZE_STEP))
            time.sleep(0.4)
            refresh_terminal_layout(stdscr)

        elif ch in (ord("-"), ord("_")):
            apply_terminal_font_size(max(MIN_FONT_SIZE, current_size - FONT_SIZE_STEP))
            time.sleep(0.4)
            refresh_terminal_layout(stdscr)

        elif ch in (ord("r"), ord("R")):
            apply_terminal_font_size(DEFAULT_FONT_SIZE)
            time.sleep(0.4)
            refresh_terminal_layout(stdscr)


# ---------- text selection ----------

def choose_text_screen(stdscr):
    while True:
        stdscr.clear()

        width = dynamic_width(stdscr)
        x = center_x(stdscr, width)
        y = center_y(stdscr, 13)

        draw_title(stdscr, y, x, "Choose text source")
        y += 3

        menu = [
            "D - use default text",
            "C - enter / paste custom text",
            "F - choose a .txt or .rtf file from Finder",
            "L - load saved text",
            "Enter / Esc - back",
        ]

        for item in menu:
            safe_addstr(stdscr, y, x, item)
            y += 1

        stdscr.refresh()

        ch = stdscr.getch()

        if ch in (10, 13, 27):
            return None

        if ch in (ord("d"), ord("D")):
            return DEFAULT_TEXT

        if ch in (ord("c"), ord("C")):
            text = enter_custom_text(stdscr)
            if text:
                return text

        if ch in (ord("f"), ord("F")):
            text = load_text_from_finder_screen(stdscr)
            if text:
                return text

        if ch in (ord("l"), ord("L")):
            text = load_saved_text_screen(stdscr)
            if text:
                return text


def enter_custom_text(stdscr):
    stdscr.clear()

    width = dynamic_width(stdscr)
    x = center_x(stdscr, width)
    y = center_y(stdscr, 6)

    safe_addstr(stdscr, y, x, "Enter or paste your custom text below:", curses.A_BOLD | curses.color_pair(5))
    y += 2

    prompt = "> "
    safe_addstr(stdscr, y, x, prompt)

    user_input = get_string(stdscr, y, x + len(prompt), 3000)
    user_input = normalize_text(user_input)

    return user_input if user_input else None


def load_text_from_finder_screen(stdscr):
    stdscr.clear()

    width = dynamic_width(stdscr)
    x = center_x(stdscr, width)
    y = center_y(stdscr, 5)

    safe_addstr(stdscr, y, x, "Opening Finder file picker...", curses.A_BOLD | curses.color_pair(5))
    y += 2
    safe_addstr(stdscr, y, x, "Choose a .txt or .rtf file.")
    stdscr.refresh()

    curses.endwin()

    try:
        path = choose_file_with_finder()
    finally:
        refresh_terminal_layout(stdscr)

    if not path:
        message_screen(stdscr, "No file selected", "Returning to text source menu.")
        return None

    try:
        text = read_text_file(path)

        if text:
            return text

        message_screen(stdscr, "Empty file", "The selected file has no readable text.")
        return None

    except Exception:
        message_screen(stdscr, "File error", "Could not read the selected file.")
        return None


def load_saved_text_screen(stdscr):
    library = load_text_library()

    if not library:
        message_screen(stdscr, "Saved texts", "No saved texts yet.")
        return None

    names = list(library.keys())
    page = 0
    per_page = 9

    while True:
        total_pages = max((len(names) - 1) // per_page + 1, 1)
        page = max(0, min(page, total_pages - 1))

        start = page * per_page
        end = start + per_page
        visible_names = names[start:end]

        stdscr.clear()

        width = dynamic_width(stdscr)
        x = center_x(stdscr, width)
        y = center_y(stdscr, min(19, len(visible_names) + 10))

        safe_addstr(stdscr, y, x, "Saved texts", curses.A_BOLD | curses.color_pair(5))
        y += 2

        safe_addstr(stdscr, y, x, f"Page {page + 1}/{total_pages}")
        y += 2

        for local_i, name in enumerate(visible_names, start=1):
            global_i = start + local_i
            preview = library[name][:45]
            safe_addstr(stdscr, y, x, f"{global_i} - {name}: {preview}...")
            y += 1

        y += 2
        safe_addstr(stdscr, y, x, "N - next page")
        y += 1
        safe_addstr(stdscr, y, x, "P - previous page")
        y += 1
        safe_addstr(stdscr, y, x, "E - last page")
        y += 1
        safe_addstr(stdscr, y, x, "Enter / Esc - back")
        y += 1
        safe_addstr(stdscr, y, x, "Press 1-9 to load visible item.")
        stdscr.refresh()

        ch = stdscr.getch()

        if ch in (10, 13, 27):
            return None

        if ch in (ord("n"), ord("N")) and page < total_pages - 1:
            page += 1

        elif ch in (ord("p"), ord("P")) and page > 0:
            page -= 1

        elif ch in (ord("e"), ord("E")):
            page = total_pages - 1

        elif ord("1") <= ch <= ord("9"):
            idx = ch - ord("1")
            if idx < len(visible_names):
                return library[visible_names[idx]]


def save_current_text_screen(stdscr, text):
    library = load_text_library()

    stdscr.clear()

    width = dynamic_width(stdscr)
    x = center_x(stdscr, width)
    y = center_y(stdscr, 7)

    safe_addstr(stdscr, y, x, "Save current text", curses.A_BOLD | curses.color_pair(5))
    y += 2

    prompt = "Name: "
    safe_addstr(stdscr, y, x, prompt)

    name = get_string(stdscr, y, x + len(prompt), 100).strip()

    if not name:
        return

    library[name] = text
    save_text_library(library)

    y += 2
    safe_addstr(stdscr, y, x, f"Saved as: {name}")
    y += 2
    safe_addstr(stdscr, y, x, "Press Enter, Esc, or any key to continue.")
    wait_key(stdscr)


# ---------- delete saved texts ----------

def delete_saved_texts_screen(stdscr):
    page = 0
    per_page = 9

    while True:
        library = load_text_library()

        if not library:
            message_screen(stdscr, "Saved texts", "There are no saved texts.")
            return

        names = list(library.keys())
        total_pages = max((len(names) - 1) // per_page + 1, 1)
        page = max(0, min(page, total_pages - 1))

        start = page * per_page
        end = start + per_page
        visible_names = names[start:end]

        stdscr.clear()

        width = dynamic_width(stdscr)
        x = center_x(stdscr, width)
        y = center_y(stdscr, min(20, len(visible_names) + 11))

        safe_addstr(stdscr, y, x, "Delete saved text", curses.A_BOLD | curses.color_pair(5))
        y += 2

        safe_addstr(stdscr, y, x, f"Page {page + 1}/{total_pages}")
        y += 2

        for local_i, name in enumerate(visible_names, start=1):
            global_i = start + local_i
            preview = library[name][:42]
            safe_addstr(stdscr, y, x, f"{global_i} - {name}: {preview}...")
            y += 1

        y += 2
        safe_addstr(stdscr, y, x, "1-9 - delete visible saved text")
        y += 1
        safe_addstr(stdscr, y, x, "N - next page")
        y += 1
        safe_addstr(stdscr, y, x, "P - previous page")
        y += 1
        safe_addstr(stdscr, y, x, "E - last page")
        y += 1
        safe_addstr(stdscr, y, x, "A - delete all saved texts")
        y += 1
        safe_addstr(stdscr, y, x, "Enter / Esc - back")
        stdscr.refresh()

        ch = stdscr.getch()

        if ch in (10, 13, 27):
            return

        if ch in (ord("n"), ord("N")) and page < total_pages - 1:
            page += 1

        elif ch in (ord("p"), ord("P")) and page > 0:
            page -= 1

        elif ch in (ord("e"), ord("E")):
            page = total_pages - 1

        elif ch in (ord("a"), ord("A")):
            if confirm_screen(stdscr, "Delete all saved texts?"):
                if os.path.exists(TEXTS_PATH):
                    os.remove(TEXTS_PATH)
                message_screen(stdscr, "Deleted", "All saved texts have been deleted.")
                return

        elif ord("1") <= ch <= ord("9"):
            idx = ch - ord("1")
            if idx < len(visible_names):
                name = visible_names[idx]
                if confirm_screen(stdscr, f"Delete saved text: {name}?"):
                    library = load_text_library()
                    if name in library:
                        del library[name]
                        if library:
                            save_text_library(library)
                        elif os.path.exists(TEXTS_PATH):
                            os.remove(TEXTS_PATH)
                    message_screen(stdscr, "Deleted", f"Saved text deleted: {name}")


# ---------- records ----------

def add_record(text, correct, mistakes, elapsed):
    records = load_records()

    total = correct + mistakes
    accuracy = correct / total * 100 if total else 0
    minutes = elapsed / 60 if elapsed > 0 else 1e-9
    wpm = (correct / 5) / minutes

    record = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "characters": len(text),
        "mistakes": mistakes,
        "total_keystrokes": total,
        "accuracy": round(accuracy, 2),
        "wpm": round(wpm, 2),
        "seconds": round(elapsed, 2),
        "preview": text[:80],
    }

    records.append(record)
    save_records(records)


def records_screen(stdscr):
    page = 0
    per_page = 7

    while True:
        records = load_records()

        stdscr.clear()

        width = dynamic_width(stdscr)
        x = center_x(stdscr, width)
        y = center_y(stdscr, 17)

        safe_addstr(stdscr, y, x, "Typing Records", curses.A_BOLD | curses.color_pair(5))
        y += 2

        if not records:
            safe_addstr(stdscr, y, x, "No records yet.")
            y += 2
            safe_addstr(stdscr, y, x, "Enter / Esc - back.")
            stdscr.refresh()

            ch = stdscr.getch()
            if ch in (10, 13, 27):
                return
            continue

        total_pages = max((len(records) - 1) // per_page + 1, 1)
        page = max(0, min(page, total_pages - 1))

        start = page * per_page
        end = start + per_page
        visible = records[start:end]

        safe_addstr(stdscr, y, x, f"Page {page + 1}/{total_pages}")
        y += 2

        for local_i, r in enumerate(visible, start=1):
            global_i = start + local_i
            line = (
                f"{global_i} - {r.get('time', '')} | "
                f"WPM {r.get('wpm', 0)} | "
                f"Acc {r.get('accuracy', 0)}% | "
                f"Mistakes {r.get('mistakes', 0)}"
            )
            safe_addstr(stdscr, y, x, line)
            y += 1

        y += 2
        safe_addstr(stdscr, y, x, "N - next page")
        y += 1
        safe_addstr(stdscr, y, x, "P - previous page")
        y += 1
        safe_addstr(stdscr, y, x, "E - last page")
        y += 1
        safe_addstr(stdscr, y, x, "D - delete records")
        y += 1
        safe_addstr(stdscr, y, x, "Enter / Esc - back")
        stdscr.refresh()

        ch = stdscr.getch()

        if ch in (ord("n"), ord("N")) and page < total_pages - 1:
            page += 1

        elif ch in (ord("p"), ord("P")) and page > 0:
            page -= 1

        elif ch in (ord("e"), ord("E")):
            page = total_pages - 1

        elif ch in (ord("d"), ord("D")):
            delete_records_screen(stdscr)

        elif ch in (10, 13, 27):
            return


def delete_records_screen(stdscr):
    page = 0
    per_page = 9

    while True:
        records = load_records()

        if not records:
            message_screen(stdscr, "Records", "There are no records to delete.")
            return

        total_pages = max((len(records) - 1) // per_page + 1, 1)
        page = max(0, min(page, total_pages - 1))

        start = page * per_page
        end = start + per_page
        visible = records[start:end]

        stdscr.clear()

        width = dynamic_width(stdscr)
        x = center_x(stdscr, width)
        y = center_y(stdscr, min(20, len(visible) + 11))

        safe_addstr(stdscr, y, x, "Delete typing record", curses.A_BOLD | curses.color_pair(5))
        y += 2

        safe_addstr(stdscr, y, x, f"Page {page + 1}/{total_pages}")
        y += 2

        for local_i, r in enumerate(visible, start=1):
            global_i = start + local_i
            line = (
                f"{global_i} - {r.get('time', '')} | "
                f"WPM {r.get('wpm', 0)} | "
                f"Acc {r.get('accuracy', 0)}%"
            )
            safe_addstr(stdscr, y, x, line)
            y += 1

        y += 2
        safe_addstr(stdscr, y, x, "1-9 - delete visible record")
        y += 1
        safe_addstr(stdscr, y, x, "N - next page")
        y += 1
        safe_addstr(stdscr, y, x, "P - previous page")
        y += 1
        safe_addstr(stdscr, y, x, "E - last page")
        y += 1
        safe_addstr(stdscr, y, x, "A - delete all records")
        y += 1
        safe_addstr(stdscr, y, x, "Enter / Esc - back")
        stdscr.refresh()

        ch = stdscr.getch()

        if ch in (10, 13, 27):
            return

        if ch in (ord("n"), ord("N")) and page < total_pages - 1:
            page += 1

        elif ch in (ord("p"), ord("P")) and page > 0:
            page -= 1

        elif ch in (ord("e"), ord("E")):
            page = total_pages - 1

        elif ch in (ord("a"), ord("A")):
            if confirm_screen(stdscr, "Delete all typing records?"):
                if os.path.exists(RECORDS_PATH):
                    os.remove(RECORDS_PATH)
                message_screen(stdscr, "Deleted", "All typing records have been deleted.")
                return

        elif ord("1") <= ch <= ord("9"):
            idx = ch - ord("1")
            if idx < len(visible):
                target_global_index = start + idx

                if confirm_screen(stdscr, "Delete this typing record?"):
                    records = load_records()

                    if 0 <= target_global_index < len(records):
                        records.pop(target_global_index)

                    if records:
                        save_records(records)
                    elif os.path.exists(RECORDS_PATH):
                        os.remove(RECORDS_PATH)

                    message_screen(stdscr, "Deleted", "Typing record deleted.")


# ---------- game screens ----------

def wait_for_start(stdscr, text):
    stdscr.clear()

    width = dynamic_width(stdscr)
    x = center_x(stdscr, width)
    lines = wrap_text(text, width)
    y = center_y(stdscr, min(len(lines) + 7, 19))

    draw_title(stdscr, y, x, "Text ready.")
    y += 3

    for start, end in lines[:10]:
        safe_addstr(stdscr, y, x, text[start:end])
        y += 1

    y += 2
    safe_addstr(stdscr, y, x, "Press Enter to start. Esc = return home.")
    stdscr.refresh()

    while True:
        ch = stdscr.getch()

        if ch in (10, 13):
            return "start"

        if ch == 27:
            return "home"

        if ch == 3:
            raise KeyboardInterrupt


def render_game(stdscr, text, index, mistakes, wrong_flash=False):
    stdscr.clear()

    width = dynamic_width(stdscr)
    x = center_x(stdscr, width)
    lines = wrap_text(text, width)
    block_height = len(lines) + 7
    y = center_y(stdscr, min(block_height, 22))

    draw_title(stdscr, y, x, "Type the highlighted character. Esc = quit this round.")
    y += 3

    for start, end in lines:
        col = x

        for i in range(start, end):
            ch = text[i]

            if i < index:
                attr = curses.color_pair(1) | curses.A_BOLD
            elif i == index:
                attr = curses.color_pair(6) | curses.A_BOLD if wrong_flash else curses.color_pair(3) | curses.A_BOLD
            else:
                attr = curses.color_pair(4)

            safe_addstr(stdscr, y, col, ch, attr)
            col += 1

        y += 1

    y += 2
    progress = f"Progress: {index}/{len(text)}    Mistakes: {mistakes}"
    safe_addstr(stdscr, y, x, progress, curses.color_pair(4))

    stdscr.refresh()


def show_results(stdscr, text, correct, mistakes, elapsed):
    stdscr.clear()

    width = dynamic_width(stdscr)
    x = center_x(stdscr, width)
    y = center_y(stdscr, 16)

    total_keystrokes = correct + mistakes
    accuracy = correct / total_keystrokes * 100 if total_keystrokes else 0
    minutes = elapsed / 60 if elapsed > 0 else 1e-9
    wpm = (correct / 5) / minutes

    safe_addstr(stdscr, y, x, "Pytho Type - Results", curses.A_BOLD | curses.color_pair(5))
    y += 2

    results = [
        f"Characters: {len(text)}",
        f"Mistakes: {mistakes}",
        f"Total keystrokes: {total_keystrokes}",
        f"Time: {round(elapsed, 2)} seconds",
        f"Accuracy: {round(accuracy, 2)} %",
        f"WPM: {round(wpm, 2)}",
    ]

    for line in results:
        safe_addstr(stdscr, y, x, line)
        y += 1

    y += 2
    menu = [
        "R - replay same text",
        "T - choose another text",
        "S - save current text",
        "Enter / Esc / H - home",
        "Q - quit",
    ]

    for item in menu:
        safe_addstr(stdscr, y, x, item)
        y += 1

    stdscr.refresh()


# ---------- game logic ----------

def play_round(stdscr, text):
    index = 0
    mistakes = 0
    correct = 0

    start_time = time.time()
    render_game(stdscr, text, index, mistakes)

    while index < len(text):
        ch_code = stdscr.getch()

        if ch_code == 3:
            raise KeyboardInterrupt

        if ch_code == 27:
            return None

        try:
            ch = chr(ch_code)
        except Exception:
            continue

        if ch == "\r":
            ch = "\n"

        expected = text[index]

        if ch == expected:
            index += 1
            correct += 1
            render_game(stdscr, text, index, mistakes)
        else:
            mistakes += 1
            render_game(stdscr, text, index, mistakes, wrong_flash=True)
            time.sleep(0.05)
            render_game(stdscr, text, index, mistakes)

    elapsed = time.time() - start_time
    add_record(text, correct, mistakes, elapsed)
    show_results(stdscr, text, correct, mistakes, elapsed)
    return correct, mistakes, elapsed


# ---------- main ----------

def main(stdscr):
    init_colors()

    try:
        curses.set_escdelay(1)
    except Exception:
        pass

    curses.curs_set(0)
    curses.noecho()

    # Keep keypad False so Esc responds immediately.
    stdscr.keypad(False)

    stdscr.nodelay(False)

    current_text = DEFAULT_TEXT

    while True:
        action = home_screen(stdscr)

        if action == "quit":
            return

        if action == "settings":
            settings_screen(stdscr)
            continue

        if action == "records":
            records_screen(stdscr)
            continue

        if action == "choose_text":
            selected = choose_text_screen(stdscr)
            if selected:
                current_text = selected
            continue

        if action == "practice":
            while True:
                start_action = wait_for_start(stdscr, current_text)

                if start_action == "home":
                    break

                result = play_round(stdscr, current_text)

                if result is None:
                    break

                correct, mistakes, elapsed = result

                while True:
                    ch = stdscr.getch()

                    if ch in (ord("r"), ord("R")):
                        break

                    if ch in (ord("t"), ord("T")):
                        selected = choose_text_screen(stdscr)
                        if selected:
                            current_text = selected
                        break

                    if ch in (ord("s"), ord("S")):
                        save_current_text_screen(stdscr, current_text)
                        show_results(stdscr, current_text, correct, mistakes, elapsed)
                        continue

                    if ch in (10, 13, 27, ord("h"), ord("H")):
                        break

                    if ch in (ord("q"), ord("Q")):
                        return

                    if ch == 3:
                        raise KeyboardInterrupt

                if ch in (10, 13, 27, ord("h"), ord("H")):
                    break


curses.wrapper(main)
