# SPDX-License-Identifier: MIT
import argparse,fcntl,hashlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path
import yaml
from . import lock,git_sources,prepare
SHARDS=os.environ.get('SHARDS_PURIFIER_SHARDS','shards')
CRYSTAL=os.environ.get('SHARDS_PURIFIER_CRYSTAL','crystal')
def run(args,**kwargs):return subprocess.run(list(map(str,args)),check=True,**kwargs)
def write(path,text):
 path.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',dir=path.parent,delete=False) as stream:stream.write(text);temporary=Path(stream.name)
 temporary.replace(path)
def versions():return {'shards':os.environ['SHARDS_PURIFIER_SHARDS_VERSION'],'crystal':os.environ['SHARDS_PURIFIER_CRYSTAL_VERSION'],'resolver':hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))).hexdigest()}
def environment():
 result=dict(os.environ)
 for key in ('SHARDS_OPTS','SHARDS_OVERRIDE','SHARDS_INSTALL_PATH','SHARDS_BIN_PATH','SHARDS_PURIFIER_OFFLINE','CRYSTAL_VERSION','GIT_CONFIG_COUNT'):result.pop(key,None)
 result.update(CRYSTAL=CRYSTAL,GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1')
 return result
def do_lock(root,native,sidecar,update=False,names=()):
 previous=None
 if sidecar.is_file():
  try:
   candidate=json.loads(sidecar.read_text())
   if isinstance(candidate,dict) and candidate.get('contentHash')==lock.seal(candidate)['contentHash']:previous=candidate
   if not update and candidate.get('toolVersions')==versions() and not lock.problems(root,native,candidate):
    print('Existing native Shards resolution retained',file=sys.stderr);return
  except (ValueError,OSError,AttributeError,TypeError):pass
 if names and (not previous or any(name not in {d['name'] for d in previous['dependencies']} for name in names)):raise ValueError('named updates require existing locked dependencies'+lock.FIX)
 with tempfile.TemporaryDirectory(prefix='shards-purifier-lock-') as temporary:
  temp=Path(temporary);stage=temp/'project'
  shutil.copytree(root,stage,ignore=shutil.ignore_patterns('.git','.shards-purifier','lib','bin','result','__pycache__'))
  staged=stage/'shard.lock';prior=native if native.exists() else root/'shard.lock'
  seeded=False
  if prior.is_file():
   try:lock.native(prior.read_text());shutil.copyfile(prior,staged);seeded=True
   except (ValueError,yaml.YAMLError):pass
  if not seeded and previous and previous.get('inputs')==lock.inputs(root):
   recovery=previous.get('nativeLock','')
   try:lock.native(recovery);write(staged,recovery);seeded=True
   except (ValueError,yaml.YAMLError):pass
  if not seeded and staged.exists():staged.unlink()
  env={**environment(),'HOME':str(temp/'home'),'XDG_CACHE_HOME':str(temp/'xdg'),'CRYSTAL_CACHE_DIR':str(temp/'compiler'),'SHARDS_CACHE_PATH':str(temp/'cache'),'SHARDS_INSTALL_PATH':str(temp/'lib'),'SHARDS_BIN_PATH':str(temp/'bin'),'SHARDS_PURIFIER_NATIVE_LOCKFILE':str(staged)}
  Path(env['HOME']).mkdir();cache=Path(env['SHARDS_CACHE_PATH']);cache.mkdir()
  command=[SHARDS,'update',*names] if update else [SHARDS,'install']
  run([*command,'--skip-postinstall','--skip-executables'],cwd=stage,env=env,stdout=sys.stderr)
  selected=lock.native(staged.read_text())
  manifest=yaml.load((stage/'shard.yml').read_text(),Loader=yaml.BaseLoader)
  if (stage/'shard.override.yml').exists():raise ValueError('project dependency overrides need explicit source validation; not supported yet')
  dependencies=git_sources.export(selected,cache,temp,manifest)
  native_text=lock.native_text(selected)
  # This is Shards' native Git-commit version syntax, including semantic versions
  # which upstream ordinarily serializes as mutable tag names.
  write(staged,native_text)
  info=Path(env['SHARDS_INSTALL_PATH'])/'.shards.info'
  if info.exists():
   installed=yaml.load(info.read_text(),Loader=yaml.BaseLoader)
   for dep in dependencies:installed['shards'][dep['name']]['version']=dep['version']
   info.write_text(yaml.safe_dump(installed,sort_keys=False))
  run([SHARDS,'check','--frozen','--local'],cwd=stage,env=env,stdout=sys.stderr)
  targets=manifest.get('targets',{})
  if not isinstance(targets,dict) or any(not re.fullmatch(lock.NAME,name) for name in targets):raise ValueError('invalid native application targets')
  data={'version':1,'nativeHash':hashlib.sha256(native_text.encode()).hexdigest(),'nativeLock':native_text,'inputs':lock.inputs(root),'toolVersions':versions(),'manifest':(root/'shard.yml').read_text(),'dependencies':dependencies,'targets':sorted(targets)}
  write(native,native_text);write(sidecar,json.dumps(lock.seal(data),sort_keys=True,indent=2,ensure_ascii=False)+'\n')
  print('Locked native Shards graph',file=sys.stderr)
def checked(root,native,sidecar):
 data=json.loads(sidecar.read_text())
 if problems:=lock.problems(root,native,data):raise ValueError('\n'.join(problems))
 return data
def realize(root,native,sidecar,target):
 definition=Path(__file__).resolve().parents[1]/'nix/realize.nix'
 args=['nix','build','--impure','--file',definition,'--argstr','project',root,'--argstr','lockFile',sidecar,'--argstr','shardLock',native,'--argstr','target',target,'--no-link','--print-out-paths']
 return Path(run(args,text=True,stdout=subprocess.PIPE).stdout.strip())
def prefetch(root,native,sidecar):
 checked(root,native,sidecar)
 cache=sidecar.parent/'.shards-purifier'/hashlib.sha256(str(sidecar).encode()).hexdigest()[:16];cache.mkdir(parents=True,exist_ok=True)
 for target in ('environment','runtime'):
  output=realize(root,native,sidecar,target);run(['nix-store','--add-root',cache/target,'--indirect','--realise',output],stdout=subprocess.DEVNULL)
 return (cache/'environment').resolve()
def runtime(root,native,sidecar,tool,arguments):
 command={'shards':SHARDS,'crystal':CRYSTAL,'crystalline':os.environ['SHARDS_PURIFIER_CRYSTALLINE']}[tool]
 if not sidecar.exists():
  if os.environ.get('SHARDS_PURIFIER_OFFLINE')=='1':
   for key in ('SHARDS_PURIFIER_OFFLINE','SHARDS_PURIFIER_PROJECT_ROOT','SHARDS_INSTALL_PATH','SHARDS_CACHE_PATH','SHARDS_BIN_PATH','CRYSTAL_PATH','CRYSTAL_CACHE_DIR'):os.environ.pop(key,None)
  os.environ['SHARDS_PURIFIER_NATIVE_LOCKFILE']=str(native)
  print('shards-purifier: no lockfile; using ordinary impure '+tool,file=sys.stderr);os.execv(command,[command,*arguments])
 data=checked(root,native,sidecar)
 command_name='install';index=0
 while index<len(arguments):
  if arguments[index]=='--jobs':index+=2;continue
  if not arguments[index].startswith('-'):command_name=arguments[index];break
  index+=1
 if tool=='shards' and command_name in ('update','lock','init','prune','outdated'):raise ValueError('use shards-purifier lock or update for dependency changes')
 output=prefetch(root,native,sidecar);state=root/'.shards-purifier';state.mkdir(exist_ok=True)
 guard=(state/'setup.lock').open('a');fcntl.flock(guard,fcntl.LOCK_EX)
 marker=state/'environment';installed=state/'lib'
 if not marker.exists() or marker.read_text()!=str(output) or not installed.exists():
  staging=state/'lib.new'
  if staging.exists():shutil.rmtree(staging)
  def place(source,destination):
   if Path(source).name=='.shards.info':return shutil.copyfile(source,destination)
   Path(destination).symlink_to(source)
  shutil.copytree(output/'lib',staging,copy_function=place,symlinks=True)
  staging.chmod(0o755)
  for path in staging.rglob('*'):
   if path.is_dir() and not path.is_symlink():path.chmod(0o755)
  if installed.exists():shutil.rmtree(installed)
  staging.replace(installed)
  gitcache=state/'git-cache'
  if gitcache.exists():shutil.rmtree(gitcache)
  prepare.hydrate(output/'sources',data['dependencies'],gitcache)
  write(marker,str(output))
 guard.close()
 env=environment();env.update(SHARDS_PURIFIER_NATIVE_LOCKFILE=str(native),SHARDS_PURIFIER_PROJECT_ROOT=str(root),SHARDS_PURIFIER_OFFLINE='1',SHARDS_INSTALL_PATH=str(installed),SHARDS_CACHE_PATH=str(state/'git-cache'),SHARDS_BIN_PATH=str(root/'bin'),CRYSTAL_CACHE_DIR=str(state/'compiler-cache'),CRYSTAL_PATH=str(installed),PATH=str(output/'bin')+os.pathsep+env['PATH'])
 os.environ.clear();os.environ.update(env)
 if tool=='shards':arguments=['--local','--frozen',*arguments]
 os.execv(command,[command,*arguments])
def project(arguments):
 candidate=Path.cwd()
 for argument in arguments:
  source=re.sub(r':\d+(:\d+)?$','',argument)
  if source.endswith('.cr') and Path(source).exists():candidate=Path(source).resolve().parent;break
 for directory in [candidate,*candidate.parents]:
  if (directory/'shard.yml').exists():return directory
 return candidate
def publish(root,native,sidecar,repository,tag):
 checked(root,native,sidecar);release=realize(root,native,sidecar,'release');gh=os.environ.get('SHARDS_PURIFIER_GH','gh')
 if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*',tag):raise ValueError('publish requires OWNER/REPOSITORY and a release tag')
 present=subprocess.run([gh,'release','view',tag,'--repo',repository],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
 if present:run([gh,'release','upload',tag,'--repo',repository,release/'project.tar.gz','--clobber'])
 else:run([gh,'release','create',tag,'--repo',repository,'--title',tag,'--notes','Source release built by Nix.',release/'project.tar.gz'])
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--project');parser.add_argument('--lockfile',default=os.environ.get('SHARDS_PURIFIER_LOCKFILE'));parser.add_argument('--native-lock','--shard-lock','--tool-lockfile',dest='native_lock')
 sub=parser.add_subparsers(dest='command',required=True)
 for name in ('lock','prefetch'):sub.add_parser(name)
 p=sub.add_parser('update');p.add_argument('names',nargs='*');p=sub.add_parser('native');p.add_argument('tool',choices=['shards','crystal','crystalline']);p.add_argument('args',nargs=argparse.REMAINDER)
 p=sub.add_parser('publish');p.add_argument('--repo',required=True);p.add_argument('--tag',required=True)
 args=parser.parse_args();arguments=args.args if args.command=='native' else []
 if arguments[:1]==['--']:arguments=arguments[1:]
 root=Path(args.project).expanduser().resolve() if args.project else project(arguments)
 elsewhere=os.environ.get('SHARDS_PURIFIER_OFFLINE')=='1' and os.environ.get('SHARDS_PURIFIER_PROJECT_ROOT')!=str(root)
 selection=args.native_lock or (None if elsewhere else os.environ.get('SHARDS_PURIFIER_NATIVE_LOCKFILE')) or os.environ.get('SHARDS_PURIFIER_TOOL_LOCKFILE')
 native=Path(selection).expanduser().resolve() if selection else root/'shard.lock';sidecar=Path(args.lockfile).expanduser().resolve() if args.lockfile else root/'shards-purifier.lock.json'
 if args.command in ('lock','update'):do_lock(root,native,sidecar,args.command=='update',getattr(args,'names',[]))
 elif args.command=='prefetch':print(prefetch(root,native,sidecar))
 elif args.command=='publish':publish(root,native,sidecar,args.repo,args.tag)
 else:runtime(root,native,sidecar,args.tool,arguments)
