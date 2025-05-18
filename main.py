import os
import json
import tomllib
import requests
from io import BytesIO
from typing import List, Dict, Any
import asyncio
import threading
import base64 # For QR code in HTML
import time

from loguru import logger
# 延迟导入playwright，避免启动时加载
# from playwright.async_api import async_playwright

from utils.plugin_base import PluginBase
from utils.decorators import on_text_message
from WechatAPI.Client import WechatAPIClient

class AIReport(PluginBase):
    description = "获取AI相关资讯，支持文字版和图片版"
    author = "老金"
    version = "3.2"

    def __init__(self):
        super().__init__()
        self.enable = False
        self.api_key = None
        self.text_news_count = 10
        self.image_news_count = 6
        self.api_endpoint = "https://apis.tianapi.com/ai/index"
        self.handler_priority = 20
        
        # 将这些变量设为None但不初始化，实现真正的懒加载
        self.browser = None
        self.playwright_instance = None
        self.is_initializing = False
        self.playwright_lock = threading.Lock()
        self.initialization_thread = None
        
        # 设置模板路径
        self.template_path = os.path.join(os.path.dirname(__file__), "news_template.html")
        
        # 只加载基本配置
        logger.info(f"[{self.__class__.__name__}] 初始化中 - 仅加载基本配置")
        self._load_config()
        logger.info(f"[{self.__class__.__name__}] 初始化完成 - 懒加载模式，Playwright将在首次需要时才初始化")

    def _load_config(self):
        """加载配置文件"""
        config_path = os.path.join(os.path.dirname(__file__), "config.toml")
        example_config_path = os.path.join(os.path.dirname(__file__), "config.toml.example")

        try:
            if not os.path.exists(config_path):
                logger.warning(f"[{self.__class__.__name__}] 配置文件 {config_path} 不存在.")
                if not os.path.exists(example_config_path):
                    self._create_example_config(example_config_path)
                self.enable = False 
                return

            with open(config_path, "rb") as f_config:
                config = tomllib.load(f_config)
            
            # 从基础配置加载
            basic_config = config.get("basic", {})
            self.enable = basic_config.get("enable", True) 
            self.api_key = basic_config.get("TIAN_API_KEY")
            self.handler_priority = basic_config.get("HANDLER_PRIORITY", 20)
            self.api_endpoint = basic_config.get("API_ENDPOINT", "https://apis.tianapi.com/ai/index")

            # 从设置配置加载
            settings_config = config.get("settings", {})
            self.text_news_count = int(settings_config.get("text_news_count", 10))
            self.image_news_count = int(settings_config.get("image_news_count", 6))

            if not self.api_key or self.api_key == "YOUR_TIAN_API_KEY_HERE" or self.api_key == "":
                logger.warning(f"[{self.__class__.__name__}] TIAN_API_KEY 未配置或无效")
                self.enable = False

        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] 加载配置文件失败: {e}", exc_info=True)
            self.enable = False

    def _create_example_config(self, example_config_path):
        """创建示例配置文件"""
        default_config_content = (
            "[basic]\n"
            "# 是否启用AIReport插件\n"
            "enable = true\n"
            "# 天行API的KEY，请替换为你自己的KEY\n"
            'TIAN_API_KEY = ""\n'
            "# 插件处理优先级\n"
            "HANDLER_PRIORITY = 20\n"
            "# API端点URL\n"
            'API_ENDPOINT = "https://apis.tianapi.com/ai/index"\n\n'
            "[settings]\n"
            "# 文本版新闻条数\n"
            "text_news_count = 10\n"
            "# 图片版新闻条数\n"
            "image_news_count = 6\n"
        )
        try:
            with open(example_config_path, "w", encoding="utf-8") as f_example:
                f_example.write(default_config_content)
            logger.info(f"[{self.__class__.__name__}] 已创建示例配置文件: {example_config_path}")
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] 创建示例配置文件失败: {e}")

    async def async_init(self):
        """完全不做初始化，确保启动速度"""
        logger.debug(f"[{self.__class__.__name__}] async_init - 使用真正的懒加载模式，跳过初始化")
        return

    async def on_disable(self):
        """插件被禁用时清理资源"""
        logger.info(f"[{self.__class__.__name__}] on_disable called.")
        await self._cleanup_playwright()

    def reload_config(self):
        """重新加载配置文件"""
        logger.info(f"[{self.__class__.__name__}] 正在重新加载配置...")
        old_enable_state = self.enable
        self._load_config()
        if old_enable_state != self.enable:
            if self.enable:
                logger.info(f"[{self.__class__.__name__}] 插件已启用。")
            else:
                logger.info(f"[{self.__class__.__name__}] 插件已禁用。")
        return {"success": True, "message": "配置已重新加载", "enable": self.enable}

    @on_text_message(priority=20)
    async def handle_text(self, bot: WechatAPIClient, message: dict):
        """处理文本消息，响应AI简讯和AI快讯命令"""
        # 提取消息内容
        message_content = ""
        if isinstance(message, dict):
            if 'Content' in message:
                message_content = message['Content']
            elif 'content' in message:
                message_content = message['content']
            elif 'text' in message:
                message_content = message['text']
        
        message_content = message_content.strip() if isinstance(message_content, str) else ""
        
        # 提取会话ID
        conversation_id = None
        if isinstance(message, dict):
            if 'FromWxid' in message:
                conversation_id = message['FromWxid']
            elif 'fromWxid' in message:
                conversation_id = message['fromWxid']
            elif 'conversation_id' in message:
                conversation_id = message['conversation_id']
        
        if not message_content or not conversation_id:
            return True
        
        if not self.enable:
            return True

        content = message_content.strip()
        
        # 检查命令
        if content in ["AI简讯", "ai简讯"]:
            await bot.send_text_message(conversation_id, "正在获取AI简讯，请稍候...")
            await self._process_request("AI简讯", bot, conversation_id)
            return False
        elif content in ["AI快讯", "ai快讯", "AI资讯", "ai资讯"]:
            await bot.send_text_message(conversation_id, "正在获取AI快讯，请稍候...")
            await self._process_request("AI快讯", bot, conversation_id)
            return False
            
        return True

    async def _process_request(self, command: str, bot: WechatAPIClient, conversation_id: str):
        try:
            if not self.api_key:
                await bot.send_text_message(conversation_id, "API Key未配置，插件无法工作。")
                return

            num = self.text_news_count if command == "AI简讯" else self.image_news_count
            news_data = await self._fetch_news(self.api_key, num)
            if not news_data:
                await bot.send_text_message(conversation_id, "获取资讯失败，请稍后重试。")
                return

            if command == "AI简讯":
                await self._handle_text_report(news_data, bot, conversation_id)
            else:
                # 使用更稳健的线程处理方式
                start_time = time.time()
                logger.debug(f"[{self.__class__.__name__}] 开始处理图片报告")
                
                # 创建和启动线程
                thread = threading.Thread(
                    target=self._run_playwright_in_thread,
                    args=(news_data, bot, conversation_id)
                )
                thread.daemon = True
                thread.start()
                
                # 不阻塞等待线程完成
                logger.debug(f"[{self.__class__.__name__}] 已启动处理图片报告的后台线程")
                
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] 处理请求失败: {e}", exc_info=True)
            await bot.send_text_message(conversation_id, "处理请求失败，请稍后重试。")

    def _run_playwright_in_thread(self, news_data, bot, conversation_id):
        """在单独的线程中运行Playwright操作"""
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 在新事件循环中运行异步任务
            start_time = time.time()
            loop.run_until_complete(self._handle_image_report(news_data, bot, conversation_id))
            duration = time.time() - start_time
            logger.info(f"[{self.__class__.__name__}] 图片报告处理完成，用时: {duration:.2f}秒")
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Playwright线程异常: {e}", exc_info=True)
            # 在异常情况下使用文本模式
            try:
                loop.run_until_complete(self._send_text_alternative(news_data, bot, conversation_id))
            except Exception as text_err:
                logger.error(f"[{self.__class__.__name__}] 发送文本替代内容失败: {text_err}", exc_info=True)
        finally:
            # 清理事件循环
            try:
                # 取消所有未完成的任务
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                
                # 运行取消任务的回调
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
                # 关闭事件循环
                loop.close()
                logger.debug(f"[{self.__class__.__name__}] 成功清理事件循环")
            except Exception as cleanup_err:
                logger.error(f"[{self.__class__.__name__}] 清理事件循环失败: {cleanup_err}")

    async def _fetch_news(self, api_key: str, num: int) -> List[Dict[str, Any]]:
        try:
            url = f"{self.api_endpoint}?key={api_key}&num={num}"
            
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: requests.get(url, timeout=30))
            
            if response.status_code != 200:
                logger.error(f"[{self.__class__.__name__}] API返回非200状态码: {response.status_code}")
                return []
            
            data = response.json()
            
            if data.get('code') == 200 and 'result' in data and 'newslist' in data['result']:
                return data['result']['newslist']
            
            logger.error(f"[{self.__class__.__name__}] API返回格式不正确: {data}")
            return []
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] 获取新闻数据失败: {e}")
            return []

    async def _handle_text_report(self, newslist: List[Dict[str, Any]], bot: WechatAPIClient, conversation_id: str):
        """处理文本版资讯并发送"""
        content_parts = ["📢 最新AI资讯如下："]
        for i, news in enumerate(newslist, 1):
            title = news.get('title', '未知标题').replace('\n', '')
            link = news.get('url', '未知链接').replace('\n', '')
            content_parts.append(f"No.{i}《{title}》\n🔗{link}")
        
        content = "\n".join(content_parts)
        await bot.send_text_message(conversation_id, content)

    async def _send_text_alternative(self, newslist: List[Dict[str, Any]], bot: WechatAPIClient, conversation_id: str):
        """当图片渲染失败时发送文本替代内容"""
        content_parts = ["📢 最新AI资讯 (图片渲染不可用，以文本形式显示)："]
        for i, news in enumerate(newslist, 1):
            title = news.get('title', '未知标题').replace('\n', '')
            desc = news.get('description', '无描述').replace('\n', '')
            if len(desc) > 100:
                desc = desc[:97] + "..."
            content_parts.append(f"No.{i}《{title}》\n📝{desc}")
        
        content = "\n".join(content_parts)
        await bot.send_text_message(conversation_id, content)

    async def _handle_image_report(self, newslist: List[Dict[str, Any]], bot: WechatAPIClient, conversation_id: str):
        """处理图片版资讯并发送"""
        try:
            html_content = self._generate_html(newslist)
            if not html_content:
                logger.error(f"[{self.__class__.__name__}] 生成HTML内容失败")
                await bot.send_text_message(conversation_id, "生成HTML内容失败，无法创建图片报告。")
                await self._send_text_alternative(newslist, bot, conversation_id)
                return
                
            # 渲染并发送图片
            await self._render_and_send_image(html_content, bot, conversation_id)
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] 处理图片报告失败: {e}", exc_info=True)
            await self._send_text_alternative(newslist, bot, conversation_id)

    async def _init_playwright(self):
        """延迟初始化Playwright，只在需要时才创建实例"""
        # 使用锁确保只有一个线程执行初始化
        with self.playwright_lock:
            # 如果已经初始化完成，直接返回
            if self.browser:
                return True
                
            # 如果已经在初始化中，等待初始化完成
            if self.is_initializing:
                logger.debug(f"[{self.__class__.__name__}] Playwright正在初始化中，等待...")
                return False  # 让调用者知道目前无法使用Playwright
            
            # 设置初始化标志
            self.is_initializing = True
        
        try:
            # 这里才真正导入playwright，避免启动时加载
            try:
                from playwright.async_api import async_playwright
                logger.info(f"[{self.__class__.__name__}] 成功导入playwright模块")
            except ImportError as imp_err:
                logger.error(f"[{self.__class__.__name__}] 导入playwright模块失败: {imp_err}")
                self.is_initializing = False
                return False
                
            logger.info(f"[{self.__class__.__name__}] 正在初始化Playwright...")
            start_time = time.time()
            
            try:
                playwright_instance = await async_playwright().start()
                logger.debug(f"[{self.__class__.__name__}] async_playwright().start() 完成，用时: {time.time() - start_time:.2f}秒")
            except NotImplementedError as nie:
                logger.error(f"[{self.__class__.__name__}] Playwright初始化失败 (NotImplementedError - 可能是Anaconda环境问题): {nie}")
                self.is_initializing = False
                return False
            except Exception as start_err:
                logger.error(f"[{self.__class__.__name__}] Playwright启动失败: {start_err}", exc_info=True)
                self.is_initializing = False
                return False
            
            try:
                logger.debug(f"[{self.__class__.__name__}] 正在启动Chromium浏览器...")
                browser_start = time.time()
                browser = await playwright_instance.chromium.launch(
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
                    headless=True
                )
                logger.debug(f"[{self.__class__.__name__}] Chromium浏览器启动完成，用时: {time.time() - browser_start:.2f}秒")
                
                # 只有成功启动浏览器后才设置实例变量
                self.playwright_instance = playwright_instance
                self.browser = browser
                
                logger.success(f"[{self.__class__.__name__}] Playwright初始化成功，总用时: {time.time() - start_time:.2f}秒")
                return True
            except Exception as browser_err:
                # 浏览器启动失败，关闭playwright实例
                logger.error(f"[{self.__class__.__name__}] 启动Chromium浏览器失败: {browser_err}", exc_info=True)
                try:
                    if playwright_instance:
                        await playwright_instance.stop()
                except Exception as stop_err:
                    logger.error(f"[{self.__class__.__name__}] 停止Playwright实例失败: {stop_err}")
                return False
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Playwright初始化过程中发生未捕获的异常: {e}", exc_info=True)
            return False
        finally:
            # 重置初始化标志
            self.is_initializing = False

    async def _cleanup_playwright(self):
        """清理Playwright资源"""
        try:
            with self.playwright_lock:
                if self.browser:
                    logger.info(f"[{self.__class__.__name__}] 正在关闭Playwright浏览器...")
                    try:
                        await self.browser.close()
                        logger.debug(f"[{self.__class__.__name__}] Playwright浏览器已关闭")
                    except Exception as e:
                        logger.error(f"[{self.__class__.__name__}] 关闭浏览器失败: {e}")
                    finally:
                        self.browser = None
                    
                if self.playwright_instance:
                    logger.info(f"[{self.__class__.__name__}] 正在停止Playwright实例...")
                    try:
                        await self.playwright_instance.stop()
                        logger.debug(f"[{self.__class__.__name__}] Playwright实例已停止")
                    except Exception as e:
                        logger.error(f"[{self.__class__.__name__}] 停止Playwright实例失败: {e}")
                    finally:
                        self.playwright_instance = None
                        
                logger.success(f"[{self.__class__.__name__}] Playwright资源已清理")
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] 清理Playwright资源失败: {e}", exc_info=True)
        finally:
            self.browser = None
            self.playwright_instance = None
            self.is_initializing = False

    async def _render_and_send_image(self, html_content: str, bot: WechatAPIClient, conversation_id: str):
        """渲染HTML并发送图片"""
        # 懒加载初始化Playwright - 这是唯一需要Playwright的地方
        initialized = await self._init_playwright()
        if not initialized:
            logger.error(f"[{self.__class__.__name__}] Playwright初始化失败，回退到文本模式")
            await self._send_text_alternative([], bot, conversation_id)
            return
        
        page = None
        try:
            page = await self.browser.new_page()
            await page.set_viewport_size({"width": 700, "height": 1380})
            
            # 设置更长的超时时间
            await page.set_content(html_content, timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=60000)  # 等待所有资源加载完成
            
            screenshot_bytes = await page.screenshot(full_page=True, type='png')
            
            if screenshot_bytes:
                try:
                    await bot.send_image(conversation_id, screenshot_bytes)
                    logger.info(f"[{self.__class__.__name__}] 图片发送成功")
                except AttributeError:
                    await bot.send_image_message(conversation_id, screenshot_bytes)
                    logger.info(f"[{self.__class__.__name__}] 图片发送成功(使用send_image_message)")
            else:
                logger.error(f"[{self.__class__.__name__}] 截图为空")
                await bot.send_text_message(conversation_id, "生成图片失败，请稍后重试。")
                await self._send_text_alternative([], bot, conversation_id)
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] 渲染图片失败: {e}", exc_info=True)
            await self._send_text_alternative([], bot, conversation_id)
        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.error(f"[{self.__class__.__name__}] 关闭页面失败: {e}")

    def _generate_html(self, newslist: List[Dict[str, Any]]) -> str:
        """生成HTML内容"""
        try:
            if not os.path.exists(self.template_path):
                logger.error(f"[{self.__class__.__name__}] HTML模板文件未找到: {self.template_path}")
                return ""

            with open(self.template_path, 'r', encoding='utf-8') as f:
                template = f.read()
    
            # 读取QR码图片并编码为Base64
            qr_code_path = os.path.join(os.path.dirname(__file__), "QRcode.png")
            if os.path.exists(qr_code_path):
                try:
                    with open(qr_code_path, 'rb') as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    data_uri = f"data:image/png;base64,{encoded_string}"
                    template = template.replace("QRcode.png", data_uri)
                except:
                    pass
    
            # 渲染新闻内容
            news_units = ""
            for news_item in newslist:
                title = news_item.get('title', '未知标题')
                description = news_item.get('description', '无描述')
                if len(description) > 100:
                    description = description[:100] + '...'
                ctime = news_item.get('ctime', '未知时间')
                picUrl = news_item.get('picUrl', '')
    
                news_units += f'''
                <div class="news-unit">
                    <img src="{picUrl}" alt="news image">
                    <div class="text-block">
                        <div class="title">{title}</div>
                        <div class="description">{description}</div>
                        <div class="ctime">{ctime}</div>
                    </div>
                </div>'''
    
            # 将动态生成的新闻单元替换到模板中
            final_html = template.replace('<!-- NEWS_CONTENT -->', news_units)
            return final_html
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] 生成HTML内容失败: {e}", exc_info=True)
            return ""

    def get_help_text(self, **kwargs):
        help_text = """AI资讯获取助手
        指令：
        1. 发送"AI简讯"：获取文字版AI资讯，包含标题和原文链接
        2. 发送"AI快讯"或"AI资讯"：获取图片版AI资讯，包含标题、简介和发布时间
        
        注意：
        - 文字版显示10条最新资讯
        - 图片版显示6条最新资讯
        """
        return help_text 