"""Seiten, sichere Exporte und Wiederherstellung des offenen Dokuments."""
from pathlib import Path
import json,os,tempfile,uuid
from PIL import Image,ImageOps,ImageSequence

def load_images(path):
    with Image.open(path) as image:
        pages=[]
        for frame in ImageSequence.Iterator(image):
            frame.load();pages.append(ImageOps.exif_transpose(frame).convert('RGB'))
        return pages

def export(pages,path,kind,dpi=300):
    path=Path(path)
    if not pages:raise ValueError('no_pages')
    if kind!='PDF' and len(pages)!=1:raise ValueError('one_image_only')
    fd,temp=tempfile.mkstemp(prefix='.docscan-',dir=path.parent);os.close(fd)
    try:
        if kind=='PDF':pages[0].save(temp,format='PDF',save_all=True,append_images=pages[1:],resolution=dpi)
        else:pages[0].save(temp,format=kind,dpi=(dpi,dpi))
        # Kein bestehendes Ziel überschreiben, auch bei konkurrierendem Dateizugriff.
        os.link(temp,path)
    finally:Path(temp).unlink(missing_ok=True)

def save_session(pages,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    old=list(directory.glob('page-*.png'));names=[]
    for image in pages:
        name='page-'+uuid.uuid4().hex+'.png';image.save(directory/name);os.chmod(directory/name,0o600);names.append(name)
    manifest=directory/'session.json';tmp=directory/'session.tmp'
    tmp.write_text(json.dumps({'version':1,'pages':names}));tmp.chmod(0o600);os.replace(tmp,manifest)
    for path in old:path.unlink(missing_ok=True)

def restore(directory):
    directory=Path(directory);manifest=directory/'session.json'
    if not manifest.exists():return []
    data=json.loads(manifest.read_text());pages=[]
    if data.get('version')!=1 or not isinstance(data.get('pages'),list):raise ValueError('invalid_session')
    for name in data['pages']:
        import re
        if not isinstance(name,str) or not re.fullmatch(r'page-[0-9a-f]{32}\.png',name):raise ValueError('invalid_session')
        pages.extend(load_images(directory/name))
    return pages
