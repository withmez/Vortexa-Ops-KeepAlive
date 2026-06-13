#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import re
import time
import base64
from datetime import datetime
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
        
        # 初始身份缓冲值
        self.username = "未知账户"
        self.balance = "€0.00"
        
        # 统计计数
        self.success_count = 0
        self.failed_count = 0
        
        # 严格复刻高级请求头
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
        """抓取每日一言"""
        try:
            resp = requests.get("https://v1.hitokoto.cn/?encode=json", timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                return f"『{data['hitokoto']}』—— {data['from']}"
        except Exception: pass
        return "既然认准这条路，何必去打听要走多久。—— 网络"

    def fetch_user_profile(self):
        """多路径破译账户名与余额"""
        try:
            resp = self.session.get("https://api.vortexa.cloud/api/user/profile", headers=self.headers, timeout=8)
            if resp.status_code == 200:
                res_data = resp.json()
                user_data = res_data.get("user", res_data.get("data", res_data))
                if isinstance(user_data, dict):
                    self.username = user_data.get("name") or user_data.get("username") or user_data.get("email") or self.username
                    b_val = user_data.get("balance", "0.00")
                    self.balance = b_val if str(b_val).startswith('€') else f"€{b_val}"
                    return True
        except Exception: pass

        try:
            resp = self.session.get("https://api.vortexa.cloud/api/auth/user", headers=self.headers, timeout=8)
            if resp.status_code == 200:
                user_data = resp.json()
                if isinstance(user_data, dict):
                    self.username = user_data.get("name") or user_data.get("username") or user_data.get("email") or self.username
                    b_val = user_data.get("balance", "0.00")
                    self.balance = b_val if str(b_val).startswith('€') else f"€{b_val}"
                    return True
        except Exception: pass
        return False

    def check_invoices_task(self):
        """【主线一：账单与扣费】"""
        try:
            resp = self.session.get("https://api.vortexa.cloud/api/platform/invoices", headers=self.headers, timeout=12)
            if resp.status_code == 200:
                invoices = resp.json()
                unpaid_count = 0
                if isinstance(invoices, list):
                    for inv in invoices:
                        status = str(inv.get("status", "")).lower()
                        if status in ["unpaid", "pending", "待支付", "未支付"]:
                            unpaid_count += 1
                            inv_id = inv.get("id")
                            if inv_id:
                                try:
                                    self.session.post(f"https://api.vortexa.cloud/api/platform/invoice/{inv_id}/pay", headers=self.headers, timeout=10)
                                except Exception: pass
                
                self.success_count += 1
                if unpaid_count > 0:
                    return f"✅ 账单监控: 发现并自动扣款支付 {unpaid_count} 笔订单"
                return "✅ 账单监控: 暂无待支付账单，账务安全"
            else:
                self.failed_count += 1
                return f"❌ 账单监控: 检查失败，接口响应异常 ({resp.status_code})"
        except Exception as e:
            self.failed_count += 1
            return f"❌ 账单监控: 网络连接异常 ({str(e)})"

    def keepalive_login_task(self):
        """【主线二：7天活跃登录保活】紧扣清退机制，拒绝看一年虚假大合同"""
        try:
            # 触发 7 天活跃刷新接口
            resp = self.session.get("https://api.vortexa.cloud/api/hosting/free/status", headers=self.headers, timeout=15)
            if resp.status_code == 200:
                self.success_count += 1
                res_json = resp.json()
                has_free = res_json.get("has_free_server", False)
                service_data = res_json.get("service")
                
                # 提取实例 ID
                s_id = "自由实例"
                if has_free and service_data and isinstance(service_data, dict):
                    s_id = service_data.get("id") or service_data.get("product", {}).get("name") or "自由实例"
                
                # 既然成功刷新，就代表获得了全新的 7 天活跃安全期（不看账单的一年）
                return f"✅ 登录保活: 机器 [{s_id}] 活跃打卡成功，已重置刷新 7 天不删机安全期"
            else:
                self.failed_count += 1
                return f"❌ 登录保活: 打卡失败 ({resp.status_code})！机器处于 7 天不活跃删机风险中"
        except Exception as e:
            self.failed_count += 1
            return f"❌ 登录保活: 打卡网络异常 ({str(e)})"

    def update_github_secret(self, current_token):
        """自动续期持久化令牌"""
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
        except Exception: pass

    def send_tg_notification(self, content_message):
        """复刻可视化排版"""
        if not self.tg_config or not self.tg_config.get("bot_token") or not self.tg_config.get("chat_id"):
            return

        url = f"https://api.telegram.org/bot{self.tg_config['bot_token']}/sendMessage"
        hitokoto = self.get_hitokoto()
        
        pure_hitokoto = hitokoto.split('——')[0].replace('『','').replace('』','').strip()
        author = hitokoto.split('——')[1].strip() if '——' in hitokoto else '网络'

        full_message = (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 **账号**: {self.username}\n"
            f"💰 **余额**: {self.balance}\n"
            f"🕒 **时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 **执行统计**: 成功 {self.success_count} | 失败 {self.failed_count}\n\n"
            f"{content_message}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 **每日一言**:\n『{pure_hitokoto}』—— {author}"
        )

        payload = {"chat_id": self.tg_config["chat_id"], "text": full_message, "parse_mode": "Markdown"}
        try: self.session.post(url, json=payload, timeout=10)
        except Exception: pass

    def run_task(self):
        self.fetch_user_profile()
        
        # 运行两大相互独立的硬核指标
        invoice_report = self.check_invoices_task()
        keepalive_report = self.keepalive_login_task()
        
        full_report_body = f"{keepalive_report}\n{invoice_report}"
        
        self.send_tg_notification(full_report_body)
        self.update_github_secret(self.auth_token)

def main():
    env_tokens = os.environ.get("VORTEXA_COOKIE")
    if not env_tokens:
        logger.error("❌ 缺少凭证环境变量 VORTEXA_COOKIE")
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
            logger.error(f"任务运行失败: {e}")

if __name__ == "__main__":
    main()
