"""
skills/xfyun_tts.py — 讯飞语音合成（TTS）模块

规范来源：
- project_start.md 第六节第7款（语音管家）
- project_start.md 第七条（异常处理：SDK 初始化失败降级纯文字）
- project_start.md 第十四条（讯飞 SDK 合规责任）
- 讯飞在线语音合成 API 文档 v2

核心行为：
- 唱诺文案 → 讯飞 TTS API 合成 → 写入临时 WAV 文件 → 播放 → 删除临时文件
- 讯飞密钥硬编码（不暴露给用户）
- voice_enabled 设置可关（默认开启）
- API 调用失败 → 降级为纯文字模式，文字记账功能正常

技术方案：
- 桌面/Android 通用：WebSocket 在线 API（wss://tts-api.xfyun.cn/v2/tts）
- 鉴权：HMAC-SHA256 签名
- 音频：PCM 16kHz 单声道 → 添加 WAV 文件头 → SDL2 播放
- 异步：speak() 立即返回，后台线程完成合成+播放

对外接口：
- XfyunTTS.speak(text) → bool     播放唱诺文案（异步）
- XfyunTTS.synthesize(text) → bytes|None  同步合成，返回 WAV 二进制
- XfyunTTS.is_available() → bool   检查 TTS 是否可用
- XfyunTTS.shutdown()               释放资源
"""

import os
import sys
import json
import hmac
import base64
import hashlib
import struct
import threading
import tempfile
import time
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# 讯飞配置（硬编码，不暴露给用户）
# ══════════════════════════════════════════════

XFYUN_APP_ID = "43000a3c"
XFYUN_API_KEY = "d42f6a93055e76adbb795b0cf09e1baf"
XFYUN_API_SECRET = "NjUxYzFjMGNkMzE5OTc5MGNlOTY0NzJm"

# TTS 参数
TTS_VCN = "xiaoyan"                # 发音人：小燕（女声，利索不拖音）
TTS_SPEED = 50                     # 语速 [0-100]，50 为正常
TTS_VOLUME = 80                    # 音量 [0-100]
TTS_PITCH = 50                     # 音调 [0-100]
TTS_SAMPLE_RATE = 16000            # 采样率
TTS_AUDIO_FORMAT = "raw"           # 音频编码（raw = PCM 未压缩）

# WebSocket API
_TTS_URL = "wss://tts-api.xfyun.cn/v2/tts"
_TTS_HOST = "tts-api.xfyun.cn"

# 播放超时
_PLAY_TIMEOUT = 30  # 最长等待播放 30 秒


def _generate_auth_url() -> str:
    """
    生成带鉴权参数的 WebSocket URL。

    鉴权流程：
    1. RFC1123 格式 UTC 时间
    2. 构建 origin 字符串：host + date + request-line
    3. HMAC-SHA256 签名（密钥 = API_SECRET）
    4. Base64 编码签名，拼入 authorization 参数
    """
    # RFC1123 格式 UTC 时间
    date = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')

    # 签名字符串
    sign_string = (
        f"host: {_TTS_HOST}\n"
        f"date: {date}\n"
        f"GET /v2/tts HTTP/1.1"
    )

    # HMAC-SHA256 签名
    signature_sha = hmac.new(
        XFYUN_API_SECRET.encode('utf-8'),
        sign_string.encode('utf-8'),
        hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode('utf-8')

    # authorization 原始字符串
    auth_origin = (
        f'api_key="{XFYUN_API_KEY}", '
        f'algorithm="hmac-sha256", '
        f'headers="host date request-line", '
        f'signature="{signature}"'
    )
    authorization = base64.b64encode(auth_origin.encode('utf-8')).decode('utf-8')

    # 构建完整 URL
    params = {
        'host': _TTS_HOST,
        'date': date,
        'authorization': authorization,
    }

    return f"{_TTS_URL}?{urlencode(params)}"


def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000,
                channels: int = 1, bits_per_sample: int = 16) -> bytes:
    """
    将 PCM 原始数据包装为 WAV 文件格式。

    WAV 文件结构：
    - RIFF Header (12 bytes)
    - fmt Chunk (24 bytes)
    - data Chunk (8 bytes + pcm_data)
    """
    data_size = len(pcm_data)
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8

    # RIFF Header
    riff = b'RIFF'
    file_size = 36 + data_size
    wave = b'WAVE'

    # fmt Subchunk
    fmt_tag = b'fmt '
    fmt_size = 16  # PCM
    audio_format = 1  # PCM (uncompressed)
    num_channels = channels
    sample_rate_val = sample_rate
    byte_rate_val = byte_rate
    block_align_val = block_align
    bits_per_sample_val = bits_per_sample

    # data Subchunk
    data_tag = b'data'

    wav = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        riff, file_size, wave,
        fmt_tag, fmt_size, audio_format,
        num_channels, sample_rate_val, byte_rate_val,
        block_align_val, bits_per_sample_val,
        data_tag, data_size,
    )
    wav += pcm_data

    return wav


class XfyunTTS:
    """
    讯飞 TTS 引擎封装。

    使用方式：
        tts = XfyunTTS()
        tts.speak("3号桌30串羊肉串，稍等！")  # 异步播放

    或者同步合成：
        wav_data = tts.synthesize("你好")
    """

    def __init__(self):
        self._available = True
        self._lock = threading.Lock()
        self._is_playing = False

        # 预检查 websocket-client
        try:
            import websocket
            self._available = True
        except ImportError:
            logger.warning("[TTS] websocket-client 未安装，TTS 不可用")
            self._available = False

    def is_available(self) -> bool:
        """检查 TTS 是否可用"""
        return self._available

    def is_voice_enabled(self) -> bool:
        """从数据库设置读取语音开关状态（默认开启）"""
        try:
            from data.db import get_setting
            val = get_setting("voice_enabled")
            if val is None:
                return True
            return val == "1" or val == 1
        except Exception:
            return True

    def synthesize(self, text: str) -> bytes | None:
        """
        同步合成语音，返回 WAV 二进制数据。

        Args:
            text: 要合成的文本

        Returns:
            WAV 音频二进制（含 WAV 文件头），失败返回 None
        """
        if not text or not text.strip():
            return None

        if not self._available:
            return None

        return self._tts_synth(text.strip())

    def speak(self, text: str) -> bool:
        """
        播放唱诺文案（异步，不阻塞调用方）。

        Args:
            text: 要朗读的文本（唱诺文案，已过东北话滤镜）

        Returns:
            True=已提交播放 / False=不可用或文本为空
        """
        if not text or not text.strip():
            return False

        if not self.is_voice_enabled():
            logger.debug("[TTS] 语音已关闭，跳过播放")
            return False

        if not self._available:
            logger.debug("[TTS] 引擎不可用，跳过播放")
            return False

        with self._lock:
            if self._is_playing:
                logger.debug("[TTS] 上次播放尚未结束，跳过本次")
                return False
            self._is_playing = True

        t = threading.Thread(
            target=self._do_speak,
            args=(text.strip(),),
            daemon=True,
        )
        t.start()
        return True

    def _do_speak(self, text: str):
        """后台线程：合成 → 写临时文件 → 播放 → 删除临时文件"""
        temp_file = None
        try:
            wav_data = self._tts_synth(text)
            if not wav_data:
                logger.warning("[TTS] 合成失败，无音频数据")
                return

            # 写入临时文件
            temp_file = tempfile.NamedTemporaryFile(
                suffix='.wav',
                prefix='tts_',
                delete=False,
            )
            temp_file.write(wav_data)
            temp_file.close()
            logger.info(f"[TTS] 音频写入: {temp_file.name} ({len(wav_data)} bytes)")

            # 播放
            self._play_file(temp_file.name)

        except Exception as e:
            logger.error(f"[TTS] 播放出错: {e}")
        finally:
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except OSError:
                    pass
            with self._lock:
                self._is_playing = False

    def _tts_synth(self, text: str) -> bytes | None:
        """
        调用讯飞在线 TTS API 合成音频。

        流程：
        1. 生成鉴权 URL
        2. WebSocket 连接
        3. 发送请求 JSON
        4. 接收音频帧（Base64 编码 PCM）
        5. 合并 + 添加 WAV 文件头
        """
        import websocket

        audio_frames = []
        error_msg = [None]  # 用列表以便在闭包中修改
        done = threading.Event()

        def on_message(ws, message):
            """处理 WebSocket 消息"""
            try:
                data = json.loads(message)
                code = data.get("code")

                if code != 0:
                    error_msg[0] = f"API 错误: code={code}, msg={data.get('message')}"
                    logger.error(f"[TTS] {error_msg[0]}")
                    ws.close()
                    done.set()
                    return

                inner = data.get("data")
                if inner and inner.get("audio"):
                    frame = base64.b64decode(inner["audio"])
                    audio_frames.append(frame)

                if inner and inner.get("status") == 2:
                    ws.close()
                    done.set()

            except Exception as e:
                error_msg[0] = f"解析消息异常: {e}"
                logger.error(f"[TTS] {error_msg[0]}")
                ws.close()
                done.set()

        def on_error(ws, error):
            error_msg[0] = f"WebSocket 错误: {error}"
            logger.error(f"[TTS] {error_msg[0]}")
            done.set()

        def on_close(ws, close_status_code, close_msg):
            done.set()

        def on_open(ws):
            """连接成功后发送 TTS 请求"""
            request = {
                "common": {"app_id": XFYUN_APP_ID},
                "business": {
                    "aue": TTS_AUDIO_FORMAT,
                    "auf": f"audio/L16;rate={TTS_SAMPLE_RATE}",
                    "vcn": TTS_VCN,
                    "speed": TTS_SPEED,
                    "volume": TTS_VOLUME,
                    "pitch": TTS_PITCH,
                    "bgs": 0,
                    "tte": "UTF8",
                },
                "data": {
                    "status": 2,
                    "text": base64.b64encode(
                        text.encode('utf-8')
                    ).decode('utf-8'),
                },
            }
            ws.send(json.dumps(request))

        try:
            auth_url = _generate_auth_url()

            ws = websocket.WebSocketApp(
                auth_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open,
            )
            # 同步运行，带超时
            wst = threading.Thread(target=ws.run_forever, daemon=True)
            wst.start()

            if not done.wait(timeout=15):
                ws.close()
                logger.warning("[TTS] 合成超时 (15s)")
                return None

            if error_msg[0]:
                return None

            if not audio_frames:
                logger.warning("[TTS] 未收到音频数据")
                return None

            # 合并 PCM + 转 WAV
            pcm_data = b''.join(audio_frames)
            wav_data = _pcm_to_wav(pcm_data, sample_rate=TTS_SAMPLE_RATE)

            logger.info(
                f"[TTS] 合成完成: {len(pcm_data)} bytes PCM → "
                f"{len(wav_data)} bytes WAV"
            )
            return wav_data

        except Exception as e:
            logger.error(f"[TTS] 合成异常: {e}")
            return None

    def _play_file(self, file_path: str):
        """
        播放 WAV 音频文件。

        使用 Kivy SoundLoader（SDL2 后端）。
        如果 Kivy 未初始化则降级为静默。
        """
        try:
            from kivy.core.audio import SoundLoader

            sound = SoundLoader.load(file_path)
            if sound is None:
                logger.warning(f"[TTS] 无法加载音频: {file_path}")
                return

            sound.play()

            # 轮询等待播放完成
            waited = 0
            while sound.state == 'play' and waited < _PLAY_TIMEOUT:
                time.sleep(0.1)
                waited += 0.1

            sound.stop()
            sound.unload()

        except Exception as e:
            logger.error(f"[TTS] 播放失败: {e}")

    def shutdown(self):
        """释放 TTS 资源"""
        self._available = False


# ══════════════════════════════════════════════
# 模块级单例
# ══════════════════════════════════════════════

_tts_instance = None
_tts_lock = threading.Lock()


def get_tts() -> XfyunTTS:
    """获取 TTS 单例（线程安全）"""
    global _tts_instance
    with _tts_lock:
        if _tts_instance is None:
            _tts_instance = XfyunTTS()
        return _tts_instance


def speak(text: str) -> bool:
    """
    便捷函数：播放唱诺文案。

    自动检查 voice_enabled 开关和 TTS 可用性。
    返回 True 表示已提交播放，False 表示跳过。
    """
    return get_tts().speak(text)


def shutdown_tts():
    """释放 TTS 资源"""
    global _tts_instance
    with _tts_lock:
        if _tts_instance:
            _tts_instance.shutdown()
            _tts_instance = None


# ══════════════════════════════════════════════
# 契约测试（python -m skills.xfyun_tts 直接运行）
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import sys, os

    _root = os.path.join(os.path.dirname(__file__), "..")
    sys.path.insert(0, os.path.abspath(_root))

    # 初始化数据库
    from data.db import set_db_path, init_db, set_setting
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    set_db_path(tmp_db.name)
    init_db()
    set_setting("voice_enabled", "1")

    passed = 0
    failed_tests = []

    def run_test(name):
        def decorator(fn):
            try:
                fn()
                print(f"  T{name}: PASS")
            except AssertionError as e:
                print(f"  T{name}: FAIL - {e}")
                failed_tests.append(name)
            except Exception as e:
                print(f"  T{name}: ERROR - {type(e).__name__}: {e}")
                failed_tests.append(name)
        return decorator

    print("=== skills/xfyun_tts.py 契约测试 ===")

    # ── T1: XfyunTTS 类可实例化 ──
    @run_test("1")
    def test_T1():
        tts = XfyunTTS()
        assert tts is not None
        assert isinstance(tts.is_available(), bool)
        tts.shutdown()

    # ── T2: speak() 空文本不崩溃，返回 False ──
    @run_test("2")
    def test_T2():
        tts = XfyunTTS()
        assert tts.speak("") is False
        assert tts.speak("   ") is False
        assert tts.speak(None) is False
        tts.shutdown()

    # ── T3: is_voice_enabled() 正确读取设置 ──
    @run_test("3")
    def test_T3():
        tts = XfyunTTS()
        set_setting("voice_enabled", "1")
        assert tts.is_voice_enabled() is True
        set_setting("voice_enabled", "0")
        assert tts.is_voice_enabled() is False
        set_setting("voice_enabled", 1)
        assert tts.is_voice_enabled() is True
        set_setting("voice_enabled", "1")
        tts.shutdown()

    # ── T4: 模块单例一致性 ──
    @run_test("4")
    def test_T4():
        global _tts_instance
        _tts_instance = None
        t1 = get_tts()
        t2 = get_tts()
        assert t1 is t2
        shutdown_tts()
        assert _tts_instance is None

    # ── T5: shutdown() 后 speak 安全 ──
    @run_test("5")
    def test_T5():
        tts = XfyunTTS()
        tts.shutdown()
        assert tts.is_available() is False
        assert tts.speak("测试") is False

    # ── T6: 并发 speak 安全 ──
    @run_test("6")
    def test_T6():
        tts = XfyunTTS()
        results = []
        def worker(txt):
            try:
                r = tts.speak(txt)
                results.append(r)
            except Exception as e:
                results.append(e)
        threads = [
            threading.Thread(target=worker, args=(f"测试{i}",), daemon=True)
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2)
        for r in results:
            assert not isinstance(r, Exception), f"并发 speak 异常: {r}"
        tts.shutdown()

    # ── T7: _pcm_to_wav 输出有效 WAV ──
    @run_test("7")
    def test_T7():
        # 生成假 PCM 数据（1 秒静音）
        pcm = b'\x00\x00' * 16000  # 16kHz 16bit 单声道 1秒
        wav = _pcm_to_wav(pcm)
        assert wav[:4] == b'RIFF', "WAV 应以 RIFF 开头"
        assert wav[8:12] == b'WAVE', "应为 WAVE 格式"
        assert len(wav) == len(pcm) + 44, f"WAV 应为 PCM + 44 字节头，实际 {len(wav)}"

    # ── T8: _generate_auth_url 生成有效 URL ──
    @run_test("8")
    def test_T8():
        url = _generate_auth_url()
        assert url.startswith("wss://tts-api.xfyun.cn/v2/tts?"), f"URL 前缀错误: {url[:50]}"
        assert "host=" in url
        assert "date=" in url
        assert "authorization=" in url

    # ── T9: synthesize() 真实 API 调用（需要网络）──
    @run_test("9")
    def test_T9():
        tts = XfyunTTS()
        wav = tts.synthesize("你好")
        assert wav is not None, "合成应返回 WAV 数据"
        assert wav[:4] == b'RIFF', "应返回有效 WAV 格式"
        assert len(wav) > 44, f"WAV 数据过小: {len(wav)} bytes"
        print(f"    (合成成功: {len(wav)} bytes WAV)")
        tts.shutdown()

    # ── T10: synthesize() 空文本返回 None ──
    @run_test("10")
    def test_T10():
        tts = XfyunTTS()
        assert tts.synthesize("") is None
        assert tts.synthesize(None) is None
        assert tts.synthesize("   ") is None
        tts.shutdown()

    # 统计
    passed = 10 - len(failed_tests)

    # 清理
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(tmp_db.name + suffix)
        except OSError:
            pass

    print(f"\n{'='*40}")
    if failed_tests:
        print(f"测试结果: {passed}/10 通过，失败项: {failed_tests}")
        sys.exit(1)
    else:
        print(f"全部 {passed}/10 契约测试通过 ✅  skills/xfyun_tts.py 可交付")
    print(f"{'='*40}")
