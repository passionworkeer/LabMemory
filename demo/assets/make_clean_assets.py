from PIL import Image, ImageDraw, ImageFont

FONT_CN = '/System/Library/Fonts/STHeiti Medium.ttc'
PPT_BLUE = (31, 78, 140, 255)


def make_subtitle_clean(text, output, w=1920, h=90, font_size=46):
    """底部纯文字字幕，白色 + 黑色描边，无背景框"""
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_CN, font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (w - tw) / 2
    y = (h - th) / 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255),
              stroke_width=3, stroke_fill=(0, 0, 0, 220))
    img.save(output)


def make_badge_clean(text, output, font_size=26):
    """左上角角标，浅色背景 + 深色文字，无边框"""
    font = ImageFont.truetype(FONT_CN, font_size)
    tmp = Image.new('RGBA', (1, 1))
    d = ImageDraw.Draw(tmp)
    bbox = d.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0] + 36
    text_h = bbox[3] - bbox[1] + 16
    img = Image.new('RGBA', (text_w, text_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = text_h // 2
    # 浅蓝半透背景
    draw.rounded_rectangle((0, 0, text_w, text_h), radius=radius, fill=(255, 255, 255, 230))
    # 深蓝文字
    draw.text((18, 8 - bbox[1]), text, font=font, fill=(31, 78, 140, 255))
    img.save(output)


SHOTS = [
    (1, '① 研发控制塔：会后待确认决策，一处汇总', '模块 1/8 · 研发控制塔'),
    (2, '② 会前简报：带着当前有效版本与上轮结果进会', '模块 2/8 · 会前简报'),
    (3, '③ 决策编译：妙记原话 → AI 候选，三值全程留痕', '模块 3/8 · 决策编译'),
    (4, '重点一：AI 只出候选，人一次点选才生效', '模块 4/8 · 会后复核'),
    (5, '④ 版本接棒：新版本生效，旧版本只读留痕、不覆盖', '模块 5/8 · 实验护照·版本链'),
    (6, '重点二：引用失效版本，任务建立瞬间被阻断', '模块 6/8 · 行动前审计'),
    (7, '重点三：结果判「部分支持」，自动派生下一轮复验', '模块 7/8 · 结果回流'),
    (8, '⑤ 实验护照：一条实验从头到尾，步步可溯', '模块 8/8 · 数据关系链'),
    (9, '⑥ 可信问答：答案必带出处，证据不足明确拒答', '模块 8/8 · 可信问答'),
]

for shot_no, sub_text, badge_text in SHOTS:
    make_subtitle_clean(sub_text, f'sub_{shot_no:02d}.png')
    make_badge_clean(badge_text, f'badge_{shot_no:02d}.png')

make_subtitle_clean('飞书会议结束 · 妙记自动生成 · 系统收到待复核', 'sub_feishu.png')
make_badge_clean('外部信号入口', 'badge_feishu.png')

print('done')