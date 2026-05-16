"""
utils/backup.py — 加密备份导出/导入

规范来源：
- project_start.md 第六节第9款（加密备份）
- project_start.md 第九条第7条（.bbk 魔数和哈希格式）
- project_start.md 第十节（利润计算逻辑）

备份格式规范（.bbk）：
┌──────────────────────────────────────┐
│ 字节 0-3   : 魔数 0x42424B31 (BBK1) │
│ 字节 4-19  : 16字节随机 IV           │
│ 字节 20-EOF: AES-256-CBC 加密数据     │
└──────────────────────────────────────┘

加密前明文结构：
┌──────────────────────────────────────┐
│ SQLite 文件原始字节                   │
│ + 末尾 32 字节 SHA-256 哈希          │
└──────────────────────────────────────┘
哈希计算范围：整个 SQLite 文件内容（不含哈希本身）

加密算法：AES-256-CBC
密钥派生：sha256(盐 + 用户密码)，盐与登录密码相同（dianxiaoer_salt_v1）
"""

import os
import hashlib
import struct

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

# ══════════════════════════════════════════════
# 常量
# ══════════════════════════════════════════════

# 魔数：BBK1（0x42 0x42 0x4B 0x31）
_MAGIC = b"BBK1"

# IV 长度（AES 块大小 = 16 字节）
_IV_SIZE = 16

# AES 块大小
_BLOCK_SIZE = 16

# 密钥长度（AES-256 = 32 字节）
_KEY_SIZE = 32

# SHA-256 哈希长度
_HASH_SIZE = 32

# 固定盐（与 data.db 中的登录密码盐一致）
_SALT = "dianxiaoer_salt_v1"


# ══════════════════════════════════════════════
# 密钥派生
# ══════════════════════════════════════════════

def _derive_key(password: str) -> bytes:
    """从用户密码派生 AES-256 密钥（SHA-256 + 固定盐）"""
    raw = (_SALT + password).encode("utf-8")
    return hashlib.sha256(raw).digest()  # 32 字节


# ══════════════════════════════════════════════
# PKCS7 填充/去填充
# ══════════════════════════════════════════════

def _pkcs7_pad(data: bytes) -> bytes:
    """PKCS7 填充到 AES 块大小的整数倍"""
    pad_len = _BLOCK_SIZE - (len(data) % _BLOCK_SIZE)
    return data + bytes([pad_len]) * pad_len


def _pkcs7_unpad(data: bytes) -> bytes:
    """移除 PKCS7 填充"""
    if not data:
        raise ValueError("解密数据为空")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > _BLOCK_SIZE:
        raise ValueError(f"无效的PKCS7填充长度: {pad_len}")
    # 验证填充字节
    for i in range(pad_len):
        if data[-(i + 1)] != pad_len:
            raise ValueError("PKCS7填充校验失败")
    return data[:-pad_len]


# ══════════════════════════════════════════════
# 导出备份
# ══════════════════════════════════════════════

def export_backup(password: str, output_path: str) -> str:
    """
    导出加密备份到 .bbk 文件。

    参数：
    - password: 用户密码（用于派生加密密钥）
    - output_path: 输出文件路径（通常以 .bbk 结尾）

    返回值：
    - 成功: "ok"
    - 失败: 错误描述字符串

    流程：
    1. 读取当前 SQLite 数据库文件
    2. 计算 SHA-256 哈希
    3. 拼接: 数据库字节 + 哈希
    4. PKCS7 填充
    5. 生成随机 IV
    6. AES-256-CBC 加密
    7. 写入: 魔数 + IV + 密文
    """
    from data.db import _db_path

    db_file = _db_path

    # 1. 读取 SQLite 文件
    if not os.path.exists(db_file):
        return "数据库文件不存在"

    with open(db_file, "rb") as f:
        db_data = f.read()

    if len(db_data) == 0:
        return "数据库文件为空"

    # 2. 计算 SHA-256（哈希范围：整个 SQLite 文件）
    db_hash = hashlib.sha256(db_data).digest()

    # 3. 拼接：数据库 + 哈希
    plaintext = db_data + db_hash

    # 4. PKCS7 填充
    padded = _pkcs7_pad(plaintext)

    # 5. 生成随机 IV
    iv = get_random_bytes(_IV_SIZE)

    # 6. AES-256-CBC 加密
    key = _derive_key(password)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(padded)

    # 7. 写入文件：魔数 + IV + 密文
    try:
        with open(output_path, "wb") as f:
            f.write(_MAGIC)
            f.write(iv)
            f.write(ciphertext)
    except OSError as e:
        return f"写入失败: {e}"

    # 记录备份日志
    file_hash = hashlib.sha256(db_data).hexdigest()
    from data.db import add_backup_log
    add_backup_log(file_hash)

    return "ok"


# ══════════════════════════════════════════════
# 导入备份
# ══════════════════════════════════════════════

class BackupError(Exception):
    """备份文件异常基类"""
    pass


class InvalidBackupError(BackupError):
    """无效备份文件（魔数错误等）"""
    pass


class CorruptBackupError(BackupError):
    """备份文件损坏或密码错误（哈希不匹配）"""
    pass


def import_backup(password: str, input_path: str) -> str:
    """
    从 .bbk 文件导入并恢复数据库。

    参数：
    - password: 用户密码（用于派生解密密钥）
    - input_path: 备份文件路径

    返回值：
    - 成功: "ok"
    - 失败: 错误描述字符串

    流程：
    1. 读取前4字节验证魔数
    2. 读取 IV（16字节）
    3. 解密剩余数据
    4. 分离：末尾32字节为哈希，其余为数据库
    5. 重算 SHA-256 比对
    6. 通过后替换本地数据库并重新初始化
    """
    from data.db import _db_path, init_db

    # 1. 读取文件
    if not os.path.exists(input_path):
        return "备份文件不存在"

    try:
        with open(input_path, "rb") as f:
            raw = f.read()
    except OSError as e:
        return f"读取失败: {e}"

    if len(raw) < len(_MAGIC) + _IV_SIZE + _BLOCK_SIZE:
        return "备份文件太小，可能已损坏"

    # 2. 验证魔数
    magic = raw[:4]
    if magic != _MAGIC:
        return "无效备份文件"

    # 3. 读取 IV
    iv = raw[4:4 + _IV_SIZE]
    ciphertext = raw[4 + _IV_SIZE:]

    # 4. 解密
    key = _derive_key(password)
    try:
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded = cipher.decrypt(ciphertext)
    except ValueError as e:
        return f"解密失败: {e}"

    # 5. 去填充
    try:
        plaintext = _pkcs7_unpad(padded)
    except ValueError as e:
        return f"数据损坏: {e}"

    if len(plaintext) < _HASH_SIZE + 16:
        return "备份数据太短，数据库内容不完整"

    # 6. 分离哈希和数据库
    stored_hash = plaintext[-_HASH_SIZE:]
    db_data = plaintext[:-_HASH_SIZE]

    # 7. 验证哈希
    actual_hash = hashlib.sha256(db_data).digest()
    if stored_hash != actual_hash:
        return "文件损坏或密码错误"

    # 8. 替换本地数据库
    # 先删除旧文件（含 WAL 辅助文件）
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(_db_path + suffix)
        except OSError:
            pass

    # 写入新数据库
    try:
        with open(_db_path, "wb") as f:
            f.write(db_data)
    except OSError as e:
        return f"写入数据库失败: {e}"

    # 重新初始化（确保连接有效）
    init_db()

    return "ok"


# ══════════════════════════════════════════════
# 契约测试（python -m utils.backup 直接运行）
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile, sys, shutil

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from data.db import set_db_path, init_db, add_menu_item as db_add_menu, \
        add_order, get_all_menu, checkout, _db_path

    # 使用临时数据库
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    set_db_path(tmp_db.name)
    init_db()

    # 写入测试数据
    db_add_menu("羊肉串", 3.0, "串")
    db_add_menu("啤酒", 5.0, "瓶")
    add_order("羊肉串", 10, 3.0, table_num=1)
    add_order("啤酒", 2, 5.0, table_num=1)

    passed = 0
    failed_tests = []

    def run_test(name):
        def decorator(fn):
            try:
                fn()
                print(f"  E{name}: PASS")
            except AssertionError as e:
                print(f"  E{name}: FAIL - {e}")
                failed_tests.append(name)
            except Exception as e:
                print(f"  E{name}: ERROR - {type(e).__name__}: {e}")
                failed_tests.append(name)
        return decorator

    print("=== utils/backup.py 契约测试 ===")

    # ── E1: 导出文件格式验证 ──
    @run_test("1")
    def test_E1():
        bbk_path = tmp_db.name + ".test.bbk"
        result = export_backup("mypassword", bbk_path)
        assert result == "ok", f"导出应返回ok，实际: {result}"
        assert os.path.exists(bbk_path), "备份文件应存在"

        # 验证文件结构
        with open(bbk_path, "rb") as f:
            data = f.read()

        # 魔数
        assert data[:4] == b"BBK1", "魔数应为 BBK1"

        # IV（16字节）
        iv = data[4:20]
        assert len(iv) == 16, "IV 应为 16 字节"

        # 密文部分长度应是16的倍数
        ciphertext = data[20:]
        assert len(ciphertext) % 16 == 0, f"密文长度应为16的倍数，实际: {len(ciphertext)}"

        # 文件总长度 > 魔数 + IV + 原始数据 + 哈希
        assert len(data) > 4 + 16 + 32, "文件应包含足够数据"

    # ── E2: 导入恢复验证 ──
    @run_test("2")
    def test_E2():
        bbk_path = tmp_db.name + ".test.bbk"

        # 先记录原始数据
        original_menu = get_all_menu()
        assert len(original_menu) == 2, "导入前应有2个品类"

        # 导入（使用正确密码）
        result = import_backup("mypassword", bbk_path)
        assert result == "ok", f"导入应返回ok，实际: {result}"

        # 验证数据恢复
        restored_menu = get_all_menu()
        assert len(restored_menu) == 2, f"恢复后应有2个品类，实际: {len(restored_menu)}"
        names = {m["item_name"] for m in restored_menu}
        assert names == {"羊肉串", "啤酒"}, f"品类名应恢复，实际: {names}"

    # ── E3: 错误密码拒绝 ──
    @run_test("3")
    def test_E3():
        bbk_path = tmp_db.name + ".test.bbk"
        result = import_backup("wrongpassword", bbk_path)
        assert result != "ok", "错误密码不应导入成功"
        assert "密码错误" in result or "损坏" in result, f"应提示密码错误，实际: {result}"

    # ── E4: 损坏/无效文件拒绝 ──
    @run_test("4")
    def test_E4():
        # 非BBK文件（太小）
        fake_path = tmp_db.name + ".fake.bbk"
        with open(fake_path, "wb") as f:
            f.write(b"NOT_A_BACKUP_FILE_CONTENT")
        result = import_backup("mypassword", fake_path)
        assert result != "ok"
        assert "无效" in result or "太小" in result or "损坏" in result, f"应提示文件异常，实际: {result}"

        # BBK头正确但内容被篡改
        tamper_path = tmp_db.name + ".tamper.bbk"
        with open(tmp_db.name + ".test.bbk", "rb") as f:
            original = f.read()
        # 保留魔数+IV，篡改密文
        tampered = original[:20] + b"\x00" * 32 + original[52:]
        with open(tamper_path, "wb") as f:
            f.write(tampered)
        result = import_backup("mypassword", tamper_path)
        assert result != "ok", "篡改文件不应导入成功"
        assert "损坏" in result or "密码错误" in result or "数据" in result, f"应提示损坏，实际: {result}"

    # 统计
    passed = 4 - len(failed_tests)

    # 清理
    for suffix in ("", "-wal", "-shm", ".test.bbk", ".fake.bbk", ".tamper.bbk"):
        try:
            os.unlink(tmp_db.name + suffix)
        except OSError:
            pass

    print(f"\n{'='*40}")
    if failed_tests:
        print(f"测试结果: {passed}/4 通过，失败项: {failed_tests}")
        sys.exit(1)
    else:
        print(f"全部 {passed}/4 契约测试通过 ✅  utils/backup.py 可交付")
    print(f"{'='*40}")
