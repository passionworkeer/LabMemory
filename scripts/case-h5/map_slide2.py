import zipfile, re
from xml.etree import ElementTree as ET

pptx = "/Users/wangjianjun/me/LabMemory/LabMemory晶研智流-12强答辩优化版 (2).pptx"
z = zipfile.ZipFile(pptx)
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

rels = z.read("ppt/slides/_rels/slide2.xml.rels").decode()
rid_map = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="\.\./media/([^"]+)"', rels))

root = ET.fromstring(z.read("ppt/slides/slide2.xml"))

def texts_of(el):
    out = []
    for t in el.iter(f"{{{A}}}t"):
        if t.text and t.text.strip():
            out.append(t.text.strip())
    return out

# 遍历所有 grpSp，输出每个组内的图片与文字
def walk(el, depth=0):
    for child in el:
        tag = child.tag.split("}")[-1]
        if tag == "grpSp":
            pics = []
            for pic in child.iter(f"{{{P}}}pic"):
                blip = pic.find(f".//{{{A}}}blip")
                if blip is not None:
                    rid = blip.get(f"{{{R}}}embed")
                    pics.append(rid_map.get(rid))
            big = [p for p in pics if p and re.match(r"image1[234]", p)]
            if big:
                print(f"组(深度{depth}) 图片: {big}")
                print(f"  组内文字: {texts_of(child)[:12]}")
            walk(child, depth + 1)

walk(root)
