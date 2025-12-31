"""
RadioScript Prompter
TUI interface for displaying prompts and controlling recording.
"""

import curses
import textwrap
from typing import Callable, Optional


class Prompter:
    """
    Terminal UI prompter for recording sessions.
    Displays text to read and controls recording.
    """
    
    def __init__(self):
        self.scroll_speed = 2  # lines per second (when auto-scrolling)
        self.current_line = 0
    
    def show_prompt(
        self,
        text: str,
        segment_info: str,
        on_record: Callable[[], Optional[str]],
        on_playback: Optional[Callable[[], None]] = None,
        on_start_recording: Optional[Callable[[], bool]] = None,
        on_stop_recording: Optional[Callable[[], Optional[str]]] = None,
        on_is_recording: Optional[Callable[[], bool]] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Display a prompt and wait for user action.

        Args:
            text: The text to display
            segment_info: Info about current segment (e.g., "Segment 3/10")
            on_record: Callback to start recording, returns filepath (legacy, blocking)
            on_playback: Optional callback to play last recording
            on_start_recording: Optional callback to start background recording
            on_stop_recording: Optional callback to stop background recording
            on_is_recording: Optional callback to check if recording

        Returns:
            (continue_session, recorded_filepath)
        """
        return curses.wrapper(
            self._run_prompt,
            text,
            segment_info,
            on_record,
            on_playback,
            on_start_recording,
            on_stop_recording,
            on_is_recording,
        )
    
    def _run_prompt(
        self,
        stdscr,
        text: str,
        segment_info: str,
        on_record: Callable[[], Optional[str]],
        on_playback: Optional[Callable[[], None]],
        on_start_recording: Optional[Callable[[], bool]],
        on_stop_recording: Optional[Callable[[], Optional[str]]],
        on_is_recording: Optional[Callable[[], bool]],
    ) -> tuple[bool, Optional[str]]:
        """Curses main loop for the prompter."""

        curses.curs_set(0)  # Hide cursor
        curses.use_default_colors()

        # Initialize colors
        curses.init_pair(1, curses.COLOR_GREEN, -1)   # Header
        curses.init_pair(2, curses.COLOR_YELLOW, -1)  # Highlight
        curses.init_pair(3, curses.COLOR_CYAN, -1)    # Help
        curses.init_pair(4, curses.COLOR_RED, -1)     # Recording

        recorded_path = None
        self.current_line = 0
        is_recording = False
        
        while True:
            # Check recording status
            if on_is_recording:
                is_recording = on_is_recording()

            stdscr.clear()
            height, width = stdscr.getmaxyx()

            # Calculate text area (leave room for header and footer)
            text_height = height - 6
            text_width = width - 4

            # Wrap text to fit width
            wrapped_lines = []
            for paragraph in text.split('\n'):
                if paragraph.strip():
                    wrapped = textwrap.wrap(paragraph, width=text_width)
                    wrapped_lines.extend(wrapped)
                else:
                    wrapped_lines.append('')

            # Header
            if is_recording:
                header = f" 🔴 RECORDING - {segment_info} "
                stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
            else:
                header = f" 📻 RadioScript - {segment_info} "
                stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
            stdscr.addstr(0, (width - len(header)) // 2, header)
            if is_recording:
                stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)
            else:
                stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
            
            # Separator
            stdscr.addstr(1, 0, "─" * width)
            
            # Text area
            visible_lines = wrapped_lines[self.current_line:self.current_line + text_height]
            
            for i, line in enumerate(visible_lines):
                y = i + 3
                if y < height - 3:
                    # Highlight first visible line
                    if i == 0:
                        stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
                        stdscr.addstr(y, 2, line[:text_width])
                        stdscr.attroff(curses.color_pair(2) | curses.A_BOLD)
                    else:
                        stdscr.addstr(y, 2, line[:text_width])
            
            # Scroll indicator
            if len(wrapped_lines) > text_height:
                progress = (self.current_line + 1) / max(1, len(wrapped_lines) - text_height + 1)
                bar_height = text_height
                bar_pos = int(progress * (bar_height - 1))
                for i in range(bar_height):
                    char = "█" if i == bar_pos else "│"
                    if 3 + i < height - 3:
                        stdscr.addstr(3 + i, width - 1, char)
            
            # Footer separator
            stdscr.addstr(height - 3, 0, "─" * width)
            
            # Help line
            stdscr.attron(curses.color_pair(3))
            if is_recording:
                help_text = "[SPACE] Stop  [↑/↓] Scroll  [Q] Quit"
            else:
                help_text = "[R] Record  [P] Play  [↑/↓] Scroll  [N] Next  [S] Skip  [Q] Quit"
            stdscr.addstr(height - 2, (width - len(help_text)) // 2, help_text)
            stdscr.attroff(curses.color_pair(3))
            
            # Status
            if recorded_path:
                status = "✅ Recorded"
                stdscr.attron(curses.color_pair(1))
            else:
                status = "⏳ Not recorded"
                stdscr.attron(curses.color_pair(4))
            stdscr.addstr(height - 1, (width - len(status)) // 2, status)
            stdscr.attroff(curses.color_pair(1) | curses.color_pair(4))
            
            stdscr.refresh()

            # Handle input (non-blocking if recording)
            if is_recording:
                stdscr.timeout(100)  # 100ms timeout for refresh
            else:
                stdscr.timeout(-1)  # Blocking
            key = stdscr.getch()
            
            if key == ord('q') or key == ord('Q'):
                # If recording, stop it first
                if is_recording and on_stop_recording:
                    on_stop_recording()
                return (False, recorded_path)

            elif key == ord('r') or key == ord('R'):
                if not is_recording:
                    # Start background recording
                    if on_start_recording:
                        if on_start_recording():
                            is_recording = True
                    else:
                        # Fallback to legacy blocking mode
                        curses.endwin()
                        recorded_path = on_record()
                        stdscr = curses.initscr()
                        curses.curs_set(0)
                        curses.use_default_colors()
                        curses.init_pair(1, curses.COLOR_GREEN, -1)
                        curses.init_pair(2, curses.COLOR_YELLOW, -1)
                        curses.init_pair(3, curses.COLOR_CYAN, -1)
                        curses.init_pair(4, curses.COLOR_RED, -1)

            elif key == ord(' '):
                # Stop recording with spacebar
                if is_recording and on_stop_recording:
                    result = on_stop_recording()
                    if result:
                        recorded_path = result
                    is_recording = False
            
            elif key == ord('p') or key == ord('P'):
                if on_playback and recorded_path:
                    curses.endwin()
                    on_playback()
                    stdscr = curses.initscr()
                    curses.curs_set(0)
            
            elif key == ord('n') or key == ord('N'):
                # Next segment (only if recorded)
                if recorded_path:
                    return (True, recorded_path)
            
            elif key == ord('s') or key == ord('S'):
                # Skip segment
                return (True, recorded_path)
            
            elif key == curses.KEY_UP or key == -1:
                if key == curses.KEY_UP:
                    self.current_line = max(0, self.current_line - 1)

            elif key == curses.KEY_DOWN:
                max_scroll = max(0, len(wrapped_lines) - text_height)
                self.current_line = min(max_scroll, self.current_line + 1)
            
            elif key == curses.KEY_PPAGE:  # Page Up
                self.current_line = max(0, self.current_line - text_height)
            
            elif key == curses.KEY_NPAGE:  # Page Down
                max_scroll = max(0, len(wrapped_lines) - text_height)
                self.current_line = min(max_scroll, self.current_line + text_height)
            
            elif key == curses.KEY_HOME:
                self.current_line = 0
            
            elif key == curses.KEY_END:
                max_scroll = max(0, len(wrapped_lines) - text_height)
                self.current_line = max_scroll


def demo():
    """Demo the prompter."""
    sample_text = """
Bonjour à tous et bienvenue dans cette émission spéciale consacrée aux nouvelles technologies.

Aujourd'hui nous allons explorer les dernières avancées en intelligence artificielle et leur impact sur notre quotidien.

Nous recevons pour en parler Jean Dupont, chercheur au CNRS et spécialiste des modèles de langage.

Jean, pouvez-vous nous expliquer en quelques mots ce qu'est un grand modèle de langage et pourquoi cela révolutionne notre rapport à l'informatique ?

Merci Jean pour ces explications passionnantes. Nous allons maintenant passer aux questions de nos auditeurs.
""".strip()
    
    prompter = Prompter()
    
    def mock_record():
        print("\n[Mock recording started...]")
        input("Press Enter to stop mock recording...")
        return "/tmp/mock_recording.wav"
    
    def mock_playback():
        print("\n[Mock playback...]")
        input("Press Enter to continue...")
    
    result = prompter.show_prompt(
        text=sample_text,
        segment_info="Segment 1/5",
        on_record=mock_record,
        on_playback=mock_playback,
    )
    
    print(f"\nResult: continue={result[0]}, path={result[1]}")


if __name__ == '__main__':
    demo()
