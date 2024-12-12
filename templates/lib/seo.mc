<%doc>
  SEO relevant information for the <head> of the page.
  Includes the <title> tag by default. Much of the functionality
  depends on `site.base_url` (and optionally the related attributes
  `site.seo_base_url` and/or `site.leading_path`) to be set.
</%doc>
<%!
import re
from wmk import VERSION

def add_baseurl(baseurl, url):
    if not baseurl:
        return None
    if baseurl.endswith('/'):
        baseurl = baseurl.rstrip('/')
    if url.startswith('/'):
        return baseurl + url
    else:
        return baseurl + '/' + url
%>

<%def name="seo(site, page, nav=None,
                title=None, with_title=True,
                img=None, with_img=True,
                description=None, with_description=True,
                author=None, with_author=True,
                url=None, with_url=True,
                locale=None, with_locale=True,
                site_name=None, with_site_name=True,
                prev_url=None, next_url=None, with_prevnext=True,
                generator=None, with_generator=True,
                json_ld=None, with_json_ld=True,
                robots=None,
                page_type='article',
                )">
<!-- Begin /lib/seo.mc:seo -->
<%
    page_title = title or (page.title if page else None) or site.title or site.name or 'wmk'
    if callable(page_title):
        page_title = capture(page_title)

    if with_author and author is None:
        if page and page.author:
            author = page.author.name if hasattr(page.author, 'name') else page.author
        elif page and page.authors:
            author = ', '.join([(_.name if hasattr(_, 'name') else _) for _ in page.authors])
        elif site.author:
            author = site.author
        elif site.authors:
            author = ', '.join([(_.name if hasattr(_, 'name') else _) for _ in site.authors])

    if with_description and description is None:
        if page and page.description:
            description = page.description
        elif page and page.meta_description:
            description = page.meta_description
        elif page and page.summary:
            description = page.summary
        elif site.description:
            description = site.description
    if with_description and description and callable(description):
        description = capture(description)

    if with_locale and locale is None:
        locale = ((page.locale or page.lang) if page else None) or site.locale or site.lang

    # Baseurl is needed for img, url, prev_url, next_url
    baseurl = site.seo_base_url or site.base_url or None
    if baseurl and site.leading_path:
        baseurl = baseurl.rstrip('/') + site.leading_path
    if baseurl and baseurl.endswith('/'):
        baseurl = baseurl.rstrip('/')
    if baseurl and not baseurl.startswith(('https://', 'http://')):
        baseurl = None

    if with_img and img is None:
        if page:
            img = page.seo_img or page.main_img or page.image or None
        if img is None and CONTENT:
            # Use the first image in the page body, if found
            found = re.search(r'([^ "]+\.(?:jpe?g|png))', CONTENT, flags=re.I)
            if found:
                img = found.group(1)
        if img is None:
            img = site.seo_img or site.main_img or site.fallback_img or None
    if with_img and img and not img.startswith(('https:', 'http:')):
        img = add_baseurl(baseurl, img)

    orig_url = url
    if with_url and url is not None and not url.startswith(('https:', 'http:')):
        url = add_baseurl(baseurl, cleanurl(url))

    if with_site_name and site_name is None:
        site_name = site.seo_name or site.name or site.title

    if with_prevnext and orig_url and nav and (prev_url is None or next_url is None):
        nav_page = nav.find_item(url=orig_url)
        if nav_page:
            if prev_url is None and nav_page.previous:
                prev_url = nav_page.previous.url
            if next_url is None and nav_page.next:
                next_url = nav_page.next.url
        if prev_url and not prev_url.startswith(('https:', 'http:')):
            prev_url = add_baseurl(baseurl, prev_url)
        if next_url and not next_url.startswith(('https:', 'http:')):
            next_url = add_baseurl(baseurl, prev_url)

    if robots is None and page:
        robots = page.robots or page.meta_robots or None
        if robots is None and page.noindex:
            robots = 'noindex,nofollow'
    if isinstance(robots, (list, tuple)):
        robots = robots.join(',')

    if with_json_ld:
        if json_ld is None:
            if page and page.json_ld:
                json_ld = page.json_ld
            else:
                json_ld = site.json_ld.defaults or {}
        if '@context' not in json_ld:
            json_ld['@context'] = "https://schema.org"
        if '@type' not in json_ld:
            json_ld['@type'] = 'WebPage'
        if 'mainEntityOfPage' not in json_ld and url:
            json_ld['mainEntityOfPage'] = {
                '@type': 'WebPage',
                '@id': url,
            }
        if 'headline' not in json_ld:
            json_ld['headline'] = page_title
        if 'url' not in json_ld and url:
            json_ld['url'] = url
        if 'description' not in json_ld and description:
            json_ld['description'] = description
        if 'image' not in json_ld and img:
            json_ld['image'] = img
        if 'dateModified' not in json_ld and page:
            mdate = page.modified_date or page.date_modified or page.date
            if mdate:
                json_ld['dateModified'] = date_to_iso(mdate)
        if 'datePublished' not in json_ld and page:
            pdate = page.pubdate or page.created_date or page.date
            if pdate:
                json_ld['datePublished'] = date_to_iso(pdate)
        if 'author' not in json_ld and author:
            json_ld['author'] = {'name': author}
        if 'publisher' not in json_ld and (site.publisher or site.facebook.publisher):
            pbl = site.publisher or site.facebook.publisher
            if isinstance(pbl, str):
                json_ld['publisher'] = {'name': pbl}
            else:
                json_ld['publisher'] = pbl
%>\
% if with_title:
  <title>${ page_title }</title>
  <meta property="og:title" content="${ page_title }">
% endif
% if with_generator:
  <meta name="generator" content="${ generator or ('wmk v%s' % VERSION) }">
% endif

% if with_author and author:
  <meta name="author" content="${ author }">
% endif

% if with_locale and locale:
<meta property="og:locale" content="${ locale }">
% endif

% if with_description and description:
  <meta name="description" content="${ description }">
  <meta property="og:description" content="${ description }">
  <meta property="twitter:description" content="${ description }">
% endif

% if with_url and url:
  <link rel="canonical" href="${ url }">
  <meta property="og:url" content="${ url }">
% endif

% if with_site_name and site_name:
  <meta property="og:site_name" content="${ site_name }">
% endif

% if with_img and img:
  <meta property="og:image" content="${ img }">
% endif

% if page_type == 'article':
  <meta property="og:type" content="article">
  % if page and (page.pubdate or page.date):
  <meta property="article:published_time" content="${ date_to_iso(page.pubdate or page.date) }}">
  % endif
% else:
  <meta property="og:type" content="website">
% endif

% if with_prevnext and prev_url:
  <link rel="prev" href="${ prev_url }">
% endif
% if with_prevnext and next_url:
  <link rel="next" href="${ next_url }">
% endif

% if img:
  <meta name="twitter:card" content="${ page.twitter.card or site.twitter.card or "summary_large_image" }">
  <meta property="twitter:image" content="${ img }">
% else:
  <meta name="twitter:card" content="summary">
% endif

  <meta property="twitter:title" content="${ page_title }">

% if site.twitter:
  <meta name="twitter:site" content="@${ site.twitter.username.replace('@', '') }">
% endif

% if site.facebook:
  % if site.facebook.admins:
    <meta property="fb:admins" content="${ site.facebook.admins }">
  % endif
  % if site.facebook.publisher:
    <meta property="article:publisher" content="${ site.facebook.publisher }">
  % endif
  % if site.facebook.app_id:
    <meta property="fb:app_id" content="${ site.facebook.app_id }">
  % endif
% endif

% if robots:
  <meta name="robots" content="${ robots }">
% endif

<script type="application/ld+json">${ to_json(json_ld) }</script>

<!-- End /lib/seo.mc:seo -->
</%def>
