import os
import re
import datetime
import unicodedata
import sqlite3
import hashlib
import json
import locale


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

    def group_by(self, pred, normalize=None, keep_empty=False):
        """
        Group items in an MDContentList using a given criterion.

        - `pred`: A callable receiving a content item and returning a string or
          a list of strings. For convenience, `pred` may also be specified as
          a string and is then interpreted as the value of the named `page`
          variable, e.g. `category`.
        - `normalize`: a callable that transforms the grouping values, e.g.
          to lowercase.
        - `keep_empty`: Normally items are omitted if their predicate evaluates
          to the empty string. This can be overridden by setting this to True.

        Returns a dict whose keys are strings and whose values are MDContentList
        instances.
        """
        if isinstance(pred, str):
            pagekey = pred
            pred = lambda x: x['data']['page'].get(pagekey, '')
        found = {}
        for it in self:
            keys = pred(it)
            if not isinstance(keys, list):
                keys = [keys]
            if normalize:
                keys = list(set([normalize(_) for _ in keys]))
            for k in keys:
                if not k and not keep_empty:
                    continue
                if k in found:
                    found[k].append(it)
                else:
                    found[k] = MDContentList([it])
        return found

    def sorted_by(self, key, reverse=False, default_val=-1):
        if isinstance(default_val, str):
            k = lambda x: locale.strxfrm(
                x['data']['page'].get(key, default_val))
        else:
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
        is_bool = len(needles) == 1 and isinstance(needles[0], bool) and needles[0]
        if not is_bool:
            needles = [_.lower() for _ in needles]
        def found(x):
            for k in haystack_keys:
                if k in x:
                    if is_bool and x[k]:
                        return True  ## at least one tag/category/etc. is present
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
            found.sort(key=lambda x: locale.strxfrm(x[order]), reverse=False)
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

    def page_match(self, match_expr, ordering=None, limit=None, inverse=False):
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

        `inverse` means that all the above conditions except `exclude_url` will
        be negated, i.e. will NOT match the specified title, slug, url, etc.

        The `ordering` parameter, if specified, should be either
        `title`, `slug`, `url`, `weight` or `date`, with an optional `-` in
        front to indicate reverse ordering. The `limit`, if specified, indicates
        the maximum number of pages to return.
        """
        found = MDContentList([])
        known_conds = (
            'title', 'slug', 'id', 'url', 'path', 'doc', 'date_range',
            'has_attrs', 'attrs', 'has_tag', 'in_section', 'in_category',
            'is_post', 'exclude_url')
        boolval = lambda x: not bool(x) if inverse else bool(x)
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
                    if k in x and not boolval(re.search(x[k], p.get(k, ''), flags=re.I)):
                        return False
                if 'id' in x:
                    idlist = (x['id'], ) if isinstance(x['id'], str) else x['id']
                    if not boolval(p['id'] in idlist):
                        return False
                if 'url' in x and not boolval(re.search(x['url'], c['url'], flags=re.I)):
                    return False
                if 'path' in x and not boolval(re.search(x['path'], c['source_file_short'], flags=re.I)):
                    return False
                if 'doc' in x and not boolval(re.search(x['doc'], c['doc'], flags=re.I)):
                    return False
                if 'has_attrs' in x:
                    for a in x['has_attrs']:
                        if not boolval(p.get(a)):
                            return False
                if 'attrs' in x:
                    for k in x['attrs']:
                        if not boolval(str(p.get(k, '')).lower() == str(x['attrs'][k]).lower()):
                            return False
                if 'has_tag' in x:
                    if not boolval(MDContentList([c]).has_tag(x['has_tag'])):
                        return False
                if 'in_section' in x:
                    if not boolval(MDContentList([c]).in_section(x['in_section'])):
                        return False
                if 'in_category' in x:
                    if not boolval(MDContentList([c]).in_category(x['in_category'])):
                        return False
                if 'is_post' in x:
                    posts = MDContentList([c]).posts(ordered=False)
                    if x['is_post'] and not boolval(posts):
                        return False
                    elif not x['is_post'] and boolval(posts):
                        return False
                if 'date_range' in x and not boolval(MDContentList([c]).in_date_range(*x['date_range'])):
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
            found = MDContentList(found[:limit])
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

    def get_db(self):
        """
        Get a connection to an in-memory SQLite database representing the pages
        in the MDContent list.
        """
        if hasattr(self, '_db'):
            return self._db
        db = sqlite3.connect(':memory:')
        db.row_factory = sqlite3.Row
        def _locale_collation(a, b):
            va = locale.strxfrm(a)
            vb = locale.strxfrm(b)
            return 1 if va > vb else -1 if va < vb else 0
        db.create_collation('locale', _locale_collation)
        _casefold = lambda x: x.casefold() if isinstance(x, str) else str(x or '').casefold()
        db.create_function('casefold', 1, _casefold, deterministic=True)
        cur = db.cursor()
        fixed_cols = [
            'url', 'source_file', 'source_file_short', 'target',
            'template', 'MTIME', 'DATE', 'doc', 'rendered', ]
        page_cols = set()
        guess_type = {}
        for it in self:
            pg = it['data']['page']
            valid_keys = [_ for _ in pg.keys() if re.match(r'^[a-z][a-zA-Z0-9_]*$', _)]
            for k in valid_keys:
                page_cols.add('page_' + k)
                if not k in guess_type:
                    if isinstance(pg[k], bool):
                        guess_type[k] = 'bool'
                    elif isinstance(pg[k], int):
                        guess_type[k] = 'int'
                    elif isinstance(pg[k], float):
                        guess_type[k] = 'numeric'
                    elif isinstance(pg[k], datetime.date):
                        guess_type[k] = 'date'
                    elif isinstance(pg[k], datetime.datetime):
                        guess_type[k] = 'timestamp'
                    elif isinstance(pg[k], (list, dict)):
                        guess_type[k] = 'json'
                    else:
                        guess_type[k] = 'text'
        sql = """
          CREATE TABLE content (
            url text,
            source_file text,
            source_file_short text,
            target text,
            template text,
            mtime timestamp,
            "date" timestamp,
            doc text,
            rendered text"""
        for pc in page_cols:
            sql += ',\n    %s %s' % (pc, guess_type[pc[5:]])
        sql += "\n);"
        cur.execute(sql);
        page_cols_list = list(page_cols)
        all_cols = fixed_cols + page_cols_list
        ins_sql = "INSERT INTO content (%s) VALUES (%s)" % (
            ', '.join(all_cols), ', '.join([':'+_ for _ in all_cols]))
        def _val(v):
            if not v and isinstance(v, dict):
                return None
            elif isinstance(v, (bool, int, float, str)):
                return v
            elif isinstance(v, (datetime.date, datetime.datetime)):
                return str(v)
            elif v is None:
                return None
            else:
                return json.dumps(v, default=str, ensure_ascii=False)
        for it in self:
            rec = {}
            for k in fixed_cols:
                rec[k] = it['data'][k] if k.upper()==k else it[k]
            for pc in page_cols_list:
                k = pc[5:]
                rec[pc] = _val(it['data']['page'].get(k))
            cur.execute(ins_sql, rec)
        db.commit()
        self._db = db
        return db

    def get_db_columns(self):
        """
        Gets a list of columns in the content table of the SQLite database
        provided by the .get_db() method (some columns are fixed, but many
        of the `page_*` columns depend upon the metadata of the content items).
        """
        db = self.get_db()
        cur = db.cursor()
        cur.execute("select * from content where 0=1")
        return [_[0] for _ in cur.description]

    def page_match_sql(self, where_clause=None, bind=None,
                       order_by=None, limit=None, offset=None,
                       raw_sql=None, raw_result=False, first=False):
        """
        Filter this MDContentList by a SQL SELECT statement run against the
        SQLite database generated by self.get_db(). Parameters: `where_clause`
        (string), `bind` (bind values for the where clause), `order_by`
        (string), `limit` (int), `offset` (int), `raw_sql` (string),
        `raw_result` (string), `first` (bool). Either `where_clause` or
        `raw_sql` must be specified. If `first` is True, only the first item in
        the result is returned (or None, if the list of results is empty).
        """
        db = self.get_db()
        cur = db.cursor()
        if not (where_clause or raw_sql):
            raise Exception('Need either where_clause or raw_sql')
        if raw_sql:
            sql = raw_sql
            if not raw_result and not 'source_file' in sql.lower():
                raise Exception(
                    'The raw_sql has no source_file column')
        else:
            sql = "SELECT {0} FROM content WHERE {1}".format(
                '*' if raw_result else 'source_file', where_clause)
        if order_by:
            sql += ' ORDER BY {}'.format(order_by)
        if limit:
            sql += ' LIMIT {}'.format(int(limit))
            if offset:
                sql += ' OFFSET {}'.format(int(offset))
        res = cur.execute(sql, bind) if bind else cur.execute(sql)
        if raw_result:
            return res.fetchone() if first else res
        else:
            self_as_dict = dict([(_['source_file'], _) for _ in self])
            if first:
                it = res.fetchone()
                return self_as_dict[it['source_file']] if it else it
            res_as_list = [self_as_dict[_['source_file']] for _ in res.fetchall()]
            return MDContentList(res_as_list)


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


class NavBase:
    is_root = False
    is_section = False
    is_link = False
    title = None
    url = None  # only applicable to links
    parent = None
    children = [] # empty for links
    level = 0
    next = None  # only applicable to *local* links
    previous = None  # only applicable to *local* links
    attr = {} # things like link_target, css_class, css_id...


    def nav_item_list(self, items, level=-1):
        ret = []
        for it in items:
            if not isinstance(it, dict):
                raise ValueError('Bad input; not dict: ' + str(it))
            # Special case: Section as dict rather than list
            if 'title' in it and 'children' in it:
                title = it.pop('title')
                children = it.pop('children')
                ret.append(
                    NavSection(title=title, children=children,
                               parent=self, level=level+1, attr=it))
                continue
            elif len(it) != 1:
                raise ValueError('Bad input: ' + str(it))
            for title in it:
                if isinstance(it[title], list):
                    ret.append(
                        NavSection(title=title, children=it[title],
                                   parent=self, level=level+1))
                elif isinstance(it[title], str):
                    ret.append(
                        NavLink(title=title, url=it[title],
                                parent=self, level=level+1))
                elif isinstance(it[title], dict):
                    # Special case: Link as dict rather than str
                    ret.append(
                        NavLink(title=title, url=it[title]['url'],
                                parent=self, level=level+1, attr=it[title]))
        return ret


class NavItem(NavBase):
    @property
    def ancestors(self):
        ret = []
        parent = self.parent
        while parent:
            ret.append(parent)
            parent = parent.parent
        return ret

    @property
    def siblings(self):
        parent = self.parent
        return [c for c in self.parent.children if c != self]


class NavLink(NavItem):
    is_link = True
    is_homepage = False

    def __init__(self, title, url, parent=None, level=0, attr=None):
        self.title = title
        self.url = url
        self.parent = parent
        self.level = level
        if attr:
            self.attr = attr

    def is_url(self, url, normalize):
        "The given url is the same as self.url after normalization."
        return normalize(url) == normalize(self.url)

    def contains_url(self, url, normalize, best=False):
        """
        The given url starts with self.url or is identical to it (after
        normalization). If best is True, self.url must be the best-matching such
        link in the entire nav (i.e. the longest one).
        """
        if best:
            if not self.contains_url(url, normalize):
                return False
            better = [link for link in self.ancestors[-1]._links_in_order()
                      if link != self
                         and link.contains_url(url, normalize)
                         and not link.contains_url(self.url, normalize)]
            return not better
        else:
            return normalize(url).startswith(normalize(self.url))

    def _indented(self):
        ret = "  " * self.level or ''
        ret += self.title + ': ' + self.url + "\n"
        return ret

    @property
    def is_local(self):
        if 'is_local' in self.attr:
            return self.attr['is_local']
        return not self.url.startswith(('https:', 'http:'))

    def __repr__(self):
        return 'NavLink %s: %s [level=%d]' % (self.title, self.url, self.level)


class NavSection(NavItem):
    is_section = True

    def __init__(self, title, children, parent=None, level=0, attr=None):
        self.title = title
        self.children = self.nav_item_list(children, level=level)
        self.parent = parent
        self.level = level
        if attr:
            self.attr = attr

    def _indented(self):
        ret = "  " * self.level or ''
        ret += self.title + ":\n"
        for c in self.children:
            ret += c._indented()
        return ret

    def _links_in_order(self):
        links = []
        for it in self.children:
            if it.children:
                sublinks = it._links_in_order()
                links += sublinks
            else:
                links.append(it)
        return links

    def contains_url(self, url, normalize, best=False):
        """
        This section contains a link for which contains_url() is True given
        the conditions. If best is True, the link must be an immediate child of
        this section (i.e. not of a subsection).
        """
        if best:
            links = [_ for _ in self.children if isinstance(_, NavLink)]
        else:
            links = self._links_in_order()
        links = [_ for _ in links if _.contains_url(url, normalize, best)]
        return True if links else False

    def __repr__(self):
        return 'NavSection %s [level=%d, children=%d]' % (
            self.title, self.level, len(self.children))

    def __iter__(self):
        return iter(self.children)

    def __len__(self):
        return len(self.children)


class Nav(NavSection):
    """
    A Nav is a root-level NavSection without a title and with the optional extra
    attribute homepage.
    """
    is_root = True
    level = None
    homepage = None

    def __init__(self, nav, homepage=None):
        """
        Normal YAML for nav looks something like this:

        nav:
          - Home: 'index.html'
          - User Guide:
            - Writing: writing
            - Styling: styling
          - Resources:
            - Community: 'https://example.com/'
            - Source code: 'https://github.com/example/com/'
          - About:
            - License: about/license
            - History: about/history
        """
        if isinstance(nav, dict) and 'nav' in nav:
            nav = nav['nav']
        self.children = self.nav_item_list(nav)
        # Fill out previous/next attributes for local links
        links = self._links_in_order()
        local_links = [_ for _ in links if _.is_local]
        if len(local_links) > 1:
            for i, link in enumerate(local_links):
                link.previous = local_links[i-1] if i > 0 else None
                link.next = local_links[i+1] if i < len(local_links) - 1 else None
        # Homepage setting
        if homepage:
            self.homepage = homepage if isinstance(homepage, NavLink) \
                else NavLink(homepage['title'], homepage['url'])
        elif homepage is None and links:
            found = [_ for _ in links if _.attr.get('is_homepage', False)]
            self.homepage = found[0] if found else links[0]
        if self.homepage:
            # Note that this marks at most one link as the homepage
            for link in links:
                if link.url == self.homepage.url:
                    link.is_homepage = True
                    break

    def __repr__(self):
        return ''.join([_._indented() for _ in self.children])


class Toc:
    """
    Extracts an iterable table of contents from HTML containing headings with id
    attributes. The attribute item_count counts all toc items, regardless of
    nesting. Each item has title, url, level and children attributes.
    """
    def __init__(self, html):
        self.items = []
        raw_items = self._extract_headings(html)
        self.item_count = len(raw_items)
        for it in raw_items:
            if self.items and it.level > self.items[-1].level:
                self.items[-1].add_child(it)
            else:
                self.items.append(it)

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)

    def _extract_headings(self, html):
        ret = []
        found = re.findall(
            r'<[hH]([1-6])[^>]* id="([^"]+)"[^>]*>(.*?)</[hH][1-6]>',
            html, flags=re.S)
        for level, url, title in found:
            # remove possible self-permalinks from header content
            title = re.sub(r'<a[^>]* href="#[^"]+"[^>]*>.+?</a>', '', title)
            ret.append(TocItem(title, '#'+url, int(level)))
        return ret


class TocItem:
    def __init__(self, title, url, level):
        self.title = title
        self.url = url
        self.level = level
        self.children = []

    def add_child(self, child):
        if child.level <= self.level:
            raise ValueError('A child must have a higher level than a parent')
        elif child.level == self.level + 1:
            self.children.append(child)
        else:
            cand = self.children[-1]
            while cand.level < child.level - 1:
                cand = cand.children[-1]
            cand.children.append(child)


def hookable(fn):
    nam = fn.__name__
    orig_fn = fn
    def wrapper(*args, **kwargs):
        try:
            import wmk_hooks
        except ModuleNotFoundError:
            wmk_hooks = None
        try:
            import wmk_theme_hooks
        except ModuleNotFoundError:
            wmk_theme_hooks = None
        if not (wmk_hooks or wmk_theme_hooks):
            return orig_fn(*args, **kwargs)
        new_fn = None
        if hasattr(wmk_hooks, nam):
            new_fn = getattr(wmk_hooks, nam)
        elif hasattr(wmk_theme_hooks, nam):
            new_fn = getattr(wmk_theme_hooks, nam)
        actions = {'before': None, 'after': None}
        for action in ('before', 'after'):
            for hooks in (wmk_hooks, wmk_theme_hooks):
                if hasattr(hooks, f'{nam}__{action}'):
                    actions[action] = getattr(hooks, f'{nam}__{action}')
                    break
        if actions['before']:
            ret = actions['before'](*args, **kwargs)
            if isinstance(ret, tuple):
                args = ret[0]
                kwargs.update(ret[1])
            elif isinstance(ret, dict):
                kwargs.update(ret)
        main_ret = new_fn(*args, **kwargs) if new_fn else orig_fn(*args, **kwargs)
        if actions['after']:
            ret = actions['after'](main_ret)
            if ret:
                return ret
        return main_ret
    return wrapper
