"""Validierte Datenpakete für zusätzliche Sprachen und lokale Offline-Hilfe."""
import base64,json,os,re,string,tempfile,shutil,time
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import build_opener,HTTPRedirectHandler,ProxyHandler,Request
ROOT=Path(__file__).resolve().parents[1]
MAX_BYTES=3_000_000

class InvalidPack(ValueError):pass

def code_ok(code):return isinstance(code,str) and bool(re.fullmatch(r'[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?',code))
def fields(text):return sorted(field for _,field,_,_ in string.Formatter().parse(text) if field is not None)

class HelpCheck(HTMLParser):
    def handle_starttag(self,tag,attrs):
        if tag not in {'html','head','title','meta','body','main','section','h1','h2','h3','p','ul','ol','li','br','hr','strong','em','code','pre','table','tr','th','td','img','a','span','style'}:
            raise InvalidPack('Invalid language package')
        for name,value in attrs:
            if name.lower().startswith('on') or name in ('srcdoc','http-equiv','style'):raise InvalidPack('Invalid language package')
            if name in ('src','href') and value and not (value.startswith('#') or value.startswith('data:image/png;base64,') or value=='data:image/svg+xml;base64,'+base64.b64encode((ROOT/'assets/docscan.svg').read_bytes()).decode()):
                raise InvalidPack('Invalid language package')
    def handle_data(self,data):
        if re.search(r'@import|url\s*\(\s*[\'"]?(?:https?:|//|file:)|expression\s*\(',data,re.I):
            raise InvalidPack('Invalid language package')

def validate(data):
    reference=json.loads((ROOT/'lang/en.json').read_text())
    if not isinstance(data,dict) or data.get('program_id')!='docscan':raise InvalidPack('Invalid language package')
    code=data.get('code');name=data.get('name');strings=data.get('strings');help_html=data.get('help_html')
    if not code_ok(code) or code in ('de','en') or not isinstance(name,str) or not 0<len(name.strip())<=100:
        raise InvalidPack('Invalid language package')
    if not isinstance(strings,dict) or set(strings)!=set(reference):raise InvalidPack('Incomplete language package')
    for key,value in strings.items():
        if not isinstance(value,str) or not value.strip() or fields(value)!=fields(reference[key]):raise InvalidPack('Invalid language package')
    if not isinstance(help_html,str) or not help_html.strip() or '<h1' not in help_html or '<html' not in help_html:
        raise InvalidPack('Invalid language package')
    HelpCheck().feed(help_html)
    return data

def installed(config):
    result={'de':{'name':'Deutsch'},'en':{'name':'English'}}
    folder=Path(config)/'languages'
    if folder.is_dir() and not folder.is_symlink():
        for child in sorted(folder.iterdir()):
            if not code_ok(child.name) or child.is_symlink():continue
            try:
                path=child/'package.json'
                if path.is_symlink() or path.stat().st_size>MAX_BYTES:continue
                data=validate(json.loads(path.read_text()))
                help_path=child/'index.html'
                if data['code']!=child.name or help_path.is_symlink() or not help_path.is_file() or help_path.read_text()!=data['help_html']:continue
                result[child.name]=data
            except (OSError,ValueError,TypeError):continue
    return result

def install(config,data):
    data=validate(data);base=Path(config)/'languages';target=base/data['code']
    base.mkdir(parents=True,exist_ok=True)
    if base.is_symlink() or target.exists() or target.is_symlink():raise FileExistsError('Language already installed')
    temp=Path(tempfile.mkdtemp(prefix='.import-',dir=base))
    try:
        (temp/'package.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        (temp/'index.html').write_text(data['help_html'])
        for path in temp.iterdir():path.chmod(0o600)
        # Kein vorhandenes Sprachpaket ersetzen, auch nicht bei parallelem Import.
        target.mkdir()
        try:
            for path in temp.iterdir():os.replace(path,target/path.name)
        except BaseException:
            shutil.rmtree(target);raise
    finally:shutil.rmtree(temp)
    return data['code']

def import_file(config,path):
    path=Path(path)
    with path.open('rb') as stream:raw=stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise InvalidPack('Invalid language package')
    return install(config,json.loads(raw))

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise InvalidPack('Invalid GitHub source')

def github_json(url):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ('raw.githubusercontent.com','github.com','api.github.com') or parsed.username or parsed.password or parsed.port not in (None,443):
        raise InvalidPack('Invalid GitHub source')
    opener=build_opener(ProxyHandler({}),NoRedirect())
    with opener.open(Request(url,headers={'User-Agent':'Docscan language packages'}),timeout=15) as response:
        data=bytearray();start=time.monotonic()
        while chunk:=response.read(65536):
            data.extend(chunk)
            if len(data)>MAX_BYTES or time.monotonic()-start>20:raise InvalidPack('Invalid language package')
        return json.loads(data)

def catalog(base):
    data=github_json(base.rstrip('/')+'/catalog.json')
    if not isinstance(data,dict) or data.get('program_id')!='docscan' or not isinstance(data.get('languages'),list) or len(data['languages'])>200:
        raise InvalidPack('Invalid language package')
    seen=set();entries=[]
    for entry in data['languages']:
        if not isinstance(entry,dict):raise InvalidPack('Invalid language package')
        code=entry.get('code');name=entry.get('name')
        if not code_ok(code) or code in seen or not isinstance(name,str) or not 0<len(name.strip())<=100:raise InvalidPack('Invalid language package')
        seen.add(code)
        if code not in ('de','en'):entries.append({'code':code,'name':name})
    return entries

def download(config,base,code):
    if not code_ok(code):raise InvalidPack('Invalid language package')
    data=github_json(base.rstrip('/')+'/'+code+'.json')
    if not isinstance(data,dict) or data.get('code')!=code:raise InvalidPack('Invalid language package')
    return install(config,data)
