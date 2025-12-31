"""
RadioScript Builder
Assembles audio segments with crossfades and exports the final file.
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class AudioSegment:
    """Represents an audio segment for building."""
    path: str
    type: str  # "voice" or "music"
    crossfade: Optional[float] = None


class Builder:
    """
    Builds the final audio file from segments.
    Handles crossfades, concatenation, and normalization.
    """
    
    def __init__(
        self,
        output_dir: str = "./output",
        crossfade_defaults: Optional[dict] = None,
        normalization: str = "-16 LUFS",
        gap: Optional[float] = None,
        bitrate: str = "192k",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.gap = gap  # if set, use silence gaps instead of crossfades
        self.bitrate = bitrate
        self.crossfade_defaults = crossfade_defaults or {
            "voice_to_music": 0.1,
            "music_to_voice": 0.1,
            "voice_to_voice": 0.1,
            "music_to_music": 0.1,
        }

        # Parse normalization target
        self.normalization_lufs = self._parse_lufs(normalization)
    
    def _parse_lufs(self, value: str) -> float:
        """Parse LUFS value from string like '-16 LUFS'."""
        import re
        match = re.search(r'(-?\d+(?:\.\d+)?)', value)
        if match:
            return float(match.group(1))
        return -16.0
    
    def get_duration(self, filepath: str) -> float:
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
        except (subprocess.CalledProcessError, ValueError):
            return 0.0
    
    def _get_crossfade_duration(
        self,
        prev_type: str,
        next_type: str,
        override: Optional[float] = None,
    ) -> float:
        """Get crossfade duration based on segment types."""
        if override is not None:
            return override
        
        key = f"{prev_type}_to_{next_type}"
        return self.crossfade_defaults.get(key, 0.3)
    
    def _crossfade_two(
        self,
        file1: str,
        file2: str,
        duration: float,
        output: str,
    ) -> bool:
        """Apply crossfade between two audio files."""
        cmd = [
            "ffmpeg", "-y",
            "-i", file1,
            "-i", file2,
            "-filter_complex",
            f"acrossfade=d={duration}:c1=tri:c2=tri",
            output,
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Crossfade error: {e.stderr.decode()}")
            return False
    
    def _concat_simple(self, files: list[str], output: str) -> bool:
        """Simple concatenation without crossfade (for fallback)."""
        # Create file list
        list_file = self.output_dir / "_concat_list.txt"
        with open(list_file, 'w') as f:
            for filepath in files:
                f.write(f"file '{os.path.abspath(filepath)}'\n")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            output,
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Concat error: {e.stderr.decode()}")
            return False
        finally:
            if list_file.exists():
                list_file.unlink()
    
    def _normalize(self, input_file: str, output_file: str) -> bool:
        """Apply loudness normalization using ffmpeg loudnorm (two-pass)."""
        target_lufs = self.normalization_lufs
        
        # First pass: analyze
        print("   Analyzing loudness...")
        analyze_cmd = [
            "ffmpeg", "-y",
            "-i", input_file,
            "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json",
            "-f", "null", "-",
        ]
        
        try:
            result = subprocess.run(
                analyze_cmd,
                capture_output=True,
                text=True,
            )
            
            # Parse loudnorm output from stderr
            stderr = result.stderr
            # Find JSON in output
            json_start = stderr.rfind('{')
            json_end = stderr.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                loudnorm_data = json.loads(stderr[json_start:json_end])
            else:
                print("   ⚠️  Could not parse loudnorm analysis, using single-pass")
                return self._normalize_single_pass(input_file, output_file)
            
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f"   ⚠️  Analysis failed: {e}")
            return self._normalize_single_pass(input_file, output_file)
        
        # Second pass: normalize
        print("   Applying normalization...")
        measured_i = loudnorm_data.get('input_i', '-24')
        measured_tp = loudnorm_data.get('input_tp', '-2')
        measured_lra = loudnorm_data.get('input_lra', '7')
        measured_thresh = loudnorm_data.get('input_thresh', '-34')
        offset = loudnorm_data.get('target_offset', '0')
        
        normalize_cmd = [
            "ffmpeg", "-y",
            "-i", input_file,
            "-af",
            f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:"
            f"measured_I={measured_i}:measured_TP={measured_tp}:"
            f"measured_LRA={measured_lra}:measured_thresh={measured_thresh}:"
            f"offset={offset}:linear=true",
            "-ar", "48000",
            output_file,
        ]
        
        try:
            subprocess.run(normalize_cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"   ⚠️  Normalization failed: {e.stderr.decode()}")
            return False
    
    def _normalize_single_pass(self, input_file: str, output_file: str) -> bool:
        """Single-pass normalization (less accurate but simpler)."""
        cmd = [
            "ffmpeg", "-y",
            "-i", input_file,
            "-af", f"loudnorm=I={self.normalization_lufs}:TP=-1.5:LRA=11",
            "-ar", "48000",
            output_file,
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Normalization error: {e.stderr.decode()}")
            return False
    
    def _export_mp3(self, input_file: str, output_file: str, bitrate: str = "192k") -> bool:
        """Export to MP3 format."""
        cmd = [
            "ffmpeg", "-y",
            "-i", input_file,
            "-codec:a", "libmp3lame",
            "-b:a", bitrate,
            output_file,
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Export error: {e.stderr.decode()}")
            return False
    
    def build(
        self,
        segments: list[AudioSegment],
        output_filename: str,
        normalize: bool = True,
    ) -> Optional[str]:
        """
        Build final audio from segments.
        
        Args:
            segments: List of AudioSegment objects
            output_filename: Name of output file
            normalize: Whether to apply loudness normalization
        
        Returns:
            Path to output file, or None if failed
        """
        if not segments:
            print("No segments to build.")
            return None
        
        # Verify all files exist
        for seg in segments:
            if not Path(seg.path).exists():
                print(f"Error: File not found: {seg.path}")
                return None
        
        print(f"\n🔧 Building {len(segments)} segments...")
        
        # If only one segment, just copy/normalize it
        if len(segments) == 1:
            temp_file = str(self.output_dir / "_temp_single.wav")
            # Convert to wav for processing
            subprocess.run([
                "ffmpeg", "-y", "-i", segments[0].path, temp_file
            ], capture_output=True)
            merged_file = temp_file
        else:
            # Build with crossfades or gaps iteratively
            if self.gap is not None:
                print(f"   Using {self.gap}s silence gaps...")
            else:
                print("   Applying crossfades...")

            current_file = segments[0].path
            temp_counter = 0

            for i in range(1, len(segments)):
                prev_seg = segments[i - 1] if i > 0 else None
                curr_seg = segments[i]

                temp_output = str(self.output_dir / f"_temp_{temp_counter}.wav")
                temp_counter += 1

                if self.gap is not None:
                    # Use silence gap instead of crossfade
                    # Create a temporary silence file
                    silence_file = str(self.output_dir / f"_silence_{temp_counter}.wav")
                    silence_cmd = [
                        "sox", "-n", "-r", "48000", "-c", "2",
                        silence_file,
                        "trim", "0.0", str(self.gap)
                    ]
                    subprocess.run(silence_cmd, capture_output=True)

                    # Concatenate: current + silence + next
                    success = self._concat_simple(
                        [current_file, silence_file, curr_seg.path],
                        temp_output,
                    )

                    # Clean up silence file
                    Path(silence_file).unlink(missing_ok=True)
                else:
                    # Use crossfade
                    prev_type = segments[i - 1].type if i > 0 else "voice"
                    curr_type = curr_seg.type
                    xfade_duration = self._get_crossfade_duration(
                        prev_type, curr_type, curr_seg.crossfade
                    )

                    # Clamp crossfade to not exceed file durations
                    prev_duration = self.get_duration(current_file)
                    curr_duration = self.get_duration(curr_seg.path)
                    max_xfade = min(prev_duration, curr_duration) * 0.5
                    xfade_duration = min(xfade_duration, max_xfade)

                    if xfade_duration < 0.05:
                        xfade_duration = 0  # Too short, skip crossfade

                    if xfade_duration > 0:
                        success = self._crossfade_two(
                            current_file,
                            curr_seg.path,
                            xfade_duration,
                            temp_output,
                        )
                    else:
                        # No crossfade, simple concat
                        success = self._concat_simple(
                            [current_file, curr_seg.path],
                            temp_output,
                        )

                if not success:
                    print(f"   ⚠️  Failed at segment {i}")
                    return None

                # Clean up previous temp file
                if current_file.startswith(str(self.output_dir / "_temp")):
                    Path(current_file).unlink(missing_ok=True)

                current_file = temp_output
                print(f"   ✓ Merged segment {i + 1}/{len(segments)}")

            merged_file = current_file
        
        # Normalize
        if normalize:
            print("   Normalizing loudness...")
            normalized_file = str(self.output_dir / "_temp_normalized.wav")
            if not self._normalize(merged_file, normalized_file):
                normalized_file = merged_file
            else:
                if merged_file != normalized_file:
                    Path(merged_file).unlink(missing_ok=True)
                merged_file = normalized_file
        
        # Export to final format
        output_path = self.output_dir / output_filename
        print(f"   Exporting to {output_filename}...")

        if output_filename.endswith('.mp3'):
            success = self._export_mp3(merged_file, str(output_path), bitrate=self.bitrate)
        else:
            # Just copy/convert to output format
            subprocess.run([
                "ffmpeg", "-y", "-i", merged_file, str(output_path)
            ], capture_output=True)
            success = output_path.exists()
        
        # Cleanup temp files
        Path(merged_file).unlink(missing_ok=True)
        for f in self.output_dir.glob("_temp_*.wav"):
            f.unlink(missing_ok=True)
        
        if success:
            duration = self.get_duration(str(output_path))
            print(f"\n✅ Built: {output_path}")
            print(f"   Duration: {duration:.1f}s ({duration/60:.1f} min)")
            return str(output_path)
        else:
            print("❌ Build failed")
            return None


def test_builder():
    """Test the builder with sample files."""
    # Create some test audio files
    print("Creating test audio files...")
    
    # Generate test tones
    subprocess.run([
        "sox", "-n", "test1.wav",
        "synth", "3", "sine", "440",
        "fade", "t", "0.1", "0", "0.1",
    ], capture_output=True)
    
    subprocess.run([
        "sox", "-n", "test2.wav",
        "synth", "2", "sine", "880",
        "fade", "t", "0.1", "0", "0.1",
    ], capture_output=True)
    
    subprocess.run([
        "sox", "-n", "test3.wav",
        "synth", "3", "sine", "660",
        "fade", "t", "0.1", "0", "0.1",
    ], capture_output=True)
    
    # Build
    builder = Builder()
    segments = [
        AudioSegment(path="test1.wav", type="voice"),
        AudioSegment(path="test2.wav", type="music"),
        AudioSegment(path="test3.wav", type="voice", crossfade=1.0),
    ]
    
    result = builder.build(segments, "test_output.mp3")
    
    # Cleanup
    for f in ["test1.wav", "test2.wav", "test3.wav"]:
        Path(f).unlink(missing_ok=True)
    
    return result


if __name__ == '__main__':
    result = test_builder()
    if result:
        print(f"\nTest successful: {result}")
