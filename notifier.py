"""
实时通知模块 - 发现可用 Key 时立即推送通知

支持:
- 声音提醒
- 文件记录
- QQ 邮箱推送
- PushPlus 推送
- Telegram Bot 推送
- 钉钉机器人推送
"""

import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import aiohttp


class Notifier:
    """通知器"""

    def __init__(
        self,
        output_file: str = None,
        qq_email: str = "",
        qq_smtp_password: str = "",
        pushplus_token: str = "",
        telegram_token: str = "",      # Telegram Bot Token
        telegram_chat_id: str = "",    # Telegram Chat ID
        dingtalk_webhook: str = "",    # 钉钉机器人 Webhook
        wxpusher_token: str = "",      # WxPusher AppToken
        wxpusher_uid: str = "",        # WxPusher UID
    ):
        self.output_file = output_file or os.path.expanduser("~/Desktop/found_keys.txt")
        self.qq_email = qq_email
        self.qq_smtp_password = qq_smtp_password
        self.pushplus_token = pushplus_token
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.dingtalk_webhook = dingtalk_webhook
        self.wxpusher_token = wxpusher_token
        self.wxpusher_uid = wxpusher_uid

    def notify_sound(self):
        """播放提示音"""
        try:
            import winsound
            winsound.Beep(1000, 300)
            winsound.Beep(1500, 300)
            winsound.Beep(2000, 300)
        except:
            pass

    def notify_file(self, platform: str, api_key: str, base_url: str):
        """写入文件"""
        try:
            with open(self.output_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发现可用 Key!\n")
                f.write(f"平台: {platform}\n")
                f.write(f"Key: {api_key}\n")
                f.write(f"URL: {base_url}\n")
        except:
            pass

    def notify_qq_email(self, platform: str, api_key: str, base_url: str):
        """QQ 邮箱推送"""
        if not self.qq_email or not self.qq_smtp_password:
            return False

        try:
            subject = f"🔑 发现可用 {platform.upper()} Key!"
            content = f"""
发现可用 API Key!

平台: {platform}
Key: {api_key}
URL: {base_url}
时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
GitHub Secret Scanner
"""
            msg = MIMEText(content, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = self.qq_email
            msg["To"] = self.qq_email

            # QQ 邮箱 SMTP
            server = smtplib.SMTP_SSL("smtp.qq.com", 465)
            server.login(self.qq_email, self.qq_smtp_password)
            server.sendmail(self.qq_email, [self.qq_email], msg.as_string())
            server.quit()
            return True
        except Exception as e:
            print(f"QQ邮箱发送失败: {e}")
            return False

    async def notify_pushplus(self, platform: str, api_key: str, base_url: str):
        """PushPlus 推送 (支持 QQ/微信)"""
        if not self.pushplus_token:
            return False

        try:
            url = "http://www.pushplus.plus/send"
            data = {
                "token": self.pushplus_token,
                "title": f"发现可用 {platform.upper()} Key!",
                "content": f"平台: {platform}<br>Key: {api_key}<br>URL: {base_url}",
                "template": "html"
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=10) as resp:
                    return resp.status == 200
        except:
            return False

    async def notify_telegram(self, platform: str, api_key: str, base_url: str):
        """Telegram Bot 推送 (完全免费无限制)"""
        if not self.telegram_token or not self.telegram_chat_id:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            text = f"🔑 发现可用 {platform.upper()} Key!\n\n平台: {platform}\nKey: {api_key}\nURL: {base_url}"
            data = {"chat_id": self.telegram_chat_id, "text": text}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=10) as resp:
                    return resp.status == 200
        except:
            return False

    async def notify_dingtalk(self, platform: str, api_key: str, base_url: str):
        """钉钉机器人推送 (完全免费无限制)"""
        if not self.dingtalk_webhook:
            return False

        try:
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": f"发现可用 {platform.upper()} Key!",
                    "text": f"### 🔑 发现可用 Key!\n- 平台: {platform}\n- Key: {api_key}\n- URL: {base_url}"
                }
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.dingtalk_webhook, json=data, timeout=10) as resp:
                    return resp.status == 200
        except:
            return False

    async def notify_wxpusher(self, platform: str, api_key: str, base_url: str):
        """WxPusher 微信推送 (完全免费无限制)"""
        if not self.wxpusher_token or not self.wxpusher_uid:
            return False

        try:
            url = "https://wxpusher.zjiecode.com/api/send/message"
            data = {
                "appToken": self.wxpusher_token,
                "content": f"🔑 发现可用 {platform.upper()} Key!\n\n平台: {platform}\nKey: {api_key}\nURL: {base_url}",
                "contentType": 1,  # 1=文本
                "uids": [self.wxpusher_uid]
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=10) as resp:
                    return resp.status == 200
        except:
            return False

    def notify(self, platform: str, api_key: str, base_url: str = ""):
        """发送所有同步通知"""
        self.notify_sound()
        self.notify_file(platform, api_key, base_url)
        self.notify_qq_email(platform, api_key, base_url)

    async def notify_async(self, platform: str, api_key: str, base_url: str = ""):
        """发送所有通知（包括异步）"""
        self.notify_sound()
        self.notify_file(platform, api_key, base_url)
        self.notify_qq_email(platform, api_key, base_url)
        await self.notify_pushplus(platform, api_key, base_url)
        await self.notify_telegram(platform, api_key, base_url)
        await self.notify_dingtalk(platform, api_key, base_url)
        await self.notify_wxpusher(platform, api_key, base_url)


# 全局通知器 - 需要配置后使用
notifier = Notifier()
