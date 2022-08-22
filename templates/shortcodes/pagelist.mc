<%page args="match_expr, ordering=None, limit=None, template=None, fallback='', template_args=None" />\
<%!
def pagelist_handler(match_expr, ordering, limit, template, fallback, nth, lookup, template_args):
    placeholder = '((PAGELIST::%d))' % nth
    def cb(html, **data):
        found = data['MDCONTENT'].page_match(match_expr, ordering, limit)
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
if template_args is None:
    template_args = {}
page.POSTPROCESS.append(
    pagelist_handler(match_expr, ordering, limit, template, fallback, nth, LOOKUP, template_args))
%>\
((PAGELIST::${ nth}))\
