"""Read-only public-source collector; never executes downloaded repository code."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json, sys, urllib.request, datetime, re, html
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent

def collect(job):
    name, url = job['name'], job['url']
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Research-source-audit/1.0'})
        with urllib.request.urlopen(req, timeout=45) as response:
            data = response.read()
        dest = ROOT / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        result = {'name':name,'url':url,'bytes':len(data),'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        if name.endswith('.pdf'):
            pdf = PdfReader(dest)
            text = '\n\n'.join(f'=== PAGE {i+1} ===\n'+(page.extract_text() or '') for i,page in enumerate(pdf.pages))
            dest.with_suffix('.txt').write_text(text,encoding='utf-8',errors='replace')
            result['pages'] = len(pdf.pages)
        elif name.endswith('.html'):
            raw = data.decode('utf-8',errors='replace')
            text = html.unescape(re.sub('<[^>]+>','\n',raw))
            dest.with_suffix('.txt').write_text(text,encoding='utf-8',errors='replace')
            result['links'] = [html.unescape(u) for u in re.findall(r'href=[\"\x27]([^\"\x27]+)',raw) if any(s in u for s in ['github.com','arxiv.org','.pdf','openreview'])][:30]
        return result
    except Exception as e:
        return {'name':name,'url':url,'error':str(e)}

if __name__ == '__main__':
    jobs = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(collect,jobs):
            with (ROOT/'fetch_manifest.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps(result,ensure_ascii=False)+'\n')
            print(json.dumps(result,ensure_ascii=True),flush=True)
