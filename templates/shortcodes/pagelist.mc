<%page args="match_expr, ordering=None, limit=None, template=None, fallback=''" />\
<%!
def pagelist_handler(match_expr, ordering, limit, template, fallback, nth, lookup):
    placeholder = '((PAGELIST::%d))' % nth
    def cb(html, **data):
        found = data['MDCONTENT'].page_match(match_expr, ordering, limit)
        repl = fallback
        if found and template:
            tpl = lookup.get_template(template)
            repl = tpl.render(pagelist=found)
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
page.POSTPROCESS.append(
    pagelist_handler(match_expr, ordering, limit, template, fallback, nth, LOOKUP))
%>\
((PAGELIST::${ nth}))\
