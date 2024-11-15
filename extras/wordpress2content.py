#!/usr/bin/env python

import requests
import json
import re
import datetime
import os
import yaml
import sys


DEFAULT_SETTINGS = {
    'url': 'http://localhost',
    'per_page': 10, # max 100
    'max_pages': 10000,
    'get_images': True, # applies to non-image media as well
    'content_types': ['posts', 'pages'],
    'content_prefix': 'from-wp',
    'posts_dir': 'posts',
    'pages_dir': 'pages',
}
DEFAULT_REFDATE = '1990-01-01T00:00:00'
API_BASE_URL = '/?rest_route=/wp/v2/'
MEDIA_REPLACE = {
    'from': r'''/wp-content/uploads/([^"'\?\s]+)''',
    'to_dir': r'/_fetched',
}
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.3'}



def get_all_wp_content(basedir='.', settings=None):
    """
    Gets all posts and pagees within range, then processes them, i.e.
    munges, writes to file and fetches images/media.
    """
    settings = get_full_settings(basedir, settings)
    raw = []
    for typ in settings['content_types']:
        chunk = get_partial_wp_content(typ, settings)
        if chunk:
            set_refdate(settings, typ, chunk[0]['modified'])
            raw += chunk
    for it in raw:
        process_item(it, settings)


def get_full_settings(basedir, settings):
    """
    Makes sure the configuration dict contains all required settings.
    """
    if settings is None:
        settings = DEFAULT_SETTINGS
    if basedir is None:
        basedir = '.'
    basedir = basedir.rstrip('/')
    for k in DEFAULT_SETTINGS:
        if not k in settings:
            settings[k] = DEFAULT_SETTINGS[k]
    settings['url'] = settings['url'].strip('/')
    settings['api_url'] = settings['url'] + API_BASE_URL
    if 'source_name' not in settings:
        sn = re.sub(r'^https?://', '', settings['url'])
        sn = re.sub(r'^www\.', '', sn)
        sn = re.sub(r'\.[a-z]{2,6}$', '', sn)
        settings['source_name'] = sn
    settings['content_prefix'] = settings['content_prefix'].strip('/')
    dirs = {'base': basedir}
    for d in ('content', 'data', 'static'):
        dirs[d] = os.path.join(basedir, d)
        if not os.path.exists(dirs[d]):
            raise Exception('The directory %s needs to exist' % dirs[d])
    dirs['media'] = os.path.join(
        dirs['static'], '_fetched', settings['content_prefix']).rstrip('/')
    dirs['pages'] = os.path.join(
        dirs['content'], settings['content_prefix'], settings['pages_dir']).rstrip('/')
    dirs['posts'] = os.path.join(
        dirs['content'], settings['content_prefix'], settings['posts_dir']).rstrip('/')
    for d in ('media', 'pages', 'posts'):
        if not os.path.exists(dirs[d]):
            os.makedirs(dirs[d])
    settings['dirs'] = dirs
    mrepl_to = MEDIA_REPLACE['to_dir'] + '/' + settings['content_prefix'] + r'/\1'
    settings['media_replace'] = {
        'from': MEDIA_REPLACE['from'],
        'to': mrepl_to.replace('//', '/'),
    }
    refdate_fn = os.path.join(settings['dirs']['data'], 'wordpress2content-refdate.json')
    refdate_unsaved = False
    if os.path.exists(refdate_fn):
        with open(refdate_fn) as f:
            refdate_info = json.loads(f.read())
            if not settings['url'] in refdate_info:
                refdate_unsaved = True
                refdate_info[settings['url']] = {
                    'posts': DEFAULT_REFDATE,
                    'pages': DEFAULT_REFDATE,
                }
            for k in ('posts', 'pages'):
                if not k in refdate_info:
                    refdate_info[k] = DEFAULT_REFDATE
                    refdate_unsaved = True
    else:
        refdate_unsaved = True
        refdate_info = {
            settings['url']: {
                'posts': DEFAULT_REFDATE,
                'pages': DEFAULT_REFDATE,
            }
        }
    # TODO: handle other potential content types, not just posts and pages
    settings['refdate'] = {
        'filename': refdate_fn,
        'all': refdate_info,
        'posts': refdate_info[settings['url']]['posts'],
        'pages': refdate_info[settings['url']]['pages'],
    }
    if refdate_unsaved:
        set_refdate(settings, 'posts', settings['refdate']['posts'])
        set_refdate(settings, 'pages', settings['refdate']['pages'])
    return settings


def set_refdate(settings, typ, modified):
    """
    Save the last changed date to a file for use next time.
    """
    settings['refdate'][typ] = modified
    refdate_info = settings['refdate']['all']
    fn = settings['refdate']['filename']
    refdate_info[settings['url']][typ] = modified
    with open(fn, 'w') as f:
        f.write(json.dumps(refdate_info))



def get_partial_wp_content(typ, settings):
    """
    Fetches all information within scope about either posts or pages (or
    potentially other content types, such as products). Images are not
    downloaded at this stage.
    """
    # typ is either 'posts' or 'pages'
    url = settings['api_url'] \
            + '{}/&per_page={}&_embed=true&orderby=modified'.format(
                typ, settings['per_page'])
    refdate = settings['refdate'].get(typ, DEFAULT_REFDATE)
    ret = []
    print("GET", url)
    resp = requests.get(url, headers=UA)
    if resp.status_code == 200:
        try:
            chunk = resp.json()
            if chunk and chunk[0]['modified'] > refdate:
                ret += chunk
            else:
                print("INFO: Found nothing new for", typ, "- refdate is", refdate)
                return ret
        except requests.exceptions.JSONDecodeError as e:
            print("WARNING: JSON decode error: %s - bailing out!" % e)
            return
        lastpage = int(resp.headers.get('X-WP-TotalPages', 0))
        if lastpage > settings['max_pages']:
            print("WARNING: Will fetch at most", settings['max_pages'], "instead of", lastpage, "because of max_pages setting")
            lastpage = settings['max_pages']
        if lastpage > 1:
            curpage = 2
            while curpage < lastpage:
                pageurl = url + '&page={}'.format(curpage)
                print("GET", pageurl)
                resp = requests.get(pageurl, headers=UA)
                if resp.status_code == 200:
                    try:
                        chunk = resp.json()
                        if chunk and chunk[0]['modified'] > refdate:
                            ret += chunk
                        else:
                            print("INFO: Stopping at", typ, "page", curpage, "of", lastpage, "- refdate is", refdate)
                            return ret
                    except requests.exceptions.JSONDecodeError as e:
                        print("WARNING: JSON decode error: %s - skipping items on this page!" % e)
                else:
                    print("WARNING: Error for url", url, "page", curpage, "status", resp.status_code)
                curpage += 1
    else:
        print("WARNING: Error for url", url, "status", resp.status_code)
    return ret


def process_item(it, settings):
    """
    Convert the post/page to a content file and download any associated
    images/media.
    """
    pubdate = datetime.datetime.fromisoformat(it['date'])
    refdate = settings['refdate'].get(it['type']+'s', str(datetime.datetime.now()))
    meta = {
        'date': it['date'],
        'pubdate': it['date'],
        'modified_date': it['modified'],
        'refdate': refdate,
        'title': it['title']['rendered'],
        'slug': it['slug'],
        'summary': it['excerpt']['rendered'],
        'page_type': it['type'],
        'source_system': 'wordpress',
        'source_url': settings['api_url'],
        'source_name': settings['source_name'],
    }
    if it.get('id'):
        meta['external_id'] = it['id']
    if it.get('featured_media', None):
        try:
            meta['main_img'] = get_media(
                it['_embedded']['wp:featuredmedia'][0]['source_url'],
                settings)
        except Exception as e:
            print("WARNING: Could not get main_img for", it['slug'], ":", e)
    if it.get('author', None):
        au = it['_embedded']['author']
        try:
            if len(au) > 1:
                meta['authors'] = [_['name'] for _ in au]
            else:
                meta['author'] = au[0]['name']
        except KeyError as e:
            # 'code' normally indicates we don't have access to author info;
            # in that case, just skip over authors silently.
            if 'code' not in au[0]:
                print("WARNING: KeyError for autor(s):", e, " - using raw value")
                meta['authors'] = au
    tags = []
    cats = []
    for tx in it['_embedded'].get('wp:term', []):
        for taxo in tx:
            typ = taxo.get('taxonomy', '')
            if typ == 'category':
                cats.append(taxo['name'])
            elif typ == 'post_tag':
                tags.append(taxo['name'])
    if tags:
        meta['tags'] = tags
    if cats:
        meta['categories'] = cats
    doc = media_filter(it['content']['rendered'], settings)
    typ = 'post' if it['type'] == 'post' else 'page'
    if typ == 'post':
        subdir = '%04d-%02d' % (pubdate.year, pubdate.month)
        destdir = os.path.join(settings['dirs']['posts'], subdir)
    else:
        if it['_embedded'].get('up'):
            # pages may be arranged hierarchically
            parent_dirs = []
            for parent in it['_embedded']['up']:
                if 'slug' in parent:
                    parent_dirs.append(parent['slug'])
            parent_dirs.reverse()
            destdir = os.path.join(settings['dirs']['pages'], *parent_dirs)
        else:
            destdir = settings['dirs']['pages']
    if not os.path.exists(destdir):
        os.makedirs(destdir)
    html_fn = os.path.join(destdir, it['slug'] + '.html')
    json_fn = os.path.join(destdir, it['slug'] + '.wp_source.json')
    with open(html_fn, 'w') as f:
        f.write("---\n" + yaml.safe_dump(meta, allow_unicode=True).strip() + "\n---\n\n" + doc)
    with open(json_fn, 'w') as f:
        f.write(json.dumps(it))
    print("- wrote file", html_fn, "(+ json)")


def media_filter(s, settings):
    """
    Filter an HTML string, replacing every occurence of an original
    image/video/audio file URL with another URL/path pointing to its new
    location.
    """
    return re.sub(
            settings['url'] + settings['media_replace']['from'],
            lambda x: get_media(x.group(0), settings),
            s)


def get_media(url, settings):
    """
    Replace url with relative path after downloading the file and placing it in
    the correct place. Applies only to images from the original site and inside
    wp-content/uploads/.
    """
    if not settings['get_images']:
        return url
    if not url.startswith('http'):
        return url
    path = re.sub(settings['url'] + settings['media_replace']['from'],
                  settings['media_replace']['to'], url)
    if path.startswith(('http:', 'https:')):
        return path
    fullpath = os.path.join(settings['dirs']['static'], path.strip('/'))
    if os.path.exists(fullpath):
        return path
    fulldir = os.path.dirname(fullpath)
    if not os.path.exists(fulldir):
        os.makedirs(fulldir)
    resp = requests.get(url, headers=UA)
    if resp and resp.status_code == 200:
        print('- writing img/media', fullpath)
        with open(fullpath, 'wb') as f:
            f.write(resp.content)
        return path
    else:
        return url

def usage():
    print("""wordpress2content.py [basedir] [url|json_file|json_literal]

Fetch content from a WordPress API endpoint for use by wmk.

  - basedir: Base directory for wmk project. By default '.' (i.e. cwd)

  - url: The URL of the WordPress site for fetching data from.
    Without a trailing slash. Default: http://localhost. The REST endpoint
    '/?rest_route=/wp/v2/' will be appended automatically.

  - json_file: A JSON file with further settings. Needed if you want to
    specify other things than just the source URL, e.g. how many posts/pages
    per page of JSON results or whether to stop after at most some number of
    JSON pages fetched, or what content_prefix subdirectory to use.
    Read the source of this script to see which settings are supported.

  - json_literal: A string containing the JSON to use as settings.

The script will detect automatically which of url, json_file or json
literal is being specified. The directory specified (or the current
directory) must contain the folders content/, static/ and data/.

Content files go into content/<content_prefix>/ (where the default for
content_prefix is from-wp), images and other media files into
static/_fetched/<content_prefix>/. Last-modified time is kept in the JSON
file data/wordpress2content-refdate.json, which must be edited or removed
if you wish to start over (i.e. fetch everything again).

The timestamp will be used to determine at what point to stop fetching more
information via the API. Static files will not be refetched. Note that
renames of posts or pages are not detected.
""")

if __name__ == '__main__':
    basedir = '.'
    settings = {}
    if len(sys.argv) == 3:
        basedir = sys.argv[1]
        info = sys.argv[2]
    elif len(sys.argv) == 2:
        if os.path.isdir(sys.argv[1]):
            basedir = sys.argv[1]
        else:
            info = sys.argv[1]
    else:
        usage()
        exit(1)
    if info.startswith(('http:', 'https:')):
        settings['url'] = info
    elif info.startswith('{'):
        settings = json.loads(info)
    else:
        with open(info) as f:
            settings = json.loads(f.read())

    get_all_wp_content(basedir=basedir, settings=settings)
