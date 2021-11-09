#!/usr/bin/env python3

import os
import sys
import datetime

import sass
import yaml
import frontmatter
import markdown

from mako.template import Template
from mako.lookup import TemplateLookup


def main(basedir=None):
    actions = []
    if basedir is None:
        basedir = os.path.dirname(os.path.realpath(__file__)) or '.'
    if not os.path.isdir(basedir):
        raise Exception('{} is not a directory'.format(basedir))
    dirs = get_dirs(basedir)
    ensure_dirs(dirs)
    # render templates
    lookup = TemplateLookup(directories=[dirs['templates']])
    templates = get_templates(dirs['templates'], dirs['output'])
    for tpl in templates:
        # NOTE: very crude, not affected by template dependencies
        if is_older_than(tpl['src_path'], tpl['target']):
            continue
        template = lookup.get_template(tpl['src'])
        #data = get_data(tpl['data'], datadir=datadir)
        #kannski byggt á tpl.module.DATA attribute?
        data = {}
        maybe_mkdir(tpl['target'])
        with open(tpl['target'], 'w') as f:
            f.write(template.render(**data))
        actions.append('[%s] - template: %s' % (
            str(datetime.datetime.now()), tpl['src']))
    content = get_content(dirs['content'], dirs['data'], dirs['output'])
    for ct in content:
        if is_older_than(ct['source_file'], ct['target']):
            continue
        template = lookup.get_template(ct['template'])
        maybe_mkdir(ct['target'])
        data = ct['data']
        data['CONTENT'] = markdown.markdown(ct['doc'], extensions=['extra', 'sane_lists'])
        data['RAW_CONTENT'] = ct['doc']
        with open(ct['target'], 'w') as f:
            f.write(template.render(**data))
        actions.append('[%s] - content: %s' % (
            str(datetime.datetime.now()), ct['source_file']))
    # copy static files
    os.system("rsync -a --exclude=.keep %s/ %s/" % (dirs['static'], dirs['output']))
    # compile assets (only scss for now):
    scss_input = os.path.join(dirs['assets'], 'scss')
    css_output = os.path.join(dirs['output'], 'css')
    if not os.path.exists(css_output):
        os.mkdir(css_output)
    if os.path.exists(scss_input) and not dir_is_older_than(scss_input, css_output):
        sass.compile(
            dirname=(scss_input, css_output), output_style='expanded')
        actions.append('[%s] - sass: refresh' % datetime.datetime.now())
    if actions:
        print("\n".join(actions))


def get_dirs(basedir):
    return {
        'templates': basedir + '/templates', # Mako templates
        'content': basedir + '/content',  # Markdown files
        'output': basedir + '/htdocs',
        'static': basedir + '/static',
        'assets': basedir + '/assets',
        'data': basedir + '/data',
    }


def get_content(ctdir, datadir, outputdir):
    content = []
    default_template = 'md_base.mhtml'
    default_pretty_path = True
    for root, dirs, files in os.walk(ctdir):
        for fn in files:
            if not fn.endswith('.md'):
                continue
            if fn.startswith('_') or fn.startswith('.'):
                continue
            source_file = os.path.join(root, fn)
            with open(source_file) as f:
                meta, doc = frontmatter.parse(f.read())
            template = meta.get('template', default_template)
            pretty_path = meta.get('pretty_path', default_pretty_path)
            if 'LOAD' in meta:
                load_path = os.path.join(datadir, meta['LOAD'])
                if os.path.exists(load_path):
                    loaded = {}
                    with open(load_path) as yf:
                        loaded = yaml.safe_load(yf) or {}
                    meta.update(loaded)
            html_fn = fn.replace('.md', '/index.html' if pretty_path else '.html')
            html_dir = root.replace(ctdir, outputdir, 1)
            content.append({
                'source_file': source_file,
                'source_file_short': source_file.replace(ctdir, '', 1),
                'target': os.path.join(html_dir, html_fn),
                'template': template,
                'data': meta,
                'doc': doc,
            })
    return content


def get_templates(tpldir, outputdir):
    templates = []
    for root, dirs, files in os.walk(tpldir):
        if root.endswith('/base'):
            continue
        for fn in files:
            if 'base' in fn or fn.startswith('_'):
                continue
            if fn.endswith('.mhtml'):
                source = os.path.join(root.replace(tpldir, '', 1), fn)
                if source.startswith('/'):
                    source = source[1:]
                html_fn = fn.replace('.mhtml', '.html')
                html_dir = root.replace(tpldir, outputdir, 1)
                templates.append({
                    'src': source,
                    'src_path': os.path.join(root, fn),  # full path
                    'target': os.path.join(html_dir, html_fn)
                })
    return templates


def maybe_mkdir(fn):
    dirname = os.path.dirname(fn)
    if not os.path.isdir(dirname):
        os.mkdir(dirname)


def ensure_dirs(dirs):
    for path in dirs.values():
        if os.path.exists(path):
            continue
        os.mkdir(path)


def is_older_than(src, trg):
    # true if src is older than trg; both are files
    if not (os.path.exists(src) and os.path.exists(trg)):
        return False
    return os.path.getmtime(src) < os.path.getmtime(trg)


def dir_is_older_than(src, trg):
    # true if timestamp of newest file in src is older than
    # timestamp of newest file in trg
    if not (os.path.exists(src) and os.path.exists(trg)):
        return False
    newest_src = get_newest_ts_of_dir(src)
    newest_trg = get_newest_ts_of_dir(trg)
    return newest_src < newest_trg


def get_newest_ts_of_dir(src):
    newest = 0
    for root, dirs, files in os.walk(src):
        for fn in files:
            ts = os.path.getmtime(os.path.join(root, fn))
            if ts > newest:
                newest = ts
    return newest


if __name__ == '__main__':
    basedir = sys.argv[1] if len(sys.argv) > 1 else None
    main(basedir)
