#!/usr/bin/env python

import os
import yaml
import re
import sys
import requests

# fill out with: posts/pages, list-of-ids, pagenum
CHECK_URL = '/?rest_route=/wp/v2/%s/&per_page=100&include=%s&_fields=id&page=%d'

UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.3'}


def look_for_removals(baseurl, dirname):
    """
    Look for items inside dirname that have an external_id which is no longer
    present as either a page or a post in the WordPress source site indicated
    with baseurl.
    """
    baseurl = baseurl.strip('/')
    cand = get_page_info(dirname)
    if not cand:
        print("No external_ids found: Nothing to do")
        exit(0)
    ids = sorted([int(_) for _ in cand.keys()])
    chunknum = int(len(ids) / 100) + 1
    missing = []
    for i in range(chunknum):
        start, end = (i*100, (i+1)*100)
        checking = ids[start:end]
        idlist_str = ','.join([str(_) for _ in checking])
        seen = set()
        for typ in ('posts', 'pages'):
            url = baseurl + (CHECK_URL % (typ, idlist_str, i+1))
            got = requests.get(url, headers=UA).json() or []
            for it in got:
                seen.add(int(it['id']))
        for k in checking:
            if not k in seen:
                missing.append(k)
    if missing:
        print("POSTS/PAGES NOW MISSING IN API (%d/%d):\n" % (len(missing), len(ids)))
        for k in missing:
            for it in cand[k]['items']:
                print("  -", it['path'])
    else:
        print("Checked", len(ids), "external IDs")
        print("No deleted/deactivated items found")


def get_page_info(dirname):
    if not os.path.isdir(dirname):
        print("ERROR: %s is not a directory" % dirname)
        exit(1)
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
    return cand


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

    if len(sys.argv) > 2:
        look_for_removals(sys.argv[1], sys.argv[2])
    else:
        print("Usage:", sys.argv[0], "baseurl content-subdirectory")
        print(" e.g.:", sys.argv[0], "http://localhost content/from-wp")
