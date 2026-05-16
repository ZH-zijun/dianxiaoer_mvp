"""
skills/xfyun_asr.py — 讯飞语音听写（ASR）模块

规范来源：
- project_start.md 第六节第7款（语音管家）
- project_start.md 第七条（异常处理：SDK 初始化失败降级纯文字）
- 讯飞实时语音转写 API 文档

核心行为：
- 录音 → 讯飞 ASR API 识别 → 返回文字，填入输入区
- 按住录音，松开结束
- 讯飞密钥硬编码（不暴露给用户）
- API 调用失败 → 降级为纯文字模式，文字记账功能正常

技术方案：
- 桌面/Android 通用：WebSocket 在线 API（wss://iat-api.xfyun.cn/v2/iat）
- 鉴权：HMAC-SHA256 签名
- 音频采集：Python sounddevice / Android pyaudio
- 识别结果：实时返回，拼接为完整文字

对外接口：
- XfyunASR.is_available() → bool
- XfyunASR.start_recording() → None    开始录音
- XfyunASR.stop_recording() → str      停止录音，返回识别文字
"""

import os
import json
import hmac
import base64
import hashlib
import threading
import time
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode
from io import BytesIO

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# 讯飞配置（硬编码，不暴露给用户）
# ══════════════════════════════════════════════

# 复用 TTS 的密钥（同一个讯飞账号）
XFYUN_APP_ID = "43000a3c"
XFYUN_API_KEY = "d42f6a93055e76adbb795b0cf09e1baf"
XFYUN_API_SECRET = "NjUxYzFjMGNkMzE5OTc5MGNlOTY0NzJm"

# ASR 参数
ASR_SAMPLE_RATE = 16000       # 采样率
ASR_AUDIO_FORMAT = "raw"      # 音频编码（raw = PCM 未压缩）
ASR_ENCODING = "raw"          # 与 audio_format 对应
ASR_DOMAIN = "iat"            # 普通话听写
ASR_PTT_NUM = 0               # 首帧为 0，后续帧递增
ASR_LANGUAGE = "zh_cn"        # 语言：中文普通话
ASR_ACcent = "mandarin"       # 方言：普通话
ASR_VAD_EOS = 2000            # 静音检测超时（毫秒）

# WebSocket API
_IAT_URL = "wss://iat-api.xfyun.cn/v2/iat"
_IAT_HOST = "iat-api.xfyun.cn"

# 录音参数
_RECORD_TIMEOUT = 60           # 最长录音 60 秒
_FRAME_SIZE = 1280             # 每帧发送 40ms 音频（16000 * 0.04 * 2 = 1280 bytes）


def _generate_auth_url() -> str:
    """生成带鉴权参数的 WebSocket URL（与 TTS 共用鉴权逻辑）"""
    date = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')

    sign_string = (
        f"host: {_IAT_HOST}\n"
        f"date: {date}\n"
        f"GET /v2/iat HTTP/1.1"
    )

    signature_sha = hmac.new(
        XFYUN_API_SECRET.encode('utf-8'),
        sign_string.encode('utf-8'),
        hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode('utf-8')

    auth_origin = (
        f'api_key="{XFYUN_API_KEY}", '
        f'algorithm="hmac-sha256", '
        f'headers="host date request-line", '
        f'signature="{signature}"'
    )
    authorization = base64.b64encode(auth_origin.encode('utf-8')).decode('utf-8')

    params = {
        'host': _IAT_HOST,
        'date': date,
        'authorization': authorization,
    }

    return f"{_IAT_URL}?{urlencode(params)}"


class XfyunASR:
    """
    讯飞语音听写引擎封装。

    使用方式：
        asr = XfyunASR()
        asr.start_recording()
        # ... 用户说话 ...
        text = asr.stop_recording()  # 返回识别结果
    """

    def __init__(self):
        self._available = True
        self._is_recording = False
        self._record_thread = None
        self._stop_event = threading.Event()
        self._result_text = ""
        self._audio_buffer = []

        # 预检查依赖
        try:
            import websocket
            self._available = True
        except ImportError:
            logger.warning("[ASR] websocket-client 未安装，ASR 不可用")
            self._available = False

    def is_available(self) -> bool:
        """检查 ASR 是否可用"""
        return self._available

    def start_recording(self):
        """开始录音并实时发送到讯飞 ASR"""
        if not self._available:
            logger.debug("[ASR] 引擎不可用")
            return

        if self._is_recording:
            logger.debug("[ASR] 已在录音中，忽略")
            return

        self._is_recording = True
        self._result_text = ""
        self._audio_buffer = []
        self._stop_event.clear()

        self._record_thread = threading.Thread(
            target=self._record_and_recognize,
            daemon=True,
        )
        self._record_thread.start()

    def stop_recording(self) -> str:
        """
        停止录音，等待识别完成，返回识别文字。
        如果未在录音则返回空字符串。
        """
        if not self._is_recording:
            return ""

        self._stop_event.set()
        self._is_recording = False

        # 等待识别线程结束（最多 5 秒）
        if self._record_thread and self._record_thread.is_alive():
            self._record_thread.join(timeout=5)

        return self._result_text

    def _record_and_recognize(self):
        """录音线程：采集音频 → 发送 WebSocket → 接收识别结果"""
        import websocket

        audio_frames = []
        result_parts = []
        error_msg = [None]
        ws_done = threading.Event()
        ws_started = threading.Event()
        send_done = threading.Event()

        # 音频采集线程
        self._audio_buffer = []
        record_error = [None]

        def _audio_collector():
            """采集音频数据（使用 sounddevice）"""
            try:
                import sounddevice as sd
                with sd.InputStream(
                    samplerate=ASR_SAMPLE_RATE,
                    channels=1,
                    dtype='int16',
                    blocksize=_FRAME_SIZE // 2,  # 每个样本 2 字节
                ):
                    while not self._stop_event.is_set():
                        data = sd.rec(_FRAME_SIZE // 2, samplerate=ASR_SAMPLE_RATE,
                                      channels=1, dtype='int16', blocking=True)
                        frame_bytes = data.tobytes()
                        audio_frames.append(frame_bytes)
                        self._audio_buffer.append(frame_bytes)

                        # 等待 WebSocket 准备好
                        ws_started.wait(timeout=5)

                        # 发送音频帧到 WebSocket
                        if ws_done.is_set():
                            break
            except ImportError:
                record_error[0] = "sounddevice 未安装"
                logger.error("[ASR] sounddevice 未安装，无法录音")
                self._stop_event.set()
                ws_done.set()
            except Exception as e:
                record_error[0] = str(e)
                logger.error(f"[ASR] 录音异常: {e}")
                self._stop_event.set()
                ws_done.set()

        def on_message(ws, message):
            """处理 WebSocket 消息"""
            try:
                data = json.loads(message)
                code = data.get("code")

                if code != 0:
                    error_msg[0] = f"API 错误: code={code}, msg={data.get('message')}"
                    logger.error(f"[ASR] {error_msg[0]}")
                    ws.close()
                    ws_done.set()
                    return

                inner = data.get("data")
                if inner:
                    result = inner.get("result", {})
                    ws_text = result.get("ws", [])

                    # 拼接识别文字
                    for ws_item in ws_text:
                        for cw in ws_item.get("cw", []):
                            w = cw.get("w", "")
                            if w:
                                result_parts.append(w)

                data_status = inner.get("status", 0) if inner else 0
                if data_status == 2:
                    ws.close()
                    ws_done.set()
            except Exception as e:
                error_msg[0] = f"解析消息异常: {e}"
                logger.error(f"[ASR] {error_msg[0]}")
                ws.close()
                ws_done.set()

        def on_error(ws, error):
            error_msg[0] = f"WebSocket 错误: {error}"
            logger.error(f"[ASR] {error_msg[0]}")
            ws_done.set()

        def on_close(ws, close_status_code, close_msg):
            ws_done.set()

        def on_open(ws):
            """WebSocket 连接成功，开始发送音频"""
            frame_idx = 0
            send_started = threading.Event()

            def _sender():
                nonlocal frame_idx
                ws_started.set()

                # 遍历已录制和即将录制的音频帧
                sent_count = 0
                audio_idx = 0
                while True:
                    # 检查是否有新帧
                    if audio_idx < len(audio_frames):
                        frame = audio_frames[audio_idx]
                        audio_idx += 1
                    elif self._stop_event.is_set() and audio_idx >= len(audio_frames):
                        break
                    else:
                        time.sleep(0.02)
                        continue

                    status = 0 if frame_idx == 0 else (2 if self._stop_event.is_set() else 1)
                    frame_idx += 1

                    request = {
                        "common": {"app_id": XFYUN_APP_ID},
                        "business": {
                            "language": ASR_LANGUAGE,
                            "domain": ASR_DOMAIN,
                            "accent": ASR_ACcent,
                            "vad_eos": ASR_VAD_EOS,
                            "dwa": "wpgs",  # 动态修正
                        },
                        "data": {
                            "status": status,
                            "format": "audio/L16;rate=16000",
                            "encoding": "raw",
                            "audio": base64.b64encode(frame).decode('utf-8'),
                        },
                    }

                    try:
                        ws.send(json.dumps(request))
                        sent_count += 1
                    except Exception:
                        break

                    # 发送间隔（模拟实时）
                    if not self._stop_event.is_set():
                        time.sleep(0.04)

                send_done.set()

            threading.Thread(target=_sender, daemon=True).start()

        try:
            auth_url = _generate_auth_url()

            # 启动音频采集线程
            collector_thread = threading.Thread(target=_audio_collector, daemon=True)
            collector_thread.start()

            # 等一小会儿让采集线程启动
            time.sleep(0.1)

            if record_error[0]:
                self._result_text = ""
                return

            ws = websocket.WebSocketApp(
                auth_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open,
            )

            wst = threading.Thread(target=ws.run_forever, daemon=True)
            wst.start()

            # 等待完成（超时保护）
            ws_done.wait(timeout=_RECORD_TIMEOUT + 10)

            ws.close()

        except Exception as e:
            logger.error(f"[ASR] 识别异常: {e}")
            error_msg[0] = str(e)

        # 组装结果
        if error_msg[0]:
            logger.warning(f"[ASR] 识别失败: {error_msg[0]}")
            self._result_text = ""
        else:
            self._result_text = "".join(result_parts).strip()
            logger.info(f"[ASR] 识别结果: {self._result_text}")


# ══════════════════════════════════════════════
# 模块级单例
# ══════════════════════════════════════════════

_asr_instance = None
_asr_lock = threading.Lock()


def get_asr() -> XfyunASR:
    """获取 ASR 单例（线程安全）"""
    global _asr_instance
    with _asr_lock:
        if _asr_instance is None:
            _asr_instance = XfyunASR()
        return _asr_instance


def start_recording():
    """便捷函数：开始录音"""
    get_asr().start_recording()


def stop_recording() -> str:
    """便捷函数：停止录音，返回识别文字"""
    return get_asr().stop_recording()


def shutdown_asr():
    """释放 ASR 资源"""
    global _asr_instance
    with _asr_lock:
        if _asr_instance:
            _asr_instance._available = False
            _asr_instance = None


# ══════════════════════════════════════════════
# 契约测试（python -m skills.xfyun_asr 直接运行）
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    _root = os.path.join(os.path.dirname(__file__), "..")
    sys.path.insert(0, os.path.abspath(_root))

    failed_tests = []

    def run_test(name):
        def decorator(fn):
            try:
                fn()
                print(f"  A{name}: PASS")
            except AssertionError as e:
                print(f"  A{name}: FAIL - {e}")
                failed_tests.append(name)
            except Exception as e:
                print(f"  A{name}: ERROR - {type(e).__name__}: {e}")
                failed_tests.append(name)
        return decorator

    print("=== skills/xfyun_asr.py 契约测试 ===")

    # ── A1: XfyunASR 类可实例化 ──
    @run_test("1")
    def test_A1():
        asr = XfyunASR()
        assert asr is not None
        assert isinstance(asr.is_available(), bool)
        asr._available = False

    # ── A2: _generate_auth_url 生成有效 URL ──
    @run_test("2")
    def test_A2():
        url = _generate_auth_url()
        assert url.startswith("wss://iat-api.xfyun.cn/v2/iat?"), f"URL 前缀错误: {url[:50]}"
        assert "host=" in url
        assert "date=" in url
        assert "authorization=" in url

    # ── A3: stop_recording 未录音时返回空 ──
    @run_test("3")
    def test_A3():
        asr = XfyunASR()
        result = asr.stop_recording()
        assert result == "", f"未录音时应返回空字符串，实际: {result!r}"
        assert asr._is_recording is False

    # ── A4: start/stop 状态切换 ──
    @run_test("4")
    def test_A4():
        asr = XfyunASR()
        assert asr._is_recording is False

        # 模拟快速 start+stop（不可用时不真正录音）
        asr._available = False
        asr.start_recording()
        assert asr._is_recording is False, "不可用时应不启动录音"

        result = asr.stop_recording()
        assert result == ""

    # ── A5: 模块单例一致性 ──
    @run_test("5")
    def test_A5():
        global _asr_instance
        _asr_instance = None
        a1 = get_asr()
        a2 = get_asr()
        assert a1 is a2
        shutdown_asr()
        assert _asr_instance is None

    # ── A6: shutdown 后安全调用 ──
    @run_test("6")
    def test_A6():
        asr = XfyunASR()
        asr._available = False
        asr.start_recording()
        result = asr.stop_recording()
        assert isinstance(result, str)

    # 统计
    passed = 6 - len(failed_tests)

    print(f"\n{'='*40}")
    if failed_tests:
        print(f"测试结果: {passed}/6 通过，失败项: {failed_tests}")
        sys.exit(1)
    else:
        print(f"全部 {passed}/6 契约测试通过 ✅  skills/xfyun_asr.py 可交付")
    print(f"{'='*40}")
