from dataclasses import dataclass

import pytest

from heimdex_media_contracts.scenes.merge import (
    aggregate_speaker_transcript,
    count_distinct_speakers,
)


@dataclass
class FakeSpeechSegment:
    start: float
    end: float
    text: str
    speaker_id: str | None = None


class TestAggregateSpeakerTranscript:
    def test_empty_segments_returns_empty_string(self):
        result = aggregate_speaker_transcript([])
        assert result == ""

    def test_segments_with_no_speaker_id_returns_empty_string(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id=None),
            FakeSpeechSegment(1.0, 2.0, "world", speaker_id=None),
        ]
        result = aggregate_speaker_transcript(segments)
        assert result == ""

    def test_single_speaker_single_segment(self):
        segments = [FakeSpeechSegment(0.0, 1.0, "hello", speaker_id="SPEAKER_00")]
        result = aggregate_speaker_transcript(segments)
        assert result == "SPEAKER_00: hello"

    def test_single_speaker_multiple_segments_merged(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(1.0, 2.0, "world", speaker_id="SPEAKER_00"),
        ]
        result = aggregate_speaker_transcript(segments)
        assert result == "SPEAKER_00: hello world"

    def test_two_speakers_alternating(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(1.0, 2.0, "hi", speaker_id="SPEAKER_01"),
            FakeSpeechSegment(2.0, 3.0, "world", speaker_id="SPEAKER_00"),
        ]
        result = aggregate_speaker_transcript(segments)
        lines = result.split("\n")
        assert len(lines) == 3
        assert lines[0] == "SPEAKER_00: hello"
        assert lines[1] == "SPEAKER_01: hi"
        assert lines[2] == "SPEAKER_00: world"

    def test_consecutive_same_speaker_merged_into_one_line(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(1.0, 2.0, "my", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(2.0, 3.0, "friend", speaker_id="SPEAKER_00"),
        ]
        result = aggregate_speaker_transcript(segments)
        assert result == "SPEAKER_00: hello my friend"

    def test_unknown_fallback_when_speaker_id_none_but_others_have_speaker_id(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(1.0, 2.0, "unknown", speaker_id=None),
            FakeSpeechSegment(2.0, 3.0, "world", speaker_id="SPEAKER_00"),
        ]
        result = aggregate_speaker_transcript(segments)
        lines = result.split("\n")
        assert len(lines) == 3
        assert lines[0] == "SPEAKER_00: hello"
        assert lines[1] == "UNKNOWN: unknown"
        assert lines[2] == "SPEAKER_00: world"

    def test_empty_text_segments_skipped(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(1.0, 2.0, "", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(2.0, 3.0, "world", speaker_id="SPEAKER_00"),
        ]
        result = aggregate_speaker_transcript(segments)
        assert result == "SPEAKER_00: hello world"

    def test_whitespace_only_text_skipped(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(1.0, 2.0, "   ", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(2.0, 3.0, "world", speaker_id="SPEAKER_00"),
        ]
        result = aggregate_speaker_transcript(segments)
        assert result == "SPEAKER_00: hello world"

    def test_multiple_speakers_with_korean_text(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "안녕하세요", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(1.0, 2.0, "네 감사합니다", speaker_id="SPEAKER_01"),
        ]
        result = aggregate_speaker_transcript(segments)
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "SPEAKER_00: 안녕하세요"
        assert lines[1] == "SPEAKER_01: 네 감사합니다"


class TestCountDistinctSpeakers:
    def test_empty_list_returns_zero(self):
        result = count_distinct_speakers([])
        assert result == 0

    def test_all_none_speaker_ids_returns_zero(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id=None),
            FakeSpeechSegment(1.0, 2.0, "world", speaker_id=None),
        ]
        result = count_distinct_speakers(segments)
        assert result == 0

    def test_single_speaker_returns_one(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(1.0, 2.0, "world", speaker_id="SPEAKER_00"),
        ]
        result = count_distinct_speakers(segments)
        assert result == 1

    def test_two_distinct_speakers_returns_two(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(1.0, 2.0, "hi", speaker_id="SPEAKER_01"),
        ]
        result = count_distinct_speakers(segments)
        assert result == 2

    def test_three_distinct_speakers_returns_three(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(1.0, 2.0, "hi", speaker_id="SPEAKER_01"),
            FakeSpeechSegment(2.0, 3.0, "hey", speaker_id="SPEAKER_02"),
        ]
        result = count_distinct_speakers(segments)
        assert result == 3

    def test_duplicate_speaker_ids_counted_once(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(1.0, 2.0, "world", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(2.0, 3.0, "hi", speaker_id="SPEAKER_01"),
            FakeSpeechSegment(3.0, 4.0, "there", speaker_id="SPEAKER_01"),
        ]
        result = count_distinct_speakers(segments)
        assert result == 2

    def test_mixed_none_and_speaker_ids(self):
        segments = [
            FakeSpeechSegment(0.0, 1.0, "hello", speaker_id="SPEAKER_00"),
            FakeSpeechSegment(1.0, 2.0, "unknown", speaker_id=None),
            FakeSpeechSegment(2.0, 3.0, "hi", speaker_id="SPEAKER_01"),
            FakeSpeechSegment(3.0, 4.0, "also unknown", speaker_id=None),
        ]
        result = count_distinct_speakers(segments)
        assert result == 2
