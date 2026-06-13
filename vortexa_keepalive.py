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
        # 1. 靶向定位你抓出来的全新 API 地址
        self.api_url = "https://api.vortexa.cloud/api/hosting/free/status"
        self.auth_token = auth_token.strip()
        self.tg_config = tg_config
        # 模拟真实 Edge/Chrome 混合指纹，完美穿透防御
        self.session = requests.Session(impersonate="chrome110")
        self.username = "云 API 托管账户"

    def update_github_secret(self, current_token):
        """持久化：如果后续需要更新或重写，利用 PAT 保持 Secret 覆盖能力"""
        gh_pat = os.environ.get("GH_PAT")
        repo = os.environ.get("GITHUB_REPOSITORY")
        secret_name = "VORTEXA_COOKIE"  # 变量名保持不变，防止你重新去改 Actions 变量名

        if not gh_pat or not repo or not HAS_NACL:
            return

        headers = {
            "Authorization": f"token {gh_pat}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Vortexa-KeepAlive-Bot"
        }

        try:
            pub_key_resp = self.session.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=headers)
            if pub_key_resp.status_code != 200: return
            
            pub_key_data = pub_key_resp.json()
            public_key = pub_key_data['key']
            key_id = pub_key_data['key_id']

            public_key_obj = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
            sealed_box = public.SealedBox(public_key_obj)
            encrypted = sealed_box.encrypt(current_token.encode("utf-8"))
            encrypted_value = base64.b64encode(encrypted).decode("utf-8")

            self.session.put(
                f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}",
                headers=headers,
                json={"encrypted_value": encrypted_value, "key_id": key_id}
            )
            logger.info("✅ GitHub Secret 凭证持久化同步成功！")
        except Exception as e:
            logger.error(f"❌ 自动更新 Secret 出错: {e}")

    def send_tg_notification(self, message):
        """TG 推送功能"""
        if not self.tg_config or not self.tg_config.get("bot_token") or not self.tg_config.get("chat_id"):
            return

        url = f"https://api.telegram.org/bot{self.tg_config['bot_token']}/sendMessage"
        formatted_message = (
            f"☁️ **Vortexa API 实例保活报告**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 **凭证标识**: `Bearer Token`\n"
            f"🕒 **维保时间**: `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{message}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 状态提示：已按照 2-3 天周期成功提交网络活跃流量"
        )

        payload = {"chat_id": self.tg_config["chat_id"], "text": formatted_message, "parse_mode": "Markdown"}
        try:
            self.session.post(url, json=payload, timeout=10)
        except Exception: pass

    def do_keepalive(self):
        """核心保活：直接往 API 接口轰炸状态请求，100%产生有登入特征的流量记录 (Traffic)"""
        # 组装跟你抓包一模一样的全量高级请求头
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "authorization": f"Bearer {self.auth_token}", # 👈 动态注入你的核心密钥
            "content-type": "application/json",
            "sec-ch-ua": '"Microsoft Edge";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "x-fingerprint": "a9076b31f4616d9beee9446fa4f2c22f", # 固化防爬虫设备指纹
            "Referer": "https://www.vortexa.cloud/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
        }

        try:
            # 向后端提交心跳流量，获取当前免费托管服务的状态列表
            resp = self.session.get(self.api_url, headers=headers, timeout=25)
            
            if resp.status_code == 200:
                logger.info("✅ 成功穿透 Cloudflare 并向云端 API 刷新了活跃记录！")
                # 尝试解析官方返回的实例状态
                try:
                    res_json = resp.json()
                    status_msg = f"✅ **保活成功**\n\n接口返回元数据片段:\n`{str(res_json)[:150]}...`"
                except Exception:
                    status_msg = "✅ **保活成功**\n\n接口响应 200 OK，活跃流量记录已成功刷新。"
                
                self.send_tg_notification(status_msg)
                # 触发持久化回写
                self.update_github_secret(self.auth_token)
                return True
            elif resp.status_code == 401:
                logger.error("❌ 接口返回 401 Unauthorized：你的 Bearer Token 已经完全失效或复制错了！")
                self.send_tg_notification("❌ **保活失败**\n\n接口提示 Token 认证未通过（401），请重新抓取替换。")
                return False
            else:
                logger.warning(f"⚠️ 接口请求异常，状态码: {resp.status_code}")
                self.send_tg_notification(f"⚠️ **保活异常**\n\n接口响应非预期状态码: `{resp.status_code}`")
                return False
        except Exception as e:
            logger.error(f"❌ 请求云端保活发生物理网络异常: {e}")
            return False

def main():
    # 兼容老配置，你不需要在 GitHub 里修改变量名，继续在这个变量里填 Token 即可
    env_tokens = os.environ.get("VORTEXA_COOKIE")
    if not env_tokens:
        logger.error("❌ 缺少核心凭证环境变量。")
        return

    tg_config = {
        "bot_token": os.environ.get("TG_BOT_TOKEN"),
        "chat_id": os.environ.get("TG_CHAT_ID")
    }

    # 依然完美兼容多账号：用 & 或换行符隔开多个 Token 字符串即可
    tokens = re.split(r'[&\n]', env_tokens)
    for token_str in tokens:
        if not token_str.strip(): continue
        try:
            # 如果不小心把整段 fetch 贴进去了，自动帮你把 Bearer Token 抠出来
            pure_token = token_str
            if "Bearer " in token_str:
                match = re.search(r'Bearer\s+([a-zA-Z0-9_\-\.]+)', token_str)
                if match: pure_token = match.group(1)
            
            bot = VortexaCloudKeepAlive(pure_token, tg_config)
            bot.do_keepalive()
        except Exception as e:
            logger.error(f"执行异常: {e}")

if __name__ == "__main__":
    main()
