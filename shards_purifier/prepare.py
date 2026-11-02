# SPDX-License-Identifier: MIT
"""Prepare a writable native Git mirror cache from Nix's fixed Git objects."""
import json,os,shutil,subprocess,sys
from pathlib import Path
def hydrate(sources,dependencies,destination):
 for dep in dependencies:
  target=destination/dep['cachePath']
  if not target.exists():
   target.parent.mkdir(parents=True,exist_ok=True)
   shutil.copytree(sources/dep['name']/'.git',target,symlinks=True)
   target.chmod(0o755)
   for path in target.rglob('*'):
    if not path.is_symlink():path.chmod(0o755 if path.is_dir() else 0o644)
  command=['git','--git-dir',str(target)]
  for key,value in [('core.bare','true'),('remote.origin.url',dep['git']['url']),('remote.origin.mirror','true')]:subprocess.run([*command,'config',key,value],check=True)
  for alias in dep['aliases']:subprocess.run([*command,'update-ref',alias,dep['git']['rev']],check=True)
if __name__=='__main__':
 metadata,sources,destination=map(Path,sys.argv[1:])
 hydrate(sources,json.loads(metadata.read_text())['dependencies'],destination)
