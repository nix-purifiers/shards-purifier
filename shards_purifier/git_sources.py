# SPDX-License-Identifier: MIT
"""Capture exact commits selected by Shards, using its native mirror cache."""
import base64,json,re,subprocess
from pathlib import Path
from urllib.parse import urlsplit
import yaml
def git(directory,*args,binary=False):
 return subprocess.check_output(['git','--git-dir',str(directory),*args],text=not binary).strip() if not binary else subprocess.check_output(['git','--git-dir',str(directory),*args])
def export(native,cache,temporary,manifest):
 mirrors={}
 for head in cache.rglob('HEAD'):
  repository=head.parent
  if (repository/'objects').is_dir() and (repository/'config').is_file():
   origin=git(repository,'config','--get','remote.origin.url');mirrors[origin]=repository
 dependencies=[];manifests=[manifest]
 for name,record in sorted(native['shards'].items()):
  if set(record)!={'git','version'}:raise ValueError('only native Git shards are supported yet: '+name)
  origin=record['git'];version=str(record['version']);repository=mirrors.get(origin)
  if repository is None:raise ValueError('native mirror missing for '+name)
  p=urlsplit(origin)
  if p.scheme not in ('http','https','git','file') or p.username is not None or p.password is not None:raise ValueError('unsupported Git transport: '+origin)
  base,separator,revision=version.partition('+git.commit.')
  ref=revision if separator else 'refs/tags/v'+version
  revision=git(repository,'rev-parse',ref+'^{commit}')
  if not re.fullmatch('[0-9a-f]{40}',revision):raise ValueError('unsupported Git object format')
  tree=temporary/'trees'/name;tree.mkdir(parents=True)
  subprocess.run(['git','--git-dir',str(repository),'--work-tree',str(tree),'checkout',revision,'--','.'],cwd=repository,check=True,stdout=subprocess.DEVNULL)
  nar=subprocess.check_output(['nix','hash','path',str(tree)],text=True).strip()
  raw=git(repository,'cat-file','commit',revision,binary=True)
  gitlinks=[]
  for item in git(repository,'ls-tree','-rz',revision,binary=True).split(b'\0'):
   if not item:continue
   metadata,path=item.split(b'\t',1);mode,kind,object_id=metadata.split()
   if mode==b'160000':gitlinks.append({'path':path.decode(),'rev':object_id.decode()})
  if gitlinks:raise ValueError('Git submodules are not supported yet: '+name)
  aliases={'refs/tags/v'+base}
  frozen=base+'+git.commit.'+revision
  native['shards'][name]={'git':origin,'version':frozen}
  sourcespec=yaml.load((tree/'shard.yml').read_text(),Loader=yaml.BaseLoader) if (tree/'shard.yml').exists() else {}
  manifests.append(sourcespec)
  dependencies.append({'name':name,'version':frozen,'cachePath':str(repository.relative_to(cache)),
    'aliases':sorted(aliases),'hash':nar,'git':{'url':origin,'rev':revision,'submodules':False,'leaveDotGit':True,
    'commitObject':{'object':base64.b64encode(raw).decode(),'gitlinks':gitlinks}}})
 byname={d['name']:d for d in dependencies}
 for spec in manifests:
  for table in ('dependencies','development_dependencies'):
   for name,requirement in spec.get(table,{}).items():
    if name not in byname or not isinstance(requirement,dict):continue
    for key,prefix in [('branch','refs/heads/'),('tag','refs/tags/')]:
     if key in requirement:byname[name]['aliases'].append(prefix+requirement[key])
 for dependency in dependencies:
  dependency['aliases']=sorted(set(dependency['aliases']))
  for alias in dependency['aliases']:subprocess.run(['git','check-ref-format',alias],check=True)
 bycache={}
 for dependency in dependencies:
  identity=(dependency['git']['url'],dependency['git']['rev'])
  if dependency['cachePath'] in bycache and bycache[dependency['cachePath']]!=identity:raise ValueError('multiple revisions/origins in one native cache slot are not supported yet')
  bycache[dependency['cachePath']]=identity
 return dependencies
