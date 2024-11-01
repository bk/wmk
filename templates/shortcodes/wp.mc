<%page args="title, label=None, lang='en', target=None" />
<%
title = title.replace(' ', '_')
if not label:
    label = title.replace('_', ' ')
maybe_target = ' target="{}"'.format(target) if target else ''
%>
<a href="https://${ lang }.wikipedia.org/wiki/${ title |u }" class="wikipedia"${ maybe_target |n }>${ label }</a>
