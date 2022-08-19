<%page args="match, label=None, ordering=None, fallback=None, unique=False, link_attr=None" />\
<%!
default_fallback = '(LINKTO: page not found for "%s")'

def linkto_handler(match, label, ordering, fallback, unique, link_attr, nth):
    placeholder = '((LINKTO::%d))' % nth
    if not fallback:
        fallback = default_fallback % str(match)
    if link_attr is None:
        link_attr = 'class="linkto"'
    if isinstance(match, str):
        # heuristics for interpreting the match pattern before
        # passing to page_match()
        if match.startswith('^') or match.endswith('$'):
            match = [
                {'slug': match}, {'title': match},
                {'path': match}, {'url': match}]
        elif match.endswith('.md'):
            match = match.replace('.md', r'\.md')
            match = [{'path': match+'$'}]
        elif match.endswith('.html') or match.endswith('/'):
            if match.endswith('/'):
                match += 'index.html'
            match = match.replace('.html', r'\.html')
            match = [{'url': match+'$'}]
        elif not ' ' in match and not '/' in match:
            match = [
                {'slug': '^'+match+'$'},
                {'title': match},
                {'path': '/'+match+r'\.md$'},
                {'path': '/'+match+r'/index\.md$'}]
        elif '*' in match or '[' in match:
            match = [{'title': match}, {'path': match}]
        else:
            match = [{'title': match}]
    def cb(html, **data):
        found = data['MDCONTENT'].page_match(
            match, ordering=ordering, limit=2)
        repl = fallback
        if len(found) > 1 and unique:
            raise Exception(
                'LINKTO: multiple matches found for "%s"' % str(match))
        elif found:
            repl = '<a %s href="%s">%s</a>'  % (
                link_attr,
                found[0]['url'],
                (label or found[0]['data']['page'].title))
        return html.replace(placeholder, repl)
    return cb
%>\
<%
if not 'POSTPROCESS' in page:
    page.POSTPROCESS = []
page.POSTPROCESS.append(
    linkto_handler(match, label, ordering, fallback, unique, link_attr, nth))
%>\
((LINKTO::${nth}))\
