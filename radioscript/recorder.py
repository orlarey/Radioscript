"""
RadioScript Recorder
Handles audio recording with sox and silence trimming.
"""

import subprocess
import os
import time
from pathlib import Path
from typing import Optional


class Recorder:
    """Audio recorder using sox."""

    def __init__(
        self,
        output_dir: str = "./recordings",
        sample_rate: int = 48000,
        channels: int = 1,
        bits: int = 16,
        trim_silence: bool = True,
        trim_threshold: str = "1%",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.sample_rate = sample_rate
        self.channels = channels
        self.bits = bits
        self.trim_silence = trim_silence
        self.trim_threshold = trim_threshold

        # For background recording
        self.recording_process = None
        self.recording_temp_path = None
    
    def record(self, filename: str) -> Optional[str]:
        """
        Record audio to a file.
        Returns the path to the recorded file, or None if cancelled.
        
        The recording runs until the user presses Ctrl+C.
        """
        output_path = self.output_dir / filename
        temp_path = self.output_dir / f"_temp_{filename}"
        
        # Build sox rec command
        cmd = [
            "rec",
            "-r", str(self.sample_rate),
            "-c", str(self.channels),
            "-b", str(self.bits),
            str(temp_path),
        ]
        
        print(f"\n🎙️  Recording to: {filename}")
        print("   Press Ctrl+C to stop recording...\n")
        
        try:
            # Run recording
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            process.wait()
        except KeyboardInterrupt:
            # User stopped recording
            process.terminate()
            process.wait()
            print("\n   Recording stopped.")
        
        if not temp_path.exists():
            print("   ⚠️  No audio recorded.")
            return None
        
        # Check if file has content
        if temp_path.stat().st_size < 1000:
            print("   ⚠️  Recording too short, discarding.")
            temp_path.unlink()
            return None
        
        # Apply silence trimming if enabled
        if self.trim_silence:
            print("   Trimming silence...")
            self._trim_silence(temp_path, output_path)
            temp_path.unlink()
        else:
            temp_path.rename(output_path)
        
        print(f"   ✅ Saved: {output_path}")
        return str(output_path)

    def start_recording(self, filename: str) -> bool:
        """
        Start recording in background.
        Returns True if recording started successfully.
        """
        if self.recording_process is not None:
            return False  # Already recording

        self.recording_temp_path = self.output_dir / f"_temp_{filename}"

        # Build sox rec command
        cmd = [
            "rec",
            "-r", str(self.sample_rate),
            "-c", str(self.channels),
            "-b", str(self.bits),
            str(self.recording_temp_path),
        ]

        try:
            self.recording_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Give it a moment to start
            time.sleep(0.1)
            # Check if it's still running
            if self.recording_process.poll() is not None:
                self.recording_process = None
                return False
            return True
        except Exception:
            self.recording_process = None
            return False

    def stop_recording(self, filename: str) -> Optional[str]:
        """
        Stop background recording and process the file.
        Returns the path to the final recording, or None if failed.
        """
        if self.recording_process is None:
            return None

        output_path = self.output_dir / filename

        # Stop the recording process
        self.recording_process.terminate()
        self.recording_process.wait()
        self.recording_process = None

        if not self.recording_temp_path.exists():
            return None

        # Check if file has content
        if self.recording_temp_path.stat().st_size < 1000:
            self.recording_temp_path.unlink()
            return None

        # Apply silence trimming if enabled
        if self.trim_silence:
            self._trim_silence(self.recording_temp_path, output_path)
            self.recording_temp_path.unlink()
        else:
            self.recording_temp_path.rename(output_path)

        return str(output_path)

    def is_recording(self) -> bool:
        """Check if currently recording."""
        if self.recording_process is None:
            return False
        # Check if process is still alive
        if self.recording_process.poll() is not None:
            # Process has ended
            self.recording_process = None
            return False
        return True
    
    def _trim_silence(self, input_path: Path, output_path: Path):
        """
        Trim silence from beginning of audio file only.
        The end is left untouched to preserve natural decay and avoid cutting off speech.
        """
        threshold = self.trim_threshold

        # sox input output silence 1 0.1 threshold
        # - silence 1 0.1 threshold: trim start only (requires 0.1s of silence minimum)
        # - No reverse/trim at end to avoid cutting off natural speech decay
        cmd = [
            "sox",
            str(input_path),
            str(output_path),
            "silence", "1", "0.1", threshold,  # trim start only
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"   ⚠️  Trim failed: {e.stderr.decode()}")
            # Fall back to just copying
            import shutil
            shutil.copy(input_path, output_path)
    
    def get_duration(self, filepath: str) -> float:
        """Get duration of an audio file in seconds."""
        cmd = ["soxi", "-D", filepath]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError):
            return 0.0
    
    def play(self, filepath: str):
        """Play an audio file."""
        cmd = ["play", filepath]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"Playback error: {e.stderr.decode()}")


def test_recording():
    """Test the recorder."""
    recorder = Recorder(output_dir="./test_recordings")
    
    print("Testing recorder...")
    print("Speak something and press Ctrl+C to stop.\n")
    
    result = recorder.record("test_recording.wav")
    
    if result:
        duration = recorder.get_duration(result)
        print(f"\nRecorded {duration:.2f} seconds")
        print("Playing back...")
        recorder.play(result)


if __name__ == '__main__':
    test_recording()
