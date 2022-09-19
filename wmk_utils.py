import os
import re
import unicodedata
import sqlite3
import hashlib


def slugify(s):
    """
    Make a 'slug' from the given string. If it seems to end with a file
    extension, remove that first and re-append a lower case version of it before
    returning the result. Probably only works for Latin text.
    """
    if not isinstance(s, str):
        # print("WARNING: NOT A STRING: ", s)
        s = str(s)

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

    An attempt to access a non-existing key as an attribute results in an empty
    attrdict. Chained attrdict access is provided to dict values of keys in the
    original dict (so, e.g., `page.more.nested.val` works does not raise an error
    even if the `more` key is not present).
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
        for k in self:
            if isinstance(self[k], dict) and not isinstance(self[k], attrdict):
                self[k] = attrdict(self[k])
            elif isinstance(self[k], list):
                for i, it in enumerate(self[k]):
                    if isinstance(it, dict) and not isinstance(it, attrdict):
                        self[k][i] = attrdict(it)
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
            #return Undefined()
            return attrdict({})


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

    def sorted_by_title(self, reverse=False):
        return self.sorted_by('title', reverse=reverse, default_val='ZZZ')

    def in_date_range(self, start, end, date_key='DATE'):
        std = lambda ts: str(ts).replace(' ', 'T')  # standard ISO fmt
        def found(x):
            pg = x['page']
            date = x[date_key] if date_key in ('DATE', 'MTIME') else pg.get(date_key, x['DATE'])
            return std(start) <= std(date) <= std(end)
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

    def non_posts(self):
        """
        'Pages', i.e. all entries that are NOT posts/blog entreis.
        """
        not_post = lambda x: not (
            x['source_file_short'].strip('/').startswith(('posts/', 'blog/'))
            or x['data']['page'].get('type', '') in (
                'post', 'blog', 'blog-entry', 'blog_entry'))
        return self.match_entry(not_post)

    def has_slug(self, sluglist):
        """
        Pages with any of the given slugs.
        """
        if isinstance(sluglist, str):
            sluglist = (sluglist, )
        slugpred = lambda x: x.slug in sluglist
        return self.match_page(slugpred)

    def has_id(self, idlist):
        """
        Pages with any of the given ids.
        """
        if isinstance(idlist, str):
            idlist = (idlist, )
        idpred = lambda x: x['id'] in idlist
        return self.match_page(idpred)

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
                            if not _:
                                continue
                            if _.lower() in needles:
                                return True
                    elif x[k] and x[k].lower() in needles:
                        return True
            return False
        return self.match_page(found)

    def taxonomy_info(self, keys, order='count'):
        """
        A list of values for any of the keys in `keys`. The values are assumed
        to be strings/ints or lists of strings/ints. Example usage:

        tags = MDCONTENT.taxonomy_info(['tag', 'tags'])

        Each record in the returned list looks like

        {'name': f1,  # First found form of this taxon
         'slug': slug, # result of slugifying first-found-item
         'forms': [f1,f2...], # Different forms of this taxon found (e.g. lower/uppercase)
         'count': n, # how many documents match
         'items': items, } # MDContentList object
        """
        if isinstance(keys, str):
            keys = [keys]
        if not keys:
            return []
        taxons = {}
        slug2name = {}
        seen_urls = set()
        def _additem(tx, item):
            seen_key = ':'.join([slugify(tx), item['url']])
            if tx in taxons:
                taxons[tx]['count'] += 1
                if not item['url'] in seen_urls:
                    taxons[tx]['items'].append(item)
                    seen_urls.add(seen_key)
            else:
                slug = slugify(tx)
                if slug in slug2name:
                    taxons[slug2name[slug]]['count'] += 1
                    if not seen_key in seen_urls:
                        taxons[slug2name[slug]]['items'].append(item)
                        seen_urls.add(seen_key)
                    if not tx in taxons[slug2name[slug]]['forms']:
                        taxons[slug2name[slug]]['forms'].append(tx)
                else:
                    taxons[tx] = {
                        'name': tx,
                        'slug': slug,
                        'forms': [tx],
                        'count': 1,
                        'items': MDContentList([item]),
                    }
                    seen_urls.add(seen_key)
                    slug2name[slug] = tx
        for it in self:
            pg = it['data']['page']
            for k in keys:
                if k in pg:
                    if isinstance(pg[k], (str, int)):
                        _additem(pg[k], it)
                    elif isinstance(pg[k], (list, tuple)):
                        for tx in pg[k]:
                            _additem(tx, it)
        found = list(taxons.values())
        if order == 'count':
            found.sort(key=lambda x: x['count'], reverse=True)
        elif order in ('name', 'slug'):
            found.sort(key=lambda x: x[order], reverse=False)
        return found

    def get_categories(self, order='name'):
        "Categories along with list of pages/posts in them."
        return self.taxonomy_info(['category', 'categories'], order)

    def get_tags(self, order='name'):
        "Tags along with list of pages/posts tagged with them."
        return self.taxonomy_info(['tag', 'tags'], order)

    def get_sections(self, order='name'):
        "Sections along with list of pages/posts in them."
        return self.taxonomy_info(['section', 'sections'], order)

    def in_category(self, catlist):
        "Pages/posts in any of the listed categories."
        return self.has_taxonomy(['category', 'categories'], catlist)

    def has_tag(self, taglist):
        "Pages/posts having any of the given tags."
        return self.has_taxonomy(['tag', 'tags'], taglist)

    def in_section(self, sectionlist):
        "Pages/posts in any of the given sections."
        return self.has_taxonomy(['section', 'sections'], sectionlist)

    def page_match(self, match_expr, ordering=None, limit=None):
        """
        The `match expr` is either a dict or a list of dicts. Each dict contains
        one or more of the following keys, all of which must match. If a list of
        dicts is given, the union of matching entries from all dicts is
        returned.

        - `title`: A regular expression which will be applied to the page title.
        - `slug`: A regular expression which will be applied to the slug.
        - `id`: A string or list of strings which must match the id exactly.
        - `url`: A regular expression which will be applied to the target URL.
        - `path`: A regular expression which will be applied to the path to the markdown
           source file (i.e. the `source_file_short` field).
        - `doc`: A regular expression which will be applied to the body of the markdown
          source document.
        - `date_range`: A list containing two ISO-formatted dates and optionally a date
          key (`DATE` by default)
        - `has_attrs`: A list of frontmatter variable names. Matching pages must have a
          non-empty value for each of them.
        - `attrs`: A dict where each key is the name of a frontmatter variable and the
          value is the value of that attribute. If the value is a string, it will be
          matched case-insensitively. All key-value pairs must match.
        - `has_tag`, `in_section`, `in_category`: The values are lists of tags, sections
          or categories, respectively, at least one of which must match
          (case-insensitively).
        - `is_post`: If set to True, will match if the page is a blog post; if set to
          False will match if the page is not a blog post.
        - `exclude_url`: The page with this URL should be omitted (normally the
          calling page).

        The `ordering` parameter, if specified, should be either
        `title`, `slug`, `url`, `weight` or `date`, with an optional `-` in
        front to indicate reverse ordering. The `limit`, if specified, indicates
        the maximum number of pages to return.
        """
        found = MDContentList([])
        known_conds = (
            'title', 'slug', 'url', 'path', 'doc', 'date_range',
            'has_attrs', 'attrs', 'has_tag', 'in_section', 'in_category',
            'is_post', 'exclude_url')
        if isinstance(match_expr, dict):
            if not match_expr:
                raise Exception('No condition for page_match')
            for k in match_expr:
                if not k in known_conds:
                    raise Exception('Unknown condition for page_match: %s' % k)
            def pred(c):
                x = match_expr
                p = c['data']['page']
                if 'exclude_url' in x:
                    # Normalize both URLs somewhat
                    c_url = c['url'].replace('/index.html', '/')
                    x_url = x['exclude_url'].replace('/index.html', '/')
                    if c_url == x_url:
                        return False
                for k in ('title', 'slug'):
                    if k in x and not re.search(x[k], p.get(k, ''), flags=re.I):
                        return False
                if 'id' in x:
                    idlist = (x['id'], ) if isinstance(x['id'], str) else x['id']
                    if not p['id'] in idlist:
                        return False
                if 'url' in x and not re.search(x['url'], c['url'], flags=re.I):
                    return False
                if 'path' in x and not re.search(x['path'], c['source_file_short'], flags=re.I):
                    return False
                if 'doc' in x and not re.search(x['doc'], c['doc'], flags=re.I):
                    return False
                if 'has_attrs' in x:
                    for a in x['has_attrs']:
                        if not p.get(a):
                            return False
                if 'attrs' in x:
                    for k in x['attrs']:
                        if not str(p.get(k, '')).lower() == str(x['attrs'][k]).lower():
                            return False
                if 'has_tag' in x:
                    if not MDContentList([c]).has_tag(x['has_tag']):
                        return False
                if 'in_section' in x:
                    if not MDContentList([c]).in_section(x['in_section']):
                        return False
                if 'in_category' in x:
                    if not MDContentList([c]).in_category(x['in_category']):
                        return False
                if 'is_post' in x:
                    posts = MDContentList([c]).posts(ordered=False)
                    if x['is_post'] and not posts:
                        return False
                    elif not x['is_post'] and posts:
                        return False
                if 'date_range' in x and not MDContentList([c]).in_date_range(*x['date_range']):
                    return False
                return True
            found = self.match_entry(pred)
        elif isinstance(match_expr, (list, tuple)):
            accum = {}
            for exp in match_expr:
                partial = self.page_match(exp)
                for it in partial:
                    if it['url'] in accum:
                        continue
                    accum[it['url']] = it
            found = MDContentList(list(accum.values()))
        else:
            raise Exception(
                'page_match: the match_expr must be either a dict or a list of dicts')
        if ordering and found:
            # title,slug,url,date
            reverse = False
            if ordering[0] == '-':
                reverse = True
                ordering = ordering[1:]
            if ordering in ('title', 'slug'):
                found = found.sorted_by(ordering, reverse, 'ZZZ')
            elif ordering == 'url':
                k = lambda x: x.get('url', 'zzz')
                found = MDContentList(sorted(found, key=k, reverse=reverse))
            elif ordering == 'weight':
                k = lambda x: int(x['data']['page'].get('weight', 999999))
                found = MDContentList(sorted(found, key=k, reverse=reverse))
            elif ordering.startswith('date'):
                if ':' in ordering:
                    dateorder, datefield = ordering.split(':')
                else:
                    datefield = 'DATE'
                found = found.sorted_by_date(
                    newest_first=reverse, date_key=datefield)
            else:
                raise Exception('Unknown ordering for page_match: %s' % ordering)
        if limit and len(found) > limit:
            found = found[:limit]
        return found

    def write_to(self, dest, context, extra_kwargs=None, template=None):
        """
        Add self to the context as 'CHUNK' and call the calling template again
        (or a different template if 'template' is specified), putting the result
        in dest. Directories are created if necessary. Useful for tag pages and
        such. Minimal usage in a template:

          mdcontent_chunk.write_to('/my/path/index.html', context)

        Note that the calling template must be careful to avoid infinite loops.
        """
        if extra_kwargs is None:
            extra_kwargs = {}
        if template is None:
            template = context.get('SELF_TEMPLATE')
        full_path = os.path.join(context.get('WEBROOT'), dest.strip('/'))
        dest_dir = re.sub(r'/[^/]+$', '', full_path)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        tpl = context.lookup.get_template(template)
        kw = dict(**context.kwargs)
        kw['SELF_URL'] = dest
        kw['CHUNK'] = self
        with open(full_path, 'w') as f:
            f.write(tpl.render(**kw, **extra_kwargs))

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

        TODO: Rewrite this in terms of write_to().
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


class RenderCache:
    """
    Extremely simple cache for rendered HTML, keyed on a SHA1 hash of the
    markdown contents and the serialized rendering options.
    May become invalid if shortcodes change without changes in the markdown
    source.
    """
    SQL_INIT = """
      CREATE TABLE cache (
          key varchar not null primary key,
          val text,
          creat int not null default (strftime('%s', 'now')),
          upd int not null default (strftime('%s', 'now'))
      );
    """
    SQL_GETROW = "SELECT val FROM cache WHERE key = :key"
    SQL_INS = "INSERT INTO cache (key, val) VALUES (:key, :val)"
    SQL_UPD = "UPDATE cache SET val = :val, upd = strftime('%s', 'now') WHERE key = :key"

    def __init__(self, doc, optstr='', projdir=None):
        if not projdir:
            cachedir = '/tmp'
        else:
            cachedir = os.path.join(projdir, 'tmp')
            if not os.path.exists(cachedir):
                os.mkdir(cachedir)
        self.filename = os.path.join(
            cachedir, 'wmk_render_cache.%d.db') % os.getuid()
        need_init = not os.path.exists(self.filename)
        self.db = sqlite3.connect(self.filename)
        self.cur = self.db.cursor()
        self.in_cache = False
        if need_init:
            self.cur.execute(self.SQL_INIT)
        self.key = hashlib.sha1(
            doc.encode('utf-8') + str(optstr).encode('utf-8')).hexdigest()

    def get_cache(self):
        self.cur.execute(self.SQL_GETROW, {'key': self.key})
        row = self.cur.fetchone()
        self.in_cache = True if row else False
        return row[0] if row else None

    def write_cache(self, html):
        if self.in_cache:
            return
        prev_val = self.get_cache()
        if prev_val is None:
            self.cur.execute(self.SQL_INS, {'key': self.key, 'val': html})
            self.cur.execute('COMMIT')
            self.in_cache = True
        elif prev_val != html:
            # An update should actually never happen; if it does, the optstr
            # will not have been based on all relevant options
            self.cur.execute(self.SQL_UPD, {'key': self.key, 'val': html})
            self.cur.execute('COMMIT')
