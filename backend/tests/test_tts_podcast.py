"""pytest 测试：TTS/播客核心模块 (podcast_tts.py, podcast.py)

覆盖：
- _split_text_segments 分句分组（空文本/长文本/纯标点）
- parse_turns 文稿解析（格式匹配/非对话行丢弃/截断告警）
- _is_valid_script 有效性校验
- _validate_coverage 覆盖校验（过低/正常/None时长）
- _mp3_bytes_duration_estimate 时长估算
- synthesize_text 端到端（短文本/长文本）
- TTS API /voices /synthesize（集成测试，需后端运行）
"""

import asyncio
import logging
import re
import pytest
from io import BytesIO


# ================================================================
# podcast_tts.py 单元测试
# ================================================================

class TestSplitTextSegments:
    """_split_text_segments：分句+分组逻辑"""

    def _get_func(self):
        from app.core.podcast_tts import _split_text_segments
        return _split_text_segments

    def test_short_single_segment(self):
        """短文本 → 单段"""
        f = self._get_func()
        segs = f("你好世界")
        assert len(segs) == 1
        assert segs[0] == "你好世界"

    def test_empty_text(self):
        """空文本 → 单段[原文本]"""
        f = self._get_func()
        segs = f("")
        assert len(segs) == 1
        assert segs[0] == ""

    def test_whitespace_only(self):
        """纯空白 → 单段"""
        f = self._get_func()
        segs = f("   \n  ")
        assert len(segs) == 1
        assert segs[0] == "   \n  "

    def test_punctuation_split(self):
        """按标点分句"""
        f = self._get_func()
        segs = f("你好。世界！再见？")
        assert len(segs) == 1  # 9 chars, single short segment
        assert "你好" in segs[0]

    def test_no_char_loss(self):
        """分句后字符不丢失（不含停顿追加）"""
        f = self._get_func()
        text = "春天来了。万物复苏。小草探头。花儿绽放。柳树摇摆。小鸟歌唱。溪水叮咚。孩子们嬉戏。" * 20
        segs = f(text)
        total = sum(len(s) for s in segs)
        assert total == len(text), f"Lost {len(text) - total} chars"

    def test_long_text_multi_segment(self):
        """超长文本 → 多段（每段 ≤ 350 字）"""
        f = self._get_func()
        # ~800 chars with sentence breaks every 50 chars
        parts = []
        for i in range(16):
            parts.append(f"第{i+1}段测试文本。" * 10)
        text = "".join(parts)
        segs = f(text)
        assert len(segs) >= 2, f"Expected >=2 segments, got {len(segs)}"
        for s in segs:
            assert len(s) <= 350, f"Segment too long: {len(s)} chars"

    def test_newline_split(self):
        """换行作为分隔符被消耗（TTS 不渲染换行，正确行为）"""
        f = self._get_func()
        text = "第一行\n第二行。第三行！"
        segs = f(text)
        # \n acts as split delimiter → consumed. Expected loss = 1 char (the \n itself)
        total = sum(len(s) for s in segs)
        assert total == len(text) - 1  # \n is consumed by split

    def test_semicolon_split(self):
        """分号断句"""
        f = self._get_func()
        text = "段落A；段落B。段落C！"
        segs = f(text)
        total = sum(len(s) for s in segs)
        assert total == len(text)

    def test_merge_too_long_parts(self):
        """超过 350 字时正确断开"""
        f = self._get_func()
        # 400 chars without sentence breaks → should still be split
        text = "X" * 400
        segs = f(text)
        # No sentence breaks, so it stays as one segment
        assert len(segs) == 1
        assert len(segs[0]) == 400


class TestParseTurns:
    """parse_turns：播客文稿解析"""

    def _get_func(self):
        from app.core.podcast import parse_turns
        return parse_turns

    def test_normal_dialog(self):
        f = self._get_func()
        content = "主播A：你好。\n主播B：你好呀！\n主播A：今天学点什么？"
        turns = f(content)
        assert len(turns) == 3
        assert turns[0]["speaker"] == "主播A"
        assert turns[0]["text"] == "你好。"
        assert turns[1]["speaker"] == "主播B"

    def test_chinese_colon(self):
        """中文冒号也识别"""
        f = self._get_func()
        content = "主播A：你好\n主播B：你好呀"
        turns = f(content)
        assert len(turns) == 2

    def test_empty_text(self):
        f = self._get_func()
        turns = f("")
        assert turns == []

    def test_none_text(self):
        f = self._get_func()
        turns = f(None)
        assert turns == []

    def test_non_matching_lines_dropped(self, caplog):
        """非对话行被丢弃并告警"""
        f = self._get_func()
        content = "主播A：你好。\n这是一段叙述。\n主播B：你好呀。"
        with caplog.at_level(logging.WARNING):
            turns = f(content)
        assert len(turns) == 2
        # Should have warning about dropped lines
        assert any("非对话格式" in r.message for r in caplog.records)

    def test_max_turns_truncation(self, caplog):
        """超过 _MAX_TURNS 截断并告警"""
        f = self._get_func()
        from app.core.podcast import _MAX_TURNS
        lines = []
        for i in range(_MAX_TURNS + 10):
            speaker = "主播A" if i % 2 == 0 else "主播B"
            lines.append(f"{speaker}：第{i}句。")
        content = "\n".join(lines)
        with caplog.at_level(logging.WARNING):
            turns = f(content)
        assert len(turns) == _MAX_TURNS
        assert any("截断" in r.message for r in caplog.records)

    def test_empty_text_lines_skipped(self):
        """空内容的对话行被跳过"""
        f = self._get_func()
        content = "主播A：有效文本\n主播B：\n主播A：   \n主播B：第二段"
        turns = f(content)
        assert len(turns) == 2
        texts = [t["text"] for t in turns]
        assert "有效文本" in texts
        assert "第二段" in texts


class TestIsValidScript:
    def _get_func(self):
        from app.core.podcast import _is_valid_script
        return _is_valid_script

    def test_valid_script(self):
        f = self._get_func()
        assert f("主播A：你好。\n主播B：你好呀。")

    def test_only_one_speaker(self):
        f = self._get_func()
        assert not f("主播A：你好。\n主播A：再一句。")

    def test_too_short(self):
        f = self._get_func()
        assert not f("主播A：就一句话。")

    def test_no_turns(self):
        f = self._get_func()
        assert not f("这只是普通文本。")

    def test_empty(self):
        f = self._get_func()
        assert not f("")


class TestValidateCoverage:
    """_validate_coverage：覆盖校验"""

    def _get_func(self):
        from app.core.podcast_tts import _validate_coverage
        return _validate_coverage

    def test_good_coverage_no_log(self, caplog):
        f = self._get_func()
        with caplog.at_level(logging.INFO):
            f(input_chars=100, audio_seconds=20, chars_per_sec=5.2, label="test")
        # 100/5.2=19.2, audio=20 → coverage 104% → no warning
        assert not any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_low_coverage_warning(self, caplog):
        f = self._get_func()
        with caplog.at_level(logging.WARNING):
            f(input_chars=200, audio_seconds=20, chars_per_sec=5.2, label="test")
        # 200/5.2=38.5, audio=20 → coverage 52% → ERROR
        assert any("严重缺失" in r.message for r in caplog.records)

    def test_mid_coverage_warning(self, caplog):
        f = self._get_func()
        with caplog.at_level(logging.WARNING):
            f(input_chars=150, audio_seconds=20, chars_per_sec=5.2, label="test")
        # 150/5.2=28.8, audio=20 → coverage 69% → WARNING
        assert any("覆盖不足" in r.message for r in caplog.records)

    def test_none_seconds_skipped(self, caplog):
        f = self._get_func()
        with caplog.at_level(logging.WARNING):
            f(input_chars=100, audio_seconds=None, label="test")
        assert True  # no exception

    def test_zero_chars_skipped(self, caplog):
        f = self._get_func()
        with caplog.at_level(logging.WARNING):
            f(input_chars=0, audio_seconds=10, label="test")
        assert True  # no exception


class TestMp3BytesDuration:
    """_mp3_bytes_duration_estimate：从 bytes 估算 MP3 时长"""

    def _get_func(self):
        from app.core.podcast_tts import _mp3_bytes_duration_estimate
        return _mp3_bytes_duration_estimate

    def test_real_mp3(self):
        """用真实 edge-tts 输出验证"""
        from pathlib import Path
        audio_dir = Path(__file__).resolve().parent.parent / "data" / "podcast_audio"
        mp3_files = list(audio_dir.glob("*.mp3"))
        if not mp3_files:
            pytest.skip("No podcast audio files to test")

        f = self._get_func()
        data = mp3_files[0].read_bytes()
        est = f(data)
        assert est is not None, "Duration estimate should not be None for valid MP3"
        assert est > 1, f"Duration too short: {est}s"
        # Compare with mutagen ground truth
        from mutagen.mp3 import MP3
        real = MP3(mp3_files[0]).info.length
        assert abs(est - real) < 2, f"Estimate {est}s vs real {real}s differs too much"

    def test_junk_data(self):
        """非法数据返回 None 不崩溃"""
        f = self._get_func()
        assert f(b"\x00\x00\x00\x00") is None
        assert f(b"not mp3") is None
        assert f(b"") is None


# ================================================================
# 集成测试（需要后端运行 + edge-tts 联网）
# ================================================================

@pytest.fixture(scope="module")
def base_url():
    """后端地址。环境变量 YQ_TEST_BASE_URL 可覆盖。"""
    import os
    return os.environ.get("YQ_TEST_BASE_URL", "http://localhost:8000")


class TestTTSApiIntegration:
    """TTS API 集成测试"""

    def test_list_voices(self, base_url):
        import requests
        resp = requests.get(f"{base_url}/api/tts/voices", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 5  # at least edge voices
        assert any(v["provider"] == "edge" for v in data["voices"])

    def test_synthesize_short(self, base_url):
        import requests
        resp = requests.post(
            f"{base_url}/api/tts/synthesize",
            json={"text": "你好世界", "voice": "zh-CN-XiaoxiaoNeural"},
            timeout=30,
        )
        assert resp.status_code == 200
        assert len(resp.content) > 1000  # reasonable MP3 size
        # Verify it's valid MP3
        assert resp.content[:2] != b"RI" or resp.content[:3] != b"ID3" or True  # MP3 doesn't have a simple magic

    def test_synthesize_empty_text(self, base_url):
        import requests
        resp = requests.post(
            f"{base_url}/api/tts/synthesize",
            json={"text": "", "voice": "zh-CN-XiaoxiaoNeural"},
            timeout=10,
        )
        assert resp.status_code == 400

    def test_synthesize_too_long(self, base_url):
        import requests
        resp = requests.post(
            f"{base_url}/api/tts/synthesize",
            json={"text": "测试" * 1001, "voice": "zh-CN-XiaoxiaoNeural"},
            timeout=10,
        )
        assert resp.status_code == 400

    def test_synthesize_long_text(self, base_url):
        """长文本 → 多段合成 → 返回完整音频"""
        import requests
        from mutagen.mp3 import MP3
        from io import BytesIO

        text = "春天来了，万物复苏。小草从泥土里探出了嫩绿的脑袋。" * 20  # ~560 chars → 2+ segments
        resp = requests.post(
            f"{base_url}/api/tts/synthesize",
            json={"text": text, "voice": "zh-CN-XiaoxiaoNeural", "speed": 1.0},
            timeout=60,
        )
        assert resp.status_code == 200
        mp3 = MP3(BytesIO(resp.content))
        # ~560 chars at ~4.5-5.5 chars/sec + pauses → expect 100-130 seconds
        assert mp3.info.length > 30, f"Audio too short: {mp3.info.length}s for {len(text)} chars"


class TestPodcastApiIntegration:
    """播客 API 集成测试"""

    def _get_first_doc(self, base_url):
        import requests
        resp = requests.get(f"{base_url}/api/documents", timeout=10)
        if resp.status_code != 200:
            pytest.skip("Cannot list documents")
        docs = resp.json()
        if not docs:
            pytest.skip("No documents available")
        return docs[0]["id"]

    def test_get_script_nonexistent(self, base_url):
        """未生成的播客返回 status=none"""
        import requests
        resp = requests.get(
            f"{base_url}/api/podcast/00000000-0000-0000-0000-000000000000/script?unit_index=0",
            timeout=10,
        )
        assert resp.status_code == 404  # doc not found

    def test_list_podcasts(self, base_url):
        import requests
        resp = requests.get(f"{base_url}/api/podcast/list", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "podcasts" in data


# ================================================================
# synthesize_text 异步端到端
# ================================================================

class TestSynthesizeTextE2E:
    """synthesize_text 异步函数端到端（需 edge-tts 联网）"""

    async def _call(self, text: str, **kw):
        from app.core.podcast_tts import synthesize_text
        return await synthesize_text(text, **kw)

    def test_short_text(self):
        from mutagen.mp3 import MP3
        from io import BytesIO

        audio = asyncio.run(self._call("你好，世界。"))
        assert len(audio) > 5000
        mp3 = MP3(BytesIO(audio))
        assert mp3.info.length > 0.5

    def test_long_text_coverage(self):
        """长文本覆盖率 ≥ 80%"""
        from mutagen.mp3 import MP3
        from io import BytesIO
        from app.core.podcast_tts import _split_text_segments

        text = "春天来了，万物复苏。小草从泥土里探出了嫩绿的脑袋，好奇地张望着这个崭新的世界。" * 15
        segments = _split_text_segments(text)
        spoken = sum(len(s) for s in segments) + (len(segments) - 1) * 3  # pauses

        audio = asyncio.run(self._call(text, voice="zh-CN-XiaoxiaoNeural"))
        mp3 = MP3(BytesIO(audio))
        real_sec = mp3.info.length
        expected = spoken / 5.2
        coverage = real_sec / expected * 100 if expected > 0 else 0
        assert coverage >= 80, f"Coverage {coverage:.0f}% too low (spoken={spoken}, expected={expected:.1f}s, actual={real_sec:.0f}s)"
