import os
import re
import unicodedata


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
