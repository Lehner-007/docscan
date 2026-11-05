"""SANE über scanimage; Scannerzugriffe ausschließlich in Hintergrundaufträgen."""
import os,re,shutil,subprocess,threading,time
from pathlib import Path
from PIL import Image

class ScanError(RuntimeError):
    def __init__(self,message,pages=None):
        super().__init__(message);self.pages=pages or []
class Cancelled(ScanError):pass

def run(args,cancel,*,output=None,timeout=30,env=None,poll=None):
    executable=shutil.which('scanimage')
    if not executable:raise ScanError('scanimage_missing')
    import tempfile
    # Diagnoseausgabe auf Datei begrenzen, stdout bei Scans direkt auf Bilddatei.
    with tempfile.TemporaryFile() as err:
        p=subprocess.Popen([executable,*args],stdout=output or subprocess.PIPE,stderr=err,env=env)
        start=time.monotonic()
        try:
            while True:
                if poll:poll()
                if cancel.is_set():raise Cancelled('cancelled')
                if time.monotonic()-start>timeout:raise ScanError('timeout')
                try:
                    stdout,_=p.communicate(timeout=.1);break
                except subprocess.TimeoutExpired:continue
        except BaseException:
            p.terminate()
            try:p.wait(2)
            except subprocess.TimeoutExpired:p.kill();p.wait()
            raise
        err.seek(0);diagnostic=err.read(12000).decode(errors='replace').strip()
        return p.returncode,(stdout or b'').decode(errors='replace'),diagnostic

def discover(cancel,env=None):
    code,out,err=run(['--formatted-device-list=%d\t%v %m%n'],cancel,env=env)
    if code:raise ScanError(err or 'discovery_failed')
    return [tuple(line.split('\t',1)) for line in out.splitlines() if '\t' in line]

def options(device,cancel,env=None):
    code,out,err=run(['--device-name',device,'--all-options'],cancel,env=env)
    if code:raise ScanError(err or 'options_failed')
    result={'modes':[],'sources':[],'resolution':None,'diagnostic':out}
    for key,dest in [('mode','modes'),('source','sources')]:
        m=re.search(r'^\s+--'+key+r'\s+(.+)',out,re.M)
        if m:
            values=re.sub(r'\s+\[.*','',m[1]).strip()
            if '|' in values:result[dest]=values.split('|')
            elif values and not values.startswith(('<','[')):result[dest]=[values]
    m=re.search(r'^\s+--resolution\s+(\d+)\.\.(\d+)',out,re.M)
    if m:result['resolution']=(int(m[1]),int(m[2]),None)
    else:
        m=re.search(r'^\s+--resolution\s+([\d|]+)dpi',out,re.M)
        if m:
            values=[int(x) for x in m[1].split('|')];result['resolution']=(min(values),max(values),values)
    return result

def pnm_state(path):
    """Vollständige Rasterzeilen einer noch wachsenden binären PNM-Datei."""
    with path.open('rb') as stream:
        header=stream.read(4096)
    tokens=[];offset=0
    while len(tokens)<4:
        while offset<len(header) and header[offset] in b' \t\r\n':offset+=1
        if offset>=len(header):return None
        if header[offset]==35:
            end=header.find(b'\n',offset)
            if end<0:return None
            offset=end+1;continue
        start=offset
        while offset<len(header) and header[offset] not in b' \t\r\n':offset+=1
        if offset==len(header):return None
        tokens.append(header[start:offset])
        if len(tokens)==3 and tokens[0]==b'P4':break
    if tokens[0] not in (b'P4',b'P5',b'P6'):return None
    try:
        width,height=map(int,tokens[1:3]);maximum=int(tokens[3]) if len(tokens)==4 else 1
    except ValueError:return None
    if not (0<width<=200000 and 0<height<=200000 and 0<maximum<=65535):return None
    # Genau den Headerabschluss verbrauchen, niemals weiße Rasterpixel überspringen.
    offset+=2 if header[offset:offset+2]==b'\r\n' else 1
    channels=3 if tokens[0]==b'P6' else 1
    rowbytes=(width+7)//8 if tokens[0]==b'P4' else width*channels*(2 if maximum>255 else 1)
    rows=min(height,max(0,path.stat().st_size-offset)//rowbytes)
    return width,height,maximum,tokens[0],offset,rowbytes,rows

def pnm_preview(path,state):
    """Zeilenweise verkleinerte Vorschau; Speicher bleibt unabhängig von der DPI klein."""
    width,height,maximum,kind,offset,rowbytes,rows=state
    factor=min(1,700/max(width,height));size=(max(1,int(width*factor)),max(1,int(height*factor)))
    image=Image.new('RGB',size,'white')
    with path.open('rb') as stream:
        for y in range(size[1]):
            source_y=min(height-1,int(y/factor))
            if source_y>=rows:break
            stream.seek(offset+source_y*rowbytes);raw=stream.read(rowbytes)
            if len(raw)!=rowbytes:break
            if kind==b'P4':
                line=Image.frombytes('1',(width,1),raw).convert('RGB')
                # PBM: Bit 1 bedeutet schwarz, Pillow-Modus 1 dagegen weiß.
                from PIL import ImageChops
                line=ImageChops.invert(line)
            else:
                if maximum>255:raw=raw[::2]
                line=Image.frombytes('RGB' if kind==b'P6' else 'L',(width,1),raw).convert('RGB')
            image.paste(line.resize((size[0],1)),(0,y))
    return image

def scan(device,mode,source,dpi,count,directory,cancel,progress,env=None,preview=None):
    if cancel.is_set():return [],True
    directory=Path(directory)
    args=['--device-name',device,'--format=pnm',f'--batch={directory}/scan-%04d.pnm']
    if count is not None:args+=[f'--batch-count={count}']
    if mode:args+=['--mode',mode]
    if source:args+=['--source',source]
    if dpi is not None:args+=['--resolution',str(dpi)]
    stopped=False;failure=None;last_preview=0;last_state=None
    def poll(force=False):
        nonlocal last_preview,last_state
        paths=sorted(directory.glob('scan-*.pnm*'));completed=0;current=None
        for index,path in enumerate(paths):
            try:state=pnm_state(path)
            except FileNotFoundError:continue  # scanimage benennt .part atomar um.
            if state and state[-1]==state[1]:completed+=1
            if state:current=(index,path,state)
        progress(completed,count or 0)
        if preview and current:
            index,path,state=current;key=(index,state[-1]);now=time.monotonic()
            if key!=last_state and (force or now-last_preview>=.4):
                try:image=pnm_preview(path,state)
                except FileNotFoundError:return
                preview(image,state[-1]/state[1],index+1,count or 0)
                last_preview=now;last_state=key
    try:
        code,out,err=run(args,cancel,timeout=300*count if count is not None else 3600,env=env,
                         poll=poll)
        poll(force=True)
    except Cancelled:stopped=True;code=0;err=''
    except ScanError as exc:failure=exc;code=0;err=''
    pages=[]
    for path in sorted(directory.glob('scan-*.pnm')):
        try:
            with Image.open(path) as image:
                image.load();pages.append(image.convert('RGB'))
        except (OSError,ValueError):
            if not stopped and failure is None:raise ScanError('incomplete_page',pages)
    if failure:raise ScanError(str(failure),pages)
    if code and not (code==7 and (pages or count is None)):raise ScanError(err or f'SANE exit {code}',pages)
    return pages,stopped
