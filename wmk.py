#!/usr/bin/env python3

import os
import sys
import datetime
import re
import ast
import json
import subprocess
import hashlib
import shutil

import sass
import yaml
import frontmatter
import markdown
import pypandoc
import lunr

from mako.lookup import TemplateLookup
from mako.exceptions import text_error_template, TemplateLookupException
from mako.runtime import Undefined

from wmk_utils import slugify, attrdict, MDContentList, RenderCache
import wmk_mako_filters as wmf

# To be imported from wmk_autoload and/or wmk_theme_autoload, if applicable
autoload = {}

VERSION = '1.1.1'

# Template variables with these names will be converted to date or datetime
# objects (depending on length) - if they conform to ISO 8601.
KNOWN_DATE_KEYS = (
    'date', 'pubdate', 'modified_date', 'expire_date', 'created_date')

CONTENT_EXTENSIONS = {
    '.md': {}, # just markdown...
    '.mdwn': {},
    '.mdown': {},
    '.markdown': {},
    '.mmd': {'pandoc_input_format': 'markdown_mmd'},
    '.gfm': {'pandoc_input_format': 'gfm'},
    '.html': {'raw': True},
    '.htm': {'raw': True},
    # pandoc-only formats below
    '.org': {'pandoc': True, 'pandoc_input_format': 'org'},
    '.rst': {'pandoc': True, 'pandoc_input_format': 'rst'},
    '.tex': {'pandoc': True, 'pandoc_input_format': 'latex'},
    '.man': {'pandoc': True, 'pandoc_input_format': 'man'},
    '.rtf': {'pandoc': True, 'pandoc_input_format': 'rtf'},
    '.textile': {'pandoc': True, 'pandoc_input_format': 'textile'},
    '.xml': {'pandoc': True, 'pandoc_input_format': 'jats'},
    '.jats': {'pandoc': True, 'pandoc_input_format': 'jats'},
    '.tei': {'pandoc': True, 'pandoc_input_format': 'tei'},
    '.docbook': {'pandoc': True, 'pandoc_input_format': 'docbook'},
    # binary formats supported via pandoc (converted to markdown as an intermediary step)
    '.docx': {'is_binary': True, 'pandoc': True, 'pandoc_binary_format': 'docx',
              'pandoc_input_format': 'markdown'},
    '.odt': {'is_binary': True, 'pandoc': True, 'pandoc_binary_format': 'odt',
             'pandoc_input_format': 'markdown'},
    '.epub': {'is_binary': True, 'pandoc': True, 'pandoc_binary_format': 'epub',
             'pandoc_input_format': 'markdown'},
}


def main(basedir=None, quick=False):
    """
    Builds/copies everything into the output dir (normally htdocs).
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
    conf = get_config(basedir, conf_file)
    dirs = get_dirs(basedir, conf)
    ensure_dirs(dirs)
    sys.path.insert(0, dirs['python'])
    global autoload
    try:
        from wmk_autoload import autoload
    except:
        pass
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
        try:
            from wmk_theme_autoload import autoload as theme_autoload
            for k in theme_autoload:
                if k in autoload:
                    continue
                autoload[k] = theme_autoload[k]
        except:
            pass
    os.system('rsync -a "%s/" "%s/"' % (dirs['static'], dirs['output']))
    # support content bundles (mainly images inside content dir)
    ext_excludes = ' '.join(['--exclude "*{}"'.format(_) for _ in CONTENT_EXTENSIONS.keys()])
    os.system(
        'rsync -a ' + ext_excludes + ' --exclude "*.yaml" --exclude "_*" --exclude ".*" --prune-empty-dirs "%s/" "%s/"'
        % (dirs['content'], dirs['output']))
    # 2) compile assets (only scss for now):
    theme_assets = os.path.join(themedir, 'assets') if themedir else None
    process_assets(
        dirs['assets'], theme_assets, dirs['output'],
        conf, css_dir_from_start, force)
    assets_map = fingerprint_assets(conf, dirs['output'], dirs['data'])
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
    # If assets_fingerprinting is off fallback to the 'assets_map' setting
    template_vars['ASSETS_MAP'] = assets_map or get_assets_map(conf, template_vars['DATADIR'])
    # Used as a filter in Mako templates
    template_vars['fingerprint'] = wmf.fingerprint_gen(
            template_vars['WEBROOT'], template_vars['ASSETS_MAP'])
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
    # 3) write redirect files
    handle_redirects(
        conf.get('redirects'), template_vars['DATADIR'], template_vars['WEBROOT'])
    # 4) get info about stand-alone templates and Markdown content
    template_vars['site'].build_time = datetime.datetime.now()
    templates = get_templates(
        dirs['templates'], themedir, dirs['output'], template_vars)
    index_yaml = get_index_yaml_data(dirs['content'], dirs['data'])
    conf['_index_yaml_data'] = index_yaml or {}
    content = get_content(
        dirs['content'], dirs['data'], dirs['output'],
        template_vars, conf, force)
    # 5) render templates
    process_templates(templates, lookup, template_vars, force)
    # 6) render Markdown/HTML content
    process_markdown_content(content, lookup, conf, force)


def get_assets_map(conf, datadir):
    if not 'assets_map' in conf:
        return {}
    am = conf['assets_map']
    if isinstance(am, dict):
        return conf['assets_map']
    elif isinstance(am, str):
        if not am.endswith(('.json', '.yaml')):
            return {}
        path = os.path.join(datadir, am.strip('/'))
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            if am.endswith('.json'):
                return json.loads(f.read())
            elif am.endswith('yaml'):
                return yaml.safe_load(f)
    return {}


def get_dirs(basedir, conf):
    """
    Configuration of subdirectory names relative to the basedir.
    """
    # For those who prefer 'site' or 'public' to 'htdocs' -- or perhaps
    # in order to distinguish production and development setups.
    output_dir = conf.get('output_directory', 'htdocs')
    output_dir = re.sub(r'^[\.\/]+', '', output_dir)
    return {
        'base': basedir,
        'templates': basedir + '/templates', # Mako templates
        'content': basedir + '/content',  # Markdown files
        'output': basedir + '/' + output_dir, # normally htdocs/
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
        global autoload
        if page.POSTPROCESS and page._CACHER:
            # NOTE: Because of the way we handle caching in the presence of
            # postprocessing, the postprocess chain is potentially run twice
            # for each applicable page: once before the Mako template is called,
            # and once after. To prevent this, we use the `was_called`
            # attribute which when present prevents the postprocessing from
            # taking place after the template has been applied.
            # AS A CONSEQUENCE, the range of application for a cached and a
            # non-cached page will be slightly different in that a cached page
            # will not apply the postprocessing code to the parts of the HTML
            # supplied by the Mako template, only to the HTML directly converted
            # from Markdown. For most purposes this will not matter. If it does
            # for some specific page you will need to set `no_cache` to True
            # in its frontmatter.
            for pp in page.POSTPROCESS:
                if isinstance(pp, str):
                    if autoload and pp in autoload:
                        html = autoload[pp](html, **data)
                        autoload[pp].was_called = data['SELF_FULL_PATH']
                    else:
                        print("WARNING: postprocess action '%s' missing for %s"
                              % (pp, ct['url']))
                else:
                    html = pp(html, **data)
                    pp.was_called = data['SELF_FULL_PATH']
            page._CACHER(html)
            ct['rendered'] = html
            data['CONTENT'] = html
        html_output = ''
        try:
            html_output = template.render(**data)
        except:
            print("WARNING: Error when rendering {}: {}".format(
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
        ppr = [ppr]
    fullpath = data['SELF_FULL_PATH']
    if isinstance(ppr, (list, tuple)):
        for pp in ppr:
            ppc = pp if callable(pp) else (autoload or {}).get(pp, None)
            if not ppc:
                print("WARNING: postprocess action '%s' missing for %s"
                      % (pp, fullpath))
                continue
            was_called = getattr(ppc, 'was_called', False)
            if was_called and was_called == fullpath:
                continue
            elif was_called:
                # The attribute was set by a different (cached) page using the same
                # callable for postprocessing; let's reset it.
                ppc.was_called = False
            html = ppc(html, **data)
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
    is_html = pg.get('_is_html', ct.get('source_file', '').endswith('.html'))
    is_pandoc = pg.get('pandoc', conf.get('pandoc', False))
    pandoc_filters = pg.get('pandoc_filters', conf.get('pandoc_filters')) or []
    pandoc_options = pg.get('pandoc_options', conf.get('pandoc_options')) or []
    # This should be a markdown/commonmark subformat or gfm, unless the
    # extension dictates otherwise (e.g. rst, org, textile, man)
    pandoc_input = pg.get('pandoc_input_format',
                          conf.get('pandoc_input_format')) or 'markdown'
    # This should be an html subformat
    pandoc_output = pg.get('pandoc_output_format',
                           conf.get('pandoc_output_format')) or 'html'
    use_cache = conf.get('use_cache', True) and not pg.get('no_cache', False)
    if use_cache:
        mtime_matters = pg.get('cache_mtime_matters',
                               conf.get('cache_mtime_matters', False))
        maybe_mtime = ct['data']['MTIME'] if mtime_matters else None
        optstr = str([target, extensions, extension_configs,
                      is_pandoc, pandoc_filters, pandoc_options,
                      pandoc_input, pandoc_output, maybe_mtime])
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
        incpat = r'{{<[ \n\r\t]*(include)\(\s*(.*?)\s*\)\s*>}}'
        incfound = re.search(incpat, doc, re.DOTALL)
        while incfound:
            doc = re.sub(incpat, mako_shortcode(conf, data, nth), doc, flags=re.DOTALL)
            incfound = re.search(incpat, doc, re.DOTALL)
        # Now other shortcodes.
        # funcname, argstring
        pat = r'{{<[ \n\r\t]*(\w+)\(\s*(.*?)\s*\)\s*>}}'
        found = re.search(pat, doc, re.DOTALL)
        while found:
            doc = re.sub(pat, mako_shortcode(conf, data, nth), doc, flags=re.DOTALL)
            found = re.search(pat, doc, re.DOTALL)
    ## May be added as a callable by shortcodes, or as a string pointing to an
    ## entry in autoload
    if pg.PREPROCESS:
        global autoload
        pg.is_pandoc = is_pandoc
        for pp in pg.PREPROCESS:
            if isinstance(pp, str):
                if autoload and pp in autoload:
                    doc = autoload[pp](doc, pg)
                else:
                    print("WARNING: Preprocessor '%s' not present for %s"
                          % (pp, ct['source_file_short']))
            else:
                doc = pp(doc, pg)
    if is_html:
        ret = doc
    elif is_pandoc:
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
        pd_doc = doc_with_yaml(pg, doc)
        ret = pypandoc.convert_text(
            pd_doc, pandoc_output, format=pandoc_input, **popt)
        if need_toc:
            offset = ret.find('</nav>') + 6
            toc = ret[:offset]
            ret = re.sub(r'<p>\[TOC\]</p>', toc, ret[offset:], flags=re.M)
        # map from format to target filename, e.g. {'pdf': 'subdir/myfile.pdf'}
        pdformats = pg.get('pandoc_extra_formats', {})
        # map from format to pandoc args: what to do for each format;
        # passed directly on to pypandoc. Keys: extra_args, filters
        pdformats_conf = pg.get('pandoc_extra_formats_settings', {})
        if pdformats:
            # NOTE: pd_doc will not include the output of shortcodes that affect
            #       POSTPROCESS, notably linkto and pagelist.
            pandoc_extra_formats(
                pd_doc, pandoc_input,
                pdformats, pdformats_conf, ct['data']['WEBROOT'])
    else:
        ret = markdown.markdown(
            doc, extensions=extensions, extension_configs=extension_configs)
    if cache and pg.POSTPROCESS:
        # Delay caching until just before calling the template
        pg._CACHER = lambda x: cache.write_cache(x)
    elif cache:
        cache.write_cache(ret)
    return ret


def pandoc_extra_formats(doc, pandoc_input, pdformats, pdformats_conf, webroot):
    """
    Writes extra pandoc output formats (pdf, docx, ...) to the files specified
    in `pdformats` with the optional configuration (extra_args, filters) specified
    in `pdformats_conf`.
    """
    for fmt in pdformats:
        cnf = pdformats_conf.get(fmt, {})
        if isinstance(cnf, list):
            cnf = {'extra_args': cnf}
        extra_args = cnf.get('extra_args', ())
        filters = cnf.get('filters', ())
        out_fn = pdformats[fmt].strip('/')
        outputfile = os.path.join(webroot, out_fn)
        maybe_mkdir(outputfile)
        pypandoc.convert_text(
            doc, to=fmt, format=pandoc_input,
            extra_args=extra_args, filters=filters,
            outputfile=outputfile)
        print('[%s] - extra: %s' % (
                str(datetime.datetime.now()), out_fn))



def doc_with_yaml(pg, doc):
    """
    Put YAML frontmatter back (with possible additions via inheritance), for
    potential use by Pandoc.
    """
    input_format = pg.get('pandoc_input_format', 'markdown')
    if not 'mark' in input_format and input_format != 'gfm':
        # skip out unless the input format is markdown-based
        return doc
    safe_pg = {}
    for k in pg:
        if k == 'DATE' and not 'date' in pg:
            safe_pg['date'] = str(pg[k])
        elif k.startswith('_') or k.upper() == k:
            # Skip private and system page variables
            continue
        elif isinstance(pg[k], (datetime.date, datetime.datetime)):
            safe_pg[k] = str(pg[k])
        elif isinstance(pg[k], attrdict):
            safe_pg[k] = dict(**pg[k])
        else:
            safe_pg[k] = pg[k]
    # This is primarily for pandoc, so let's accommodate it
    if not 'date' in safe_pg:
        for k in ('pubdate', 'modified_date', 'created_date', 'MTIME'):
            if k in safe_pg:
                safe_pg['date'] = safe_pg[k]
                break
    ret = '---\n' + yaml.safe_dump(safe_pg) + '---\n\n' + doc
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
    - Runs arbitrary commands from conf['assets_commands'], if specified.
    - Then handles sass/scss files in the scss subdirectory unless conf['use_sass'] is False.
    """
    assets_commands = conf.get('assets_commands', [])
    if assets_commands:
        # since timestamp check for normal scss will probably be useless now
        force = True
    for cmd in assets_commands:
        print('[%s] - assets command: %s' % (datetime.datetime.now(), cmd))
        basedir = os.path.split(assetdir.rstrip('/'))[0]
        ret = subprocess.run(
            cmd, cwd=basedir, shell=True, capture_output=True, encoding='utf-8')
        if ret.returncode == 0 and ret.stdout:
            print('  **OK**:', ret.stdout)
        elif ret.returncode != 0:
            print('  **WARNING** assets command error [exitcode={}]:'.format(
                ret.returncode), ret.stderr)
    sass_active = conf.get('use_sass', True)
    if not sass_active:
        return
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


def fingerprint_assets(conf, webroot, datadir):
    """
    Fingerprint (i.e. add hash to filename) files in the specified directories
    under the webroot, 'js/' and 'css/' by default.  For this to happen,
    'assets_fingerprinting' must be set to a true value in the configuration
    file. The directories and filename patterns may be specified in
    'assets_fingerprinting_conf' if needed.
    """
    fpr_on = conf.get('assets_fingerprinting', False)
    if not fpr_on:
        return
    # The keys are directory names
    default_fpr_dirs = {
        'js': {
            'pattern': r'\.m?js$', # pattern is required
            'except': r'\.[0-9a-f]{12}\.', # optional (this is the default)
        },
        'css': {
            'pattern': r'\.css$',
            'except': r'\.[0-9a-f]{12}\.'
        },
    }
    fpr_dirs = conf.get('assets_fingerprinting_conf', default_fpr_dirs)
    # Potentially load an initial assets map from conf or an external data file
    assets_map = get_assets_map(conf, datadir) or {}
    for dirkey in fpr_dirs:
        dirname = os.path.join(webroot, dirkey.strip('/'))
        if not os.path.isdir(dirname):
            continue
        for root, dirs, files in os.walk(dirname):
            pat = re.compile(fpr_dirs[dirkey]['pattern'])
            exc = re.compile(fpr_dirs[dirkey].get('except', r'\.[0-9a-f]{12}\.'))
            for fn in files:
                if not pat.search(fn) or exc.search(fn):
                    continue
                full_path = os.path.join(root, fn)
                with open(full_path, 'rb') as f:
                    hash = hashlib.sha1(f.read()).hexdigest()[:12]
                hashed_path = re.sub(r'\.(\w+)$', '.' + hash + '.' + r'\1', full_path)
                assets_map[full_path[len(webroot):]] = hashed_path[len(webroot):]
                if os.path.exists(hashed_path):
                    continue
                shutil.copyfile(full_path, hashed_path)
    return assets_map


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


def pandoc_metadata(doc, fn, fmt, projectdir):
    """
    Returns the parsed and converted metadata for the standard Pandoc metadata
    fields (mostly title, date and author). The input format is always a
    text-based one with native non-YAML metadata (i.e. currently org, rst,
    latex, man, rtf, xml/jats, tei or docbook).
    """
    tmpdir = os.path.join(projectdir, 'tmp')
    if not os.path.isdir(tmpdir):
        os.makedirs(tmpdir)
    meta_json_tpl = os.path.join(tmpdir, 'meta-json.tpl')
    if not os.path.exists(meta_json_tpl):
        with open(meta_json_tpl, 'w') as f:
            f.write('$meta-json$')
    cache = RenderCache(doc, str([fn, 'pandoc_metadata']), projectdir)
    ret = cache.get_cache()
    if ret:
        return json.loads(ret)
    ret = pypandoc.convert_file(
        fn,
        'html',
        format=fmt,
        extra_args=['--template={}'.format(meta_json_tpl)])
    cache.write_cache(ret)
    return json.loads(ret)


def binary_to_markdown(fn, fmt, projectdir=None):
    "Convert a docx/odt/epub file to markdown for further processing."
    if projectdir:
        st = os.stat(fn)
        fkey = '%d-%d' % (st.st_size, st.st_mtime)
        cache = RenderCache(fkey, str([fn, fmt, 'binary-to-markdown']), projectdir)
        doc = cache.get_cache()
        if not doc:
            doc = pypandoc.convert_file(
                fn, 'markdown', format=fmt, extra_args=['--standalone'])
            cache.write_cache(doc)
    else:
        doc = pypandoc.convert_file(
            fn, 'markdown', format=fmt, extra_args=['--standalone'])
    meta, doc = frontmatter.parse(doc)
    meta = maybe_extra_meta(meta, fn)
    return (meta, doc)


def maybe_extra_meta(meta, fn):
    """
    Look for a meta file with the same name as the source file, but with '.yaml'
    appended. If it exists, load it and add any new keys in it to the original
    metadata.
    """
    metafn = fn + '.yaml'
    if os.path.exists(metafn):
        with open(metafn) as yf:
            allmeta = yaml.safe_load_all(yf)
            for m in allmeta:
                if m:
                    m.update(meta)
                    meta.update(m)
    return meta


def get_content(ctdir, datadir, outputdir, template_vars, conf, force=False):
    """
    Get those markdown files that need processing.
    """
    content = []
    default_template = conf.get('default_template', 'md_base.mhtml')
    default_pretty_path = lambda x: False if x.startswith('index.') else True
    known_ids = set()
    known_exts = tuple(CONTENT_EXTENSIONS.keys())
    extpat = re.compile(r'\.(?:' + '|'.join([_[1:] for _ in known_exts]) + r')$')
    pandoc_meta_exts = ('.org', '.rst', '.tex', '.man', '.rtf',
                        '.xml' '.jats', '.tei', '.docbook')
    for root, dirs, files in os.walk(ctdir):
        for fn in files:
            if not fn.endswith(known_exts):
                continue
            if fn.startswith('_') or fn.startswith('.'):
                continue
            source_file = os.path.join(root, fn)
            source_file_short = source_file.replace(ctdir, '', 1)
            ext = re.findall(r'\.\w+$', fn)[0]
            ext_conf = CONTENT_EXTENSIONS[ext]
            if ext_conf.get('is_binary'):
                meta, doc = binary_to_markdown(
                    source_file, ext_conf.get('pandoc_binary_format'), datadir[:-5])
                for k in ext_conf:
                    if not k in meta:
                        meta[k] = ext_conf[k]
            else:
                with open(source_file) as f:
                    try:
                        meta, doc = frontmatter.parse(f.read())
                        meta = maybe_extra_meta(meta, source_file)
                        # Integrate pandoc's understanding of metadata for
                        # text-based non-markdown formats (other than textile,
                        # which uses YAML frontmatter natively).
                        # NOTE: Currently leads to the file being parsed twice --
                        # but only on the first pass, since the result is cached
                        # (regardless of the no_cache setting)
                        if fn.endswith(pandoc_meta_exts):
                            input_format = meta.get('pandoc_input_format', ext_conf['pandoc_input_format'])
                            pmeta = pandoc_metadata(doc, source_file, input_format, datadir[:-5])
                            for k in pmeta:
                                if not k in meta:
                                    meta[k] = pmeta[k]
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
                fn = re.sub(r'[^/]+\.(md|html)$', (page['slug']+r'.\1'), fn)
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
            # Ensure that id is present...
            if not 'id' in page:
                page['id'] = slugify(source_file_short[:-3])
            # ...and that it is unique
            if page['id'] in known_ids:
                id_add = 0
                id_tpl = '%s-%d'
                while True:
                    id_try = id_tpl % (page['id'], id_add)
                    if id_try in known_ids:
                        id_add += 1
                        continue
                    page['id'] = id_try
                    print("WARNING: changing id of %s to %s to prevent collision"
                          % (source_file_short, id_try))
                    break
            known_ids.add(page['id'])
            fn = '/'.join(fn_parts)
            if pretty_path:
                html_fn = extpat.sub('/index.html', fn)
            else:
                html_fn = extpat.sub('.html', fn)
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
            ext = re.search(r'\.\w+$', source_file).group(0)
            ext_conf = CONTENT_EXTENSIONS[ext]
            if ext_conf.get('raw', False):
                page['_is_html'] = True
            if ext_conf.get('pandoc', False):
                page['pandoc'] = True
            if 'pandoc_input_format' in ext_conf and not page.get('pandoc_input_format', None):
                page['pandoc_input_format'] = ext_conf['pandoc_input_format']
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


def handle_redirects(redir_file, datadir, webroot):
    if not redir_file:
        return
    if not isinstance(redir_file, str):
        redir_file = 'redirects.yaml'
    redir_file = os.path.join(datadir, redir_file.strip('/'))
    if not os.path.exists(redir_file):
        return
    redirects = []
    with open(redir_file) as f:
        redirects = yaml.safe_load(f) or {}
    if not (redirects and isinstance(redirects, list)):
        return
    for it in redirects:
        redir_to = it.get('to')
        redir_from = it.get('from')
        if not redir_to and redir_from:
            continue
        if not isinstance(redir_from, list):
            redir_from = [redir_from]
        for from_path in redir_from:
            write_redir_file(from_path, redir_to, webroot)


def write_redir_file(from_path, redir_to, webroot):
    if from_path.endswith('/'):
        from_path += 'index.html'
    filename = os.path.join(webroot, from_path.strip('/'))
    maybe_mkdir(filename)
    with open(filename, 'w') as f:
        f.write("""<html><head>
        <title>One moment... redirecting</title>
        <meta http-equiv="refresh" content="0;url={}">
        </head><body><p>Redirecting to <a href="{}">here</a>.</p>
        </body></html>""".format(redir_to, redir_to).replace(' '*8, ''))
    print("REDIR: {} => {}".format(from_path, redir_to))


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
    webroot = content[0]['data']['WEBROOT']
    idx_file = os.path.join(webroot, 'idx.json')
    # Avoid regenerating index file unless necessary
    if os.path.exists(idx_file):
        newest = sorted([_['data']['MTIME'] for _ in content], reverse=True)[0]
        idx_ts = datetime.datetime.fromtimestamp(os.path.getmtime(idx_file))
        if idx_ts > newest:
            return
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
