import zipfile, re, os, sys
from xml.etree import ElementTree as ET

pptx = "/Users/wangjianjun/me/LabMemory/LabMemory晶研智流-12强答辩优化版 (2).pptx"
outdir = "/Users/wangjianjun/me/LabMemory/scripts/case-h5/pptx"
os.makedirs(outdir, exist_ok=True)

z = zipfile.ZipFile(pptx)
ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}

slides = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                key=lambda n: int(re.search(r"(\d+)", n).group(1)))

for name in slides:
    root = ET.fromstring(z.read(name))
    texts = []
    for p in root.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}p"):
        runs = [t.text or "" for t in p.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t")]
        line = "".join(runs).strip()
        if line:
            texts.append(line)
    print(f"===== {name} =====")
    print("\n".join(texts))
    print()

# 导出媒体图片，记录大小
media = [n for n in z.namelist() if n.startswith("ppt/media/")]
print("===== MEDIA =====")
for m in sorted(media):
    info = z.getinfo(m)
    with open(os.path.join(outdir, os.path.basename(m)), "wb") as f:
        f.write(z.read(m))
    print(f"{m}\t{info.file_size}")
