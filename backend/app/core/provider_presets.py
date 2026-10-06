"""服务商预设表 —— 单一事实来源。

为什么放后端而不是前端常量：① 模型发现（拉 /models）必须服务端做，否则要把
用户的 Key 从浏览器直连第三方，还要跟 CORS 打架；② 前端只是渲染这张表；
③ 放这里能写单测校验，避免前后端两份表慢慢漂移。

**关键约束**：`OpenAICompatAdapter` 拼的是 `{base_url}/chat/completions`
（见 adapters/openai.py），**不会自动补 `/v1`**。所以下面每一条 base_url
都必须自带版本段（`/v1`、`/compatible-mode/v1`、`/api/paas/v4` 等），
少写一段就是 404。

各家模型 ID 变动频繁，预设里的 models **只是候选**，前端一律允许手填，
所以 ID 漂移不会把功能卡死。
"""

# 能力 → 该能力下可选的服务商列表
PROVIDER_PRESETS: dict[str, list[dict]] = {
    "text": [
        {
            "provider": "deepseek",
            "label": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "models": ["deepseek-chat", "deepseek-reasoner"],
            "supports_model_list": True,
            "secret_fields": [
                {"key": "api_key", "label": "API Key", "required": True,
                 "placeholder": "sk-..."},
            ],
            "option_fields": [],
            "note": "只有文本模型，没有语音能力。语音请单独配置下面的「语音」档。",
        },
        {
            "provider": "dashscope",
            "label": "阿里云百炼（通义千问）",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "models": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
            "supports_model_list": True,
            "secret_fields": [
                {"key": "api_key", "label": "API Key", "required": True,
                 "placeholder": "sk-..."},
            ],
            "option_fields": [],
        },
        {
            "provider": "moonshot",
            "label": "月之暗面 Kimi",
            "base_url": "https://api.moonshot.cn/v1",
            "models": ["moonshot-v1-8k", "moonshot-v1-32k", "kimi-latest"],
            "supports_model_list": True,
            "secret_fields": [
                {"key": "api_key", "label": "API Key", "required": True,
                 "placeholder": "sk-..."},
            ],
            "option_fields": [],
        },
        {
            "provider": "zhipu",
            "label": "智谱 GLM",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "models": ["glm-4-plus", "glm-4-air", "glm-4-flash"],
            "supports_model_list": False,
            "secret_fields": [
                {"key": "api_key", "label": "API Key", "required": True,
                 "placeholder": "..."},
            ],
            "option_fields": [],
        },
        {
            "provider": "openai",
            "label": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4o-mini"],
            "supports_model_list": True,
            "secret_fields": [
                {"key": "api_key", "label": "API Key", "required": True,
                 "placeholder": "sk-..."},
            ],
            "option_fields": [],
        },
        {
            "provider": "custom",
            "label": "其他（OpenAI 兼容接口）",
            "base_url": "",
            "models": [],
            "supports_model_list": True,
            "secret_fields": [
                {"key": "api_key", "label": "API Key", "required": True,
                 "placeholder": ""},
            ],
            "option_fields": [],
            "note": "地址要写全，含版本段，例如 https://example.com/v1 —— "
                    "系统会在它后面直接拼 /chat/completions。",
        },
    ],
    "vision": [
        {
            "provider": "dashscope",
            "label": "阿里云百炼（通义千问 VL）",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "models": ["qwen-vl-max", "qwen-vl-plus", "qwen2.5-vl-72b-instruct"],
            "supports_model_list": True,
            "secret_fields": [
                {"key": "api_key", "label": "API Key", "required": True,
                 "placeholder": "sk-..."},
            ],
            "option_fields": [],
        },
        {
            "provider": "zhipu",
            "label": "智谱 GLM-4V",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "models": ["glm-4v-plus", "glm-4v"],
            "supports_model_list": False,
            "secret_fields": [
                {"key": "api_key", "label": "API Key", "required": True,
                 "placeholder": "..."},
            ],
            "option_fields": [],
        },
        {
            "provider": "openai",
            "label": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4o-mini"],
            "supports_model_list": True,
            "secret_fields": [
                {"key": "api_key", "label": "API Key", "required": True,
                 "placeholder": "sk-..."},
            ],
            "option_fields": [],
        },
        {
            "provider": "custom",
            "label": "其他（OpenAI 兼容多模态接口）",
            "base_url": "",
            "models": [],
            "supports_model_list": True,
            "secret_fields": [
                {"key": "api_key", "label": "API Key", "required": True,
                 "placeholder": ""},
            ],
            "option_fields": [],
        },
    ],
    "tts": [
        {
            "provider": "edge",
            "label": "edge-tts（免费，无需 Key）",
            "base_url": "",
            "models": [],
            "supports_model_list": False,
            "secret_fields": [],
            "option_fields": [
                {"key": "voice_a", "label": "主讲音色", "type": "text",
                 "default": "zh-CN-XiaoxiaoNeural"},
                {"key": "voice_b", "label": "对话音色", "type": "text",
                 "default": "zh-CN-YunxiNeural"},
            ],
            "note": "微软 edge 的免费合成通道，不需要任何凭据，开箱即用。",
        },
        {
            "provider": "volc",
            "label": "火山引擎豆包语音",
            "base_url": "",
            "models": [],
            "supports_model_list": False,
            "secret_fields": [
                {"key": "app_id", "label": "App ID", "required": True,
                 "placeholder": "数字 App ID"},
                {"key": "access_token", "label": "Access Token", "required": True,
                 "placeholder": ""},
            ],
            "option_fields": [
                {"key": "cluster", "label": "集群", "type": "text",
                 "default": "volcano_tts"},
                {"key": "voice_a", "label": "主讲音色", "type": "text",
                 "default": "zh_female_shuangkuaisisi_moon_bigtts"},
                {"key": "voice_b", "label": "对话音色", "type": "text",
                 "default": "zh_male_wennuanahu_moon_bigtts"},
            ],
            "note": "音质好、可商用，但按量计费。",
        },
        {
            "provider": "azure",
            "label": "Azure 语音服务",
            "base_url": "",
            "models": [],
            "supports_model_list": False,
            "secret_fields": [
                {"key": "api_key", "label": "订阅密钥", "required": True,
                 "placeholder": ""},
            ],
            "option_fields": [
                {"key": "region", "label": "区域", "type": "text",
                 "default": "eastasia"},
                {"key": "voice_a", "label": "主讲音色", "type": "text",
                 "default": "zh-CN-XiaoxiaoNeural"},
                {"key": "voice_b", "label": "对话音色", "type": "text",
                 "default": "zh-CN-YunxiNeural"},
            ],
        },
    ],
}

CAPABILITIES = ("text", "vision", "tts")

# 不带 Key 也能跑的服务商（「未配置」不等于「不可用」）
CREDENTIAL_FREE_PROVIDERS = {"edge"}


def presets_for(capability: str) -> list[dict]:
    return PROVIDER_PRESETS.get(capability, [])


def find_preset(capability: str, provider: str) -> dict | None:
    for p in PROVIDER_PRESETS.get(capability, []):
        if p["provider"] == provider:
            return p
    return None


def default_base_url(provider: str) -> str:
    """给 client.py 建适配器用：按服务商取默认地址（跨档取第一条命中的）。"""
    for presets in PROVIDER_PRESETS.values():
        for p in presets:
            if p["provider"] == provider and p.get("base_url"):
                return p["base_url"]
    return ""


def default_model(provider: str, capability: str = "text") -> str:
    p = find_preset(capability, provider)
    if p and p.get("models"):
        return p["models"][0]
    for presets in PROVIDER_PRESETS.values():
        for item in presets:
            if item["provider"] == provider and item.get("models"):
                return item["models"][0]
    return provider
