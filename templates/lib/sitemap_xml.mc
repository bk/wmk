<%!
def get_date(it):
    for k in ('modified_date', 'date_modified', 'changed_date', 'date_changed'):
        if k in it['data']['page']:
            return it['data']['page'][k]
    return it['data']['MTIME']
%>

<%def name="sitemap(contentlist)">\
<%
if not site.enable_sitemap:
    return ''
baseurl = site.base_url or ''
if not baseurl or not baseurl.startswith(('http:', 'https:')):
    return ''
if site.leading_path:
    baseurl = baseurl.rstrip('/') + '/' + site.leading_path.strip('/')
%>\
<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
   xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">
% for p in contentlist:
    <url>
        <loc>${ baseurl }${ p['url'] }</loc>
        <lastmod>${ get_date(p) | date_to_iso }</lastmod>
    </url>
% endfor
</urlset>
</%def>
