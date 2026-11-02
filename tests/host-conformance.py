#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Resolve native Git shards, then build with their origins unavailable."""
import json,os,shutil,socket,subprocess,sys,tarfile,tempfile,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
def run(args,**kwargs):
 result=subprocess.run(list(map(str,args)),text=True,**kwargs)
 if result.returncode:
  if result.stdout:print(result.stdout,file=sys.stderr)
  if result.stderr:print(result.stderr,file=sys.stderr)
  result.check_returncode()
 return result
case=sys.argv[1]
with tempfile.TemporaryDirectory(prefix='shards-conformance-') as temporary:
 temp=Path(temporary);cli=temp/'cli';run(['nix','build',str(REPO)+'#cli','--out-link',cli])
 helper=cli/'bin/shards-purifier';root=temp/'project';root.mkdir();repos=temp/'repos';repos.mkdir()
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 daemon=subprocess.Popen(['git','daemon','--reuseaddr','--export-all','--listen=127.0.0.1','--port='+str(port),'--base-path='+str(repos),str(repos)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 def git(directory,*args):return run(['git','-C',directory,*args],capture_output=True).stdout.strip()
 def release(name,version,value):
  repo=repos/name
  if not repo.exists():repo.mkdir();git(repo,'init','-b','main')
  (repo/'src').mkdir(exist_ok=True)
  (repo/'shard.yml').write_text('name: '+name+'\nversion: '+version+'\n')
  (repo/'src'/(name+'.cr')).write_text('module '+name.title()+'\n  VALUE = "'+value+'"\nend\n')
  git(repo,'add','.');git(repo,'-c','user.name=purifier-test','-c','user.email=fixture@example.invalid','commit','-m',version);git(repo,'tag','v'+version)
 try:
  for name in ('first','second'):release(name,'1.0.0','one')
  for attempt in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=0.1):break
   except OSError:time.sleep(0.05)
  (root/'shard.yml').write_text('name: consumer\nversion: 0.1.0\ntargets:\n  hello:\n    main: src/main.cr\ndependencies:\n'+''.join('  '+name+':\n    git: git://127.0.0.1:'+str(port)+'/'+name+'\n' for name in ('first','second')))
  (root/'src').mkdir();(root/'src/main.cr').write_text('require "first"\nrequire "second"\nputs First::VALUE + "-" + Second::VALUE\nputs ARGV.join("|") unless ARGV.empty?\n')
  args=[helper,'--project',root];native=root/'shard.lock';companion=root/'shards-purifier.lock.json'
  run([*args,'lock']);initial=companion.read_bytes();initial_native=native.read_bytes()
  run([*args,'lock']);assert companion.read_bytes()==initial and native.read_bytes()==initial_native
  for name in ('first','second'):release(name,'2.0.0','two')
  expected='one-one'
  if case=='update':
   run([*args,'update','first']);selected=json.loads(companion.read_text())
   assert {d['name']:d['version'].split('+')[0] for d in selected['dependencies']}=={'first':'2.0.0','second':'1.0.0'}
   run([*args,'update']);expected='two-two'
  elif case=='relock':
   damaged=json.loads(initial);damaged['contentHash']='bad';companion.write_text(json.dumps(damaged));run([*args,'lock']);assert native.read_bytes()==initial_native
   native.write_text('invalid native YAML');run([*args,'lock']);assert native.read_bytes()==initial_native
  elif case=='external':
   external=temp/'external';external.mkdir();selected=external/'companion.json';external_native=external/'native.lock'
   args=[helper,'--project',root,'--lockfile',selected,'--tool-lockfile',external_native]
   run([*args,'lock']);assert companion.read_bytes()==initial and native.read_bytes()==initial_native
   companion.unlink();native.write_text('intentionally invalid working lock\n')
   os.environ['SHARDS_PURIFIER_LOCKFILE']=str(selected);os.environ['SHARDS_PURIFIER_TOOL_LOCKFILE']=str(external_native)
  elif case!='native':raise ValueError(case)
  run([*args,'prefetch']);daemon.terminate();daemon.wait(timeout=10)
  run([cli/'bin/shards','check'],cwd=root)
  run([cli/'bin/shards','build'],cwd=root)
  output=run([cli/'bin/shards','run','hello','--','kept-argument'],cwd=root,capture_output=True)
  assert output.stdout.strip().endswith(expected+'\nkept-argument'),(output.stdout,output.stderr)
  assert '--local --frozen' not in output.stderr,output.stderr
  if case=='external':assert native.read_text()=='intentionally invalid working lock\n'
  if case=='native':
   (root/'shard.yml').write_text((root/'shard.yml').read_text()+'# changed manifest\n')
   stale=subprocess.run([str(cli/'bin/shards'),'check'],cwd=root,text=True,capture_output=True)
   assert stale.returncode and 'manifests changed' in stale.stderr,stale.stderr
   (root/'shard.yml').write_text((root/'shard.yml').read_text().removesuffix('# changed manifest\n'))
   fake=temp/'gh';record=temp/'gh-calls.jsonl'
   fake.write_text('#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\na=sys.argv[1:]\np=Path('+repr(str(record))+')\nwith p.open("a") as f:f.write(json.dumps(a)+"\\n")\nif a[:2]==["release","view"]:sys.exit(0 if len(p.read_text().splitlines())>2 else 1)\n')
   fake.chmod(0o755)
   for _ in range(2):run([*args,'publish','--repo','fixture/project','--tag','v0.1.0'],env={**os.environ,'SHARDS_PURIFIER_GH':str(fake)})
   calls=[json.loads(line) for line in record.read_text().splitlines()]
   assert calls[1][:2]==['release','create'] and calls[3][:2]==['release','upload'],calls
   archive=Path(next(value for value in calls[1] if value.endswith('/project.tar.gz')))
   with tarfile.open(archive) as release_archive:assert {'./shard.yml','./shard.lock','./shards-purifier.lock.json'}<=set(release_archive.getnames())
   empty=temp/'unlocked';empty.mkdir()
   fallback=run([cli/'bin/shards','--version'],cwd=empty,capture_output=True)
   assert 'ordinary impure shards' in fallback.stderr and not (empty/'shards-purifier.lock.json').exists()
   (empty/'fallback.cr').write_text('puts ARGV.join("|")\nputs STDIN.gets\nexit 7\n')
   fallback=subprocess.run([str(cli/'bin/crystal'),'run','fallback.cr','--','forwarded'],cwd=empty,input='input preserved\n',text=True,capture_output=True)
   assert fallback.returncode==7 and fallback.stdout=='forwarded\ninput preserved\n' and 'ordinary impure crystal' in fallback.stderr,(fallback.returncode,fallback.stdout,fallback.stderr)
  print('Shards native conformance passed:',case)
 finally:
  if daemon.poll() is None:daemon.terminate();daemon.wait(timeout=10)
