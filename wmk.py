#!/usr/bin/env python3

import os
import sys
import datetime
import re
import ast
import unicodedata

import sass
import yaml
import frontmatter
import markdown

from mako.template import Template
from mako.lookup import TemplateLookup
from mako.exceptions import text_error_template, TemplateLookupException
from mako.runtime import Undefined


# Template variables with these names will be converted to date or datetime
# objects (depending on length) - if they conform to ISO 8601.
KNOWN_DATE_KEYS = (
    'date', 'pubdate', 'modified_date', 'expire_date', 'created_date')


def main(basedir=None, force=False):
    """
    Builds/copies everything into the output dir (htdocs).
    """
    if basedir is None:
        basedir = os.path.dirname(os.path.realpath(__file__)) or '.'
    basedir = os.path.realpath(basedir)
    if not os.path.isdir(basedir):
        raise Exception('{} is not a directory'.format(basedir))
    if not os.path.exists(os.path.join(basedir, 'wmk_config.yaml')):
        print(
            'ERROR: {} does not contain a wmk_config.yaml'.format(
                basedir))
        sys.exit(1)
    dirs = get_dirs(basedir)
    ensure_dirs(dirs)
    sys.path.insert(0, dirs['python'])
    conf = get_config(basedir)
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
    lookup = TemplateLookup(
        directories=lookup_dirs,
        imports=conf.get('mako_imports', None))
    conf['_lookup'] = lookup
    # 3) get info about stand-alone templates and Markdown content
    templates = get_templates(
        dirs['templates'], themedir, dirs['output'], template_vars)
    index_yaml = get_index_yaml_data(dirs['content'], dirs['data'])
    conf['_index_yaml_data'] = index_yaml or {}
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
        'python': basedir + '/py', # python modeles available to Mako templates
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
        self_url = tpl['target'].replace(data['WEBROOT'], '', 1)
        self_url = re.sub(r'/index.html$', '/', self_url)
        data['SELF_URL'] = self_url
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
        try:
            html_output = template.render(**data)
        except:
            print("WARNING: Error when rendering md {}: {}".format(
                ct['source_file_short'], text_error_template().render()))
            html_output = None
        if html_output and not page.get('do_not_render', False):
            with open(ct['target'], 'w') as f:
                f.write(template.render(**data))
            print('[%s] - content: %s' % (
                str(datetime.datetime.now()), ct['source_file_short']))
        elif html_output:
            # This output is non-draft but marked as not to be rendered.
            # ("headless" in Hugo parlance)
            print('[%s] - non-rendered: %s' % (
                str(datetime.datetime.now()), ct['source_file_short']))


def render_markdown(ct, conf):
    "Convert markdown document to HTML (including shortcodes)"
    if 'CONTENT' in ct:
        return ct['CONTENT']
    data = ct['data']
    doc = ct['doc']
    nth = {}
    if '{{<' in doc:
        # Mako shortcodes
        # funcname, argstring
        pat = r'{{<\s*(\w+)\(\s*(.*?)\s*\)\s*>}}'
        found = re.search(pat, doc, re.DOTALL)
        while found:
            doc = re.sub(pat, mako_shortcode(conf, data, nth), doc, flags=re.DOTALL)
            found = re.search(pat, doc, re.DOTALL)
    extensions = conf.get('markdown_extensions', None)
    if extensions is None:
        extensions = ['extra', 'sane_lists']
    return markdown.markdown(doc, extensions=extensions)


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
                    loaded = yaml.safe_load(yf) or {}
                    if loaded:
                        loaded.update(info)
                        info = loaded
            removed = info.pop('LOAD', None)
            ret[curdir] = info
    return ret


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
            # merge with data from 'LOAD' file, if any
            if 'LOAD' in page:
                load_path = os.path.join(datadir, page['LOAD'])
                if os.path.exists(load_path):
                    loaded = {}
                    with open(load_path) as yf:
                        loaded = yaml.safe_load(yf) or {}
                    for k in loaded:
                        if not k in page:
                            page[k] = loaded[k]
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
                page['title'] = re.sub(r'[-_]', ' ', page['slug'])
                page['title'] = re.sub(r'^[0-9 ]+', '', page['title']).strip() or '??'
            fn = '/'.join(fn_parts)
            html_fn = fn.replace('.md', '/index.html' if pretty_path else '.html')
            html_dir = root.replace(ctdir, outputdir, 1)
            target_fn = os.path.join(html_dir, html_fn)
            data['SELF_URL'] = '' if page.get('do_not_render') \
                else target_fn.replace(outputdir, '', 1)
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
            try:
                if len(data[k]) == 10:
                    data[k] = datetime.date.fromisoformat(data[k])
                else:
                    data[k] = datetime.datetime.fromisoformat(data[k].replace('Z', ''))
            except:
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
            return tpl.render(*args, **ckwargs)
        except Exception as e:
            print("WARNING: shortcode {} failed: {}".format(name, e))
            # prevent infinite loops
            return match.group(0).replace('{', '(').replace('}', ')')
    return replacer


def slugify(s):
    """
    Make a 'slug' from the given string. If it seems to end with a file
    extension, remove that first and re-append a lower case version of it before
    returning the result. Probably only works for Latin text.
    """
    ext = ''
    ext_re = r'(\.[a-zA-Z0-9]{1,8})$'
    found = re.search(ext_re, s)
    if found:
        ext = found.group(1).lower()
        s = re.sub(ext_re, '', s)

    # Get rid of single quotes
    s = re.sub(r"[']+", '-', s)

    # Remove accents
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn')
    s = s.lower()
    # Normalization may leave extra quotes (?)
    s = re.sub(r"[']+", '-', s)

    # Some special chars:
    for c, r in (('þ', 'th'), ('æ', 'ae'), ('ð', 'd')):
        s = s.replace(unicodedata.normalize('NFKD', c), r)

    ret = ''

    for _ in s:
        if re.match(r'^[-a-z0-9]$', _):
            ret += _
        elif not re.match(r'^[´¨`]$', _):
            ret += '-'

    # Prevent double dashes, remove leading and trailing ones
    ret = re.sub(r'--+', '-', ret)
    ret = ret.strip('-')

    return ret + ext


class attrdict(dict):
    """
    Dict with the keys as attributes (or member variables), for nicer-looking
    and more convenient lookups.

    If the encapsulated dict has keys corresponding to the built-in attributes
    of dict, i.e. one of 'clear', 'copy', 'fromkeys', 'get', 'items', 'keys',
    'pop', 'popitem', 'setdefault', 'update', or 'values', these will be renamed
    so as to have a leading underscore.

    An attempt to access a non-existing key as an attribute results in a Mako
    Undefined object (for ease of usage in Mako templates).
    """
    __reserved = dir(dict())
    __reserved.append('__reserved')
    __reserved = set(__reserved)

    def __init__(self, *args, **kwargs):
        if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
            kwargs = args[0]
        for k in attrdict.__reserved:
            if k in kwargs:
                kwargs['_'+k] = kwargs.pop(k)
        dict.__init__(self, *args, **kwargs)
        self.__dict__ = self

    def __setitem__(self, k, v):
        if k in attrdict.__reserved:
            super().__setitem__('_'+k, v)
        else:
            super().__setitem__(k, v)

    def __setattr__(self, k, v):
        if k in attrdict.__reserved:
            super().__setattr__('_'+k, v)
        else:
            super().__setattr__(k, v)

    def __getattr__(self, k):
        if k in attrdict.__reserved:
            return super().__getattr(k)
        try:
            return self.__dict__[k]
        except KeyError:
            return Undefined()


class MDContentList(list):
    """
    Filterable MDCONTENT, for ease of list components.
    """

    def match_entry(self, pred):
        """
        Filter by all available info: source_file, source_file_short, target,
        template, data (i.e. template_context), doc (markdown source),
        url, rendered (html fragment, i.e. CONTENT).
        """
        return MDContentList([_ for _ in self if pred(_)])

    def match_ctx(self, pred):
        "Filter by template context (page, site, MTIME, SELF_URL, etc.)"
        return MDContentList([_ for _ in self if pred(_['data'])])

    def match_page(self, pred):
        "Filter by page variables"
        return MDContentList([_ for _ in self if pred(_['data']['page'])])

    def match_doc(self, pred):
        "Filter by Markdown body"
        return MDContentList([_ for _ in self if pred(_['doc'])])

    def sorted_by(self, key, reverse=False, default_val=-1):
        k = lambda x: x['data']['page'].get(key, default_val)
        return MDContentList(sorted(self, key=k, reverse=reverse))

    def sorted_by_date(self, newest_first=True, date_key='DATE'):
        k = lambda x: str(
            x['data'][date_key]
              if date_key in ('DATE', 'MTIME') \
              else x['data']['page'].get(date_key, x['data']['DATE']))
        return MDContentList(sorted(self, key=k, reverse=newest_first))

    def sorted_by_title(self, reverse=False, default_val='ZZZ'):
        return self.sorted_by('title', reverse=reverse, default_val=default_val)

    def in_date_range(self, start, end, date_key='DATE'):
        def found(x):
            pg = x['page']
            date = data[date_key] if date_key in ('DATE', 'MTIME') else pg.get(date_key, data['DATE'])
            return str(start) <= str(date) <= str(end)
        return self.match_ctx(found)

    def posts(self, ordered=True):
        """
        Posts, i.e. blog entries, are defined as content in specific directories
        (posts, blog) or having a 'type' attribute of 'post', 'blog',
        'blog-entry' or 'blog_entry'.
        """
        is_post = lambda x: (x['source_file_short'].strip('/').startswith(('posts/', 'blog/'))
                             or x['data']['page'].get('type', '') in (
                                 'post', 'blog', 'blog-entry', 'blog_entry'))
        ret = self.match_entry(is_post)
        return ret.sorted_by_date() if ordered else ret

    def url_match(self, url_pred):
        return self.match_entry(lambda x: urlpred(x['url']))

    def path_match(self, src_pred):
        return self.match_entry(lambda x: src_pred(x['source_file_short']))

    def has_taxonomy(self, haystack_keys, needles):
        if not needles:
            return MDContentList([])
        if not isinstance(needles, (list, tuple)):
            needles = [needles]
        needles = [_.lower() for _ in needles]
        def found(x):
            for k in haystack_keys:
                if k in x:
                    if isinstance(x[k], (list, tuple)):
                        for _ in x[k]:
                            if _.lower() in needles:
                                return True
                    elif x[k].lower() in needles:
                        return True
            return False
        return self.match_page(found)

    def in_category(self, catlist):
        return self.has_taxonomy(['category', 'categories'], catlist)

    def has_tag(self, taglist):
        return self.has_taxonomy(['tag', 'tags'], taglist)

    def in_section(self, sectionlist):
        return self.has_taxonomy(['section', 'sections'], sectionlist)

    def paginate(self, pagesize=5, context=None):
        """
        Divides the page list into chunks of size `pagesize` and returns
        a tuple consisting of the chunks and a list of page_urls (one for each
        page, in order).  If an appropriate template context is provided, pages
        2 and up will be written to the webroot output directory. Without the
        context, the page_urls will be None.
        NOTE: It is the responsibility of the calling template to check the
        '_page' variable for the current page to be rendered (this defaults to
        1). Each iteration will get all chunks and must use this variable to
        limit itself appriopriately.
        """
        page_urls = None
        chunks = [self[i:i+pagesize] for i in range(0, len(self), pagesize)] or [[]]
        if len(chunks) < 2:
            # We only have one page -- no need to do anything further
            if context:
                page_urls = [context.get('SELF_URL')]
            return (chunks, page_urls)
        elif context:
            # We have the context and can thus write the output for pages 2 and up.
            # We need the template, the template lookup object, the _page, the
            # webroot and the self_url of the caller.
            curpage = int(context.get('_page', 1))
            self_url = context.get('SELF_URL')
            page_urls = [self_url]
            if self_url.endswith('/'):
                self_url += 'index.html'
            # TODO: make url/output path configurable (creating directories if needed)
            url_pat = re.sub(r'\.html$', r'__page_{}.html', self_url)
            for i in range(2, len(chunks)+1):
                page_urls.append(url_pat.format(i))
            if curpage == 1:
                # So as only to write the output once, we do it for all pages > 1
                # only on page 1.
                self_tpl = context.get('SELF_TEMPLATE')
                webroot = context.get('WEBROOT')
                page_template = context.lookup.get_template(self_tpl)
                for pg in range(2, len(chunks)+1):
                    kw = dict(**context.kwargs)
                    kw['_page'] = pg
                    output_fn = os.path.join(webroot, url_pat.format(pg).strip('/'))
                    with open(output_fn, 'w') as fpg:
                        fpg.write(page_template.render(**kw))
            return (chunks, page_urls)
        else:
            # We cannot write output since we lack context.
            # Return all chunks along with their length. A page_urls value of
            # None mean that the caller must take care of writing the output
            # (and that all chunks are present in the
            # first item in the return value).
            return (chunks, None)


if __name__ == '__main__':
    basedir = sys.argv[1] if len(sys.argv) > 1 else None
    force = True if len(sys.argv) > 2 and sys.argv[2] in ('-f', '--force') else False
    main(basedir, force)
