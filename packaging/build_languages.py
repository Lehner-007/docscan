"""Acht getrennte GitHub-Sprachpakete; das DE/EN-Basispaket bleibt unverändert."""
import base64,csv,hashlib,html,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
import language_packs
NAMES={'ar':'العربية','es':'Español','fr':'Français','hi':'हिन्दी','pt':'Português','ru':'Русский','tr':'Türkçe','zh':'中文'}

def build():
    reference=json.loads((ROOT/'lang/en.json').read_text())
    translations={code:{} for code in NAMES}
    with (ROOT/'packaging/translations.tsv').open(newline='') as stream:
        for row in csv.DictReader(stream,delimiter='\t'):
            if row['key'] not in reference:raise ValueError('Unbekannter Schlüssel: '+row['key'])
            for code in NAMES:
                value=row[code]
                if value is None or not value.strip():raise ValueError('Fehlende Übersetzung: '+code+' / '+row['key'])
                if row['key'] in translations[code]:raise ValueError('Doppelter Schlüssel')
                translations[code][row['key']]=value
    help_texts=json.loads((ROOT/'packaging/help_texts.json').read_text())
    logo='data:image/svg+xml;base64,'+base64.b64encode((ROOT/'assets/docscan.svg').read_bytes()).decode()
    watermark='data:image/png;base64,'+base64.b64encode((ROOT/'assets/report_watermark.png').read_bytes()).decode()
    output=ROOT/'publishing/languages';output.mkdir(parents=True,exist_ok=True)
    catalog=[]
    for code,name in NAMES.items():
        text=help_texts[code];direction='rtl' if code=='ar' else 'ltr'
        css='body{font:17px sans-serif;line-height:1.7;max-width:900px;margin:32px auto;padding:20px;color:#17232e;background:#f6f8fa}body:before{content:"";position:fixed;inset:10%;background:url('+watermark+') center/contain no-repeat;opacity:.06;z-index:-1}img{width:100px}h1,h2{color:#175b73}'
        help_html=f'<!doctype html><html lang="{code}" dir="{direction}"><head><meta charset="utf-8"><title>{html.escape(text[0])}</title><style>{css}</style></head><body><h1>{html.escape(text[0])}</h1><img src="{logo}" alt="Docscan">'
        for i in range(1,len(text),2):help_html+=f'<h2>{html.escape(text[i])}</h2><p>{html.escape(text[i+1])}</p>'
        help_html+='</body></html>'
        data={'program_id':'docscan','code':code,'name':name,'strings':translations[code],'help_html':help_html}
        language_packs.validate(data)
        path=output/(code+'.json');path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        catalog.append({'code':code,'name':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (output/'catalog.json').write_text(json.dumps({'program_id':'docscan','languages':catalog},ensure_ascii=False,indent=2)+'\n')
    print(f'{len(catalog)} Sprachpakete mit je {len(reference)} Texten und Offline-Hilfe geprüft.')

if __name__=='__main__':build()
