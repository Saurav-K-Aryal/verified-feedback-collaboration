"""Small file and validation helpers for a portable, offline evidence audit."""
from pathlib import Path
import csv,gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parents[1]
def read_json(name):
 p=ROOT/name
 with (gzip.open(p,'rt',encoding='utf-8') if p.suffix=='.gz' else p.open()) as f:return json.load(f)
def read_rows(name):
 with gzip.open(ROOT/name,'rt',encoding='utf-8') as f:return [json.loads(s) for s in f if s.strip()]
def write_json(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def write_csv(path,rows):
 if not rows:raise ValueError('No rows to export')
 with Path(path).open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def verify_data():
 checks=read_json('data/SHA256SUMS.json')
 for name,expected in checks.items():
  actual=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
  if actual!=expected:raise ValueError('Evidence checksum mismatch: '+name)
 return len(checks)
def require(condition,message):
 if not condition:raise ValueError(message)
def verify_csv(actual,reference,key):
 with Path(actual).open(newline='') as f:a=list(csv.DictReader(f))
 with Path(reference).open(newline='') as f:b=list(csv.DictReader(f))
 def index(rows):
  result={tuple(r[k] for k in key):r for r in rows}
  require(len(result)==len(rows),'Duplicate comparison key');return result
 aa,bb=index(a),index(b);require(set(aa)==set(bb),'Reference row keys differ: '+Path(actual).name)
 for rowid in aa:
  require(set(aa[rowid])==set(bb[rowid]),'Reference columns differ')
  for field,x in aa[rowid].items():
   y=bb[rowid][field]
   if x==y:continue
   try:ok=math.isclose(float(x),float(y),rel_tol=1e-10,abs_tol=1e-10)
   except (TypeError,ValueError):ok=False
   require(ok,f'Reference value differs: {rowid} / {field}: {x!r} != {y!r}')
 return len(a)

def safe_output(path):
 """Reject locations that could replace repository evidence or source files."""
 path=Path(path).resolve()
 protected=[ROOT/name for name in ['data','provenance','studies','artifact','tests','paper','.github','results/reference']]
 require(path!=ROOT, 'Output must not be the repository root')
 require(path not in ROOT.parents, 'Output must not be a repository ancestor')
 for area in protected:
  area=area.resolve()
  require(path!=area and area not in path.parents and path not in area.parents,
          'Output overlaps protected repository files: '+str(area.relative_to(ROOT)))
 return path
