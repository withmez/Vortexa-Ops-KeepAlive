#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import re
import time
import base64
from bs4 import BeautifulSoup
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

class VortexaKeepAlive:
    def __init__(self, cookie_str, tg_config=None):
        self.base_url = "https://dash.vortexa.com"
        self.cookie_str = cookie_str
        self.tg_config = tg_config
        # 模拟真实浏览器指纹，绕过底层 Cloudflare 校验
        self.session = requests.Session(impersonate="chrome110")
        self.username = "Unknown"
        self.balance = "未知"
        self.csrf_token = ""
        self.parse_and_set_cookies()

    def parse_and_set_cookies(self):
        """解析并注入 Cookie"""
        if not self.cookie_str:
            return
        cookies = {}
        for item in self.cookie_str.split(';'):
            if '=' in item:
                parts = item.strip().split('=', 1)
                if len(parts) == 2:
                    cookies[parts[0]] = parts[1]
        self.session.cookies.update(cookies)

    def get_cookie_string(self):
        """生成当前最新 Cookie 字符串"""
        return "; ".join([f"{k}={v}" for k, v in self.session.cookies.items()])

    def update_github_secret(self, new_cookie):
        """持久化：配合 GitHub PAT 自动回写覆盖 Cookie，防止频繁手动更新"""
        gh_pat = os.environ.get("GH_PAT")
        repo = os.environ.get("GITHUB_REPOSITORY")
        secret_name = "VORTEXA_COOKIE"

        if not gh_pat or not repo:
            logger.warning("⚠️ 未配置 GH_PAT 或不在 Actions 环境中，跳过 Cookie 自动回写")
            return

        if not HAS_NACL:
            logger.error("❌ 未安装 pynacl 库，无法加密并更新 Secret")
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
            encrypted = sealed_box.encrypt(new_cookie.encode("utf-8"))
            encrypted_value = base64.b64encode(encrypted).decode("utf-8")

            self.session.put(
                f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}",
                headers=headers,
                json={"encrypted_value": encrypted_value, "key_id": key_id}
            )
            logger.info(f"✅ GitHub Secret [{secret_name}] 自动自愈回写成功！")
        except Exception as e:
            logger.error(f"❌ 自动更新 Secret 出错: {e}")

    def get_hitokoto(self):
        """TG 推送：每日一言"""
        try:
            resp = requests.get("https://v1.hitokoto.cn/?encode=json", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return f"『{data['hitokoto']}』—— {data['from']}"
        except Exception: pass
        return "保持热爱，奔赴山海。"

    def send_tg_notification(self, message):
        """TG 推送功能"""
        if not self.tg_config or not self.tg_config.get("bot_token") or not self.tg_config.get("chat_id"):
            return

        url = f"https://api.telegram.org/bot{self.tg_config['bot_token']}/sendMessage"
        hitokoto = self.get_hitokoto()
        formatted_message = (
            f"☁️ **Vortexa 7天双重活跃保活报告**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 **账户**: `{self.username}`\n"
            f"💰 **余额**: `{self.balance}`\n"
            f"🕒 **时间**: `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{message}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 **每日一言**:\n_{hitokoto}_"
        )

        payload = {"chat_id": self.tg_config["chat_id"], "text": formatted_message, "parse_mode": "Markdown"}
        try:
            self.session.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"TG 推送失败: {e}")

    def get_csrf_token(self, html):
        """解析页面 Token"""
        if not html: return None
        soup = BeautifulSoup(html, 'html.parser')
        token_meta = soup.find('meta', attrs={'name': 'csrf-token'})
        if token_meta: self.csrf_token = token_meta.get('content')
        return self.csrf_token

    def check_login(self):
        """自动续期功能：执行登入记录保活"""
        try:
            resp = self.session.get(f"{self.base_url}/dashboard", timeout=20, allow_redirects=True)
            if "/login" in resp.url: return False
                
            if resp.status_code == 200:
                self.get_csrf_token(html=resp.text)
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # 提取用户名
                email_tag = soup.select_one('p.font-light.text-gray-500') or soup.find('p', string=re.compile(r'.+@.+\..+'))
                if email_tag and "[email" not in email_tag.get_text():
                    self.username = email_tag.get_text().strip()
                
                # 提取账户余额
                balance_link = soup.select_one('a[href*="/balance"]')
                if balance_link:
                    balance_tag = balance_link.find(['dt', 'h4', 'div'], class_=re.compile(r'font-extrabold|text-3xl'))
                    if balance_tag: self.balance = balance_tag.get_text().strip()
                
                logger.info(f"✅ 成功刷新登入记录！账户: {self.username} | 余额: {self.balance}")
                return True
        except Exception as e:
            logger.error(f"校验登入活跃失败: {e}")
        return False

    def get_service_ids(self):
        """提取服务器实例 ID"""
        try:
            resp = self.session.get(f"{self.base_url}/dashboard", timeout=20)
            return list(set(re.findall(r'service/(\d+)/manage', resp.text)))
        except Exception as e:
            logger.error(f"提取实例失败: {e}")
            return []

    def generate_traffic_and_pay(self, service_id):
        """核心保活：产生实际流量记录 (Traffic) 并自动扣费兜底"""
        manage_url = f"{self.base_url}/service/{service_id}/manage"
        try:
            # 1. 访问管理页，获取控制台元数据，模拟真实的控制台流量握手
            resp = self.session.get(manage_url, timeout=20)
            token = self.get_csrf_token(html=resp.text)
            
            traffic_status = "成功 (已触发控制台网络流量握手)"

            # 2. 自动扣费：检测到未支付订单时自动用账户余额支付
            invoice_list_url = f"{self.base_url}/service/{service_id}/invoices?where=unpaid"
            inv_resp = self.session.get(invoice_list_url, timeout=20)
            inv_soup = BeautifulSoup(inv_resp.text, 'html.parser')
            invoice_links = [a['href'] for a in inv_soup.find_all('a', href=True) if '/invoice/' in a['href'] and 'download' not in a['href']]
            
            pay_status = "无需处理"
            if invoice_links:
                pay_count = 0
                for inv_link in list(set(invoice_links)):
                    if not inv_link.startswith('http'): inv_link = self.base_url + inv_link
                    item_resp = self.session.get(inv_link, timeout=20)
                    item_soup = BeautifulSoup(item_resp.text, 'html.parser')
                    
                    pay_form = None
                    for form in item_soup.find_all('form'):
                        if 'balance/add' in form.get('action', ''): continue
                        pay_form = form
                        break
                    
                    if pay_form:
                        action = pay_form.get('action', '')
                        if not action.startswith('http'): action = self.base_url + action
                        payload = {inp.get('name'): inp.get('value', '') for inp in pay_form.find_all('input') if inp.get('name')}
                        if token: payload['_token'] = token
                        
                        pay_res = self.session.post(action, data=payload, headers={"Referer": inv_link}, timeout=20)
                        if "成功" in pay_res.text or "Success" in pay_res.text or pay_res.status_code == 200:
                            pay_count += 1
                if pay_count > 0: pay_status = f"✅ 自动余额扣费成功 ({pay_count}笔)"

            return True, traffic_status, pay_status
        except Exception as e:
            return False, f"流量保活异常: {e}", "处理失败"

    def run_task(self):
        if not self.check_login():
            logger.error("❌ 任务终止：VORTEXA_COOKIE 完全失效。")
            self.send_tg_notification("❌ 账户认证失效！请手动重新在浏览器里抓取 Cookie 并覆盖 GitHub Secrets。")
            return

        service_ids = self.get_service_ids()
        if not service_ids:
            logger.warning("账户中无活跃实例。")
            return

        results = []
        for s_id in service_ids:
            _, t_msg, p_msg = self.generate_traffic_and_pay(s_id)
            results.append(f"🖥️ **实例 ID: {s_id}**\n   ├ 流量记录: `{t_msg}`\n   └ 余额扣费: `{p_msg}`")

        # 发送通知
        self.send_tg_notification("\n".join(results))

        # 持久化：更新 GitHub 里的 Cookie
        new_cookie_str = self.get_cookie_string()
        if "vortexa_session" in new_cookie_str and new_cookie_str != self.cookie_str:
            self.update_github_secret(new_cookie_str)

def main():
    env_cookies = os.environ.get("VORTEXA_COOKIE")
    if not env_cookies:
        logger.error("❌ 缺少 VORTEXA_COOKIE 环境变量。")
        return

    tg_config = {
        "bot_token": os.environ.get("TG_BOT_TOKEN"),
        "chat_id": os.environ.get("TG_CHAT_ID")
    }

    # 支持多账号：用 & 或换行符隔开
    account_cookies = re.split(r'[&\n]', env_cookies)
    for cookie_str in account_cookies:
        if not cookie_str.strip(): continue
        try:
            bot = VortexaKeepAlive(cookie_str.strip(), tg_config)
            bot.run_task()
        except Exception as e:
            logger.error(f"执行异常: {e}")

if __name__ == "__main__":
    main()
