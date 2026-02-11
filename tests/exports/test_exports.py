import re
import xml.etree.ElementTree as ET

import pytest
from pydantic import ValidationError

from heimdex_media_contracts.exports.schemas import ExportClip, ExportMarker
from heimdex_media_contracts.exports.fcpxml import generate_fcpxml
from heimdex_media_contracts.exports.edl import generate_edl


class TestExportClip:
    def test_valid_construction(self):
        clip = ExportClip(
            clip_name='clip1',
            video_id='vid001',
            media_path='/tmp/clip1.mp4',
            start_ms=0,
            end_ms=10000,
        )
        assert clip.clip_name == 'clip1'
        assert clip.video_id == 'vid001'
        assert clip.media_path == '/tmp/clip1.mp4'
        assert clip.start_ms == 0
        assert clip.end_ms == 10000

    def test_end_ms_must_be_gte_start_ms(self):
        with pytest.raises(ValidationError):
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=10000,
                end_ms=5000,
            )

    def test_duration_ms_property(self):
        clip = ExportClip(
            clip_name='clip1',
            video_id='vid001',
            media_path='/tmp/clip1.mp4',
            start_ms=1000,
            end_ms=6000,
        )
        assert clip.duration_ms == 5000

    def test_markers_default_to_empty_list(self):
        clip = ExportClip(
            clip_name='clip1',
            video_id='vid001',
            media_path='/tmp/clip1.mp4',
            start_ms=0,
            end_ms=10000,
        )
        assert clip.markers == []

    def test_roundtrip_via_model_dump(self):
        clip = ExportClip(
            clip_name='clip1',
            video_id='vid001',
            media_path='/tmp/clip1.mp4',
            media_url='https://example.com/clip1.mp4',
            start_ms=0,
            end_ms=10000,
            scene_id='scene_001',
            markers=[
                ExportMarker(name='marker1', time_ms=5000, note='test note'),
            ],
        )
        data = clip.model_dump()
        restored = ExportClip(**data)
        assert restored == clip


class TestExportMarker:
    def test_valid_construction(self):
        marker = ExportMarker(
            name='marker1',
            time_ms=5000,
        )
        assert marker.name == 'marker1'
        assert marker.time_ms == 5000

    def test_note_defaults_to_empty_string(self):
        marker = ExportMarker(
            name='marker1',
            time_ms=5000,
        )
        assert marker.note == ''


class TestGenerateFcpxml:
    def test_output_contains_xml_declaration(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
        ]
        output = generate_fcpxml(clips, 'Test Project')
        assert '<?xml' in output
        assert '<fcpxml version="1.9">' in output

    def test_contains_asset_refs_for_each_clip(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
            ExportClip(
                clip_name='clip2',
                video_id='vid002',
                media_path='/tmp/clip2.mp4',
                start_ms=0,
                end_ms=5000,
            ),
        ]
        output = generate_fcpxml(clips, 'Test Project')
        root = ET.fromstring(output)
        assets = root.findall('.//asset')
        assert len(assets) >= 2

    def test_contains_asset_clip_refs_in_spine(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
        ]
        output = generate_fcpxml(clips, 'Test Project')
        root = ET.fromstring(output)
        spine = root.find('.//spine')
        assert spine is not None
        asset_clips = spine.findall('asset-clip')
        assert len(asset_clips) >= 1

    def test_raises_value_error_on_empty_clips(self):
        with pytest.raises(ValueError):
            generate_fcpxml([], 'Test Project')

    def test_30fps_uses_ndf_tc_format(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
        ]
        output = generate_fcpxml(clips, 'Test Project', frame_rate=30.0)
        assert '30/30s' in output or '300/30s' in output

    def test_29_97fps_uses_df_tc_format(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
        ]
        output = generate_fcpxml(clips, 'Test Project', frame_rate=29.97)
        assert '1001/30000s' in output
        assert 'tcFormat="DF"' in output

    def test_project_name_is_xml_escaped(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
        ]
        output = generate_fcpxml(clips, 'Test & Project <Name>')
        assert '&amp;' in output or 'Test &amp; Project &lt;Name&gt;' in output


class TestGenerateEdl:
    def test_output_starts_with_title(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
        ]
        output = generate_edl(clips, 'Test Project')
        assert output.startswith('TITLE:')

    def test_contains_fcm_non_drop_frame_for_30fps(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
        ]
        output = generate_edl(clips, 'Test Project', frame_rate=30.0)
        assert 'FCM: NON-DROP FRAME' in output

    def test_contains_fcm_drop_frame_for_29_97fps(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
        ]
        output = generate_edl(clips, 'Test Project', frame_rate=29.97)
        assert 'FCM: DROP FRAME' in output

    def test_edit_lines_have_3_digit_event_numbers(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
            ExportClip(
                clip_name='clip2',
                video_id='vid002',
                media_path='/tmp/clip2.mp4',
                start_ms=0,
                end_ms=5000,
            ),
        ]
        output = generate_edl(clips, 'Test Project')
        assert re.search(r'^\s*001\s+', output, re.MULTILINE)
        assert re.search(r'^\s*002\s+', output, re.MULTILINE)

    def test_timecodes_are_hhmmssff_format(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
        ]
        output = generate_edl(clips, 'Test Project')
        assert re.search(r'\d{2}:\d{2}:\d{2}:\d{2}', output)

    def test_clip_names_appear_after_from_clip_name(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
        ]
        output = generate_edl(clips, 'Test Project')
        assert '* FROM CLIP NAME:' in output
        assert 'clip1' in output

    def test_raises_value_error_on_empty_clips(self):
        with pytest.raises(ValueError):
            generate_edl([], 'Test Project')

    def test_record_timecodes_advance_correctly(self):
        clips = [
            ExportClip(
                clip_name='clip1',
                video_id='vid001',
                media_path='/tmp/clip1.mp4',
                start_ms=0,
                end_ms=10000,
            ),
            ExportClip(
                clip_name='clip2',
                video_id='vid002',
                media_path='/tmp/clip2.mp4',
                start_ms=0,
                end_ms=5000,
            ),
        ]
        output = generate_edl(clips, 'Test Project')
        lines = output.split('\n')
        rec_out_clip1 = None
        rec_in_clip2 = None
        for line in lines:
            parts = line.split()
            if parts and parts[0] == '001' and len(parts) >= 8:
                rec_out_clip1 = parts[7]
            if parts and parts[0] == '002' and len(parts) >= 8:
                rec_in_clip2 = parts[6]
        assert rec_out_clip1 is not None
        assert rec_in_clip2 is not None
        assert rec_out_clip1 == rec_in_clip2
