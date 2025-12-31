#!/usr/bin/env python3
"""
RadioScript CLI
Main entry point for the radio production tool.
"""

import argparse
import json
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from .parser import parse_markdown, Config, Segment, print_segments
from .recorder import Recorder
from .prompter import Prompter
from .builder import Builder, AudioSegment
from .checker import Checker, print_check_results


class RadioScript:
    """Main application class."""

    STATE_FILE = ".radioscript.json"
    DEFAULT_SCRIPT = "script.md"
    
    def __init__(self, script_path: str):
        self.script_path = Path(script_path)
        self.script_dir = self.script_path.parent
        self.recordings_dir = self.script_dir / "recordings"
        self.output_dir = self.script_dir / "output"
        self.state_file = self.script_dir / self.STATE_FILE
        
        # Parse script
        self.config, self.segments = parse_markdown(str(self.script_path))
        
        # Load or initialize state
        self.state = self._load_state()
    
    def _load_state(self) -> dict:
        """Load state from file or create new state."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        
        return {
            "source": str(self.script_path),
            "created": datetime.now().isoformat(),
            "segments": {},
        }
    
    def _save_state(self):
        """Save state to file."""
        self.state["updated"] = datetime.now().isoformat()
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def _get_segment_state(self, segment_id: int) -> dict:
        """Get state for a specific segment."""
        key = str(segment_id)
        if key not in self.state["segments"]:
            self.state["segments"][key] = {
                "recorded": False,
                "filename": None,
            }
        return self.state["segments"][key]
    
    def _update_segment_state(self, segment_id: int, filename: str):
        """Update state after recording a segment."""
        key = str(segment_id)
        self.state["segments"][key] = {
            "recorded": True,
            "filename": filename,
            "recorded_at": datetime.now().isoformat(),
        }
        self._save_state()
    
    def cmd_parse(self):
        """Parse and display script structure."""
        print_segments(self.config, self.segments)
    
    def cmd_record(self, segment_id: Optional[int] = None):
        """Interactive recording session."""
        # Setup
        recorder = Recorder(
            output_dir=str(self.recordings_dir),
            trim_silence=self.config.trim_silence,
            trim_threshold=self.config.trim_threshold,
        )
        prompter = Prompter()
        
        # Get text segments to record
        text_segments = [s for s in self.segments if s.type == 'text']
        
        if not text_segments:
            print("No text segments to record.")
            return
        
        # If specific segment requested
        if segment_id is not None:
            target = next((s for s in text_segments if s.id == segment_id), None)
            if not target:
                print(f"Segment {segment_id} not found or not a text segment.")
                return
            text_segments = [target]
        
        print(f"\n📻 RadioScript Recording Session")
        print(f"   Script: {self.config.title}")
        print(f"   Segments to record: {len(text_segments)}")
        print()
        
        # Recording loop
        for i, segment in enumerate(text_segments):
            seg_state = self._get_segment_state(segment.id)
            
            # Generate filename if not already recorded
            if seg_state.get("filename"):
                filename = seg_state["filename"]
            else:
                filename = segment.filename
            
            # Check if already recorded
            filepath = self.recordings_dir / filename
            already_recorded = filepath.exists()
            
            def do_record():
                return recorder.record(filename)

            def do_start_recording():
                return recorder.start_recording(filename)

            def do_stop_recording():
                return recorder.stop_recording(filename)

            def do_is_recording():
                return recorder.is_recording()

            def do_playback():
                if filepath.exists():
                    print(f"\n▶️  Playing: {filename}")
                    recorder.play(str(filepath))

            # Show prompter
            segment_info = f"Segment {i + 1}/{len(text_segments)} (ID: {segment.id})"
            if already_recorded:
                segment_info += " [✓ recorded]"

            continue_session, recorded_path = prompter.show_prompt(
                text=segment.content,
                segment_info=segment_info,
                on_record=do_record,
                on_playback=do_playback if already_recorded else None,
                on_start_recording=do_start_recording,
                on_stop_recording=do_stop_recording,
                on_is_recording=do_is_recording,
            )
            
            # Update state if recorded
            if recorded_path:
                self._update_segment_state(segment.id, Path(recorded_path).name)
            
            if not continue_session:
                print("\n👋 Session ended by user.")
                break
        
        # Summary
        recorded_count = sum(
            1 for s in text_segments
            if self._get_segment_state(s.id).get("recorded")
        )
        print(f"\n📊 Session summary: {recorded_count}/{len(text_segments)} segments recorded")
    
    def cmd_build(self):
        """Build final audio file."""
        print(f"\n📻 RadioScript Build")
        print(f"   Script: {self.config.title}")
        print(f"   Output: {self.config.output}")
        
        # Collect all audio segments in order
        audio_segments: list[AudioSegment] = []
        missing_recordings = []
        
        for segment in self.segments:
            if segment.type == 'audio':
                # External audio file
                audio_path = self.script_dir / segment.content
                if not audio_path.exists():
                    print(f"⚠️  Missing audio file: {segment.content}")
                    continue
                
                audio_segments.append(AudioSegment(
                    path=str(audio_path),
                    type="music",
                    crossfade=segment.crossfade,
                ))
            
            elif segment.type == 'text':
                # Recorded segment
                seg_state = self._get_segment_state(segment.id)
                
                if not seg_state.get("recorded") or not seg_state.get("filename"):
                    missing_recordings.append(segment.id)
                    continue
                
                recording_path = self.recordings_dir / seg_state["filename"]
                if not recording_path.exists():
                    missing_recordings.append(segment.id)
                    continue
                
                audio_segments.append(AudioSegment(
                    path=str(recording_path),
                    type="voice",
                ))
        
        if missing_recordings:
            print(f"\n⚠️  Missing recordings for segments: {missing_recordings}")
            print("   Run 'radioscript record' to record missing segments.")
            
            proceed = input("\nContinue with available segments? [y/N] ")
            if proceed.lower() != 'y':
                return
        
        if not audio_segments:
            print("❌ No audio segments available to build.")
            return
        
        # Build
        builder = Builder(
            output_dir=str(self.output_dir),
            crossfade_defaults=self.config.crossfade,
            normalization=self.config.normalization,
            gap=self.config.gap,
        )
        
        result = builder.build(
            segments=audio_segments,
            output_filename=self.config.output,
        )

        # Offer to listen to the final result
        if result:
            print()
            listen = input("🎧 Listen to the final audio? [Y/n] ")
            if listen.lower() != 'n':
                import subprocess
                try:
                    print(f"\n▶️  Playing: {result}")
                    subprocess.run(["play", result], check=True, capture_output=True)
                    print("   Playback finished.")
                except subprocess.CalledProcessError:
                    print(f"   ⚠️  Playback failed. You can listen manually: {result}")
                except FileNotFoundError:
                    print(f"   ⚠️  'play' command not found. You can listen manually: {result}")

        return result
    
    def cmd_make(self):
        """Full pipeline: parse, record, build."""
        self.cmd_parse()
        
        print("\n" + "=" * 60)
        proceed = input("Start recording session? [Y/n] ")
        if proceed.lower() == 'n':
            return
        
        self.cmd_record()
        
        print("\n" + "=" * 60)
        proceed = input("Build final audio? [Y/n] ")
        if proceed.lower() == 'n':
            return
        
        self.cmd_build()
    
    def cmd_status(self):
        """Show recording status."""
        print(f"\n📻 RadioScript Status")
        print(f"   Script: {self.config.title}")
        print()

        text_segments = [s for s in self.segments if s.type == 'text']

        for segment in text_segments:
            seg_state = self._get_segment_state(segment.id)
            status = "✅" if seg_state.get("recorded") else "⏳"
            preview = segment.content[:40].replace('\n', ' ')
            if len(segment.content) > 40:
                preview += "..."

            print(f"  {status} [{segment.id}] {segment.section or 'intro'}")
            print(f"         \"{preview}\"")
            if seg_state.get("filename"):
                print(f"         → {seg_state['filename']}")
            print()

    def cmd_check(self):
        """Check audio files and recording status."""
        checker = Checker(str(self.script_path))
        results = checker.check(self.state)
        print_check_results(self.config, results, str(self.script_path))

    @staticmethod
    def cmd_init():
        """Initialize a new RadioScript project in current directory."""
        print("📻 RadioScript Init")

        # Check if already initialized
        if Path(RadioScript.DEFAULT_SCRIPT).exists():
            overwrite = input(f"⚠️  {RadioScript.DEFAULT_SCRIPT} already exists. Overwrite? [y/N] ")
            if overwrite.lower() != 'y':
                print("Cancelled.")
                return

        # Create project structure
        print("   Creating project structure...")

        # Create directories
        Path("assets").mkdir(exist_ok=True)
        Path("recordings").mkdir(exist_ok=True)
        Path("output").mkdir(exist_ok=True)

        # Get templates directory path (relative to this file)
        script_dir = Path(__file__).parent
        template_script = script_dir / "templates" / "script.md"
        template_assets = script_dir / "templates" / "assets"

        # Copy template script
        if template_script.exists():
            shutil.copy(template_script, RadioScript.DEFAULT_SCRIPT)
            print(f"   ✅ Created {RadioScript.DEFAULT_SCRIPT}")
        else:
            print(f"   ⚠️  Template not found: {template_script}")
            return

        # Copy assets
        if template_assets.exists():
            for asset in template_assets.glob("*"):
                if asset.is_file():
                    shutil.copy(asset, Path("assets") / asset.name)
                    print(f"   ✅ Copied {asset.name} to assets/")
        else:
            print(f"   ⚠️  No default assets found")

        print(f"\n✅ Project initialized!")
        print(f"   Edit your script: {RadioScript.DEFAULT_SCRIPT}")
        print(f"   Next steps:")
        print(f"     radioscript check   # Verify setup")
        print(f"     radioscript record  # Start recording")
        print(f"     radioscript build   # Build final audio")


def main():
    parser = argparse.ArgumentParser(
        description="RadioScript - Markdown-driven radio production",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  radioscript init               Initialize new project
  radioscript parse              Parse and show structure
  radioscript check              Check audio files and recordings
  radioscript record             Start recording session
  radioscript record -s 3        Re-record segment 3
  radioscript build              Build final audio
  radioscript make               Full pipeline
  radioscript status             Show recording status
        """,
    )

    parser.add_argument(
        "command",
        choices=["init", "parse", "check", "record", "build", "make", "status"],
        help="Command to run",
    )

    parser.add_argument(
        "-s", "--segment",
        type=int,
        help="Specific segment ID to record",
    )

    args = parser.parse_args()

    # Commands that don't need a script file
    if args.command == "init":
        RadioScript.cmd_init()
        return

    # All other commands use script.md
    script_path = Path(RadioScript.DEFAULT_SCRIPT)
    if not script_path.exists():
        print(f"Error: {RadioScript.DEFAULT_SCRIPT} not found in current directory.")
        print("Run 'radioscript init' to create a new project.")
        sys.exit(1)

    # Run command
    app = RadioScript(str(script_path))

    if args.command == "parse":
        app.cmd_parse()
    elif args.command == "check":
        app.cmd_check()
    elif args.command == "record":
        app.cmd_record(segment_id=args.segment)
    elif args.command == "build":
        app.cmd_build()
    elif args.command == "make":
        app.cmd_make()
    elif args.command == "status":
        app.cmd_status()


if __name__ == '__main__':
    main()
