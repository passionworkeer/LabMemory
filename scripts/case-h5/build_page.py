import base64
from pathlib import Path

ROOT = Path("/Users/wangjianjun/me/LabMemory")
AFFT = ROOT / "scripts/case-h5"

html = (AFFT / "page_template.html").read_text(encoding="utf-8")

brand = (ROOT / "source/assets/brandbar_logo.b64.txt").read_text().strip()
hero = (ROOT / "source/assets/footer_logo.b64.txt").read_text().strip()

html = html.replace("%%BRAND%%", brand)
html = html.replace("%%HERO%%", hero)
html = html.replace("%%FOOTER%%", hero)

# confirm 采用 t=5.0 的候选帧
frames = {
    "feishu": AFFT / "frames/feishu.jpg",
    "tower": AFFT / "frames/tower.jpg",
    "briefing": AFFT / "frames/briefing.jpg",
    "confirm": AFFT / "frames/confirm_t5.0.jpg",
    "qa": AFFT / "frames/qa.jpg",
    "ill_recording": AFFT / "frames/ill_recording.jpg",
    "ill_chat": AFFT / "frames/ill_chat.jpg",
    "ill_memory": AFFT / "frames/ill_memory.jpg",
}
for key, path in frames.items():
    b64 = base64.b64encode(path.read_bytes()).decode()
    html = html.replace(f"%%IMG:{key}%%", f"data:image/jpeg;base64,{b64}")

# 检查无残留占位符
assert "%%" not in html, "存在未替换的占位符"

out = ROOT / "LabMemory晶研智流-竖屏版.html"
out.write_text(html, encoding="utf-8")
print(f"输出 {out}  {out.stat().st_size} bytes")
