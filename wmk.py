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
import pypandoc
import lunr
import json

from mako.template import Template
from mako.lookup import TemplateLookup
from mako.exceptions import text_error_template, TemplateLookupException
from mako.runtime import Undefined

from wmk_utils import slugify, attrdict, MDContentList, RenderCache
import wmk_mako_filters as wmf


VERSION = '0.9.1'


# Template variables with these names will be converted to date or datetime
# objects (depending on length) - if they conform to ISO 8601.
KNOWN_DATE_KEYS = (
    'date', 'pubdate', 'modified_date', 'expire_date', 'created_date')


def main(basedir=None, quick=False):
    """
    Builds/copies everything into the output dir (htdocs).
    """
    # `force` mode is now the default and is turned on by setting --quick
    force = not quick
    if basedir is None:
        basedir = os.path.dirname(os.path.realpath(__file__)) or '.'
    basedir = os.path.realpath(basedir)
    if not os.path.isdir(basedir):
        raise Exception('{} is not a directory'.format(basedir))
    conf_file = re.sub(
        r'.*/', '', os.environ.get('WMK_CONFIG', '')) or 'wmk_config.yaml'
    if not os.path.exists(os.path.join(basedir, conf_file)):
        print('ERROR: {} does not contain a {}'.format(
                basedir, conf_file))
        sys.exit(1)
    dirs = get_dirs(basedir)
    ensure_dirs(dirs)
    sys.path.insert(0, dirs['python'])
    conf = get_config(basedir, conf_file)
    # 1) copy static files
    # css_dir_from_start is workaround for process_assets timestamp check
    css_dir_from_start = os.path.exists(os.path.join(dirs['output'], 'css'))
    themedir = os.path.join(
        dirs['themes'], conf.get('theme')) if conf.get('theme') else None
    if themedir and not os.path.exists(themedir):
        themedir = None
    if themedir and os.path.exists(os.path.join(themedir, 'static')):
        os.system('rsync -a "%s/" "%s/"' % (
            os.path.join(themedir, 'static'), dirs['output']))
    if themedir and os.path.exists(os.path.join(themedir, 'py')):
        sys.path.insert(1, os.path.join(themedir, 'py'))
    os.system('rsync -a "%s/" "%s/"' % (dirs['static'], dirs['output']))
    # support content bundles (mainly images inside content dir)
    os.system(
        'rsync -a --exclude "*.md" --exclude "*.yaml" --exclude "_*" --exclude ".*" --prune-empty-dirs "%s/" "%s/"'
        % (dirs['content'], dirs['output']))
    # 2) compile assets (only scss for now):
    theme_assets = os.path.join(themedir, 'assets') if themedir else None
    process_assets(
        dirs['assets'], theme_assets, dirs['output'],
        conf, css_dir_from_start, force)
    # Global data for template rendering, used by both process_templates
    # and process_markdown_content.
    template_vars = {
        'DATADIR': os.path.realpath(dirs['data']),
        'CONTENTDIR': os.path.realpath(dirs['content']),
        'WEBROOT': os.path.realpath(dirs['output']),
        'TEMPLATES': [],
        'MDCONTENT': MDContentList([]),
    }
    template_vars.update(conf.get('template_context', {}))
    template_vars['site'] = attrdict(conf.get('site', {}))
    lookup_dirs = [dirs['templates']]
    if themedir and os.path.exists(os.path.join(themedir, 'templates')):
        lookup_dirs.append(os.path.join(themedir, 'templates'))
    if conf.get('extra_template_dirs', None):
        lookup_dirs += conf['extra_template_dirs']
    # Add wmk_home templates for "built-in" shortcodes
    wmk_home = os.path.dirname(os.path.realpath(__file__))
    lookup_dirs.append(os.path.join(wmk_home, 'templates'))
    mako_imports = ['from wmk_mako_filters import ' + ', '.join(wmf.__all__)]
    if conf.get('mako_imports', None):
        mako_imports += conf.get('mako_imports')
    lookup = TemplateLookup(
        directories=lookup_dirs,
        imports=mako_imports)
    conf['_lookup'] = lookup
    # 3) get info about stand-alone templates and Markdown content
    template_vars['site'].build_time = datetime.datetime.now()
    templates = get_templates(
        dirs['templates'], themedir, dirs['output'], template_vars)
    index_yaml = get_index_yaml_data(dirs['content'], dirs['data'])
    conf['_index_yaml_data'] = index_yaml or {}
    content = get_content(
        dirs['content'], dirs['data'], dirs['output'],
        template_vars, conf, force)
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
        'python': basedir + '/py', # python modeles available to Mako templates
    }


def get_config(basedir, conf_file):
    filename = os.path.join(basedir, conf_file)
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
        self_url = tpl['target'].replace(data['WEBROOT'], '', 1)
        self_url = re.sub(r'/index.html$', '/', self_url)
        data['SELF_URL'] = self_url
        data['SELF_FULL_PATH'] = None
        data['SELF_TEMPLATE'] = tpl['src']
        data['page'] = attrdict({}) # empty but present...
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
        try:
            template = lookup.get_template(ct['template'])
        except TemplateLookupException:
            if not '/' in ct['template']:
                template = lookup.get_template('base/' + ct['template'])
                ct['template'] = 'base/' + ct['template']
            else:
                raise
        maybe_mkdir(ct['target'])
        data = ct['data']
        # Since 'pre_render' was dropped, this condition should always be true.
        html = ct['rendered'] if 'rendered' in ct else render_markdown(ct, conf)
        data['CONTENT'] = html
        data['RAW_CONTENT'] = ct['doc']
        page = data['page']
        html_output = ''
        try:
            html_output = template.render(**data)
        except:
            print("WARNING: Error when rendering md {}: {}".format(
                ct['source_file_short'], text_error_template().render()))
        # If present, POSTPROCESS will have been added by a shortcode call
        if html_output and page.get('POSTPROCESS'):
            html_output = postprocess_html(page.POSTPROCESS, data, html_output)
        if html_output and not page.get('do_not_render', False):
            with open(ct['target'], 'w') as f:
                f.write(html_output)
            print('[%s] - content: %s' % (
                str(datetime.datetime.now()), ct['source_file_short']))
        elif html_output:
            # This output is non-draft but marked as not to be rendered.
            # ("headless" in Hugo parlance)
            print('[%s] - non-rendered: %s' % (
                str(datetime.datetime.now()), ct['source_file_short']))


def postprocess_html(ppr, data, html):
    """
    - ppr is a postprocessing callable or a list of such.
    - data is the entire context previously passed to the mako renderer.
    - html is the entire HTML page previously returned from the mako renderer.

    Each postprocessing callable MUST return the html (changed or unchanged).
    Returning None or an empty string results in the file not being rendered.
    """
    # data contains page, CONTENT, RAW_CONTENT, etc.
    if callable(ppr):
        return ppr(html, **data)
    elif isinstance(ppr, (list, tuple)):
        for pp in ppr:
            if callable(pp):
                html = pp(html, **data)
    return html


def render_markdown(ct, conf):
    """
    Convert markdown document to HTML (including shortcodes).
    If possible, retrieve the converted version from cache.
    """
    if 'CONTENT' in ct:
        return ct['CONTENT']
    data = ct['data']
    pg = data.get('page', {})
    doc = ct['doc']
    target = ct.get('target', '')
    # The following settings affect cache validity:
    extensions, extension_configs = markdown_extensions_settings(pg, conf)
    is_pandoc = pg.get('pandoc', conf.get('pandoc', False))
    pandoc_filters = pg.get('pandoc_filters', conf.get('pandoc_filters')) or []
    pandoc_options = pg.get('pandoc_options', conf.get('pandoc_options')) or []
    # TODO: offer support for multiple output formats when using pandoc?
    # This should be a markdown subformat or gfm
    pandoc_input = pg.get('pandoc_input_format',
                          conf.get('pandoc_input_format')) or 'markdown'
    # This should be an html subformat
    pandoc_output = pg.get('pandoc_output_format',
                           conf.get('pandoc_output_format')) or 'html'
    use_cache = conf.get('use_cache', True) and not pg.get('no_cache', False)
    if use_cache:
        optstr = str([target, extensions, extension_configs,
                      is_pandoc, pandoc_filters, pandoc_options,
                      pandoc_input, pandoc_output])
        projectdir = ct['data']['DATADIR'][:-5] # remove /data from the end
        cache = RenderCache(doc, optstr, projectdir)
        ret = cache.get_cache()
        if ret:
            return ret
    else:
        ret = None
        cache = None
    nth = {}
    if '{{<' in doc:
        # Mako shortcodes
        # We need to handle include() first.
        incpat = r'{{<\s*(include)\(\s*(.*?)\s*\)\s*>}}'
        incfound = re.search(incpat, doc, re.DOTALL)
        while incfound:
            doc = re.sub(incpat, mako_shortcode(conf, data, nth), doc, flags=re.DOTALL)
            incfound = re.search(incpat, doc, re.DOTALL)
        # Now other shortcodes.
        # funcname, argstring
        pat = r'{{<\s*(\w+)\(\s*(.*?)\s*\)\s*>}}'
        found = re.search(pat, doc, re.DOTALL)
        while found:
            doc = re.sub(pat, mako_shortcode(conf, data, nth), doc, flags=re.DOTALL)
            found = re.search(pat, doc, re.DOTALL)
        if use_cache and pg.get('POSTPROCESS', None):
            use_cache = False
            print("NOTE [%s]: postprocessing, not caching %s"
                  % (str(datetime.datetime.now()), ct['url']))
    if is_pandoc:
        # For TOC to be added, page.toc must be True and the
        # markdown content must have a '[TOC]' line
        need_toc = (
            pg.get('toc', False)
            and re.search(r'^\[TOC\]$', doc, flags=re.M))
        if need_toc:
            if not pandoc_options:
                pandoc_options = []
            pandoc_options.append('--toc')
            pandoc_options.append('--standalone')
            toc_depth = ct['data']['page'].get('toc_depth')
            if toc_depth:
                pandoc_options.append('--toc-depth=%s' % toc_depth)
            toc_tpl = os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                'aux',
                'pandoc-toc-only.html')
            pandoc_options.append('--template=%s' % toc_tpl)
        popt = {}
        if pandoc_filters:
            popt['filters'] = pandoc_filters
        if pandoc_options:
            popt['extra_args'] = pandoc_options
        ret = pypandoc.convert_text(
            doc, pandoc_output, format=pandoc_input, **popt)
        if need_toc:
            offset = ret.find('</nav>') + 6
            toc = ret[:offset]
            ret = re.sub(r'<p>\[TOC\]</p>', toc, ret[offset:], flags=re.M)
    else:
        ret = markdown.markdown(
            doc, extensions=extensions, extension_configs=extension_configs)
    if cache and use_cache:
        # TODO: Delay cache saving until postprocessing is done.
        cache.write_cache(ret)
    return ret


def markdown_extensions_settings(pg, conf):
    extensions = pg.get('markdown_extensions',
                        conf.get('markdown_extensions', None))
    # Extensions can only be disabled by setting them to an empty list,
    # not by setting them to None or False.
    if not extensions and not isinstance(extensions, (list, tuple)):
        extensions = ['extra', 'sane_lists']
    extension_configs = pg.get('markdown_extension_configs',
                        conf.get('markdown_extension_configs', {}))
    # Special convenience options for specific extensions,
    # configurable on a page-by-page basis.
    if 'toc' in pg and pg['toc'] and not 'toc' in extensions:
        extensions.append('toc')
    if 'toc' in extensions:
        if 'toc' in pg and not pg['toc']:
            # toc is turned off for this page
            extensions = [_ for _ in extensions
                          if not (isinstance(_, str) and _ == 'toc')]
        elif 'toc_depth' in pg:
            if not 'toc' in extension_configs:
                extension_configs['toc'] = {'toc_depth': pg['toc_depth']}
            else:
                extension_configs['toc']['toc_depth'] = pg['toc_depth']
    if 'wikilinks' in extensions and pg.get('wikilinks', None):
        # The defaults are {'base_url': '/', 'end_url': '/', 'html_class': 'wikilink'}
        wikilinks_conf = pg['wikilinks']
        extension_configs['wikilinks'] = wikilinks_conf
    return (extensions, extension_configs)


def process_assets(assetdir, theme_assets, outputdir, conf, css_dir_from_start, force):
    """
    Compiles assets from assetdir into outputdir.
    Only handles sass/scss files in the scss subdirectory for now.
    """
    scss_input = os.path.join(assetdir, 'scss')
    theme_scss = os.path.join(theme_assets, 'scss') if theme_assets else None
    if not (os.path.exists(scss_input) or (
            theme_scss and os.path.exists(theme_scss))):
        return
    css_output = os.path.join(outputdir, 'css')
    if not os.path.exists(css_output):
        os.mkdir(css_output)
    output_style = conf.get('sass_output_style', 'expanded')
    if theme_scss and (
            force or not css_dir_from_start or not dir_is_older_than(theme_scss, css_output)):
        force = True  # since timestamp check for normal scss is now useless
        sass.compile(
            dirname=(theme_scss, css_output), output_style=output_style)
        print('[%s] - sass: theme' % datetime.datetime.now())
    if force or not css_dir_from_start or not dir_is_older_than(scss_input, css_output):
        if not os.path.exists(scss_input):
            return
        include_paths = {}
        if theme_scss:
            include_paths = {'include_paths': [theme_scss]}
        sass.compile(
            dirname=(scss_input, css_output), output_style=output_style, **include_paths)
        print('[%s] - sass: refresh' % datetime.datetime.now())


def get_index_yaml_data(ctdir, datadir):
    "Looks for index.yaml files in content dir and registers them by directory."
    ret = {}
    for root, dirs, files in os.walk(ctdir):
        if not 'index.yaml' in files:
            continue
        curdir = root.replace(ctdir, '', 1).strip('/')
        with open(os.path.join(root, 'index.yaml')) as yf:
            info = yaml.safe_load(yf) or {}
            if 'LOAD' in info:
                with open(os.path.join(datadir, info['LOAD'])) as lf:
                    loaded = yaml.safe_load(lf) or {}
                    if loaded:
                        loaded.update(info)
                        info = loaded
            for k in info:
                if isinstance(info[k], str) and info[k].startswith('LOAD '):
                    fn = info[k][5:].strip('"').strip("'")
                    try:
                        with open(os.path.join(datadir, fn)) as lf:
                            loaded = yaml.safe_load(lf) or {}
                            if loaded:
                                info[k] = loaded
                    except:
                        pass
            removed = info.pop('LOAD', None)
            ret[curdir] = info
    return ret


def get_content(ctdir, datadir, outputdir, template_vars, conf, force=False):
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
                try:
                    meta, doc = frontmatter.parse(f.read())
                except Exception as e:
                    raise Exception(
                        "Error when parsing frontmatter for " + source_file + ': ' + str(e))
            if meta.get('draft', False) and not conf.get('render_drafts', False):
                continue
            # data is global vars, page is specific to this markdown file
            data = {}
            data.update(template_vars)
            page = {}
            # load data from relevant index.yaml files
            idata = conf['_index_yaml_data']
            for k in sorted(idata.keys()):
                if source_file_short.strip('/').startswith(k):
                    page.update(idata[k])
            page.update(meta)
            # merge with data from 'LOAD' file(s), if any
            if 'LOAD' in page:
                load_path = os.path.join(datadir, page['LOAD'])
                if os.path.exists(load_path):
                    loaded = {}
                    with open(load_path) as yf:
                        loaded = yaml.safe_load(yf) or {}
                    for k in loaded:
                        if not k in page:
                            page[k] = loaded[k]
            for k in page:
                if isinstance(page[k], str) and page[k].startswith('LOAD '):
                    fn = page[k][5:].strip('"').strip("'")
                    try:
                        with open(os.path.join(datadir, fn)) as lf:
                            loaded = yaml.safe_load(lf) or {}
                            if loaded:
                                page[k] = loaded
                    except Exception as e:
                        print("LOAD ERROR FOR %s: %s" % (fn, e))
            # template
            template = page.get(
                'template', data.get(
                    'template', page.get(
                        'layout', data.get(
                            'layout', default_template))))
            if not re.search(r'\.\w{2,5}$', template):
                template += '.mhtml'
            if not 'template' in page:
                page['template'] = template
            # pretty_path
            pretty_path = page.get(
                'pretty_path', data.get('pretty_path', default_pretty_path(fn)))
            if not 'pretty_path' in page:
                page['pretty_path'] = pretty_path
            # Slug determines destination file
            if 'slug' in page and re.match(r'^[a-z0-9_-]+$', page['slug']):
                fn = re.sub(r'[^/]+\.md$', (page['slug']+'.md'), fn)
            # Ensure that the destination file/dir only contains a limited
            # set of characters
            fn_parts = fn.split('/')
            if re.search(r'[^A-Za-z0-9_.,=-]', fn_parts[-1]):
                fn_parts[-1] = slugify(fn_parts[-1])
            # Ensure that slug is present
            if not 'slug' in page:
                page['slug'] = fn_parts[-1][:-3]
            # Ensure that title is present
            if not 'title' in page:
                page['title'] = fn.split('/')[-1]
                page['title'] = re.sub(
                    r'\.(?:md|markdown|mdwn|html?)$', '', page['title'], flags=re.I)
                page['title'] = re.sub(r'[_ -]', ' ', page['title']).strip() or page['slug']
            fn = '/'.join(fn_parts)
            html_fn = fn.replace('.md', '/index.html' if pretty_path else '.html')
            html_dir = root.replace(ctdir, outputdir, 1)
            target_fn = os.path.join(html_dir, html_fn)
            data['SELF_URL'] = '' if page.get('do_not_render') \
                else target_fn.replace(outputdir, '', 1)
            data['SELF_FULL_PATH'] = source_file
            data['SELF_TEMPLATE'] = template
            data['MTIME'] = datetime.datetime.fromtimestamp(
                os.path.getmtime(source_file))
            data['RENDERER'] = lambda x: render_markdown(x, conf)
            # convert some common datetime strings to datetime objects
            parse_dates(page)
            data['page'] = attrdict(page)
            data['DATE'] = preferred_date(data)
            content.append({
                'source_file': source_file,
                'source_file_short': source_file_short,
                'target': target_fn,
                'template': template,
                'data': data,
                'doc': doc,
                'url': data['SELF_URL'],
            })
            content[-1]['rendered'] = render_markdown(content[-1], conf)
    content = MDContentList(content)
    template_vars['MDCONTENT'] = content
    for it in content:
        it['data']['MDCONTENT'] = content
    if conf.get('lunr_index', False):
        build_lunr_index(content,
                         conf.get('lunr_index_fields', None),
                         conf.get('lunr_languages', None))
    return content


def preferred_date(data):
    """
    Pick a date by priority among several date keys in `page`, with `MTIME` as
    fallback. This will be set as the `DATE` key.
    """
    for k in KNOWN_DATE_KEYS:
        if k in data['page']:
            return data['page'][k]
    return data['MTIME']


def parse_dates(data):
    for k in KNOWN_DATE_KEYS:
        if k in data:
            if isinstance(data[k], (datetime.datetime, datetime.date)):
                continue
            try:
                if len(str(data[k])) == 10:
                    data[k] = datetime.date.fromisoformat(data[k])
                else:
                    dstr = data[k].replace('Z', '')
                    dstr = re.sub(r' *([-+])(\d\d):?(\d\d) *$', r'\1\2:\3', dstr)
                    data[k] = datetime.datetime.fromisoformat(dstr)
            except Exception as e:
                pass


def get_templates(tpldir, themedir, outputdir, template_vars):
    """
    Get those templates that need processing.
    """
    templates = []
    seen = set()
    searchdirs = [tpldir]
    if themedir and os.path.exists(os.path.join(themedir, 'templates')):
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
                    if re.search(r'\.\w{2,5}\.mhtml$', fn):
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
    if not src:
        return True
    if not (os.path.exists(src) and os.path.exists(trg)):
        return False
    newest_src = get_newest_ts_of_dir(src)
    newest_trg = get_newest_ts_of_dir(trg)
    return newest_src < newest_trg


def get_newest_ts_of_dir(src):
    newest = 0
    if not src:
        return newest
    for root, dirs, files in os.walk(src):
        for fn in files:
            ts = os.path.getmtime(os.path.join(root, fn))
            if ts > newest:
                newest = ts
    return newest


def parse_argstr(argstr):
    "Parse a string representing the arguments part of a function call."
    try:
        fake = 'f({})'.format(argstr)
        tree = ast.parse(fake)
        funccall = tree.body[0].value
        args = [ast.literal_eval(arg) for arg in funccall.args]
        kwargs = {arg.arg: ast.literal_eval(arg.value) for arg in funccall.keywords}
        return args, kwargs
    except:
        raise Exception("Could not parse argstr: {}".format(argstr))


def mako_shortcode(conf, ctx, nth=None):
    "Return a match replacement function for mako shortcode handling."
    if nth is None:
        nth = {}
    def replacer(match):
        name = match.group(1)
        if name in nth:
            nth[name] += 1
        else:
            nth[name] = 1
        argstr = match.group(2)
        args, kwargs = parse_argstr(argstr)
        try:
            lookup = conf['_lookup']
            subdir = conf.get('mako_shortcodes_dir', 'shortcodes')
            tplnam = '%s/%s.mc' % (subdir.strip('/'), name)
            tpl = lookup.get_template(tplnam)
            ckwargs = {}
            ckwargs.update(ctx)
            ckwargs.update(kwargs)
            ckwargs['nth'] = nth[name]  # invocation count
            if not 'LOOKUP' in ckwargs:
                ckwargs['LOOKUP'] = lookup
            return tpl.render(*args, **ckwargs)
        except Exception as e:
            print("WARNING: shortcode {} failed: {}".format(name, e))
            # prevent infinite loops
            return match.group(0).replace('{', '(').replace('}', ')')
    return replacer


def build_lunr_index(content, index_fields, langs=None):
    """
    Builds a search index compatible with lunr.js and writes it as '/idx.json'.
    """
    if not content:
        return
    if not index_fields or not isinstance(index_fields, dict):
        index_fields = {'title': 5, 'body': 1}
    frontmatter_fields = [k for k in index_fields if not k == 'body']
    documents = []
    summaries = {}
    start = datetime.datetime.now()
    for it in content:
        if not it['url']:
            continue
        rec = {'id': it['url'].replace('/index.html', '/'), 'body': it['doc']}
        if frontmatter_fields:
            pg = it['data']['page']
            for field in frontmatter_fields:
                rec[field] = str(pg.get(field, ''))
        documents.append(rec)
        summaries[rec['id']] = lunr_summary(rec)
    weights = [
        {'field_name': k, 'boost': index_fields[k]}
        for k in index_fields]
    known_langs = (
        'de', 'da', 'en', 'fi', 'fr', 'hu', 'it', 'nl', 'no', 'pt', 'ro', 'ru')
    if langs:
        if instance(langs, str):
            langs = [langs]
        for lang in langs:
            if not lang in known_langs:
                raise Exception(
                    "Unsupported language in lunr_languages: '%s'" % lang)
        languages = {'languages': langs}
    else:
        langs = {}
    idx = lunr.lunr(ref='id', fields=weights, documents=documents, **langs)
    idx = idx.serialize()
    webroot = content[0]['data']['WEBROOT']
    idx_file = os.path.join(webroot, 'idx.json')
    summaries_file = os.path.join(webroot, 'idx.summaries.json')
    with open(idx_file, 'w') as f:
        json.dump(idx, f)
    with open(summaries_file, 'w') as f:
        json.dump(summaries, f)
    end = datetime.datetime.now()
    duration = str(end - start)
    print('[%s] - lunr index: %s [build time: %s]' % (
        str(end), '/idx.json', duration))

def lunr_summary(rec):
    ret = {'title': rec.get('title', rec['id'])}
    for k in ('summary', 'intro', 'description'):
        if k in rec and rec[k]:
            ret['summary'] = rec[k]
            break
    if not 'summary' in rec:
        summary = rec['body'][:1000] or ''
        summary = re.sub(r'[#`\*]', '', summary)
        summary = re.sub(r'====*', '', summary)
        summary = re.sub(r'----*', '', summary)
        summary = re.sub(r'\s+', ' ', summary)
        summary = summary.replace('[TOC]', '')
        summary = re.sub(r'\[(.*?)\][\[\(].*?[\]\)]', r'\1', summary)
        summary = re.sub(r'{{<.*?>}}', '', summary)
        summary = re.sub(r'<[^>]*>', r' ', summary)
        summary = re.sub(r'\s+', ' ', summary)
        summary = summary[:200].strip()
        ret['summary'] = summary
    return ret


if __name__ == '__main__':
    if sys.argv[1] == '--version':
        print('wmk version {}'.format(VERSION))
        sys.exit()
    basedir = sys.argv[1] if len(sys.argv) > 1 else None
    quick = True if len(sys.argv) > 2 and sys.argv[2] in ('-q', '--quick') else False
    main(basedir, quick)
