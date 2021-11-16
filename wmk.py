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
from mako.exceptions import text_error_template


def main(basedir=None, force=False):
    """
    Builds/copies everything into the output dir (htdocs).
    """
    if basedir is None:
        basedir = os.path.dirname(os.path.realpath(__file__)) or '.'
    basedir = os.path.realpath(basedir)
    if not os.path.isdir(basedir):
        raise Exception('{} is not a directory'.format(basedir))
    dirs = get_dirs(basedir)
    ensure_dirs(dirs)
    conf = get_config(basedir)
    # 1) copy static files
    # css_dir_from_start is workaround for process_assets timestamp check
    css_dir_from_start = os.path.exists(os.path.join(dirs['output'], 'css'))
    themedir = os.path.join(
        dirs['themes'], conf.get('theme')) if conf.get('theme') else None
    if themedir and not os.path.exists(themedir):
        themedir = None
    if themedir and os.path.exists(os.path.join(themedir, 'static')):
        os.system("rsync -a %s/ %s/" % (
            os.path.join(themedir, 'static'), dirs['output']))
    os.system("rsync -a %s/ %s/" % (dirs['static'], dirs['output']))
    # 2) compile assets (only scss for now):
    theme_assets = os.path.join(themedir, 'assets') if themedir else None
    process_assets(
        dirs['assets'], theme_assets, dirs['output'],
        conf, css_dir_from_start, force)
    # Global data for template rendering, used by both process_templates
    # and process_markdown_content.
    template_vars = {
        'DATADIR': os.path.realpath(dirs['data']),
        'WEBROOT': os.path.realpath(dirs['output']),
        'TEMPLATES': [],
        'MDCONTENT': [],
    }
    template_vars.update(conf.get('template_context', {}))
    lookup_dirs = [dirs['templates']]
    if themedir and os.path.exists(os.path.join(themedir, 'templates')):
        lookup_dirs.append(os.path.join(themedir, 'templates'))
    if conf.get('extra_template_dirs', None):
        lookup_dirs += conf['extra_template_dirs']
    lookup = TemplateLookup(directories=lookup_dirs)
    get_mako_shortcode_comp(lookup, conf)  # updates conf if applicable
    # 3) get info about stand-alone templates and Markdown content
    templates = get_templates(
        dirs['templates'], themedir, dirs['output'], template_vars)
    content = get_content(
        dirs['content'], dirs['data'], dirs['output'],
        template_vars, conf)
    # 4) render templates
    process_templates(templates, lookup, template_vars, force)
    # 5) render Markdown content
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
        'themes': basedir + '/themes', # extra static/assets/templates
    }


def get_config(basedir):
    filename = os.path.join(basedir, 'wmk_config.yaml')
    conf = {}
    if os.path.exists(filename):
        with open(filename) as f:
           conf = yaml.safe_load(f) or {}
    return conf


def get_mako_shortcode_comp(lookup, conf):
    try:
        mako_shortcode_comp = conf.get('mako_shortcodes', None)
        if mako_shortcode_comp:
            mako_shortcode_comp = lookup.get_template(mako_shortcode_comp)
    except Exception as e:
        print("WARNING: Could not load shortcodes from {}: {}".format(
            conf['mako_shortcodes'], e))
        mako_shortcode_comp = None
    conf['_mako_shortcode_comp'] = mako_shortcode_comp


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
        self_url = tpl['target'].replace(data['WEBROOT'], '', 1)
        data['SELF_URL'] = self_url
        data['SELF_TEMPLATE'] = tpl['src']
        try:
            tpl_output = template.render(**data)
        except:
            print("WARNING: Error when rendering {}: {}".format(
                tpl['src_path'], text_error_template().render()))
            tpl_output = None
        # empty output => nothing is written
        if tpl_output:
            with open(tpl['target'], 'w') as f:
                f.write(tpl_output)
            print('[%s] - template: %s' % (
                str(datetime.datetime.now()), tpl['src']))
        elif tpl_output is not None:
            # (probably) deliberately empty output
            print("NOTICE: template {} had no output, nothing written".format(
                tpl['src']))


def process_markdown_content(content, lookup, conf, force):
    """
    Renders the specified markdown content into the outputdir.
    """
    for ct in content:
        if not force and is_older_than(ct['source_file'], ct['target']):
            continue
        template = lookup.get_template(ct['template'])
        maybe_mkdir(ct['target'])
        data = ct['data']
        # depends on pre_render conf setting
        html = ct['rendered'] if 'rendered' in ct else render_markdown(ct, conf)
        data['CONTENT'] = html
        data['RAW_CONTENT'] = ct['doc']
        try:
            html_output = template.render(**data)
        except:
            print("WARNING: Error when rendering md {}: {}".format(
                ct['source_file_short'], text_error_template().render()))
            html_output = None
        if html_output:
            with open(ct['target'], 'w') as f:
                f.write(template.render(**data))
            print('[%s] - content: %s' % (
                str(datetime.datetime.now()), ct['source_file_short']))


def render_markdown(ct, conf):
    "Convert markdown document to HTML (including shortcodes)"
    if 'CONTENT' in ct:
        return ct['CONTENT']
    data = ct['data']
    doc = ct['doc']
    if '{{<' in doc:
        mako_shortcode_comp = conf.get('_mako_shortcode_comp')
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
    return markdown.markdown(doc, extensions=extensions)


def process_assets(assetdir, theme_assets, outputdir, conf, css_dir_from_start, force):
    """
    Compiles assets from assetdir into outputdir.
    Only handles sass/scss files in the sass subdirectory for now.
    """
    scss_input = os.path.join(assetdir, 'scss')
    theme_scss = os.path.join(theme_assets, 'scss') if theme_assets else None
    if not os.path.exists(scss_input) or (
            theme_scss and os.path.exists(theme_scss)):
        return
    css_output = os.path.join(outputdir, 'css')
    if not os.path.exists(css_output):
        os.mkdir(css_output)
    output_style = conf.get('sass_output_style', 'expanded')
    if force or not css_dir_from_start or not dir_is_older_than(theme_scss, css_output):
        force = True  # since timestamp check for normal scss is now useless
        sass.compile(
            dirname=(theme_scss, css_output), output_style=output_style)
        print('[%s] - sass: theme' % datetime.datetime.now())
    if force or not css_dir_from_start or not dir_is_older_than(scss_input, css_output):
        sass.compile(
            dirname=(scss_input, css_output), output_style=output_style)
        print('[%s] - sass: refresh' % datetime.datetime.now())


def get_content(ctdir, datadir, outputdir, template_vars, conf):
    """
    Get those markdown files that need processing.
    """
    content = []
    default_template = conf.get('default_template', 'md_base.mhtml')
    default_pretty_path = lambda x: False if x == 'index.md' else True
    for root, dirs, files in os.walk(ctdir):
        for fn in files:
            if not fn.endswith('.md'):
                continue
            if fn.startswith('_') or fn.startswith('.'):
                continue
            source_file = os.path.join(root, fn)
            source_file_short = source_file.replace(ctdir, '', 1)
            with open(source_file) as f:
                meta, doc = frontmatter.parse(f.read())
            if meta.get('draft', False) and not conf.get('render_drafts', False):
                continue
            data = {}
            data.update(template_vars)
            data.update(meta)
            template = data.get('template', default_template)
            pretty_path = data.get('pretty_path', default_pretty_path(fn))
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
            data['MTIME'] = os.path.getmtime(source_file)
            content.append({
                'source_file': source_file,
                'source_file_short': source_file_short,
                'target': target_fn,
                'template': template,
                'data': data,
                'doc': doc,
                'url': data['SELF_URL'],
            })
            if conf.get('pre_render', False):
                content[-1]['rendered'] = render_markdown(content[-1], conf)
    template_vars['MDCONTENT'] = content
    for it in content:
        it['data']['MDCONTENT'] = content
    return content


def get_templates(tpldir, themedir, outputdir, template_vars):
    """
    Get those templates that need processing.
    """
    templates = []
    seen = set()
    searchdirs = [tpldir]
    if os.path.exists(os.path.join(themedir, 'templates')):
        searchdirs.append(os.path.join(themedir, 'templates'))
    for tplroot in searchdirs:
        for root, dirs, files in os.walk(tplroot):
            if root.endswith('/base'):
                continue
            for fn in files:
                if 'base' in fn or fn.startswith(('_', '.')):
                    continue
                if fn.endswith('.mhtml'):
                    source = os.path.join(root.replace(tplroot, '', 1), fn)
                    if source.startswith('/'):
                        source = source[1:]
                    # we have a theme template overridden locally
                    if source in seen:
                        continue
                    seen.add(source)
                    # Keep an extra extension before .mhtml (e.g. "atom.xml.mhtml")
                    if re.search(r'\.\w{2,4}\.mhtml$', fn):
                        html_fn = fn.replace('.mhtml', '')
                    else:
                        html_fn = fn.replace('.mhtml', '.html')
                    html_dir = root.replace(tplroot, outputdir, 1)
                    target = os.path.join(html_dir, html_fn)
                    templates.append({
                        'src': source,
                        'src_path': os.path.join(root, fn),  # full path
                        'target': target,
                        'url': target.replace(outputdir, '', 1),
                    })
    template_vars['TEMPLATES'] = templates
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
