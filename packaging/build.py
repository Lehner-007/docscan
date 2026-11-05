"""Expliziter Laufzeitumfang für DEB, Benutzer-ZIP und öffentliche Quellen."""
import argparse,ast,hashlib,json,os,re,shutil,subprocess,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def version():
    value=(ROOT/'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',value):raise ValueError('Ungültige VERSION')
    return value

def files(source=False):
    selected=['VERSION','LICENSE','README.md','projekt.json','RELEASE_NOTES.md']
    selected += [str(p.relative_to(ROOT)) for folder in ('assets','lang','help','python')
                 for p in sorted((ROOT/folder).rglob('*'))
                 if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'
                 and (source or not p.name.startswith('test_'))]
    if source:
        selected+=['start.sh','erstelledeb.sh','erstellezip.sh','erstellegithub.sh','erstellesprachen.sh','.gitignore']
        selected += [str(p.relative_to(ROOT)) for folder in ('packaging','tests/sane','.github/workflows','publishing/languages') for p in sorted((ROOT/folder).rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
    for name in selected:
        path=ROOT/name
        if path.is_symlink() or not path.is_file():raise ValueError('Unsichere/fehlende Paketquelle: '+name)
        if any(part in ('.env','.pw.md','.config') for part in path.parts):raise ValueError('Verbotene Paketquelle: '+name)
        if path.suffix in ('.py','.sh','.md','.json'):
            text=path.read_text()
            if re.search(r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}',text):
                raise ValueError('Mögliches Geheimnis in '+name)
    if (ROOT/'.env').exists():raise ValueError('.env im Projektordner')
    if any(p.name=='.env' for folder in ('python','packaging') for p in (ROOT/folder).rglob('*')):
        raise ValueError('.env im Quellbereich')
    return sorted(set(selected))

def stage_package(stage):
    v=version();stage.mkdir();app=stage/'usr/share/docscan'
    for name in files():
        target=app/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    launcher=stage/'usr/bin/docscan';launcher.parent.mkdir(parents=True)
    launcher.write_text('#!/bin/sh\nexec /usr/bin/python3 -B /usr/share/docscan/python/docscan.py "$@"\n')
    lifecycle=(ROOT/'packaging/desktop_lifecycle.py').read_text()
    tree=ast.parse(lifecycle)
    desktop=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DESKTOP' for t in n.targets))+'X-Docscan-Managed=true\n'
    entry=stage/'usr/share/applications/docscan.desktop';entry.parent.mkdir(parents=True);entry.write_text(desktop)
    doc=stage/'usr/share/doc/docscan';doc.mkdir(parents=True)
    shutil.copyfile(ROOT/'LICENSE',doc/'copyright');shutil.copyfile(ROOT/'README.md',doc/'README.md')
    control=stage/'DEBIAN';control.mkdir()
    size=sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())
    (control/'control').write_text(f'''Package: docscan
Version: {v}
Section: graphics
Priority: optional
Architecture: all
Maintainer: Josef
Installed-Size: {(size+1023)//1024}
Depends: python3 (>= 3.10), python3-gi, python3-pil, gir1.2-gtk-4.0 (>= 4.8), sane-utils, util-linux
Description: GTK4 document scanner using SANE
 Scan single pages, complete feeders and multiple flatbed originals.
 Includes German and English interfaces and local help.
''')
    for hook,condition in [('postinst',"action != 'configure'"),('prerm',"action != 'remove'"),('postrm',"action != 'purge'")]:
        (control/hook).write_text(lifecycle.replace("action not in ('configure', 'remove', 'purge')",condition))
    (control/'md5sums').write_text(''.join(f'{hashlib.md5(p.read_bytes()).hexdigest()}  {p.relative_to(stage)}\n' for p in sorted(stage.rglob('*')) if p.is_file() and control not in p.parents))
    for path in stage.rglob('*'):path.chmod(0o755 if path.is_dir() else 0o644)
    for path in (launcher,control/'postinst',control/'prerm',control/'postrm'):path.chmod(0o755)
    subprocess.run(['desktop-file-validate',str(entry)],check=True)
    return v

def main():
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['deb','zip','source','languages']);args=parser.parse_args()
    v=version();out=ROOT/'dist';out.mkdir(exist_ok=True);work=ROOT/'work';work.mkdir(exist_ok=True)
    name=f'docscan_{v}_all.deb' if args.kind=='deb' else f'docscan-{v}'+('-source' if args.kind=='source' else '-languages' if args.kind=='languages' else '')+'.zip'
    target=out/name
    if target.exists():raise FileExistsError(target)
    with tempfile.TemporaryDirectory(dir=work,prefix='package-') as temporary:
        built=Path(temporary)/name
        if args.kind=='deb':
            stage=Path(temporary)/'stage';stage_package(stage)
            subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(built)],check=True)
        else:
            names=[str(p.relative_to(ROOT)) for p in sorted((ROOT/'publishing/languages').glob('*.json'))] if args.kind=='languages' else files(args.kind=='source')
            if not names:raise ValueError('Keine Paketquellen')
            with zipfile.ZipFile(built,'w',zipfile.ZIP_DEFLATED) as archive:
                for name in names:archive.write(ROOT/name,'docscan/'+name)
            with zipfile.ZipFile(built) as archive:
                if archive.testzip() is not None:raise ValueError('ZIP-Integritätsfehler')
        # Kein stilles Überschreiben, auch bei konkurrierenden Aufrufen.
        os.link(built,target)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    checksum=target.with_name(target.name+'.sha256')
    with checksum.open('x') as stream:stream.write(digest+'  '+target.name+'\n')
    print(target)

if __name__=='__main__':main()
