#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import re
import time
import base64
from curl_cffi import requests

try:
    from nacl import encoding, public
    HAS_NACL = True
except ImportError:
    HAS_NACL = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class VortexaCloudKeepAlive:
    def __init__(self, auth_token, tg_config=None):
        self.auth_token = auth_token.strip()
        self.tg_config = tg_config
        self.session = requests.Session(impersonate="chrome110")
        
        self.username = "未知账户"
        self.balance = "未知"
        
        # 统一步调的新版云 API 标头配置
        self.headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "authorization": f"Bearer {self.auth_token}",
            "content-type": "application/json",
            "sec-ch-ua": '"Microsoft Edge";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "x-fingerprint": "a9076b31f4616d9beee9446fa4f2c22f",
            "Referer": "https://www.vortexa.cloud/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
        }

    def get_hitokoto(self):
        """核心补齐：从一言开放接口异步抓取每日金句"""
        try:
            resp = requests.get("https://v1.hitokoto.cn/?encode=json", timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                return f"『{data['hitokoto']}』 —— {data['from']}"
        except Exception:
            pass
        return "保持热爱，奔赴山海。"

    def fetch_user_profile(self):
        """请求个人资料接口补齐账号邮箱和余额"""
        try:
            resp = self.session.get("https://api.vortexa.cloud/api/user/profile", headers=self.headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                user_info = data.get("user", data)
                self.username = user_info.get("email", user_info.get("username", "云 API 用户"))
                self.balance = f"{user_info.get('balance', '0.00')} 元"
                return True
        except Exception: pass
            
        try:
            resp = self.session.get("https://api.vortexa.cloud/api/auth/user", headers=self.headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                self.username = data.get("email", "云 API 用户")
                self.balance = f"{data.get('balance', '0.00')} 元"
                return True
        except Exception: pass
        return False

    def do_instance_traffic(self):
        """请求实例控制台，真正产生官方考核的流量使用记录 (Traffic)"""
        action_logs = []
        try:
            list_resp = self.session.get("https://api.vortexa.cloud/api/hosting/servers", headers=self.headers, timeout=15)
            if list_resp.status_code == 200:
                servers = list_resp.json().get("servers", []) or list_resp.json()
                if isinstance(servers, list) and len(servers) > 0:
                    for server in servers:
                        s_id = server.get("id")
                        s_name = server.get("name", "未命名实例")
                        if not s_id: continue
                        
                        ping_url = f"https://api.vortexa.cloud/api/hosting/server/{s_id}/status"
                        ping_resp = self.session.get(ping_url, headers=self.headers, timeout=15)
                        
                        if ping_resp.status_code == 200:
                            action_logs.append(f"🖥️ **实例 {s_name} ({s_id})**:\n   └ 活跃流量产生成功")
                        else:
                            action_logs.append(f"🖥️ **实例 {s_name} ({s_id})**:\n   └ 流量心跳异常 ({ping_resp.status_code})")
                else:
                    action_logs.append("⚠️ **保活提示**: 账户内未检测到任何可运行的服务器实例")
            else:
                self.session.get("https://api.vortexa.cloud/api/hosting/free/status", headers=self.headers, timeout=15)
                action_logs.append("✅ **免费通道打卡**: 成功提交全局活跃心跳流量")
        except Exception as e:
            action_logs.append(f"❌ **流量交互失败**: `{str(e)}`")
        
        return "\n".join(action_logs)

    def update_github_secret(self, current_token):
        """持久化：保持 Secret 覆盖能力，免去手动更新麻烦"""
        gh_pat = os.environ.get("GH_PAT")
        repo = os.environ.get("GITHUB_REPOSITORY")
        secret_name = "VORTEXA_COOKIE"

        if not gh_pat or not repo or not HAS_NACL: return

        headers = {
            "Authorization": f"token {gh_pat}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Vortexa-KeepAlive-Bot"
        }
        try:
            pub_key_resp = self.session.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=headers)
            if pub_key_resp.status_code != 200: return
            pub_key_data = pub_key_resp.json()
            
            public_key_obj = public.PublicKey(pub_key_data['key'].encode("utf-8"), encoding.Base64Encoder())
            sealed_box = public.SealedBox(public_key_obj)
            encrypted = sealed_box.encrypt(current_token.encode("utf-8"))
            encrypted_value = base64.b64encode(encrypted).decode("utf-8")

            self.session.put(
                f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}",
                headers=headers,
                json={"encrypted_value": encrypted_value, "key_id": pub_key_data['key_id']}
            )
            logger.info("✅ GitHub Secret 凭证自动同步成功。")
        except Exception as e:
            logger.error(f"❌ 自动更新 Secret 出错: {e}")

    def send_tg_notification(self, message):
        """补回「每日一言」并重组的高级排版推送"""
        if not self.tg_config or not self.tg_config.get("bot_token") or not self.tg_config.get("chat_id"):
            return

        url = f"https://api.telegram.org/bot{self.tg_config['bot_token']}/sendMessage"
        
        # 获取最新的每日一言
        hitokoto = self.get_hitokoto()
        
        formatted_message = (
            f"☁️ **Vortexa API 实例双重保活报告**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 **账户邮箱**: `{self.username}`\n"
            f"💰 **账户余额**: `{self.balance}`\n"
            f"🕒 **维保时间**: `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{message}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 **每日一言**:\n_{hitokoto}_"
        )

        payload = {"chat_id": self.tg_config["chat_id"], "text": formatted_message, "parse_mode": "Markdown"}
        try: self.session.post(url, json=payload, timeout=10)
        except Exception: pass

    def run_task(self):
        self.fetch_user_profile()
        report_msg = self.do_instance_traffic()
        self.send_tg_notification(report_msg)
        self.update_github_secret(self.auth_token)

def main():
    env_tokens = os.environ.get("VORTEXA_COOKIE")
    if not env_tokens:
        logger.error("❌ 缺少核心凭证环境变量。")
        return

    tg_config = {
        "bot_token": os.environ.get("TG_BOT_TOKEN"),
        "chat_id": os.environ.get("TG_CHAT_ID")
    }

    tokens = re.split(r'[&\n]', env_tokens)
    for token_str in tokens:
        if not token_str.strip(): continue
        try:
            pure_token = token_str
            if "Bearer " in token_str:
                match = re.search(r'Bearer\s+([a-zA-Z0-9_\-\.]+)', token_str)
                if match: pure_token = match.group(1)
            
            bot = VortexaCloudKeepAlive(pure_token, tg_config)
            bot.run_task()
        except Exception as e:
            logger.error(f"执行异常: {e}")

if __name__ == "__main__":
    main()
