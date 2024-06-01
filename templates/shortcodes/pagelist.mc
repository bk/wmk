<%page args="match_expr, exclude_expr=None, ordering=None, limit=None, template=None, fallback='', template_args=None, sql_match=False" />\
<%!
def pagelist_handler(match_expr, exclude_expr, ordering, limit, template, fallback, nth, lookup, template_args, sql_match):
    placeholder = '((PAGELIST::%d))' % nth
    def cb(html, **data):
        if sql_match:
            found = data['MDCONTENT'].page_match_sql(
                where_clause=match_expr, order_by=ordering, limit=limit)
        else:
            found = data['MDCONTENT'].page_match(match_expr, ordering, limit if not exclude_expr else None)
        if exclude_expr:
            found = found.page_match(exclude_expr, ordering, limit, inverse=True)
        repl = fallback
        if found and template:
            tpl = lookup.get_template(template)
            repl = tpl.render(pagelist=found, **template_args)
        elif found:
            repl = '<ul class="pagelist">'
            for it in found:
                repl += '<li><a href="%s">%s</a></li>' % (
                    it['url'], it['data']['page'].title)
            repl += '</ul>'
        return html.replace(placeholder, repl)
    return cb
%>\
<%
if not 'POSTPROCESS' in page:
    page.POSTPROCESS = []
# A page with a pagelist() should never be cached,
# regardless of the use_cache setting.
page.no_cache = True
if template_args is None:
    template_args = {}
page.POSTPROCESS.append(
    pagelist_handler(match_expr, exclude_expr, ordering, limit, template, fallback, nth, LOOKUP, template_args, sql_match))
%>\
((PAGELIST::${ nth}))\
