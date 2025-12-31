# RadioScript

**Markdown-driven radio production**

RadioScript is a command-line tool for producing radio shows from a simple Markdown file. The file describes the show as an alternation of text segments (to be recorded) and audio files (music, jingles, interviews). Once every text segment have been recorded with `radioscript record` the show can be assembled with`radioscript build`.

## Concept

```markdown
Hello everyone, welcome to the show.

[audio](./assets/jingle.mp3)

# News

Today we're talking about artificial intelligence.

[audio](./assets/transition.mp3)
```

- **Text** is displayed in a prompter and recorded by the host
- **Audio links** reference files to insert (music, jingles, interviews)
- The tool **automatically assembles** everything with crossfades

**Workflow:**
1. Initialize project in current directory → `radioscript init`
2. Edit `script.md`
3. Record voice segments → `radioscript record`
4. Build the final show → `radioscript build`

## Installation

### System Dependencies

```bash
# Ubuntu/Debian
sudo apt install sox libsox-fmt-all ffmpeg

# macOS with Homebrew
brew install sox ffmpeg

# macOS with MacPorts
sudo port install sox ffmpeg
```

**Note:** Windows is not officially supported yet, but should work with WSL2.

### Installing RadioScript

**From PyPI (recommended):**

```bash
pip install radioscript
```

**From source (for development):**

```bash
git clone https://github.com/orlarey/Radioscript.git
cd Radioscript
pip install -e .
```

The `radioscript` command will be available globally in your Python environment.

**Uninstallation:**
```bash
pip uninstall radioscript
```

## Usage

### Starting a New Project

```bash
# Create a new folder for your show
mkdir my-show
cd my-show

# Initialize the project (copies template and assets from radioscript/templates/)
radioscript init
```

Created structure:
```
my-show/
├── script.md          # Show script (editable)
├── assets/            # Audio files (jingles, music)
├── recordings/        # Voice recordings (generated)
└── output/            # Final file (generated)
```

### Commands

All commands use `script.md` from the current directory:

```bash
# Check audio files and recording status
radioscript check

# Display script structure
radioscript parse

# Start recording session (prompter mode)
radioscript record

# Re-record a specific segment
radioscript record -s 3

# Build final show
radioscript build

# Full pipeline (parse → record → build)
radioscript make

# Show recording status
radioscript status
```

### Prompter Mode

The `record` mode displays a TUI interface:

```
 📻 RadioScript - Segment 1/5

────────────────────────────────────────────────────────────
  Hello everyone and welcome to this special year-end
  edition. I'm your host and today we'll review the major
  tech trends of 2024.
────────────────────────────────────────────────────────────

[R] Record  [P] Play  [↑/↓] Scroll  [N] Next  [S] Skip  [Q] Quit

                        ⏳ Not recorded
```

**Shortcuts:**
- `R`: Start recording
- `SPACE`: Stop recording
- `↑/↓`: Scroll text (even during recording!)
- `P`: Play last recording
- `N`: Next segment (if recorded)
- `S`: Skip this segment
- `Q`: Quit session

## Markdown File Format

### Frontmatter (configuration)

```yaml
---
title: "My Show"
output: "show.mp3"                # Saved to output/show.mp3
normalization: -16 LUFS

trim_silence: true
trim_threshold: 1%

# Option 1: Use crossfades (default) - smooth transitions
crossfade:
  voice_to_music: 0.2             # Duration in seconds
  music_to_voice: 0.2
  voice_to_voice: 0.2
  music_to_music: 0.2

# Option 2: Use fixed silence gaps - hard cuts with silence
# gap: 0.5                        # 0.5 seconds of silence between segments
---
```

**Crossfades vs Gaps:**
- **Crossfades** (default): Smooth transitions where audio fades in/out
- **Gaps**: Hard cuts with silence between segments (useful for clear separation)
- Setting `gap` disables all crossfades

### Document Body

```markdown
Introduction text to record.

[audio](./assets/jingle_intro.mp3)

# Section 1

Section 1 text.

[audio](./assets/transition.mp3)

## Subsection

Subsection text.

[audio crossfade=1.5](./assets/music.mp3)  # Override: 1.5s crossfade for this segment
```

**Note:** `crossfade=X` overrides global settings for that specific audio file only.

### Rules

| Element | Behavior |
|---------|----------|
| Plain text | Segment to record |
| `[audio](path)` | Audio file to insert |
| `[audio crossfade=X](path)` | Audio with custom crossfade |
| `# Title` | Defines file name prefix |

### Recording Naming

Markdown headings define file names:

```
# Introduction          → introduction_001_<datetime>.wav
## News                 → introduction_news_001_<datetime>.wav
# Interview             → interview_001_<datetime>.wav
```

## Directory Structure

```
my_show/
├── script.md                # Source script
├── assets/                  # Audio files (jingles, music)
│   ├── jingle_intro.mp3
│   └── ...
├── recordings/              # Recordings (generated)
│   ├── introduction_001_20241230-143052.wav
│   └── ...
├── output/                  # Final file (generated)
│   └── show.mp3
└── .radioscript.json        # Session state
```

## Audio Processing

### Recording
- Format: WAV 48kHz 16bit mono
- Automatic silence trimming (start only, preserves natural ending)

### Crossfades
- Voice → Music: 0.2s (default)
- Music → Voice: 0.2s
- Voice → Voice: 0.2s
- Music → Music: 0.2s

### Normalization
- EBU R128 Standard
- Target: -16 LUFS (podcast/streaming)
- True Peak: -1.5 dBTP

### Export
- Format: MP3 192kbps (configurable)

## Complete Example

Here's a complete working `script.md`:

```markdown
---
title: "Tech Weekly Episode 42"
output: "tech-weekly-042.mp3"
normalization: -16 LUFS
trim_silence: true
trim_threshold: 1%
crossfade:
  voice_to_music: 0.2
  music_to_voice: 0.2
  voice_to_voice: 0.2
  music_to_music: 0.2
---

Welcome to Tech Weekly, your source for tech news!

[audio](./assets/jingle.mp3)

# Introduction

Hello everyone! Today we're covering AI breakthroughs,
new programming languages, and cybersecurity trends.

[audio](./assets/transition.mp3)

# Main Topic: AI Developments

Recent advances in AI have been remarkable...

[audio crossfade=0.5](./assets/music.mp3)

# Conclusion

Thanks for listening! Join us next week for more tech news.

[audio](./assets/jingle.mp3)
```

## Troubleshooting

**Missing audio files:**
- `radioscript check` shows which files are missing
- Build will warn you before proceeding with missing files

**Session state:**
- `.radioscript.json` tracks recording progress
- Delete it to start fresh
- Keep it to resume an interrupted session

## License

MIT

## Author

Yann Orlarey
