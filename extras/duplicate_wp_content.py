#!/usr/bin/env python

import os
import yaml
import re
import sys


def look_for_duplicates(dirname):
    """
    Look for duplicates inside dirname and subdirectories based on external_id
    in frontmatter. Only files with the extension .html are checked. Files
    without YAML frontmatter or without external_id are silently skipped.
    """
    if not os.path.isdir(dirname):
        print("ERROR: %s is not a directory" % dirname)
    cand = {}
    for root, dirs, fils in os.walk(dirname):
        for fn in fils:
            if fn.endswith('.html'):
                path = os.path.join(root, fn)
                with open(path) as f:
                    info = get_frontmatter(f.read())
                    if 'external_id' in info:
                        eid = info['external_id']
                        rec = {'path': path, 'info': info}
                        if eid in cand:
                            cand[eid]['duplicate'] = True
                            cand[eid]['items'].append(rec)
                        else:
                            cand[eid] = {'duplicate': False, 'items': [rec]}
    dupl = []
    for k in cand:
        if cand[k]['duplicate']:
            dupl.append(cand[k]['items'])
    if dupl:
        print("DUPLICATES FOUND:\n")
        for grp in dupl:
            eid = grp[0]['info']['external_id']
            print("External ID %s:" % eid)
            for it in grp:
                print("  - %s (%s)" % (it['path'], it['info'].get('modified_date', '?')))
    else:
        print("No duplicates found")


def get_frontmatter(fc):
    fc = fc.strip()
    if not fc.startswith('---'):
        return {}
    fc = re.sub(r'\r\n', r'\n', fc) # normalize line endings
    found = re.match(r'---\n(.+?)\n---', fc, flags=re.S)
    if found:
        content = found.group(1)
        try:
            return yaml.safe_load(content)
        except Exception as e:
            print("Could not parse with yaml.safe_load, error was '%s', content was '%s'" % (e, content))
    return {}


if __name__ == '__main__':

    if len(sys.argv) > 1:
        look_for_duplicates(sys.argv[1])
    else:
        print("Usage:", sys.argv[0], " content-directory-to-check-for-duplicates")
