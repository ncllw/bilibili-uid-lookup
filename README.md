# Bili 查名

输入哔哩哔哩 UID 或个人空间链接，查询对应昵称。本地软件，以浏览器作为界面。

![昵称查询界面](preview.jpg)

## 下载

在 GitHub 仓库页面点击 **Code → Download ZIP**，解压后启动；也可使用 Git：

```powershell
git clone https://github.com/ncllw/bilibili-uid-lookup.git
cd bilibili-uid-lookup
```

## 启动

双击 **start.cmd**，会启动服务并打开 `http://127.0.0.1:18763`。需要 Python 3.10 或更新版本，无需安装第三方依赖。关闭启动的命令窗口即可停止服务。

尚未安装 Python 时，可从 [Python 官网](https://www.python.org/downloads/) 安装 Python 3.10 或更新版本；Windows 安装时勾选 **Add Python to PATH**。

也可在本目录运行：

```powershell
python server.py --open
```

端口被其他软件占用时，可运行 `python server.py --port 18764 --open`。

## 使用

- 输入 `306936843`，或 `https://space.bilibili.com/306936843`，点击“查询昵称”。
- 支持带查询参数、带 `/video` 等子路径的个人空间链接。
- 结果显示昵称、UID、头像和可获取的公开资料，可复制昵称或 UID，也可打开个人空间。
- 最近 8 条成功查询只保存在当前浏览器，可以一键清空。点击记录会重新查询。
- 成功响应在服务内存中缓存 5 分钟，缓存结果会明确标注。重启服务会清空缓存。
- 不要求登录、不收集 Cookie；运行时需要联网访问哔哩哔哩。接口限制访问时显示错误，不会伪造或硬编码结果。
- 服务仅监听本机 `127.0.0.1`。没有部署到公共服务器。

公开仓库提供源码下载。查询功能需要在本机运行 `server.py`，仅打开 HTML 文件或将静态文件发布到 GitHub Pages 无法直接查询。

## GitHub 调研（2026-10-17）

| 项目 | 调研结果 | 本工具的处理 |
| --- | --- | --- |
| [SocialSisterYi/bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) | 原仓库已于 2026-01-30 归档并停止维护，原文档已移除 | 不作为依赖 |
| [Nemo2011/bilibili-api](https://github.com/Nemo2011/bilibili-api) | 原仓库已于 2026-07-06 归档并停止维护 | 不引入完整 SDK |
| [pskdje/bilibili-API-collect 的用户信息文档](https://github.com/pskdje/bilibili-API-collect/blob/main/docs/user/info.md#用户名片信息) | 归档分支仍保留用户名片接口说明：以 `mid` 查询，昵称位于 `data.card.name` | 参考接口说明，以 Python 标准库独立实现，无复制项目源码 |

实际请求 `https://api.bilibili.com/x/web-interface/card?mid=306936843`，读取 `data.card.name`。首次制作时已联网验证示例返回“雨说体育徐静雨”；昵称以查询时接口返回为准，可能随用户改名而变化。接口属于哔哩哔哩站内接口，能否查询取决于当时的网络和平台响应。

## 文件

- `server.py`：输入解析、请求、缓存和本机 HTTP 服务。
- `web/`：无需构建的 HTML、CSS、JavaScript 界面。
- `start.cmd`：Windows 双击启动。
- `test_server.py`：输入校验、响应处理、缓存和 HTTP 行为测试。运行 `python -m unittest -v`。
