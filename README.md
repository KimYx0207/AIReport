![image](https://github.com/user-attachments/assets/c873c4e2-443c-4df5-a7a1-bb61831ae67d)



# AIReport
AIReport是一款适用于XXXBOT框架的新闻资讯类插件，调用天聚数行的API接口，通过代码加工后生成文字版和图片版的AI日报。
该插件是原来的AIReport_pic图片版和AIReport_txt文字版AI日报插件的整合版本，已适配XXXBOT框架。

## 功能
- 支持文字版AI简讯：提供最新的AI相关新闻链接列表
- 支持图片版AI快讯：生成精美的图片日报
- 自动处理大小写字段：兼容不同的消息格式
- 提供完善的错误处理和日志记录
- 支持配置文件热重载
- 增强型Playwright渲染：确保图片生成稳定可靠

## 一. 安装Html渲染所必需的环境

安装playwright：在服务器终端执行以下命令 ：pip install playwright
安装chromium：在服务器终端执行以下命令 ：playwright install chromium
安装字体：在服务器终端执行以下命令 ：yum groupinstall "fonts"


### 手动安装
如果自动安装脚本不工作，可以按照以下步骤手动安装：

1. 安装playwright：在服务器终端执行以下命令：`pip install playwright>=1.42.0`
2. 安装chromium：在服务器终端执行以下命令：`playwright install chromium`
3. 安装系统依赖(必须, Linux系统)：`playwright install-deps chromium`


## 二. 获取TIAN_API_KEY并申请接口
1. 在天聚数行API接口网站注册账号并登录，官网链接：https://www.tianapi.com

2. 点击网站首页的"控制台"进入个人主页，点击左上角"数据管理"➡️"我的密钥KEY",复制默认的APIKEY备用。

3. 在上述网站首页"一键搜索"栏搜索"AI资讯"，跳转至对应详情页点击"申请接口"，然后点击"在线测试"测试接口是否正常。普通用户每天可免费调用100次。

## 三. 配置插件
1. 在安装插件后，打开`plugins/AIReport/config.toml`文件。

2. 将您在天行API获取的TIAN_API_KEY填入对应位置：
```toml
[basic]
# 是否启用AIReport插件
enable = true
# 天行API的KEY，请替换为你自己的KEY
TIAN_API_KEY = "你的TIAN_API_KEY"
# 插件处理优先级 (越高越优先处理消息)
HANDLER_PRIORITY = 20
# API端点URL
API_ENDPOINT = "https://apis.tianapi.com/ai/index"
```

3. 根据需要调整其他配置项，如新闻条数、命令关键词等。

4. 保存配置文件并重启XXXBOT或使用插件管理命令重新加载插件。

## 四. 使用方法
该插件支持以下命令：
- `AI简讯` 或 `ai简讯`：获取文字版新闻列表
- `AI快讯`、`ai快讯`、`AI资讯` 或 `ai资讯`：获取图片版新闻

您也可以在命令前添加以下前缀（这些前缀将被自动去除）：
- `老金`


示例：
- 发送 `AI简讯` 获取文字版新闻列表
- 发送 `AI快讯` 获取图片版新闻

## 五. 自定义
您可以修改`plugins/AIReport/news_template.html`文件来自定义图片版报告的样式。


## 六 常见问题
1. **配置文件找不到**：请确保插件目录下有`config.toml`文件，如果没有，可以复制`config.toml.example`并重命名。

2. **无法触发插件**：检查消息格式并查看日志，确保插件优先级设置正确（默认为20。

