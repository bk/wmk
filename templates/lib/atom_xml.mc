<%!
import datetime
from wmk import generate_summary

xmldate = date_to_iso(sep='T', with_tz=True)

def get_date(it, attr):
    for k in attr:
        if k in it['data']:
            return it['data'][k]
        elif k in it['data']['page']:
            return it['data']['page'][k]

def default_get_img(it):
    return it['data']['page'].get('main_img', None)

def default_get_summary(it):
    generate_summary(it, True)
    return it['data']['page'].summary or ''
%>\
<%def name="feed(contentlist, pubdate_attr=None, updated_attr=None, with_img=True, get_img=None, with_summary=True, get_summary=None, with_full_text=False, limit=None)">\
<%
if not site.atom_feed:
    return ''
baseurl = site.base_url or ''
if not baseurl or not baseurl.startswith(('http:', 'https:')):
    return ''
if site.leading_path:
    baseurl = baseurl.rstrip('/') + '/' + site.leading_path.strip('/')
if limit is None:
    limit = site.atom_feed_length or 50
# NOTE: The contentlist should be presorted in the intended reverse date order
if pubdate_attr is None:
    pubdate_attr = ('pubdate', 'published_date', 'date_published', 'date', 'DATE')
if updated_attr is None:
    updated_attr = ('modified_date', 'date_modified', 'DATE', 'MTIME')
if with_img and get_img is None:
    get_img = default_get_img
if with_summary and get_summary is None:
    get_summary = default_get_summary
exclude_attrs = (
    'is_draft', 'draft', 'do_not_render',
    'exclude_from_search', 'search_exclude',
    'no_sitemap', 'exclude_from_feed', 'feed_exclude')
posts = []
for it in contentlist:
    skip = False
    pg = it['data']['page']
    for attr in (exclude_attrs):
        if page.get(attr):
            skip = True
            break
    if not skip:
        posts.append(it)
    if len(posts) == limit:
        break
%>\
<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>${ site.title or site.name or '?' }</title>
  <link href="${ baseurl }${ SELF_URL }" rel="self"/>
  <link href="${ baseurl }/"/>
  <updated>${ datetime.datetime.now() |xmldate }</updated>
  <id>${ baseurl }/</id>
  <author>
    <name>${ site.author or 'Anonymous' }</name>
    <email>${ site.author_email or 'anonymous@unknown.net' }</email>
  </author>
% for post in posts:
<%
    pg = post['data']['page']
    img = get_img(post)
    summary = get_summary(post)
%>\
  <entry>
    <title>${ pg.title }</title>
    <link href="${ baseurl }${ post['url'] |cleanurl }"/>
    <published>${ get_date(post, pubdate_attr) |xmldate }</published>
    <updated>${ get_date(post, updated_attr) |xmldate }</updated>
    <id>${ baseurl }${ post['url'] |cleanurl }</id>
    % if img:
    <icon>${ baseurl }${ img }</icon>
    % endif
    % if summary:
    <summary>${ summary | x }</summary>
    % endif
    % if with_full_text:
    <content type="html"><![CDATA[${ it['rendered'] }]]></content>
    % endif
  </entry>
% endfor
</feed>
</%def>
