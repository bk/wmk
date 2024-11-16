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
import locale
import gettext

import sass
import yaml
import frontmatter
import markdown
import pypandoc
import lunr

from mako.lookup import TemplateLookup
from mako.exceptions import text_error_template, TemplateLookupException

from wmk_utils import (
    slugify, attrdict, MDContentList, RenderCache, Nav, Toc, hookable)
import wmk_mako_filters as wmf

# To be imported from wmk_autoload and/or wmk_theme_autoload, if applicable
autoload = {}

VERSION = '1.15.2'

# Template variables with these names will be converted to date or datetime
# objects (depending on length) - if they conform to ISO 8601.
KNOWN_DATE_KEYS = (
    'date', 'pubdate', 'modified_date', 'expire_date', 'created_date')

# Note that only markdown/html extensions will be active unless explicitly
# set in wmk_config (or pandoc is globally true).
DEFAULT_CONTENT_EXTENSIONS = {
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
    '.dj': {'pandoc': True, 'pandoc_input_format': 'djot'},
    '.textile': {'pandoc': True, 'pandoc_input_format': 'textile'},
    '.tex': {'pandoc': True, 'pandoc_input_format': 'latex'},
    '.typ': {'pandoc': True, 'pandoc_input_format': 'typst'},
    '.man': {'pandoc': True, 'pandoc_input_format': 'man'},
    '.rtf': {'pandoc': True, 'pandoc_input_format': 'rtf'},
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
    # `force` mode is now the default and is turned off by setting --quick
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
    if not dirs['python'] in sys.path:
        sys.path.insert(0, dirs['python'])
    global autoload
    try:
        from wmk_autoload import autoload
    except:
        pass

    # 1) get theme settings, copy static files
    # css_dir_from_start is workaround for process_assets timestamp check
    css_dir_from_start = os.path.exists(os.path.join(dirs['output'], 'css'))
    # a) preparation, loading plugins, setting sys.path etc
    themedir = os.path.join(
        dirs['themes'], conf.get('theme')) if conf.get('theme') else None
    if themedir and not os.path.exists(themedir):
        themedir = None
    if themedir and not conf.get('ignore_theme_config', False):
        # Partial merge of theme config with main config file.
        # NOTE that WMK_CONFIG does not affect theme settings.
        theme_conf = get_config(themedir, 'wmk_config.yaml')
        conf_merge(conf, theme_conf)
    if themedir and os.path.exists(os.path.join(themedir, 'py')):
        theme_py = os.path.join(themedir, 'py')
        if not theme_py in sys.path:
            sys.path.insert(1, os.path.join(themedir, 'py'))
        try:
            from wmk_theme_autoload import autoload as theme_autoload
            for k in theme_autoload:
                if k in autoload:
                    continue
                autoload[k] = theme_autoload[k]
        except:
            pass
    # b) Run init commands, if any
    run_init_commands(basedir, conf)
    #    (NOTE: hookable works at this point, since sys.path is ready).
    # c) Doing the actual copying.
    copy_static_files(dirs, themedir, conf, quick)

    # 2) compile assets (only scss for now):
    theme_assets = os.path.join(themedir, 'assets') if themedir else None
    process_assets(
        dirs['assets'], theme_assets, dirs['output'],
        conf, css_dir_from_start, force)
    assets_map = fingerprint_assets(conf, dirs['output'], dirs['data'])

    # 3) Preparation for remaining phases
    # a) Global data for template rendering, used by both process_templates
    # and process_markdown_content.
    template_vars = get_template_vars(dirs, themedir, conf, assets_map)
    lookup = get_template_lookup(dirs, themedir, conf, template_vars)
    conf['_lookup'] = lookup

    # 4) write redirect files
    if not quick:
        handle_redirects(
            conf.get('redirects'), template_vars['DATADIR'], template_vars['WEBROOT'])

    # 5a) templates
    templates = get_templates(
        dirs['templates'], themedir, dirs['output'], template_vars)
    # 5b) inherited yaml metadata
    index_yaml = get_index_yaml_data(dirs['content'], dirs['data'])
    conf['_index_yaml_data'] = index_yaml or {}
    # 5c) markdown (etc.) content
    content = get_content(
        dirs['content'], dirs['data'], dirs['output'],
        template_vars, conf, force=force)

    # 6) render templates
    process_templates(templates, lookup, template_vars, force)
    # 7) render Markdown/HTML/other content
    process_markdown_content(content, lookup, conf, force)
    # 8) Cleanup/external post-processing stage
    if not quick:
        post_build_actions(conf, dirs, templates, content)
        run_cleanup_commands(conf, basedir)


def get_content_info(basedir='.', content_only=True):
    """
    Gets the content (i.e. MDContent) data like it is at the stage where
    `process_markdown_content()` is called during normal processing.  Intended
    for development and debugging, i.e. usage in an interactive shell, but may
    also be used by an external script. If `content_only` is False, returns
    a tuple of (content, conf, templates).
    """
    force = True
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
    if not dirs['python'] in sys.path:
        sys.path.insert(0, dirs['python'])
    global autoload
    try:
        from wmk_autoload import autoload
    except:
        pass
    themedir = os.path.join(
        dirs['themes'], conf.get('theme')) if conf.get('theme') else None
    if themedir and not os.path.exists(themedir):
        themedir = None
    if themedir and not conf.get('ignore_theme_config', False):
        theme_conf = get_config(themedir, 'wmk_config.yaml')
        conf_merge(conf, theme_conf)
    if themedir and os.path.exists(os.path.join(themedir, 'py')):
        theme_py = os.path.join(themedir, 'py')
        if not theme_py in sys.path:
            sys.path.insert(1, os.path.join(themedir, 'py'))
        try:
            from wmk_theme_autoload import autoload as theme_autoload
            for k in theme_autoload:
                if k in autoload:
                    continue
                autoload[k] = theme_autoload[k]
        except:
            pass
    assets_map = fingerprint_assets(conf, dirs['output'], dirs['data'])
    template_vars = get_template_vars(dirs, themedir, conf, assets_map)
    lookup = get_template_lookup(dirs, themedir, conf, template_vars)
    conf['_lookup'] = lookup
    templates = get_templates(
        dirs['templates'], themedir, dirs['output'], template_vars)
    index_yaml = get_index_yaml_data(dirs['content'], dirs['data'])
    conf['_index_yaml_data'] = index_yaml or {}
    content = get_content(
        dirs['content'], dirs['data'], dirs['output'],
        template_vars, conf, force=force)
    if content_only:
        return content
    else:
        return (content, conf, templates)


@hookable
def get_template_vars(dirs, themedir, conf, assets_map=None):
    template_vars = {
        'DATADIR': os.path.realpath(dirs['data']),
        'CONTENTDIR': os.path.realpath(dirs['content']),
        'WEBROOT': os.path.realpath(dirs['output']),
        'TEMPLATES': [],
        'MDCONTENT': MDContentList([]),
    }
    template_vars.update(conf.get('template_context', {}))
    template_vars['site'] = attrdict(conf.get('site', {}))
    template_vars['nav'] = get_nav(conf, dirs, themedir)
    # b) Locale/translation related
    # site.locale affects collation; site.lang affects translations
    locale_and_translation(template_vars, themedir)
    # c) Assets fingerprinting
    # If assets_fingerprinting is off fallback to the 'assets_map' setting
    template_vars['ASSETS_MAP'] = get_assets_map(
        conf, template_vars['DATADIR']) if assets_map is None else assets_map
    # Used as a filter in Mako templates
    template_vars['fingerprint'] = wmf.fingerprint_gen(
            template_vars['WEBROOT'], template_vars['ASSETS_MAP'])
    # d) Settings-dependent Mako filters
    # Used as a filter in  Mako templates
    template_vars['url'] = wmf.url_filter_gen(
        template_vars['site'].leading_path or template_vars['site'].base_url or '/')
    template_vars['site'].build_time = datetime.datetime.now()
    template_vars['site'].lunr_search = conf.get('lunr_index', False)
    return template_vars


@hookable
def get_nav(conf, dirs=None, themedir=None):
    conf_nav = conf.get('nav', [])
    if isinstance(conf_nav, str) and conf_nav == 'auto':
        return Nav([]) # will be generated from content later
    else:
        return Nav(conf_nav)


@hookable
def auto_nav_from_content(content):
    """
    Automatically generate a simple nav from frontmatter. Called if conf.nav is
    set to 'auto'.

    Each added page MUST have nav_section and MAY have nav_title (which
    fallbacks to title) and nav_order (which fallbacks to weight or defaults to
    2**32-1 if that fails).

    Sections are ordered by the smallest weight assigned to them, with the Root
    section always being placed at the start. Non-Root sections with the same
    weight are ordered alphabetically. Page links within each seaction
    are ordered by nav_order/weight, or, if that is equal, by nav_title/title.
    """
    autonav = []
    root_section = []
    sections = {}
    fallback_weight = 2**32 - 1
    for it in content:
        pg = it['data']['page']
        if not pg.nav_section:
            continue
        item_weight = pg.nav_order or pg.weight or fallback_weight
        rec = {
            'title': pg.nav_title or pg.title,
            'url': it['url'],
            'order': item_weight,
        }
        if pg.nav_section.lower() == 'root':
            root_section.append(rec)
        elif pg.nav_section not in sections:
            sections[pg.nav_section] = {'weight': item_weight, 'items': [rec]}
        else:
            sections[pg.nav_section]['items'].append(rec)
            if sections[pg.nav_section]['weight'] > item_weight:
                sections[pg.nav_section]['weight'] = item_weight
    sortkey = lambda x: (x['order'], x['title'])
    root_section.sort(key=sortkey)
    for it in root_section:
        autonav.append({it['title']: it['url']})
    for section in sorted(list(sections.keys()), key=lambda x: (sections[x]['weight'], x)):
        items = []
        for it in sorted(sections[section]['items'], key=sortkey):
            items.append({it['title']: it['url']})
        autonav.append({section: items})
    return Nav(autonav)


@hookable
def get_template_lookup(dirs, themedir, conf, template_vars=None):
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
    is_jinja = conf.get('jinja2_templates') or False
    if is_jinja:
        from jinja2 import (
            Environment, FileSystemLoader, select_autoescape, pass_context)
        import wmk_jinja2_extras as wje
        # TODO: Handle potential Jinja2 settings in conf
        loader = FileSystemLoader(
            searchpath=lookup_dirs, encoding='utf-8', followlinks=True)
        env = Environment(
            loader=loader,
            autoescape=select_autoescape())
        env.globals = wje.get_globals()
        env.globals['mako_lookup'] = TemplateLookup(
            directories=lookup_dirs, imports=mako_imports)
        @pass_context
        def get_context(c):
            _c = c.get_all()
            reserved = ('context', 'UNDEFINED', 'loop')
            ret = {}
            for k in _c:
                if k in reserved:
                    continue
                ret[k] = _c[k]
            return ret
        env.globals['get_context'] = get_context
        env.filters.update(wje.get_filters())
        if template_vars and 'fingerprint' in template_vars:
            env.filters.update({
                'fingerprint': template_vars['fingerprint'],
                'url': template_vars.get('url')})
        # TODO: Add potential user-defined custom filters
        return env
    else:
        return TemplateLookup(
            directories=lookup_dirs, imports=mako_imports)


@hookable
def locale_and_translation(template_vars, themedir):
    if template_vars['site'].locale:
        print("NOTE: Setting collation locale to", template_vars['site'].locale)
        locale.setlocale(locale.LC_COLLATE, template_vars['site'].locale)
    # A directory which contains $LANG/LC_MESSAGES/wmk.mo
    localedir = os.path.join(template_vars['DATADIR'], 'locales')
    if themedir and not os.path.exists(localedir):
        theme_locales = os.path.join(themedir, 'data', 'locales')
        if os.path.exists(theme_locales):
            localedir = theme_locales
    if not os.path.exists(localedir):
        localedir = None
    if localedir and template_vars['site'].lang:
        langs = template_vars['site'].lang
        if isinstance(langs, str):
            langs = [langs]
        try:
            lang = gettext.translation('wmk', localedir=localedir, languages=langs)
            # Make traditional 'translate message' _ shortcut available globally,
            # including in templates:
            lang.install()
        except FileNotFoundError:
            # Rather than fall back to system locale, don't use translations at all
            # in this case. But we still need the _ shortcut...
            print("WARNING: Translations for locale (site.lang) '{}' not found".format(
                template_vars['site'].lang))
            gettext.install('wmk')
    else:
        # No localization available; nevertheless install the _ shortcut into
        # the global environment for compatibility with templates that use it.
        gettext.install('wmk')


def preview_single(basedir, preview_file,
                   preview_content=None, with_metadata=False, render_draft=True):
    """
    Returns the bare HTML (i.e. not including HTML from Mako templates other
    than shortcodes) for a single named file inside the content directory.
    This is more complicated than it sounds since all settings must be
    respected and all processing except for the actual output must be
    done. If `preview_content` is provided, then the file named does not
    actually need to exist (although a filename does need to be provided).

    Note that the POSTPROCESS will not be performed. This includes shortcodes
    relying on that, such as `linkto` and `pagelist`; only placeholders for them
    will be visible in the output. The `resize_image` will actually output
    resized images to the htdocs directory, unless they already are present.
    """
    # `force` mode is now the default and is turned off by setting --quick
    force = True
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
    if render_draft:
        conf['render_drafts'] = True
    dirs = get_dirs(basedir, conf)
    if not dirs['python'] in sys.path:
        sys.path.insert(0, dirs['python'])
    global autoload
    try:
        from wmk_autoload import autoload
    except:
        pass
    # The content may use shortcodes, so we do need this
    themedir = os.path.join(
        dirs['themes'], conf.get('theme')) if conf.get('theme') else None
    if themedir and not os.path.exists(themedir):
        themedir = None
    if themedir and not conf.get('ignore_theme_config', False):
        # Partial merge of theme config with main config file.
        # NOTE that WMK_CONFIG does not affect theme settings.
        theme_conf = get_config(themedir, 'wmk_config.yaml')
        conf_merge(conf, theme_conf)
    if themedir and os.path.exists(os.path.join(themedir, 'py')):
        theme_py = os.path.join(themedir, 'py')
        if not theme_py in sys.path:
            sys.path.insert(1, theme_py)
        try:
            from wmk_theme_autoload import autoload as theme_autoload
            for k in theme_autoload:
                if k in autoload:
                    continue
                autoload[k] = theme_autoload[k]
        except:
            pass
    # Global data for template rendering, used by both process_templates
    # and process_markdown_content.
    template_vars = get_template_vars(dirs, themedir, conf, assets_map=None)
    lookup = get_template_lookup(dirs, themedir, conf, template_vars)
    conf['_lookup'] = lookup
    # 4) get info about stand-alone templates and Markdown content
    index_yaml = get_index_yaml_data(dirs['content'], dirs['data'])
    conf['_index_yaml_data'] = index_yaml or {}
    content = get_content(
        dirs['content'], dirs['data'], dirs['output'],
        template_vars, conf, force=force,
        previewing=preview_file, preview_content=preview_content)
    return content if with_metadata else content['rendered']


def conf_merge(primary, secondary):
    """
    Merge theme_conf (= secondary) with conf (= primary), which is changed.
    Values from secondary (and from dicts inside it) are only added to primary
    if their key is not present beforehand at the same level.
    """
    if not secondary:
        return
    dictkeys = set([k for k in secondary if isinstance(secondary[k], dict)])
    for k in secondary:
        if not k in primary:
            primary[k] = secondary[k]
        elif k in dictkeys and isinstance(primary[k], dict):
            for k2 in secondary[k]:
                if not k2 in primary[k]:
                    primary[k][k2] = secondary[k][k2]


@hookable
def run_init_commands(basedir, conf):
    init_commands = conf.get('init_commands', [])
    for cmd in init_commands:
        print("[%s] - init command: %s" % (datetime.datetime.now(), cmd))
        ret = subprocess.run(
            cmd, cwd=basedir, shell=True, capture_output=True, encoding='utf-8')
        if ret.returncode == 0 and ret.stdout:
            print("  **OK**:", ret.stdout)
        elif ret.returncode != 0:
            print('  **WARNING: init command error [exitcode={}]:'.format(
                ret.returncode), ret.stderr)



@hookable
def copy_static_files(dirs, themedir, conf, quick=False):
    if themedir and os.path.exists(os.path.join(themedir, 'static')):
        os.system('rsync -a "%s/" "%s/"' % (
            os.path.join(themedir, 'static'), dirs['output']))
    if quick:
        os.system('rsync -a --update "%s/" "%s/"' % (dirs['static'], dirs['output']))
    else:
        os.system('rsync -a "%s/" "%s/"' % (dirs['static'], dirs['output']))
    # support content bundles (mainly images inside content dir)
    content_extensions = get_content_extensions(conf)
    ext_excludes = ' '.join(['--exclude "*{}"'.format(_) for _ in content_extensions.keys()])
    if quick:
        ext_excludes = '--update ' + ext_excludes
    os.system(
        'rsync -a ' + ext_excludes + ' --exclude "*.yaml" --exclude "_*" --exclude ".*" --prune-empty-dirs "%s/" "%s/"'
        % (dirs['content'], dirs['output']))


@hookable
def post_build_actions(conf, dirs, templates, content):
    """
    This is the hookable you would override for updating a search index
    (e.g. if you are not using lunr and want to have the option of indexing the
    output of stand-alone templates). By default, it just calls index_content().
    """
    index_content(content, conf, dirs['content'])


@hookable
def get_content_extensions(conf):
    ce = conf.get('content_extensions', None)
    if ce is None and not conf.get('pandoc'):
        # If pandoc is True in the global config, we support all known content
        # extensions by default. Otherwise, we only support markdown and html.
        ce = ['.md', '.mdwn', '.mdown', '.markdown', '.gfm', '.mmd' '.htm', '.html']
    if isinstance(ce, dict):
        return ce
    elif isinstance(ce, list):
        ret = {}
        for it in ce:
            k = it if it.startswith('.') else '.' + it
            ret[k] = DEFAULT_CONTENT_EXTENSIONS.get(k, None)
            if ret[k] is None:
                ret[k] = {'pandoc': True, 'pandoc_input_format': k[1:]}
        return ret
    # Should only get here if pandoc is globally true
    return DEFAULT_CONTENT_EXTENSIONS


@hookable
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
        'templates': basedir + '/templates', # Mako/Jinja2 templates
        'content': basedir + '/content',  # Markdown files
        'output': basedir + '/' + output_dir, # normally htdocs/
        'static': basedir + '/static',
        'assets': basedir + '/assets', # only scss for now
        'data': basedir + '/data', # YAML, potentially sqlite
        'themes': basedir + '/themes', # extra static/assets/templates
        'python': basedir + '/py', # python modules for hooks/templates
    }


def get_config(basedir, conf_file):
    filename = os.path.join(basedir, conf_file)
    conf_dir = os.path.join(basedir, conf_file.replace('.yaml', '.d'))
    conf = {}
    if os.path.exists(filename):
        with open(filename) as f:
           conf = yaml.safe_load(f) or {}
    # Look for yaml files inside data/wmk_config.d.  Each file contains the
    # value for the key specified by the path name to it, e.g. ./site/info.yaml
    # contains the value of site.data. (The contents of ./site.yaml, if present,
    # is merged with the contents of the files inside the ./site/ directory).
    if os.path.isdir(conf_dir):
        dirconf = {}
        for root, dirs, fils in os.walk(conf_dir):
            nesting = root[len(conf_dir)+1:]
            pathkeys = [_ for _ in nesting.split('/') if _]
            for fn in fils:
                if not fn.endswith('.yaml'):
                    continue
                filkey = fn.replace('.yaml', '')
                with open(os.path.join(root, fn)) as f:
                    partial = yaml.safe_load(f) or {}
                    _ensure_nested_dict(dirconf, pathkeys, filkey, partial)
        for k in dirconf:
            if k in conf and isinstance(conf[k], dict):
                conf[k].update(dirconf[k])
            else:
                conf[k] = dirconf[k]
    return conf


def _ensure_nested_dict(dic, keylist, key, val=None):
    # Helper function for get_config.
    for k in keylist:
        dic = dic.setdefault(k, {})
    if key in dic and isinstance(dic[key], dict) and isinstance(val, dict):
        dic[key].update(val)
    else:
        dic[key] = val


@hookable
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
        data['LOOKUP'] = lookup
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


@hookable
def process_markdown_content(content, lookup, conf, force):
    """
    Renders the specified markdown content into the outputdir.
    """
    for ct in content:
        if not force and is_older_than(ct['source_file'], ct['target']):
            continue
        try:
            template = None if ct['template'].lower() == '__empty__' \
                else lookup.get_template(ct['template'])
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
                    try:
                        html = pp(html, **data)
                        pp.was_called = data['SELF_FULL_PATH']
                    except Exception as e:
                        print("WARNING: postprocess failed for {}: {}".format(
                            ct['source_file_short'], e))
            page._CACHER(html)
            ct['rendered'] = html
            data['CONTENT'] = html
        try:
            data['TOC'] = Toc(html)
        except Exception as e:
            print("TOC ERROR for %s: %s" % (ct['url'], str(e)))
            data['TOC'] = Toc('')
        html_output = ''
        handle_taxonomy(data)
        try:
            if template is None:
                html_output = data['CONTENT'] or ''
            else:
                html_output = template.render(**data)
        except:
            # TODO: Does not really make sense for Jinja template errors
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


@hookable
def handle_taxonomy(data):
    """
    - Adds TAXONS to context (i.e. data) for the base template that will be
      called immediately after this in the flow.
    - Writes a page (using the MDContentList write_to() method) for each taxon
      with TAXON (== CHUNK) and TAXON_INDEX (indicating its ordering in TAXONS)
      in the context.
    - No return value.
    """
    txy = data['page'].TAXONOMY
    if txy and 'taxon' in txy and 'detail_template' in txy:
        txy.valid = True
        maybe_order = {'order': txy['order']} if txy['order'] else {}
        taxons = data['MDCONTENT'].taxonomy_info(txy['taxon'], **maybe_order)
        data['TAXONS'] = taxons
        base_url = data['SELF_URL']
        for i, tx in enumerate(taxons):
            # NOTE: Assumes normal pretty_path setting!
            dest = re.sub(r'/index.html$',
                          '/{}/index.html'.format(tx['slug']),
                          base_url)
            if dest == data['SELF_URL']:
                raise Exception(
                    'handle_taxonomy() requires pretty_path to be active or auto')
            ctx = dict(**data)
            ctx['SELF_TEMPLATE'] = txy['detail_template']
            tx['url'] = dest
            tx['items'].write_to(
                dest=dest,
                context=ctx,
                extra_kwargs={'TAXON': tx, 'TAXON_INDEX': i},
                template=txy['detail_template'])
    elif txy:
        print("WARNING: BAD TAXONOMY for", data['SELF_URL'])
        txy.valid = False
        data['TAXONS'] = []


@hookable
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


@hookable
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
    ## Note that PREPROCESS is now run before shortcodes are interpreted, so
    ## such actions cannot be added by them. PREPROCESS actions may for instance
    ## handle syntactic sugar that transforms into shortcodes behind the scenes.
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
    # POSTPROCESS, on the other hand may be added by shortcodes (and often is)
    if '{{<' in doc:
        # SHORTCODES:
        # We need to handle include() first.
        incpat = r'{{<[ \n\r\t]*(include)\(\s*(.*?)\s*\)\s*>}}'
        incfound = re.search(incpat, doc, re.DOTALL)
        while incfound:
            doc = re.sub(incpat, handle_shortcode(conf, data, nth), doc, flags=re.DOTALL)
            incfound = re.search(incpat, doc, re.DOTALL)
        # Now other shortcodes.
        # funcname, argstring
        pat = r'{{<[ \n\r\t]*(\w+)\(\s*(.*?)\s*\)\s*>}}'
        found = re.search(pat, doc, re.DOTALL)
        while found:
            doc = re.sub(pat, handle_shortcode(conf, data, nth), doc, flags=re.DOTALL)
            found = re.search(pat, doc, re.DOTALL)
    if is_html:
        ret = doc
    elif is_pandoc:
        # For TOC to be added inline, page.toc must be True and the
        # markdown content must have a '[TOC]' line.
        # Note that this is different from the Toc object available
        # in the template context as the TOC variable.
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
                pdformats, pdformats_conf,
                ct['data']['WEBROOT'], ct['source_file_short'])
    else:
        ret = markdown.markdown(
            doc, extensions=extensions, extension_configs=extension_configs)
    if cache and pg.POSTPROCESS:
        # Delay caching until just before calling the template
        pg._CACHER = lambda x: cache.write_cache(x)
    elif cache:
        cache.write_cache(ret)
    return ret


@hookable
def pandoc_extra_formats(
        doc, pandoc_input, pdformats, pdformats_conf, webroot, sourcefile):
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
        # Fall back to using the same base filename as that of the sourcefile
        if out_fn.lower() == 'auto' and re.search(r'\.\w+$', sourcefile):
            out_fn = re.sub(r'\.\w+$', '.'+ fmt, sourcefile.strip('/'))
        elif out_fn.lower() == 'auto':
            out_fn = None
        if not out_fn or not re.search(r'\.\w+$', out_fn):
            print("WARNING [%s]:  no valid output file name for extra format %s"
                  % (sourcefile, fmt))
            continue
        outputfile = os.path.join(webroot, out_fn)
        maybe_mkdir(outputfile)
        pypandoc.convert_text(
            doc, to=fmt, format=pandoc_input,
            extra_args=extra_args, filters=filters,
            outputfile=outputfile)
        print('[%s] - extra: %s' % (
                str(datetime.datetime.now()), out_fn))


@hookable
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
    try:
        return '---\n' + yaml.safe_dump(safe_pg) + '---\n\n' + doc
    except yaml.representer.RepresenterError:
        # A likely cause of this error is a nested attrdict loaded from a hook.
        print("WARNING: Got RepresenterError; simplifying frontmatter for pandoc")
        sanitized = json.loads(json.dumps(safe_pg, default=str))
        return '---\n' + yaml.safe_dump(sanitized) + '---\n\n' + doc


@hookable
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


@hookable
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


@hookable
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


@hookable
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
            retkey = curdir + '/' if curdir else ''
            ret[retkey] = info
    return ret


@hookable
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


@hookable
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


@hookable
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


@hookable
def get_content(ctdir, datadir, outputdir, template_vars, conf,
                force=False, previewing=None, preview_content=None):
    """
    Get those markdown files that need processing.
    """
    content = []
    known_ids = set()
    content_extensions = get_content_extensions(conf)
    known_exts = tuple(content_extensions.keys())
    extpat = re.compile(r'\.(?:' + '|'.join([_[1:] for _ in known_exts]) + r')$')
    pandoc_meta_exts = ('.org', '.rst', '.tex', '.man', '.rtf',
                        '.xml' '.jats', '.tei', '.docbook')
    if previewing:
        files_to_process = [(ctdir, [], [previewing])]
    else:
        files_to_process = [_ for _ in os.walk(ctdir)]
    for root, dirs, files in files_to_process:
        for fn in files:
            if not fn.endswith(known_exts):
                continue
            if fn.startswith('_') or fn.startswith('.'):
                continue
            source_file = os.path.join(root, fn)
            source_file_short = source_file.replace(ctdir, '', 1)
            ext = re.findall(r'\.\w+$', fn)[0]
            ext_conf = content_extensions[ext]
            if ext_conf.get('is_binary'):
                try:
                    meta, doc = binary_to_markdown(
                        source_file, ext_conf.get('pandoc_binary_format'), datadir[:-5])
                except RuntimeError as e:
                    print("ERROR: Could not convert {} using pandoc: {}".format(source_file, e))
                    continue
                for k in ext_conf:
                    if not k in meta:
                        meta[k] = ext_conf[k]
            elif previewing and preview_content:
                meta, doc = frontmatter.parse(preview_content)
                meta = maybe_extra_meta(meta, source_file)
                # TODO: handle possible pandoc metadata for non-Markdown formats?
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
            process_content_item(
                meta, doc, content, conf, template_vars,
                ctdir, outputdir, datadir, content_extensions, known_ids,
                root, fn, source_file, source_file_short, extpat,
                previewing)
    if previewing:
        return content[0]
    get_extra_content(
        content, ctdir=ctdir, datadir=datadir, outputdir=outputdir,
        template_vars=template_vars, conf=conf)
    content = MDContentList(content)
    template_vars['MDCONTENT'] = content
    if not template_vars['nav'] and isinstance(conf.get('nav'), str) and conf['nav'] == 'auto':
        autonav = auto_nav_from_content(content)
        if autonav:
            template_vars['nav'] = autonav
            for ct in content:
                ct['data']['nav'] = autonav
    # We must call this before adding MDCONTENT to each item below
    # (since that will create circular references):
    maybe_save_mdcontent_as_json(content, conf, os.path.split(ctdir)[0])
    for it in content:
        it['data']['MDCONTENT'] = content
    return content


@hookable
def get_extra_content(
        content, ctdir=None, datadir=None, outputdir=None,
        template_vars=None, conf=None):
    """
    Exists only to be overridden in a hooks file (i.e. wmk_hooks or
    wmk_theme_hooks).  Makes it possible to use content from the normal content
    folder but also to get it from other sources.

    NOTE: An implementation of this function should normally add items to `content` by
    calling process_content_item for each of them.
    """
    return


@hookable
def index_content(content, conf, ctdir):
    "Build lunr index if applicable."
    if conf.get('lunr_index', False):
        build_lunr_index(content,
                         conf.get('lunr_index_fields', None),
                         conf.get('lunr_languages', None))


@hookable
def process_content_item(
        meta, doc, content, conf, template_vars,
        ctdir, outputdir, datadir, content_extensions, known_ids,
        root, fn, source_file, source_file_short, extpat,
        previewing):
    """
    Makes sure that the content item has the expected metadata (such as title,
    slug and id, and template), give it the template variables, and add it to
    the content list. Called for each item processed in get_content().
    """
    is_jinja = conf.get('jinja2_templates') or False
    default_template = conf.get(
        'default_template', ('md_base.html' if is_jinja else 'md_base.mhtml'))
    default_pretty_path = lambda x: False if x.startswith('index.') else True
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
    # Check if we're inheriting a draft setting -- if so, skip out
    if page.get('draft', False) and not conf.get('render_drafts', False):
        return
    # template
    template = page.get(
        'template', data.get(
            'template', page.get(
                'layout', data.get(
                    'layout', default_template))))
    if not template.lower() == '__empty__' and not re.search(r'\.\w{2,5}$', template):
        template += ('.html' if is_jinja else '.mhtml')
    # TODO: get rid of this heuristic for Jinja templates and handle base/
    # fallback at final rendering time like we do with Mako:
    if is_jinja and not (re.search(r'base|/', template) or template.startswith('_')):
        template = 'base/' + template
    if 'template' not in page:
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
    # set of characters -- unless slugify_dirs is False
    slugify_dirs = page.get('slugify_dirs', True)
    fn_parts = fn.split('/')
    if re.search(r'[^A-Za-z0-9_.,=-]', fn_parts[-1]) and slugify_dirs:
        fn_parts[-1] = slugify(fn_parts[-1])
    # Ensure that slug is present
    if not 'slug' in page:
        page['slug'] = fn_parts[-1][:-3]
    # Ensure that title is present
    if not 'title' in page:
        # first try the main heading
        found = re.search(r'^##? +(.+)', doc.lstrip())
        if found:
            page['title'] = found.group(1)
        else:
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
    data['SELF_SHORT_PATH'] = source_file_short
    data['SELF_TEMPLATE'] = template
    if 'MTIME' in page or '_mtime' in page:
        data['MTIME'] = page.get('MTIME') or page.get('_mtime')
    elif previewing:
        data['MTIME'] = datetime.datetime.now()
    else:
        data['MTIME'] = datetime.datetime.fromtimestamp(
            os.path.getmtime(source_file))
    data['RENDERER'] = lambda x: render_markdown(x, conf)
    data['LOOKUP'] = conf.get('_lookup', None)
    # convert some common datetime strings to datetime objects
    parse_dates(page)
    ext = re.search(r'\.\w+$', source_file).group(0)
    ext_conf = content_extensions[ext]
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
    if not data['page'].summary and data['page'].generate_summary:
        generate_summary(content[-1])


@hookable
def generate_summary(content_item):
    """
    Generate the summary from the body (after it is rendered to HTML), if
    `page.generate_summary` is true. Maximum length can be configured with
    `page.summary_max_length` (default 300). Autogenerated summaries will
    not contain HTML (or Markdown).
    """
    pg = content_item['data']['page']
    if pg.summary:
        return
    html = content_item['rendered'] or ''
    chunks = re.split(r'<!-- *[Mm][Oo][Rr][Ee] *-->', html)
    para = ''
    if len(chunks) > 1 or not '<p' in chunks[0]:
        # Use any non-heading content as summary
        chunk = chunks[0]
        for tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            chunk = re.sub(r'<{}[^>]*>.*?</{}>'.format(tag, tag), '', chunk, flags=re.S)
        para = chunk
    else:
        found = re.search(r'(?:<p>|<p [^>]*>)(.*?)</p>', chunks[0], flags=re.S)
        if found:
            para = found.group(1).strip()
    # Primitive stripping of tags
    # TODO: maybe keep <strong>, <em> but nothing else
    para = re.sub(r'<[^>]*>', ' ', para)
    para = re.sub(r'\s\s+', ' ', para)
    para = para.strip()
    max_len = int(pg.summary_max_length or 300)
    if len(para) > max_len:
        para = para[:max_len]
        para = re.sub(r'\s\S+', '', para)
        if not para[-1] in ('.', '?', '!'):
            para += '…'
    if para:
        pg.summary = para
    else:
        print("WARNING: no autosummary for {}".format(
            content_item['data'].get('SELF_SHORT_PATH', '??')))


@hookable
def preferred_date(data):
    """
    Pick a date by priority among several date keys in `page`, with `MTIME` as
    fallback. This will be set as the `DATE` key.

    Also, check whether the auto_date setting is true for this page and set the
    corresponding field based on the source filename if possible (and not
    already set).

    """
    auto_date = data['page'].get('auto_date', False)
    auto_date_field = data['page'].get('auto_date_field', 'date')

    if auto_date and not data['page'].get(auto_date_field):
        found = re.search(r'[_/-](\d\d\d\d)[_/-](\d\d?)[_/-](\d\d?)\D', data['SELF_SHORT_PATH'])
        if found:
            try:
                dateval = datetime.date(*[int(_) for _ in found.groups()])
                data['page'][auto_date_field] = dateval
            except ValueError:
                pass

    for k in KNOWN_DATE_KEYS:
        if k in data['page']:
            return data['page'][k]
    return data['MTIME']


@hookable
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


@hookable
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
            if root.endswith('/base') or '/base/' in root:
                continue
            for fn in files:
                if 'base' in fn or fn.startswith(('_', '.')):
                    continue
                if fn.endswith(('.mhtml', '.jhtml', '.html')):
                    source = os.path.join(root.replace(tplroot, '', 1), fn)
                    if source.startswith('/'):
                        source = source[1:]
                    # we have a theme template overridden locally
                    if source in seen:
                        continue
                    seen.add(source)
                    # Keep pre-extension before .mhtml/.jhtml/.html (e.g. "atom.xml.mhtml")
                    if re.search(r'\.\w{2,5}\.[mj]?html$', fn):
                        html_fn = re.sub(r'\.[mj]?html', '', fn)
                    else:
                        html_fn = re.sub(r'\.[mj]?html', '.html', fn)
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


@hookable
def run_cleanup_commands(conf, basedir):
    cmds = conf.get('cleanup_commands', None)
    if cmds:
        print("INFO: Running external cleanup/postprocessing commands:")
        for cmd in cmds:
            print('[%s] - assets command: %s' % (datetime.datetime.now(), cmd))
            ret = subprocess.run(
                cmd, cwd=basedir, shell=True, capture_output=True, encoding='utf-8')
            if ret.returncode == 0 and ret.stdout:
                print('  **OK**:', ret.stdout)
            elif ret.returncode != 0:
                print('  **WARNING** cleanup command error [exitcode={}]:'.format(
                    ret.returncode), ret.stderr)


@hookable
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


@hookable
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


@hookable
def handle_shortcode(conf, ctx, nth=None):
    "Return a match replacement function for shortcode handling."
    is_jinja = conf.get('jinja2_templates') or False
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
            dirkey = 'jinja2_shortcodes_dir' if is_jinja else 'mako_shortcodes_dir'
            subdir = conf.get(dirkey, 'shortcodes')
            ext = 'jc' if is_jinja else 'mc'
            tplnam = '%s/%s.%s' % (subdir.strip('/'), name, ext)
            tpl = lookup.get_template(tplnam)
            ckwargs = {}
            ckwargs.update(ctx)
            ckwargs.update(kwargs)
            ckwargs['nth'] = nth[name]  # invocation count
            if not 'LOOKUP' in ckwargs:
                ckwargs['LOOKUP'] = lookup
            if is_jinja and args:
                _fix_jinja_shortcode_args(name, args, ckwargs)
                if args:
                    raise Exception(
                        'Cannot handle positional shortcode arguments with jinja_templates set to True')
                return tpl.render(**ckwargs)
            else:
                return tpl.render(*args, **ckwargs)
        except Exception as e:
            print("WARNING: shortcode {} failed in {}: {}".format(
                name, ctx.get('SELF_SHORT_PATH', '??'), e))
            # prevent infinite loops
            return match.group(0).replace('{', '(').replace('}', ')')
    return replacer


def _fix_jinja_shortcode_args(name, args, ckwargs):
    # Workaround to allow using positional arguments for "built-in" shortcodes
    # when Jinja2 templates are being used.
    argnames = {
        'figure': ['src'],
        'gist': ['username', 'gist_id'],
        'include': ['filename', 'fallback'],
        'linkto': ['match'],
        'pagelist': ['match_expr'],
        'resize_image': ['path', 'width', 'height'],
        'template': ['template'],
        'twitter': ['twitter_id'],
        'var': ['varname', 'default'],
        'vimeo': ['id'],
        'wp': ['title'],
        'youtube': ['id'],
    }
    if name not in argnames:
        return
    for k in argnames[name]:
        if not args:
            return
        ckwargs[k] = args.pop(0)


@hookable
def maybe_save_mdcontent_as_json(content, conf, basedir):
    full_dump = conf.get('mdcontent_json', None)
    if full_dump and full_dump.endswith('.json'):
        # Make sure the file ends up inside the base directory
        while full_dump.startswith(('.', '/')):
            full_dump = full_dump.strip('/')
            full_dump = full_dump.strip('.')
        # ... and inside one of the three allowed subdirectories (data by default)
        if not full_dump.startswith(('data/', 'tmp/', 'htdocs/')):
            full_dump = os.path.join('data', full_dump)
        full_dump = os.path.join(basedir, full_dump)
        # NOTE: destination directory must exist
        with open(full_dump, 'w') as f:
            f.write(json.dumps(content, indent=2, sort_keys=True, default=str))
    elif full_dump:
        print("WARNING: Invalid config value for mdcontent_json: '%s'" % full_dump)


@hookable
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
        if isinstance(langs, str):
            langs = [langs]
        for lang in langs:
            if not lang in known_langs:
                raise Exception(
                    "Unsupported language in lunr_languages: '%s'" % lang)
        languages = {'languages': langs}
    else:
        langs = {}
    #saved_locale = locale.getlocale(locale.LC_COLLATE)
    #locale.setlocale(locale.LC_COLLATE, 'C')
    idx = lunr.lunr(ref='id', fields=weights, documents=documents, **langs)
    idx = idx.serialize()
    #locale.setlocale(locale.LC_COLLATE, saved_locale)
    summaries_file = os.path.join(webroot, 'idx.summaries.json')
    with open(idx_file, 'w') as f:
        json.dump(idx, f)
    with open(summaries_file, 'w') as f:
        json.dump(summaries, f)
    end = datetime.datetime.now()
    duration = str(end - start)
    print('[%s] - lunr index: %s [build time: %s]' % (
        str(end), '/idx.json', duration))


@hookable
def lunr_summary(rec):
    ret = {'title': rec.get('title', rec['id'])}
    for k in ('summary', 'intro', 'description', 'excerpt'):
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
        summary = re.sub(r'\[\[.*?\]\]', ' ', summary)
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
    preview = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == '--preview' else None
    if preview:
        print(preview_single(basedir, preview))
    else:
        main(basedir, quick)
