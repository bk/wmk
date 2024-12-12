<%page args="match, label=None, ordering=None, fallback=None, unique=False, link_attr=None, link_append=None, url_only=False" />\
<%!
import re
default_fallback = '(LINKTO: page not found for "%s")'

def linkto_handler(match, label, ordering, fallback, unique, link_attr, link_append, url_only, nth):
    placeholder = '((LINKTO::%d))' % nth
    if not fallback:
        fallback = default_fallback % str(match)
    if link_attr is None:
        link_attr = 'class="linkto"'
    if link_append is None:
        link_append = ''
    if url_only is None:
        url_only = False
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
        elif '*' in match or '[' in match or '+' in match:
            match = [{'title': match}, {'path': match}]
        elif not ' ' in match and not '/' in match:
            match = re.sub(r'[ _-]', r'[_ -]', match)
            match = [
                {'slug': '^'+match+'$'},
                {'title': '^'+match+'$'},
                {'path': '/'+match+r'\.md$'},
                {'url': '/'+match+r'(?:\.html|/index\.html)$'}]
        else:
            match = r'\b' + match + r'\b'
            match = re.sub(r'[ _]', r'[_ -]', match)
            match = [{'title': match}, {'path': match}]
    def cb(html, **data):
        found = data['MDCONTENT'].page_match(
            match, ordering=ordering, limit=2)
        repl = fallback
        if len(found) > 1 and unique:
            raise Exception(
                'LINKTO: multiple matches found for "%s"' % str(match))
        elif found:
            url = found[0]['url'].replace('/index.html', '/')
            if url_only:
                repl = url + link_append
            else:
                repl = '<a %s href="%s%s">%s</a>'  % (
                    link_attr,
                    url,
                    link_append,
                    (label or found[0]['data']['page'].title))
        return html.replace(placeholder, repl)
    return cb
%>\
<%
if not 'POSTPROCESS' in page:
    page.POSTPROCESS = []
page.POSTPROCESS.append(
    linkto_handler(match, label, ordering, fallback, unique, link_attr, link_append, url_only, nth))
%>\
((LINKTO::${nth}))\
