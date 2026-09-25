"""Copy manifest notes into an exported PPTX without changing its slide artwork."""
import json
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

manifest_path, input_path, output_path = map(Path, sys.argv[1:])
assert input_path.resolve() != output_path.resolve(), "Use a separate output file"
slides = sorted(json.loads(manifest_path.read_text()), key=lambda s: s["position"])
ns = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}
for prefix, uri in ns.items():
    ET.register_namespace(prefix, uri)

replacements = {}
with zipfile.ZipFile(input_path) as source:
    for index, slide in enumerate(slides, 1):
        path = f"ppt/notesSlides/notesSlide{index}.xml"
        root = ET.fromstring(source.read(path))
        bodies = [
            shape.find("p:txBody", ns)
            for shape in root.findall(".//p:sp", ns)
            if shape.find("p:nvSpPr/p:nvPr/p:ph[@type='body']", ns) is not None
        ]
        assert len(bodies) == 1 and bodies[0] is not None
        body = bodies[0]
        for paragraph in body.findall("a:p", ns):
            body.remove(paragraph)
        notes = slide["speakerNotes"].strip()
        assert notes, f"Missing notes on slide {index}"
        for text in notes.split("\n"):
            paragraph = ET.SubElement(body, f"{{{ns['a']}}}p")
            run = ET.SubElement(paragraph, f"{{{ns['a']}}}r")
            ET.SubElement(run, f"{{{ns['a']}}}t").text = text
        replacements[path] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            target.writestr(item, replacements.get(item.filename, source.read(item.filename)))

with zipfile.ZipFile(output_path) as result, zipfile.ZipFile(input_path) as source:
    for index, slide in enumerate(slides, 1):
        root = ET.fromstring(result.read(f"ppt/notesSlides/notesSlide{index}.xml"))
        assert slide["speakerNotes"] in "".join(root.itertext())
    for name in source.namelist():
        if name not in replacements:
            assert result.read(name) == source.read(name), f"Unexpected change: {name}"
print(f"Verified notes on all {len(slides)} slides; all other PPTX content unchanged.")