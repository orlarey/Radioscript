"""
RadioScript Checker
Validates that all required audio files exist and checks recording status.
"""

import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from .parser import parse_markdown, Segment, Config


@dataclass
class AudioFileStatus:
    """Status of an external audio file."""
    path: str
    exists: bool
    duration: Optional[float] = None
    error: Optional[str] = None


@dataclass
class VoiceSegmentStatus:
    """Status of a voice recording segment."""
    segment: Segment
    recorded: bool
    filename: Optional[str] = None
    duration: Optional[float] = None


class Checker:
    """Checks audio files and recording status."""

    def __init__(self, script_path: str):
        self.script_path = Path(script_path)
        self.script_dir = self.script_path.parent
        self.recordings_dir = self.script_dir / "recordings"

        # Parse script
        self.config, self.segments = parse_markdown(str(self.script_path))

    def _get_duration(self, filepath: str) -> Optional[float]:
        """Get duration of an audio file in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
            return None

    def check_audio_files(self) -> list[AudioFileStatus]:
        """Check all external audio files referenced in the script."""
        audio_statuses = []

        for segment in self.segments:
            if segment.type != 'audio':
                continue

            audio_path = self.script_dir / segment.content
            exists = audio_path.exists()

            status = AudioFileStatus(
                path=segment.content,
                exists=exists,
            )

            if exists:
                status.duration = self._get_duration(str(audio_path))
                if status.duration is None:
                    status.error = "Could not read duration"

            audio_statuses.append(status)

        return audio_statuses

    def check_voice_recordings(self, state: dict) -> list[VoiceSegmentStatus]:
        """Check all voice recording segments."""
        voice_statuses = []

        for segment in self.segments:
            if segment.type != 'text':
                continue

            # Get state for this segment
            seg_key = str(segment.id)
            seg_state = state.get("segments", {}).get(seg_key, {})

            recorded = seg_state.get("recorded", False)
            filename = seg_state.get("filename")

            status = VoiceSegmentStatus(
                segment=segment,
                recorded=recorded,
                filename=filename,
            )

            # Check if file exists and get duration
            if recorded and filename:
                recording_path = self.recordings_dir / filename
                if recording_path.exists():
                    status.duration = self._get_duration(str(recording_path))
                else:
                    # Marked as recorded but file missing
                    status.recorded = False

            voice_statuses.append(status)

        return voice_statuses

    def check(self, state: dict) -> dict:
        """
        Perform complete check of the project.

        Args:
            state: The RadioScript state dict (from .radioscript.json)

        Returns:
            dict with check results
        """
        audio_files = self.check_audio_files()
        voice_recordings = self.check_voice_recordings(state)

        audio_ok = sum(1 for af in audio_files if af.exists)
        audio_total = len(audio_files)

        voice_ok = sum(1 for vr in voice_recordings if vr.recorded)
        voice_total = len(voice_recordings)

        ready_for_build = (audio_ok == audio_total) and (voice_ok == voice_total)

        return {
            "audio_files": audio_files,
            "voice_recordings": voice_recordings,
            "audio_ok": audio_ok,
            "audio_total": audio_total,
            "voice_ok": voice_ok,
            "voice_total": voice_total,
            "ready_for_build": ready_for_build,
        }


def format_duration(seconds: Optional[float]) -> str:
    """Format duration for display."""
    if seconds is None:
        return "?"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m{secs:.0f}s"


def print_check_results(config: Config, results: dict, script_path: str = None):
    """Pretty print check results."""
    print(f"📻 RadioScript Check")
    print(f"   Script: {config.title}")
    print()

    # External audio files
    audio_files = results["audio_files"]
    if audio_files:
        print("External audio files:")
        for af in audio_files:
            if af.exists:
                duration_str = format_duration(af.duration)
                error_str = f" ({af.error})" if af.error else ""
                print(f"  ✅ {af.path} ({duration_str}){error_str}")
            else:
                print(f"  ❌ {af.path} (missing)")
        print()

    # Voice recordings
    voice_recordings = results["voice_recordings"]
    if voice_recordings:
        print("Voice recordings:")
        for vr in voice_recordings:
            section = vr.segment.section or "intro"
            preview = vr.segment.content[:40].replace('\n', ' ')
            if len(vr.segment.content) > 40:
                preview += "..."

            if vr.recorded:
                duration_str = format_duration(vr.duration)
                print(f"  ✅ [{vr.segment.id}] {section}: \"{preview}\" ({duration_str})")
                if vr.filename:
                    print(f"       → {vr.filename}")
            else:
                print(f"  ⏳ [{vr.segment.id}] {section}: \"{preview}\" (not recorded)")
        print()

    # Summary
    print("Summary:")
    if audio_files:
        print(f"  Audio files: {results['audio_ok']}/{results['audio_total']} OK")
    if voice_recordings:
        print(f"  Voice segments: {results['voice_ok']}/{results['voice_total']} recorded")
    print()

    # Build readiness
    if results["ready_for_build"]:
        print("✅ Ready for build")
        print(f"   Run: radioscript build")
    else:
        print("❌ Not ready for build")
        if results['audio_ok'] < results['audio_total']:
            print("   Missing audio files")
        if results['voice_ok'] < results['voice_total']:
            missing_count = results['voice_total'] - results['voice_ok']
            print(f"   {missing_count} voice segment(s) to record")
            print(f"   Run: radioscript record")


if __name__ == '__main__':
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python checker.py <script.md>")
        sys.exit(1)

    script_path = Path(sys.argv[1])
    if not script_path.exists():
        print(f"Error: Script not found: {script_path}")
        sys.exit(1)

    # Load state
    state_file = script_path.parent / ".radioscript.json"
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
    else:
        state = {}

    # Check
    checker = Checker(str(script_path))
    results = checker.check(state)

    # Print results
    print_check_results(checker.config, results, str(script_path))
