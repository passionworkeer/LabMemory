# 案例集 H5（AFFT）构建链

大赛案例集提交（1.md 第 2 项）的页面构建链。最终交付物在仓库根：
`LabMemory晶研智流-竖屏版.html`（单文件自包含，约 1MB）。

## 文件说明

| 文件 | 用途 |
|---|---|
| `page_template.html` | 页面模板正文（带 `%%BRAND%%` `%%HERO%%` `%%FOOTER%%` `%%IMG:*%%` 占位符） |
| `build_page.py` | 组装脚本：注入大赛 logo（`source/assets/*.b64.txt`，赛方 Skill 本地解压件，未入库）与截图 base64，输出最终 HTML |
| `extract_frames.sh` | 从 `demo/remotion/public/media/source/*.mp4` 抽五个真实界面截图（裁剪参数与 `demo/scripts/prep_remotion_media.sh` 一致） |
| `frames/*.jpg` | 界面截图（`confirm_t5.0.jpg` 为多时间点按 JPEG 体积挑出）与三张痛点配图（`ill_*`，源自答辩 PPT，经 XML 位置映射到妙记录音/群聊消息/个人记忆三卡） |
| `extract_pptx.py` | 提取答辩 PPT 每页文字与全部媒体到本地 `pptx/`（产物含成员照片，未入库） |
| `map_slide2.py` | 解析 PPT 痛点页组结构，确认三张配图与三个卡片的对应关系 |
| `overflow_check.html` | 无头 Chrome 横向溢出检测 harness（iframe 390px 视口，可改宽度复用） |

## 重建

```bash
bash scripts/case-h5/extract_frames.sh   # 仅当演示视频更新时需要
python3 scripts/case-h5/build_page.py    # 重新输出根目录的竖屏版 HTML
```

改文字直接编辑 `page_template.html` 后重跑 `build_page.py`。

## 补成员照片

三人照片原件在答辩 PPT（`image31/32/33.jpeg`）。先 `python3 scripts/case-h5/extract_pptx.py`
解出媒体，再把 `page_template.html` 中对应成员的 `<div class="avatar">王</div>` 替换为
`<img class="avatar" src="data:image/jpeg;base64,...">`（或改用文件引用后由 build 脚本注入）。

## 内容口径

正文数字全部对齐 `brief.md`（数据弹药与口径表）与 12 强答辩 PPT；外部数据带主语
（微软受控实验 / 国家统计局 / 晶泰公开资料）；三项无录屏的能力按 demo README 的
诚实边界标注「流程说明」，不冒充实录。

注意：`page_template.html` 与交付 HTML 内含队长手机号（页面联系方式，用户指定），
本仓库为公开仓库，改动前先确认这一点。
