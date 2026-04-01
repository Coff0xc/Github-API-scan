#!/usr/bin/env python3
"""
实时监控推送 - 发现可用 Key 时立即通知
支持所有 AI 平台 - 使用实际 API 调用验证
"""

import asyncio
import aiohttp
import winsound
from datetime import datetime
from database import Database, KeyStatus
from notifier import Notifier

OUTPUT_FILE = r"C:\Users\12299\Desktop\found_keys.txt"

# 配置通知器 - 请在此处填入你的配置
notifier = Notifier(
    output_file=OUTPUT_FILE,
    # wxpusher_token="YOUR_WXPUSHER_TOKEN",  # 从 wxpusher.zjiecode.com 获取
    # wxpusher_uid="YOUR_WXPUSHER_UID",      # 从 wxpusher.zjiecode.com 获取
)


async def test_openai(key: str) -> tuple:
    """测试 OpenAI - 实际调用"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "1"}], "max_tokens": 1},
                timeout=15
            ) as r:
                return (r.status == 200, r.status)
    except Exception as e:
        return (False, str(e)[:15])


async def test_gemini(key: str) -> tuple:
    """测试 Gemini - 实际调用"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}",
                json={"contents": [{"parts": [{"text": "1"}]}]},
                timeout=15
            ) as r:
                return (r.status == 200, r.status)
    except Exception as e:
        return (False, str(e)[:15])


async def test_anthropic(key: str) -> tuple:
    """测试 Anthropic - 实际调用"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-3-haiku-20240307", "max_tokens": 1, "messages": [{"role": "user", "content": "1"}]},
                timeout=15
            ) as r:
                return (r.status == 200, r.status)
    except Exception as e:
        return (False, str(e)[:15])


async def test_groq(key: str) -> tuple:
    """测试 Groq - 实际调用"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "llama3-8b-8192", "messages": [{"role": "user", "content": "1"}], "max_tokens": 1},
                timeout=15
            ) as r:
                return (r.status == 200, r.status)
    except Exception as e:
        return (False, str(e)[:15])


async def test_deepseek(key: str) -> tuple:
    """测试 DeepSeek - 实际调用"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "1"}], "max_tokens": 1},
                timeout=15
            ) as r:
                return (r.status == 200, r.status)
    except Exception as e:
        return (False, str(e)[:15])


async def test_mistral(key: str) -> tuple:
    """测试 Mistral"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "mistral-tiny", "messages": [{"role": "user", "content": "1"}], "max_tokens": 1},
                timeout=15
            ) as r:
                return (r.status == 200, r.status)
    except Exception as e:
        return (False, str(e)[:15])


async def test_cohere(key: str) -> tuple:
    """测试 Cohere"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.cohere.ai/v1/chat",
                headers={"Authorization": f"Bearer {key}"},
                json={"message": "1"},
                timeout=15
            ) as r:
                return (r.status == 200, r.status)
    except Exception as e:
        return (False, str(e)[:15])


async def test_together(key: str) -> tuple:
    """测试 Together"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.together.xyz/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "meta-llama/Llama-3-8b-chat-hf", "messages": [{"role": "user", "content": "1"}], "max_tokens": 1},
                timeout=15
            ) as r:
                return (r.status == 200, r.status)
    except Exception as e:
        return (False, str(e)[:15])


async def test_huggingface(key: str) -> tuple:
    """测试 HuggingFace"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://huggingface.co/api/whoami-v2",
                headers={"Authorization": f"Bearer {key}"},
                timeout=15
            ) as r:
                return (r.status == 200, r.status)
    except Exception as e:
        return (False, str(e)[:15])


TESTERS = {
    "openai": test_openai,
    "gemini": test_gemini,
    "anthropic": test_anthropic,
    "groq": test_groq,
    "deepseek": test_deepseek,
    "mistral": test_mistral,
    "cohere": test_cohere,
    "together": test_together,
    "huggingface": test_huggingface,
}


async def notify_found(platform: str, api_key: str, base_url: str):
    """发送通知"""
    try:
        winsound.Beep(1000, 300)
        winsound.Beep(1500, 300)
        winsound.Beep(2000, 300)
    except:
        pass

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] FOUND!\n")
        f.write(f"Platform: {platform}\nKey: {api_key}\nURL: {base_url}\n")
        f.write(f"{'='*60}\n")

    await notifier.notify_wxpusher(platform, api_key, base_url)
    print(f"\n*** FOUND: {platform} {api_key[:30]}... ***\n", flush=True)


async def monitor():
    """主监控循环"""
    tested_keys = set()

    print("Monitor started - Real API call validation", flush=True)
    print(f"Output: {OUTPUT_FILE}", flush=True)
    print(f"Supported: {', '.join(TESTERS.keys())}\n", flush=True)

    while True:
        try:
            db = Database("leaked_keys.db")
            valid_keys = db.get_keys_by_status(KeyStatus.VALID)

            for key in valid_keys:
                if key.api_key in tested_keys:
                    continue

                tested_keys.add(key.api_key)
                platform = key.platform

                # relay 类型尝试多个平台
                if platform == "relay":
                    for p in ["openai", "anthropic", "groq"]:
                        ok, msg = await TESTERS[p](key.api_key)
                        if ok:
                            print(f"[OK] relay/{p}: {key.api_key[:25]}...", flush=True)
                            await notify_found(f"relay/{p}", key.api_key, key.base_url)
                            break
                    else:
                        print(f"[X] relay: {key.api_key[:25]}...", flush=True)
                elif platform in TESTERS:
                    ok, msg = await TESTERS[platform](key.api_key)
                    status = "[OK]" if ok else f"[{msg}]"
                    print(f"{status} {platform}: {key.api_key[:25]}...", flush=True)
                    if ok:
                        await notify_found(platform, key.api_key, key.base_url)

            await asyncio.sleep(10)

        except KeyboardInterrupt:
            print("\nStopped")
            break
        except Exception as e:
            print(f"Error: {e}", flush=True)
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(monitor())
