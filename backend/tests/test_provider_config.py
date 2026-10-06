"""pytest 测试：按能力分档的服务商配置。

覆盖四类**真实缺陷**的回归（每一条都对应一次已发生的错误行为）：

1. 加密密钥不稳定 —— 旧代码 `Fernet(secret.encode())`，配置留空时每次重启
   换一把随机钥匙，库里密文全部解不开；配置成任意字符串还会直接抛异常。
2. 豆包音色选不中 —— `_voice_for` 只判 `provider == "volc"`，而 `_resolve_provider`
   返回的是 `volc_mega` / `volc_standard`，于是静默掉回 edge 音色。
3. 全局回退串号 —— `list(self._adapters.keys())[0]` 一旦混入用户适配器，
   就可能把甲用户的 Key 发给乙用户。
4. 重启后用户 Key 静默失效 —— 适配器表是纯内存的，启动必须从库里重建。

另覆盖预设表的关键约束：base_url 必须自带版本段（OpenAICompatAdapter 不自补 /v1）。
"""
import asyncio
import os
import shutil
import tempfile

import pytest


# ================================================================
# 1. 加密密钥稳定
# ================================================================

class TestCryptoKeyStability:
    """密钥派生 + 跨实例解密。"""

    def test_derive_key_is_valid_fernet_key(self):
        """任意字符串（含中文、短口令）都要能派生成合法 Fernet 密钥。

        旧行为：直接 `Fernet(secret.encode())` → 抛 ValueError。
        """
        from cryptography.fernet import Fernet
        from app.core.crypto import _derive_key
        for raw in ("", "x", "中文口令", "a" * 200, "!!!not base64!!!"):
            key = _derive_key(raw)
            Fernet(key)  # 不抛即合法

    def test_secret_roundtrip(self):
        from app.core.crypto import encrypt_secret, decrypt_secret
        payload = {"api_key": "sk-abc", "app_id": "12345"}
        assert decrypt_secret(encrypt_secret(payload)) == payload

    def test_decrypt_garbage_returns_empty_not_raise(self):
        """解不开要返回 {}（调用方据此标「需重新填写」），不能把请求打崩。"""
        from app.core.crypto import decrypt_secret
        assert decrypt_secret("not-a-fernet-token", owner="u1/text") == {}
        assert decrypt_secret("") == {}
        assert decrypt_secret(None) == {}

    def test_file_key_survives_new_fernet_instance(self, tmp_path, monkeypatch):
        """**核心回归**：进程重启（新 Fernet 实例）后仍能解开旧密文。"""
        import app.core.crypto as crypto
        monkeypatch.setattr(crypto, "_SECRET_FILE", tmp_path / ".api_key_secret")
        monkeypatch.setattr(crypto, "_fernet", None)
        monkeypatch.setattr(crypto.settings, "api_key_encrypt_secret", "")
        blob = crypto.encrypt_secret({"api_key": "sk-persist"})

        # 模拟重启：丢掉缓存实例，重新构造
        monkeypatch.setattr(crypto, "_fernet", None)
        assert crypto.decrypt_secret(blob) == {"api_key": "sk-persist"}

    def test_explicit_secret_beats_file(self, tmp_path, monkeypatch):
        """配了 API_KEY_ENCRYPT_SECRET 就按它派生（可跨机器复现）。"""
        import app.core.crypto as crypto
        monkeypatch.setattr(crypto, "_SECRET_FILE", tmp_path / "never_used")
        monkeypatch.setattr(crypto.settings, "api_key_encrypt_secret", "my-passphrase")
        monkeypatch.setattr(crypto, "_fernet", None)
        blob = crypto.encrypt_secret({"api_key": "sk-x"})
        monkeypatch.setattr(crypto, "_fernet", None)
        assert crypto.decrypt_secret(blob) == {"api_key": "sk-x"}
        assert not (tmp_path / "never_used").exists()


# ================================================================
# 2. 豆包音色（bug 3）
# ================================================================

class TestVoiceSelection:
    def test_volc_variants_select_volc_voices(self):
        """`_resolve_provider` 返回 volc_mega/volc_standard，两者都必须选中豆包音色。

        旧代码只判 `== "volc"`，于是这两个值全部掉回 edge 音色。
        """
        from app.core.podcast_tts import _voice_for, TTSContext
        ctx = TTSContext(provider="volc_mega", volc_app_id="a", volc_access_token="t",
                         voice_a="VOLC-A", voice_b="VOLC-B")
        assert _voice_for("volc_mega", "主播A", ctx) == "VOLC-A"
        assert _voice_for("volc_standard", "主播B", ctx) == "VOLC-B"

    def test_azure_and_edge_unchanged(self):
        from app.core.podcast_tts import _voice_for, TTSContext
        assert _voice_for("azure", "主播A", TTSContext(provider="azure", voice_a="AZ")) == "AZ"
        # 不传 ctx 时回落 settings —— 完全向后兼容
        from app.config import settings
        assert _voice_for("edge", "主播A") == settings.edge_tts_voice_a

    def test_unknown_speaker_maps_to_b(self):
        from app.core.podcast_tts import _voice_for, TTSContext
        ctx = TTSContext(provider="edge", voice_a="A", voice_b="B")
        assert _voice_for("edge", "主播C", ctx) == "B"


# ================================================================
# 3. 适配器注册表：能力键 + 不串号（bug 3 / 4）
# ================================================================

class TestAdapterRegistry:
    def setup_method(self):
        from app.core.api_scheduler import api_client
        self.client = api_client
        self._saved = dict(api_client._adapters)
        self._saved_keys = set(api_client._user_keys)
        api_client._adapters.clear()
        api_client._user_keys.clear()

    def teardown_method(self):
        self.client._adapters.clear()
        self.client._adapters.update(self._saved)
        self.client._user_keys.clear()
        self.client._user_keys.update(self._saved_keys)

    def test_capability_keys_are_separate(self):
        """同一用户的文本档与视觉档互不干扰 —— 这正是「一个 Key 包办所有能力」答不了的。"""
        c = self.client
        c.configure_user_adapter("u1", "sk-text", provider="deepseek", capability="text")
        c.configure_user_adapter("u1", "sk-vis", provider="dashscope",
                                 base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                                 model_name="qwen-vl-max", capability="vision")
        assert c.get_adapter("deepseek-chat", user_id="u1", capability="text").api_key == "sk-text"
        v = c.get_adapter("whatever", user_id="u1", capability="vision")
        assert v.api_key == "sk-vis" and v.model_name == "qwen-vl-max"

    def test_users_do_not_share_keys(self):
        c = self.client
        c.configure_user_adapter("alice", "sk-A", provider="deepseek", capability="text")
        c.configure_user_adapter("bob", "sk-B", provider="deepseek", capability="text")
        assert c.get_adapter("deepseek-chat", user_id="alice").api_key == "sk-A"
        assert c.get_adapter("deepseek-chat", user_id="bob").api_key == "sk-B"

    def test_global_fallback_never_returns_user_adapter(self):
        """**核心回归（bug 4）**：注册表里只有用户适配器时，全局回退必须报错，
        绝不能把某个用户的 Key 当成「全局默认」发出去。"""
        c = self.client
        c.configure_user_adapter("alice", "sk-A", provider="deepseek", capability="text")
        with pytest.raises(ValueError):
            c.get_adapter("unknown-provider", user_id="carol")

    def test_global_fallback_prefers_global_adapter(self):
        c = self.client
        c.configure_user_adapter("alice", "sk-A", provider="deepseek", capability="text")
        c.configure_adapter("deepseek", "sk-GLOBAL")
        assert c.get_adapter("unknown-provider", user_id="carol").api_key == "sk-GLOBAL"

    def test_remove_user_adapter_drops_legacy_key_too(self):
        c = self.client
        c.configure_user_adapter("u1", "sk", provider="deepseek", capability="text")
        assert "deepseek-chat_u1" in c._adapters          # 过渡旧键
        c.remove_user_adapter("u1")
        assert "deepseek-chat_u1" not in c._adapters
        assert not c.has_any_user_adapter("u1")

    def test_has_any_user_adapter_only_counts_own(self):
        c = self.client
        c.configure_user_adapter("u1", "sk", provider="deepseek", capability="vision")
        assert c.has_any_user_adapter("u1")
        assert not c.has_any_user_adapter("u2")

    def test_vision_without_config_raises(self):
        """没配视觉档要看图 → 明确报错，绝不静默回落文本档。"""
        from app.core.api_scheduler.client import VisionNotConfiguredError
        with pytest.raises(VisionNotConfiguredError):
            asyncio.run(self.client.analyze_image("x", "image/png", "describe", user_id="nobody"))


# ================================================================
# 4. 启动重注册 + 旧数据迁移（bug 1）
# ================================================================

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """把数据目录指到临时目录，避免碰真库。"""
    monkeypatch.setenv("YQ_DATA_DIR", str(tmp_path))
    for mod in [m for m in list(__import__("sys").modules) if m.startswith("app.")]:
        del __import__("sys").modules[mod]
    yield tmp_path
    for mod in [m for m in list(__import__("sys").modules) if m.startswith("app.")]:
        del __import__("sys").modules[mod]


class TestStartupReload:
    def test_reload_registers_and_skips_broken(self, temp_db):
        """**核心回归（bug 1）**：重启后从库里重建适配器；
        解不开的档跳过并点名，不能把整个启动带崩。"""
        async def go():
            from app.database import init_db, async_session
            from app.models import UserProviderConfig
            from app.core.crypto import encrypt_secret
            from app.core.provider_config import reload_user_adapters
            from app.core.api_scheduler import api_client

            await init_db()
            async with async_session() as db:
                db.add(UserProviderConfig(
                    user_id="u-ok", capability="text", provider="deepseek",
                    base_url="https://api.deepseek.com/v1", model="deepseek-chat",
                    secret_encrypted=encrypt_secret({"api_key": "sk-OK"}), options_json="{}"))
                db.add(UserProviderConfig(
                    user_id="u-bad", capability="text", provider="deepseek",
                    secret_encrypted="not-a-valid-token", options_json="{}"))
                await db.commit()

            n = await reload_user_adapters()
            assert n == 1
            assert api_client.get_adapter("deepseek-chat", user_id="u-ok").api_key == "sk-OK"
            assert not api_client.has_any_user_adapter("u-bad")
        asyncio.run(go())

    def test_legacy_columns_migrate_to_text_capability(self, temp_db):
        """旧的「单 Key 三元组」迁到 text 档（幂等）。"""
        async def go():
            from app.database import init_db, async_session
            from app.models import User, UserProviderConfig
            from app.core.crypto import encrypt_api_key
            from app.database import _migrate_legacy_user_api_keys
            from sqlalchemy import select

            await init_db()
            async with async_session() as db:
                db.add(User(id="u-legacy", name="旧用户", api_key_encrypted=encrypt_api_key("sk-OLD"),
                            api_base_url="https://api.moonshot.cn/v1", api_model="kimi-latest"))
                await db.commit()

            await _migrate_legacy_user_api_keys()
            await _migrate_legacy_user_api_keys()   # 幂等：不该写第二行
            async with async_session() as db:
                rows = (await db.execute(select(UserProviderConfig).where(
                    UserProviderConfig.user_id == "u-legacy"))).scalars().all()
                assert len(rows) == 1
                assert rows[0].capability == "text"
                assert rows[0].provider == "moonshot"      # 从 base_url 猜出来的
                assert rows[0].model == "kimi-latest"
        asyncio.run(go())

    def test_options_bad_json_does_not_crash(self, temp_db):
        from app.core.provider_config import load_options

        class Row:
            user_id, capability, options_json = "u", "tts", "{not json"
        assert load_options(Row()) == {}


# ================================================================
# 5. 预设表约束
# ================================================================

class TestPresets:
    def test_all_llm_base_urls_carry_version_segment(self):
        """OpenAICompatAdapter 拼的是 `{base_url}/chat/completions`，**不自补 /v1**。
        少一段版本就是 404 —— 所以预设里每条地址都必须自带。"""
        from app.core.provider_presets import PROVIDER_PRESETS
        for cap in ("text", "vision"):
            for p in PROVIDER_PRESETS[cap]:
                if p["provider"] == "custom":
                    continue
                assert p["base_url"].strip(), f"{cap}/{p['provider']} 缺 base_url"
                tail = p["base_url"].rstrip("/").rsplit("/", 1)[-1]
                assert tail.startswith("v") or "compatible-mode" in p["base_url"], \
                    f"{cap}/{p['provider']} 的地址不含版本段：{p['base_url']}"

    def test_every_capability_has_a_credential_free_or_custom_option(self):
        """每档都得有一条「不花钱也能用」或「自定义」的路，否则用户被锁死。"""
        from app.core.provider_presets import PROVIDER_PRESETS
        for cap, presets in PROVIDER_PRESETS.items():
            providers = {p["provider"] for p in presets}
            assert "custom" in providers or cap == "tts", f"{cap} 档没有自定义选项"
        assert any(not p["secret_fields"] for p in PROVIDER_PRESETS["tts"]), \
            "语音档必须有一条免凭据的路（edge 免费档）"

    def test_required_secret_fields_declared(self):
        from app.core.provider_presets import PROVIDER_PRESETS, find_preset
        volc = find_preset("tts", "volc")
        keys = {f["key"] for f in volc["secret_fields"] if f.get("required")}
        assert keys == {"app_id", "access_token"}
        assert find_preset("tts", "edge")["secret_fields"] == []

    def test_presets_cover_all_capabilities(self):
        from app.core.provider_presets import PROVIDER_PRESETS, CAPABILITIES
        assert set(PROVIDER_PRESETS) == set(CAPABILITIES)


# ================================================================
# 6. 按用户的 TTS 上下文
# ================================================================

class TestTTSContext:
    def test_user_config_overrides_global(self, temp_db):
        async def go():
            from app.database import init_db, async_session
            from app.models import UserProviderConfig
            from app.core.crypto import encrypt_secret
            from app.core.podcast_tts import resolve_tts_context

            await init_db()
            async with async_session() as db:
                db.add(UserProviderConfig(
                    user_id="u-volc", capability="tts", provider="volc",
                    secret_encrypted=encrypt_secret({"app_id": "A1", "access_token": "T1"}),
                    options_json='{"cluster": "volcano_mega", "voice_a": "myVA"}'))
                await db.commit()
                ctx = await resolve_tts_context(db, "u-volc")
            assert ctx.provider == "volc_mega"       # volc 归一到大模型音色集群
            assert ctx.volc_app_id == "A1"
            assert ctx.volc_access_token == "T1"
            assert ctx.voice_a == "myVA"
            assert ctx.volc_cluster == "volcano_mega"
        asyncio.run(go())

    def test_missing_credentials_fall_back_to_global(self, temp_db):
        """语音档配坏了不该让人听不了 —— 回落到免费 edge。"""
        async def go():
            from app.database import init_db, async_session
            from app.models import UserProviderConfig
            from app.core.podcast_tts import resolve_tts_context

            await init_db()
            async with async_session() as db:
                db.add(UserProviderConfig(user_id="u-bad", capability="tts", provider="volc",
                                          secret_encrypted="broken", options_json="{}"))
                await db.commit()
                ctx = await resolve_tts_context(db, "u-bad")
            assert ctx.provider == "edge"
        asyncio.run(go())

    def test_anonymous_uses_global(self, temp_db):
        async def go():
            from app.database import init_db, async_session
            from app.core.podcast_tts import resolve_tts_context
            await init_db()
            async with async_session() as db:
                ctx = await resolve_tts_context(db, None)
            assert ctx.provider in ("edge", "mock", "volc_mega", "volc_standard", "azure")
        asyncio.run(go())

    def test_volc_cluster_defaults(self):
        from app.core.podcast_tts import _volc_cluster_for, TTSContext
        assert _volc_cluster_for("volc_mega") == "volcano_mega"
        assert _volc_cluster_for("volc_standard") == "volcano_tts"
        # ctx 里的 cluster 覆盖默认
        assert _volc_cluster_for("volc_mega", TTSContext(provider="volc_mega",
                                                         volc_cluster="custom")) == "custom"
