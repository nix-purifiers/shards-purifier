# SPDX-License-Identifier: MIT
import base64,hashlib,json,re
from pathlib import Path
import yaml
FIX='; run shards-purifier lock'
NAME=r'[A-Za-z0-9][A-Za-z0-9_-]*'
def canonical(data):return json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def seal(data):
 result={key:value for key,value in data.items() if key!='contentHash'}
 return {**result,'contentHash':hashlib.sha256(canonical(result).encode()).hexdigest()}
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def relative(value):return isinstance(value,str) and bool(value) and not value.startswith('/') and '\\' not in value and all(p not in ('','.','..') for p in value.split('/'))
def inputs(root):return [{'path':name,'hash':digest(root/name) if (root/name).is_file() else None} for name in ['shard.yml','shard.override.yml']]
def native(text):
 data=yaml.load(text,Loader=yaml.BaseLoader)
 if not isinstance(data,dict) or str(data.get('version')) not in ('1.0','2.0') or not isinstance(data.get('shards'),dict):raise ValueError('invalid native Shards lock'+FIX)
 if any(not isinstance(name,str) or not re.fullmatch(NAME,name) for name in data['shards']):raise ValueError('invalid native Shards package name'+FIX)
 return {'version':'2.0','shards':data['shards']}
def native_text(data):
 # JSON-quoted scalars are native YAML scalars. This stable spelling lets the
 # pure Nix reader verify every native pin without a separate YAML evaluator.
 text='version: "2.0"\nshards:'
 if not data['shards']:return text+' {}\n'
 text+='\n'
 for name,dep in sorted(data['shards'].items()):
  text+='  '+canonical(name)+':\n    git: '+canonical(dep['git'])+'\n    version: '+canonical(dep['version'])+'\n'
 return text
def problems(root,path,data):
 try:
  if not isinstance(data,dict) or data.get('version')!=1:return ['unsupported companion format'+FIX]
  if data.get('contentHash')!=seal(data)['contentHash']:return ['companion contentHash mismatch'+FIX]
  if data.get('inputs')!=inputs(root):return ['project manifests changed'+FIX]
  if data.get('manifest')!=(root/'shard.yml').read_text():return ['native manifest snapshot changed'+FIX]
  text=path.read_text();pinned=native(text)
  if data.get('nativeHash')!=digest(path) or data.get('nativeLock')!=text:return ['native Shards lock changed'+FIX]
  if native_text(pinned)!=text:return ['noncanonical native pin export'+FIX]
  if not isinstance(data.get('dependencies'),list):return ['missing native source graph'+FIX]
  names=set()
  for dep in data['dependencies']:
   if not isinstance(dep,dict) or not re.fullmatch(NAME,dep.get('name','')) or dep['name'] in names:raise ValueError('invalid native dependency name')
   names.add(dep['name']);source=dep['git']
   if not isinstance(source,dict) or not isinstance(source.get('url'),str) or not re.fullmatch('[0-9a-f]{40}',source.get('rev','')):raise ValueError('invalid Git source')
   if source.get('leaveDotGit') is not True or source.get('submodules') is not False:raise ValueError('invalid native Git cache policy')
   if not re.fullmatch('sha256-[A-Za-z0-9+/]{43}=',dep.get('hash','')) or not relative(dep.get('cachePath')):raise ValueError('invalid source hash/cache path')
   if not isinstance(dep.get('aliases'),list) or any(not isinstance(a,str) or not a.startswith(('refs/heads/','refs/tags/')) or '..' in a for a in dep['aliases']):raise ValueError('invalid native Git aliases')
   raw=base64.b64decode(source['commitObject']['object'],validate=True)
   if hashlib.sha1(b'commit '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=source['rev']:raise ValueError('raw Git commit does not match revision')
   if pinned['shards'].get(dep['name'])!={'git':source['url'],'version':dep['version']} or not dep['version'].endswith('+git.commit.'+source['rev']):raise ValueError('native pin does not match source export')
  if names!=set(pinned['shards']):raise ValueError('incomplete native source graph')
  if not isinstance(data.get('targets'),list) or any(not isinstance(name,str) or not re.fullmatch(NAME,name) for name in data['targets']):raise ValueError('invalid native application targets')
  return []
 except (OSError,ValueError,TypeError,KeyError,AttributeError,yaml.YAMLError) as error:return [str(error)+FIX]
