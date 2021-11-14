#!/usr/bin/env python3

import os
import sys
import datetime
import re
import ast

import sass
import yaml
import frontmatter
import markdown

from mako.template import Template
from mako.lookup import TemplateLookup


def main(basedir=None, force=False):
    """
    Builds/copies everything into the output dir (htdocs).
    """
    if basedir is None:
        basedir = os.path.dirname(os.path.realpath(__file__)) or '.'
    if not os.path.isdir(basedir):
        raise Exception('{} is not a directory'.format(basedir))
    dirs = get_dirs(basedir)
    ensure_dirs(dirs)
    conf = get_config(basedir)
    # 1) copy static files
    # css_dir_from_start is workaround for process_assets timestamp check
    css_dir_from_start = os.path.exists(os.path.join(dirs['output'], 'css'))
    os.system("rsync -a %s/ %s/" % (dirs['static'], dirs['output']))
    # 2) compile assets (only scss for now):
    process_assets(
        dirs['assets'], dirs['output'], conf, css_dir_from_start, force)
    # Global data for template rendering, used by both process_templates
    # and process_markdown_content.
    template_vars = {
        'DATADIR': os.path.realpath(dirs['data']),
        'WEBROOT': os.path.realpath(dirs['output']),
    }
    template_vars.update(conf.get('template_context', {}))
    # 3) render templates
    lookup = TemplateLookup(directories=[dirs['templates']])
    templates = get_templates(dirs['templates'], dirs['output'])
    process_templates(templates, lookup, template_vars, force)
    # 4) render Markdown content
    content = get_content(
        dirs['content'], dirs['data'], dirs['output'],
        template_vars, conf)
    process_markdown_content(content, lookup, conf, force)


def get_dirs(basedir):
    """
    Configuration of subdirectory names relative to the basedir.
    """
    return {
        'templates': basedir + '/templates', # Mako templates
        'content': basedir + '/content',  # Markdown files
        'output': basedir + '/htdocs',
        'static': basedir + '/static',
        'assets': basedir + '/assets', # only scss for now
        'data': basedir + '/data', # YAML, potentially sqlite
    }


def get_config(basedir):
    filename = os.path.join(basedir, 'wmk_config.yaml')
    conf = {}
    if os.path.exists(filename):
        with open(filename) as f:
           conf = yaml.safe_load(f) or {}
    return conf


def process_templates(templates, lookup, template_vars, force):
    """
    Renders the specified templates into the outputdir.
    """
    for tpl in templates:
        # NOTE: very crude, not affected by template dependencies
        if not force and is_older_than(tpl['src_path'], tpl['target']):
            continue
        template = lookup.get_template(tpl['src'])
        #data = get_data(tpl['data'], datadir=datadir)
        #kannski byggt á tpl.module.DATA attribute?
        data = template_vars
        maybe_mkdir(tpl['target'])
        with open(tpl['target'], 'w') as f:
            f.write(template.render(**data))
        print('[%s] - template: %s' % (
            str(datetime.datetime.now()), tpl['src']))


def process_markdown_content(content, lookup, conf, force):
    """
    Renders the specified markdown content into the outputdir.
    """
    try:
        mako_shortcode_comp = conf.get('mako_shortcodes', None)
        if mako_shortcode_comp:
            mako_shortcode_comp = lookup.get_template(mako_shortcode_comp)
    except Exception as e:
        print("WARNING: Could not load shortcodes from {}: {}".format(
            conf['mako_shortcodes'], e))
        mako_shortcode_comp = None
    for ct in content:
        if not force and is_older_than(ct['source_file'], ct['target']):
            continue
        template = lookup.get_template(ct['template'])
        maybe_mkdir(ct['target'])
        data = ct['data']
        doc = ct['doc']
        if '{{<' in doc:
            if conf.get('shortcodes', None):
                for k in conf['shortcodes']:
                    sc = conf['shortcodes'][k]
                    pat = r'{{< *' + sc['pattern'] + r' *>}}'
                    doc = re.sub(pat, sc['content'], doc)
            if mako_shortcode_comp:
                # funcname, argstring, directive
                pat = r'{{< *(\w+)\( *(.*?) *\) *(\w+)? *>}}'
                handler = mako_shortcode(mako_shortcode_comp, data)
                doc = re.sub(pat, handler, doc)
        extensions = conf.get('markdown_extensions', None)
        if extensions is None:
            extensions = ['extra', 'sane_lists']
        data['CONTENT'] = markdown.markdown(doc, extensions=extensions)
        data['RAW_CONTENT'] = ct['doc']
        with open(ct['target'], 'w') as f:
            f.write(template.render(**data))
        print('[%s] - content: %s' % (
            str(datetime.datetime.now()), ct['source_file']))


def process_assets(assetdir, outputdir, conf, css_dir_from_start, force):
    """
    Compiles assets from assetdir into outputdir.
    Only handles sass/scss files in the sass subdirectory for now.
    """
    scss_input = os.path.join(assetdir, 'scss')
    if not os.path.exists(scss_input):
        return
    css_output = os.path.join(outputdir, 'css')
    if not os.path.exists(css_output):
        os.mkdir(css_output)
    if force or not css_dir_from_start or not dir_is_older_than(scss_input, css_output):
        output_style = conf.get('sass_output_style', 'expanded')
        sass.compile(
            dirname=(scss_input, css_output), output_style=output_style)
        print('[%s] - sass: refresh' % datetime.datetime.now())


def get_content(ctdir, datadir, outputdir, template_vars, conf):
    """
    Get those markdown files that need processing.
    """
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
            if meta.get('draft', False) and not conf.get('render_drafts', False):
                continue
            data = {}
            data.update(template_vars)
            data.update(meta)
            template = data.get('template', default_template)
            pretty_path = data.get('pretty_path', default_pretty_path)
            if 'LOAD' in data:
                load_path = os.path.join(datadir, data['LOAD'])
                if os.path.exists(load_path):
                    loaded = {}
                    with open(load_path) as yf:
                        loaded = yaml.safe_load(yf) or {}
                    data.update(loaded)
            html_fn = fn.replace('.md', '/index.html' if pretty_path else '.html')
            html_dir = root.replace(ctdir, outputdir, 1)
            target_fn = os.path.join(html_dir, html_fn)
            data['SELF_URL'] = target_fn.replace(outputdir, '', 1)
            content.append({
                'source_file': source_file,
                'source_file_short': source_file.replace(ctdir, '', 1),
                'target': target_fn,
                'template': template,
                'data': data,
                'doc': doc,
            })
    return content


def get_templates(tpldir, outputdir):
    """
    Get those templates that need processing.
    """
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
        os.makedirs(dirname)


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


def parse_argstr(argstr):
    "Parse a string representing the arguments part of a function call."
    fake = 'f({})'.format(argstr)
    tree = ast.parse(fake)
    funccall = tree.body[0].value
    args = [ast.literal_eval(arg) for arg in funccall.args]
    kwargs = {arg.arg: ast.literal_eval(arg.value) for arg in funccall.keywords}
    return args, kwargs


def mako_shortcode(comp, ctx):
    "Return a match replacement function for mako shortcode handling."
    def replacer(match):
        defnam = match.group(1)
        argstr = match.group(2)
        directive = match.group(3) or ''
        args, kwargs = parse_argstr(argstr)
        try:
            subcomp = comp.get_def(defnam)
            if directive in ('with_context', 'ctx'):
                ckwargs = {}
                ckwargs.update(ctx)
                ckwargs.update(kwargs)
                return subcomp.render(*args, **ckwargs)
            else:
                return subcomp.render(*args, **kwargs)
        except Exception as e:
            print("WARNING: shortcode {} failed: {}".format(defnam, e))
            return match.group(0)
    return replacer


if __name__ == '__main__':
    basedir = sys.argv[1] if len(sys.argv) > 1 else None
    force = True if len(sys.argv) > 2 and sys.argv[2] in ('-f', '--force') else False
    main(basedir, force)
