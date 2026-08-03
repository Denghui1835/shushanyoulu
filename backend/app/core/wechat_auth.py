"""微信开放平台 OAuth（小程序/公众号登录）。

对接微信 jscode2session：用前端传回的 code 换取 openid。
需在 backend/.env 配置 WECHAT_APP_ID / WECHAT_APP_SECRET（见 config.py）。
当前为代码就绪状态：未配置时接口返回明确错误，不影响其他功能。
"""
import httpx

from app.config import settings


async def get_wechat_user_info(code: str) -> dict:
    """用 code 换取微信用户信息。小程序返回 {openid, unionid?, session_key}。

    若配置了 openid 额外查询用户昵称/头像（公众号网页授权）也可扩展。
    """
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise ValueError("未配置微信登录（backend/.env 需填 WECHAT_APP_ID / WECHAT_APP_SECRET）")
    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": settings.wechat_app_id,
        "secret": settings.wechat_app_secret,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        data = resp.json()
    if "errcode" in data and data.get("errcode") != 0:
        raise ValueError(f"微信登录失败：{data.get('errmsg', data.get('errcode'))}")
    openid = data.get("openid")
    if not openid:
        raise ValueError("微信未返回 openid")
    return data
