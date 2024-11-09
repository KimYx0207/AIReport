import os
import json
import requests
from common.log import logger
import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from plugins import *
from playwright.async_api import async_playwright
from typing import List, Dict, Any
from io import BytesIO
import asyncio
import os.path

@plugins.register(
    name="AIReport",
    desc="获取AI相关资讯，支持文字版和图片版",
    version="3.0",
    author="Lingyuzhou",
    desire_priority=500
)
class AIReport(Plugin):
    # 配置常量
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
    TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "news_template.html")
    API_ENDPOINT = "https://apis.tianapi.com/ai/index"
    
    def __init__(self):
        super().__init__()
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        # 确保模板目录存在
        os.makedirs(os.path.dirname(self.TEMPLATE_PATH), exist_ok=True)
        logger.info(f"[{__class__.__name__}] initialized")
        self.browser = None
        self.playwright = None
        # 创建事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def on_handle_context(self, e_context):
        """处理用户输入的上下文"""
        if e_context['context'].type != ContextType.TEXT:
            return
        
        content = e_context["context"].content.strip()
        if content in ["AI简讯", "AI快讯"]:
            logger.info(f"[{__class__.__name__}] 收到消息: {content}")
            # 在事件循环中运行异步任务
            self.loop.run_until_complete(self._process_request(content, e_context))

    async def _process_request(self, command: str, e_context):
        """异步处理不同类型的资讯请求"""
        try:
            # 获取API密钥
            api_key = self._get_api_key()
            if not api_key:
                self._send_error_reply(e_context, f"请先配置{self.CONFIG_PATH}文件")
                return

            # 根据命令类型设置获取的新闻数量
            num = 10 if command == "AI简讯" else 6
            
            # 获取新闻数据
            news_data = self._fetch_news(api_key, num)
            if not news_data:
                self._send_error_reply(e_context, "获取资讯失败，请稍后重试")
                return

            # 根据命令类型处理响应
            if command == "AI简讯":
                self._handle_text_report(news_data, e_context)
            else:
                await self._handle_image_report(news_data, e_context)
        except Exception as e:
            logger.error(f"处理请求失败: {e}")
            self._send_error_reply(e_context, "处理请求失败，请稍后重试")

    def __del__(self):
        """析构函数"""
        try:
            if self.browser or self.playwright:
                self.loop.run_until_complete(self._cleanup_playwright())
            self.loop.close()
        except Exception as e:
            logger.error(f"清理资源失败: {e}")

    async def _cleanup_playwright(self):
        """异步清理资源"""
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.error(f"Error cleaning up Playwright resources: {e}")
        finally:
            self.browser = None
            self.playwright = None

    async def _init_playwright(self):
        """异步初始化 Playwright"""
        if self.browser is None:
            try:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                logger.info("Playwright initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Playwright: {e}")
                self.playwright = None
                self.browser = None

    def _get_api_key(self) -> str:
        """获取API密钥"""
        try:
            if not os.path.exists(self.CONFIG_PATH):
                logger.error(f"配置文件不存在: {self.CONFIG_PATH}")
                return ""
            
            with open(self.CONFIG_PATH, 'r') as file:
                return json.load(file).get('TIAN_API_KEY', '')
        except Exception as e:
            logger.error(f"读取配置文件失败: {e}")
            return ""

    def _fetch_news(self, api_key: str, num: int) -> List[Dict[str, Any]]:
        """获取新闻数据"""
        try:
            url = f"{self.API_ENDPOINT}?key={api_key}&num={num}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == 200 and 'result' in data and 'newslist' in data['result']:
                return data['result']['newslist']
            logger.error(f"API返回格式不正确: {data}")
            return []
        except Exception as e:
            logger.error(f"获取新闻数据失败: {e}")
            return []

    def _handle_text_report(self, newslist: List[Dict[str, Any]], e_context):
        """处理文字版报告"""
        content = "📢 最新AI资讯如下：\n"
        for i, news in enumerate(newslist, 1):
            title = news.get('title', '未知标题').replace('\n', '')
            link = news.get('url', '未知链接').replace('\n', '')
            content += f"No.{i}《{title}》\n🔗{link}\n"

        e_context["reply"] = Reply(ReplyType.TEXT, content)
        e_context.action = EventAction.BREAK_PASS

    def _send_error_reply(self, e_context, message: str):
        """发送错误消息"""
        e_context["reply"] = Reply(ReplyType.TEXT, message)
        e_context.action = EventAction.BREAK_PASS 

    async def _handle_image_report(self, newslist: List[Dict[str, Any]], e_context):
        """异步处理图片版报告"""
        html_content = self._generate_html(newslist)
        await self._render_and_send_image(html_content, e_context)

    async def _render_and_send_image(self, html_content: str, e_context):
        """异步渲染HTML并发送图片"""
        if not self.browser:
            await self._init_playwright()
            if not self.browser:
                self._send_error_reply(e_context, "浏览器初始化失败，请稍后重试")
                return

        try:
            page = await self.browser.new_page()
            try:
                await page.set_viewport_size({"width": 600, "height": 1335})
                await page.set_content(html_content, timeout=60000)
                screenshot_bytes = await page.screenshot(
                    full_page=True,
                    type='png'  # 移除 quality 参数
                )
                
                if screenshot_bytes:
                    image_io = BytesIO(screenshot_bytes)
                    e_context["reply"] = Reply(ReplyType.IMAGE, image_io)
                    e_context.action = EventAction.BREAK_PASS
                    logger.debug("[AIReport] 图片生成并发送成功")
                else:
                    self._send_error_reply(e_context, "生成图片失败")
            finally:
                await page.close()
        except Exception as e:
            logger.error(f"渲染图片失败: {e}")
            self._send_error_reply(e_context, "生成图片失败，请稍后重试")
            # 如果发生错误，���试重新初始化浏览器
            await self._cleanup_playwright()
            await self._init_playwright()

    def _generate_html(self, newslist: List[Dict[str, Any]]) -> str:
        """生成HTML内容"""
        try:
            # 读取HTML模板
            with open(self.TEMPLATE_PATH, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # 生成新闻单元
            news_units = ""
            for news_item in newslist:
                title = news_item.get('title', '未知标题')
                description = news_item.get('description', '无描述')
                ctime = news_item.get('ctime', '未知时间')
                picUrl = news_item.get('picUrl', '')

                if len(description) > 100:
                    description = description[:100] + '...'

                if picUrl:
                    news_units += f'''
                    <div class="news-unit">
                        <img src="{picUrl}" alt="news image">
                        <div class="text-block">
                            <div class="title">{title}</div>
                            <div class="description">{description}</div>
                            <div class="ctime">{ctime}</div>
                        </div>
                    </div>'''
                else:
                    logger.warning(f"无效的图片 URL: {picUrl}")

            # 替换模板中的占位符
            final_html = template.replace('<!-- NEWS_CONTENT -->', news_units)
            
            # 记录生成的完整HTML代码到日志
            logger.info("生成的HTML内容:")
            logger.info("=== HTML START ===")
            logger.info(final_html)
            logger.info("=== HTML END ===")
            
            return final_html
            
        except Exception as e:
            logger.error(f"生成HTML内容失败: {e}")
            raise
        
    def get_help_text(self, **kwargs):
        """获取插件帮助信息"""
        help_text = """AI资讯获取助手
        指令：
        1. 发送"AI简讯"：获取文字版AI资讯，包含标题和原文链接
        2. 发送"AI快讯"：获取图片版AI资讯，包含标题、简介和发布时间
        
        注意：
        - 文字版显示10条最新资讯
        - 图片版显示6条最新资讯
        - 图片版支持查看新闻配图
        """
        return help_text
