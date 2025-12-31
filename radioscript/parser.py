"""
RadioScript Parser
Parses a Markdown file into a list of segments (text prompts and audio files).
"""

import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import unicodedata


@dataclass
class Config:
    """Configuration from frontmatter."""
    title: str = "Untitled"
    output: str = "output.mp3"
    normalization: str = "-16 LUFS"
    trim_silence: bool = True
    trim_threshold: str = "1%"
    gap: Optional[float] = None  # silence duration between segments (replaces crossfade if set)
    crossfade: dict = field(default_factory=lambda: {
        "voice_to_music": 0.1,
        "music_to_voice": 0.1,
        "voice_to_voice": 0.1,
        "music_to_music": 0.1,
    })


@dataclass
class Segment:
    """A segment in the radio script."""
    id: int
    type: str  # "text" or "audio"
    content: str  # text content or audio path
    section: Optional[str] = None  # hierarchical section name
    filename: Optional[str] = None  # generated filename for recordings
    recorded: bool = False
    crossfade: Optional[float] = None  # override crossfade duration


def slugify(text: str) -> str:
    """Convert text to a slug suitable for filenames."""
    # Normalize unicode characters
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    # Convert to lowercase
    text = text.lower()
    # Replace spaces and special chars with hyphens
    text = re.sub(r'[^a-z0-9]+', '-', text)
    # Remove leading/trailing hyphens
    text = text.strip('-')
    return text


def parse_frontmatter(content: str) -> tuple[Config, str]:
    """Extract YAML frontmatter and return config + remaining content."""
    frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n'
    match = re.match(frontmatter_pattern, content, re.DOTALL)
    
    if match:
        yaml_content = match.group(1)
        remaining = content[match.end():]
        try:
            data = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError:
            data = {}
        
        config = Config(
            title=data.get('title', Config.title),
            output=data.get('output', Config.output),
            normalization=data.get('normalization', Config.normalization),
            trim_silence=data.get('trim_silence', Config.trim_silence),
            trim_threshold=data.get('trim_threshold', Config.trim_threshold),
            gap=data.get('gap'),
        )
        if 'crossfade' in data:
            config.crossfade.update(data['crossfade'])
        
        return config, remaining
    
    return Config(), content


def parse_markdown(filepath: str) -> tuple[Config, list[Segment]]:
    """Parse a Markdown file into config and segments."""
    path = Path(filepath)
    content = path.read_text(encoding='utf-8')
    
    config, body = parse_frontmatter(content)
    
    segments: list[Segment] = []
    segment_id = 0
    
    # Track heading hierarchy: {level: slug}
    heading_context: dict[int, str] = {}
    
    # Track segment index per section for numbering
    section_counters: dict[str, int] = {}
    
    # Pattern for audio links: [audio](path) or [audio crossfade=X](path)
    audio_pattern = r'\[audio(?:\s+crossfade=([0-9.]+))?\]\(([^)]+)\)'
    
    # Pattern for headings
    heading_pattern = r'^(#{1,6})\s+(.+)$'
    
    # Current text accumulator
    current_text_lines: list[str] = []
    
    def get_section_slug() -> Optional[str]:
        """Build section slug from heading hierarchy."""
        if not heading_context:
            return None
        # Sort by level and join slugs
        sorted_levels = sorted(heading_context.keys())
        return '_'.join(heading_context[level] for level in sorted_levels)
    
    def generate_filename(section: Optional[str]) -> str:
        """Generate filename for a recording."""
        nonlocal section_counters
        
        section_key = section or ''
        if section_key not in section_counters:
            section_counters[section_key] = 0
        section_counters[section_key] += 1
        
        index = section_counters[section_key]
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        
        if section:
            return f"{section}_{index:03d}_{timestamp}.wav"
        else:
            return f"_{index:03d}_{timestamp}.wav"
    
    def flush_text():
        """Save accumulated text as a segment."""
        nonlocal segment_id, current_text_lines
        
        text = '\n'.join(current_text_lines).strip()
        if text:
            segment_id += 1
            section = get_section_slug()
            segments.append(Segment(
                id=segment_id,
                type='text',
                content=text,
                section=section,
                filename=generate_filename(section),
                recorded=False,
            ))
        current_text_lines = []
    
    # Process line by line
    lines = body.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check for heading
        heading_match = re.match(heading_pattern, line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            slug = slugify(title)
            
            # Update heading context: set this level, clear deeper levels
            heading_context[level] = slug
            for l in list(heading_context.keys()):
                if l > level:
                    del heading_context[l]
            
            i += 1
            continue
        
        # Check for audio link
        audio_match = re.search(audio_pattern, line)
        if audio_match:
            # Flush any accumulated text first
            flush_text()
            
            crossfade_str = audio_match.group(1)
            audio_path = audio_match.group(2)
            
            segment_id += 1
            segments.append(Segment(
                id=segment_id,
                type='audio',
                content=audio_path,
                crossfade=float(crossfade_str) if crossfade_str else None,
            ))
            
            i += 1
            continue
        
        # Regular line: accumulate for text segment
        current_text_lines.append(line)
        i += 1
    
    # Flush remaining text
    flush_text()
    
    return config, segments


def print_segments(config: Config, segments: list[Segment]):
    """Pretty print the parsed structure."""
    print(f"Title: {config.title}")
    print(f"Output: {config.output}")
    print(f"Normalization: {config.normalization}")
    print(f"Trim silence: {config.trim_silence} (threshold: {config.trim_threshold})")
    print(f"Crossfade settings: {config.crossfade}")
    print()
    print("Segments:")
    print("-" * 60)
    
    for seg in segments:
        if seg.type == 'text':
            preview = seg.content[:50].replace('\n', ' ')
            if len(seg.content) > 50:
                preview += '...'
            print(f"  [{seg.id}] TEXT ({seg.section or 'intro'})")
            print(f"       File: {seg.filename}")
            print(f"       Content: \"{preview}\"")
            print(f"       Recorded: {seg.recorded}")
        else:
            xfade = f" (crossfade={seg.crossfade}s)" if seg.crossfade else ""
            print(f"  [{seg.id}] AUDIO{xfade}")
            print(f"       Path: {seg.content}")
        print()


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        config, segments = parse_markdown(sys.argv[1])
        print_segments(config, segments)
    else:
        print("Usage: python parser.py <file.md>")
