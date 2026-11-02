# XTEINK 电子书库

微信公众号文章 → EPUB → OPDS 在线书库。

## 结构

```
books/     *.epub 电子书（push 新书即自动发布）
covers/    封面（自动生成，勿手动改）
scripts/   OPDS 目录生成器
opds.xml   OPDS 订阅目录（自动生成）
index.html 网页书架（自动生成）
```

## 使用

1. **仓库 Settings → Pages → Source 选 "GitHub Actions"**（首次部署前必须设置一次）。
2. 把 epub 丢进 `books/`，push 到 main，Action 自动重建目录并发布。
3. 阅读器（KOReader / Moon+ Reader / KyBook 等）添加 OPDS 目录：
   ```
   https://2dogslee.github.io/XTEINK/opds.xml
   ```
4. 浏览器直接访问 `https://2dogslee.github.io/XTEINK/` 看网页书架。

## 本地添加书籍

```bash
# 公众号文章转 epub（转换脚本见 CatPaw/调研/wechat2epub.py）
python3 wechat2epub.py "https://mp.weixin.qq.com/s/xxxx" books/新书.epub
git add books/ && git commit -m "add: 新书" && git push
```

⚠️ 仓库需为 public（阅读器不带 GitHub 鉴权），勿放私密内容。
